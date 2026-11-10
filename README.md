# Dunja Creatief — website + artwork admin

A small self-hosted setup for the Dunja Creatief website. Nginx serves the static website and admin page; a Flask API stores artwork metadata in SQLite and uploaded images on disk.

## Features

- Public gallery reads artwork from `GET /api/artworks`.
- Admin page at `/admin/` with login, add, edit, delete and image upload.
- Existing 18 sample artworks are inserted into SQLite on the first start.
- Uploaded photos are validated and converted to WebP.
- SQLite database and image uploads persist in `./data` on the Raspberry Pi.
- API write operations require an authenticated session and CSRF token.
- Login requests are rate-limited by Nginx.

## Requirements

- Raspberry Pi OS / Linux with Podman and `podman compose` (or Docker Compose).
- A domain/reverse proxy or Cloudflare Tunnel that can route the domain to `http://127.0.0.1:8080`.

## First-time setup

1. Copy this directory to the Raspberry Pi, for example to `/opt/dunja-creatief`.
2. Create the environment file:

   ```bash
   cd /opt/dunja-creatief
   cp .env.example .env
   ```

3. Build the API image so you can generate a Werkzeug password hash:

   ```bash
   podman build -t dunja-api ./backend
   ```

4. Generate a hash for the admin password. Replace the example password with a strong, unique password:

   ```bash
   podman run --rm --entrypoint python dunja-api -c \
     "from werkzeug.security import generate_password_hash; print(generate_password_hash('CHANGE-THIS-PASSWORD'))"
   ```

5. Edit `.env`:
   - Set `FLASK_SECRET_KEY` to the output of `openssl rand -hex 32`.
   - Choose `ADMIN_USERNAME`.
   - Set `ADMIN_PASSWORD_HASH` to the generated hash. Keep the hash in single quotes because it contains `$` characters.
   - Keep `COOKIE_SECURE=true` when visitors use HTTPS (recommended). Set it to `false` only for local HTTP testing.

   Generate the Flask secret with:

   ```bash
   openssl rand -hex 32
   ```

6. Start the website and API:

   ```bash
   podman compose up -d --build
   ```

7. Check that the API is healthy:

   ```bash
   curl http://127.0.0.1:8080/api/health
   ```

   Expected response: `{"status":"ok"}`.

8. Point the existing reverse proxy / Cloudflare Tunnel hostname to `http://127.0.0.1:8080`. The container port is deliberately bound to localhost and should not be exposed directly to the internet.

The public site is available at `/` and the administrator page at `/admin/` on the same domain.

## Data and backups

Persistent data is stored on the host in `./data`:

- `artworks.db` — artwork records and metadata.
- `uploads/` — uploaded photos.

Back up the complete `data` directory regularly. For a consistent SQLite backup while the app is running, use SQLite's backup command or briefly stop the stack before copying it:

```bash
podman compose down
cp -a data "data-backup-$(date +%F)"
podman compose up -d
```

Do not delete `data` when updating the containers.

## Useful commands

```bash
podman compose logs -f api       # Flask logs
podman compose logs -f web       # Nginx logs
podman compose restart api       # Restart API
podman compose down              # Stop containers (data remains)
podman compose up -d --build     # Rebuild and start
```

## Notes

- The current initial artwork photos are the external image URLs from the supplied website source. New uploads are stored locally on the Pi.
- The public gallery still uses the existing website styling. Its artwork list is now loaded from the API instead of being hard-coded in the HTML.
- The admin page is not linked from the public navigation. Visit `/admin/` directly.
- Keep `.env` private and never commit it to Git.
