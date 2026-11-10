import os
import json
import secrets
import sqlite3
import uuid
from datetime import timedelta
from functools import wraps
from contextlib import contextmanager
from pathlib import Path

from flask import Flask, jsonify, request, session, send_from_directory, redirect, url_for
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix
from PIL import Image, ImageOps, UnidentifiedImageError

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get('DATA_DIR', '/data'))
UPLOAD_DIR = DATA_DIR / 'uploads'
DB_PATH = DATA_DIR / 'artworks.db'
SEED_PATH = BASE_DIR / 'seed_artworks.json'
CATEGORIES = {'ruimtelijk', 'keramiek', 'schilderijen'}
MAX_IMAGE_BYTES = 10 * 1024 * 1024

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config.update(
    SECRET_KEY=os.environ.get('FLASK_SECRET_KEY', ''),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', 'true').lower() == 'true',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=MAX_IMAGE_BYTES + 1024 * 1024,
)

if len(app.config['SECRET_KEY']) < 32:
    raise RuntimeError('FLASK_SECRET_KEY must be set to a random value of at least 32 characters')
required_oauth = ('ADMIN_EMAIL', 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET')
missing_oauth = [name for name in required_oauth if not os.environ.get(name)]
if missing_oauth:
    raise RuntimeError('Missing required Google login settings: ' + ', '.join(missing_oauth))

oauth = OAuth(app)
oauth.register(
    name='google',
    client_id=os.environ['GOOGLE_CLIENT_ID'],
    client_secret=os.environ['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)


@contextmanager
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db_connect() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS artworks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                price TEXT NOT NULL,
                category TEXT NOT NULL,
                img TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        count = conn.execute('SELECT COUNT(*) FROM artworks').fetchone()[0]
        if count == 0 and SEED_PATH.exists():
            seed = json.loads(SEED_PATH.read_text(encoding='utf-8'))
            conn.executemany(
                'INSERT INTO artworks (id, title, price, category, img, description) VALUES (?, ?, ?, ?, ?, ?)',
                [(a['id'], a['title'], a['price'], a['category'], a['img'], a.get('desc', '')) for a in seed]
            )


def artwork_dict(row):
    return {
        'id': row['id'], 'title': row['title'], 'price': row['price'],
        'category': row['category'], 'img': row['img'], 'desc': row['description']
    }


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('admin'):
            return jsonify({'error': 'Authenticatie vereist'}), 401
        token = session.get('csrf_token')
        if not token or not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), token):
            return jsonify({'error': 'Ongeldige CSRF-token'}), 403
        return fn(*args, **kwargs)
    return wrapper


def clean_fields(form):
    title = (form.get('title') or '').strip()
    price = (form.get('price') or '').strip()
    category = (form.get('category') or '').strip()
    description = (form.get('desc') or '').strip()
    if not title or len(title) > 120:
        raise ValueError('Titel is verplicht en mag maximaal 120 tekens bevatten.')
    if not price or len(price) > 40:
        raise ValueError('Prijs is verplicht en mag maximaal 40 tekens bevatten.')
    if category not in CATEGORIES:
        raise ValueError('Kies een geldige categorie.')
    if len(description) > 2000:
        raise ValueError('De beschrijving mag maximaal 2000 tekens bevatten.')
    return title, price, category, description


def save_uploaded_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    raw = file_storage.stream.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError('Afbeelding is te groot (maximaal 10 MB).')
    try:
        from io import BytesIO
        with Image.open(BytesIO(raw)) as check_image:
            if check_image.format not in {'JPEG', 'PNG', 'WEBP'}:
                raise ValueError('Gebruik een JPG-, PNG- of WebP-afbeelding.')
            if check_image.width > 7000 or check_image.height > 7000:
                raise ValueError('De afbeelding is te groot qua afmetingen (maximaal 7000 × 7000).')
            check_image.verify()
        with Image.open(BytesIO(raw)) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ('RGB', 'RGBA'):
                image = image.convert('RGBA' if 'transparency' in image.info else 'RGB')
            filename = f'{uuid.uuid4().hex}.webp'
            image.save(UPLOAD_DIR / filename, 'WEBP', quality=88, method=5)
            return f'/uploads/{filename}'
    except (UnidentifiedImageError, OSError):
        raise ValueError('Dit bestand is geen geldige afbeelding.')


def remove_local_image(url):
    if not url or not url.startswith('/uploads/'):
        return
    filename = Path(url).name
    if filename and filename == url.rsplit('/', 1)[-1]:
        try:
            (UPLOAD_DIR / filename).unlink(missing_ok=True)
        except OSError:
            app.logger.warning('Could not remove old image %s', filename)


@app.get('/api/health')
def health():
    return jsonify({'status': 'ok'})


@app.get('/api/artworks')
def get_artworks():
    with db_connect() as conn:
        rows = conn.execute('SELECT * FROM artworks ORDER BY id ASC').fetchall()
    return jsonify([artwork_dict(row) for row in rows])


@app.get('/api/artworks/<int:artwork_id>')
def get_artwork(artwork_id):
    with db_connect() as conn:
        row = conn.execute('SELECT * FROM artworks WHERE id = ?', (artwork_id,)).fetchone()
    if row is None:
        return jsonify({'error': 'Kunstwerk niet gevonden'}), 404
    return jsonify(artwork_dict(row))


@app.get('/api/auth/google')
def google_login():
    callback_url = os.environ.get('GOOGLE_REDIRECT_URI') or url_for('google_callback', _external=True)
    return oauth.google.authorize_redirect(callback_url)


@app.get('/api/auth/google/callback')
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get('userinfo') or oauth.google.userinfo()
        email = str(user_info.get('email', '')).strip().casefold()
        allowed_email = os.environ['ADMIN_EMAIL'].strip().casefold()
        email_verified = user_info.get('email_verified') is True

        if not email_verified or not secrets.compare_digest(email, allowed_email):
            app.logger.warning('Rejected Google login for email: %s', email or '<missing>')
            session.clear()
            return redirect('/admin/?error=not_allowed')

        session.clear()
        session.permanent = True
        session['admin'] = True
        session['admin_email'] = email
        session['csrf_token'] = secrets.token_urlsafe(32)
        return redirect('/admin/?login=success')
    except Exception:
        app.logger.exception('Google OAuth login failed')
        session.clear()
        return redirect('/admin/?error=google_login')


@app.get('/api/session')
def get_session():
    if not session.get('admin'):
        return jsonify({'authenticated': False})
    return jsonify({'authenticated': True, 'email': session.get('admin_email'), 'csrfToken': session.get('csrf_token')})


@app.post('/api/logout')
@require_auth
def logout():
    session.clear()
    return jsonify({'authenticated': False})


@app.post('/api/artworks')
@require_auth
def create_artwork():
    try:
        title, price, category, description = clean_fields(request.form)
        image_url = save_uploaded_image(request.files.get('image'))
        if not image_url:
            return jsonify({'error': 'Upload een afbeelding voor het nieuwe kunstwerk.'}), 400
        with db_connect() as conn:
            cursor = conn.execute(
                'INSERT INTO artworks (title, price, category, img, description) VALUES (?, ?, ?, ?, ?)',
                (title, price, category, image_url, description)
            )
            row = conn.execute('SELECT * FROM artworks WHERE id = ?', (cursor.lastrowid,)).fetchone()
        return jsonify(artwork_dict(row)), 201
    except ValueError as error:
        return jsonify({'error': str(error)}), 400


@app.put('/api/artworks/<int:artwork_id>')
@require_auth
def update_artwork(artwork_id):
    with db_connect() as conn:
        existing = conn.execute('SELECT * FROM artworks WHERE id = ?', (artwork_id,)).fetchone()
        if existing is None:
            return jsonify({'error': 'Kunstwerk niet gevonden'}), 404
        try:
            title, price, category, description = clean_fields(request.form)
            new_image = save_uploaded_image(request.files.get('image'))
        except ValueError as error:
            return jsonify({'error': str(error)}), 400
        image_url = new_image or existing['img']
        conn.execute(
            '''UPDATE artworks SET title = ?, price = ?, category = ?, img = ?, description = ?,
               updated_at = CURRENT_TIMESTAMP WHERE id = ?''',
            (title, price, category, image_url, description, artwork_id)
        )
        row = conn.execute('SELECT * FROM artworks WHERE id = ?', (artwork_id,)).fetchone()
    if new_image:
        remove_local_image(existing['img'])
    return jsonify(artwork_dict(row))


@app.delete('/api/artworks/<int:artwork_id>')
@require_auth
def delete_artwork(artwork_id):
    with db_connect() as conn:
        existing = conn.execute('SELECT * FROM artworks WHERE id = ?', (artwork_id,)).fetchone()
        if existing is None:
            return jsonify({'error': 'Kunstwerk niet gevonden'}), 404
        conn.execute('DELETE FROM artworks WHERE id = ?', (artwork_id,))
    remove_local_image(existing['img'])
    return jsonify({'deleted': True})


@app.get('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename, max_age=86400)


@app.errorhandler(413)
def too_large(_error):
    return jsonify({'error': 'Upload te groot. De maximale uploadgrootte is 10 MB.'}), 413


init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
