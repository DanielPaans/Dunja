const loginView = document.querySelector('#loginView');
const dashboardView = document.querySelector('#dashboardView');
const artworkForm = document.querySelector('#artworkForm');
let csrfToken = '';
let artworks = [];

const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (csrfToken && !['GET', 'HEAD'].includes((options.method || 'GET').toUpperCase())) {
    headers.set('X-CSRF-Token', csrfToken);
  }
  const response = await fetch(path, { ...options, headers, credentials: 'same-origin' });
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : null;
  if (!response.ok) throw new Error(payload?.error || `Er ging iets mis (${response.status}).`);
  return payload;
}

function showDashboard() {
  loginView.hidden = true;
  dashboardView.hidden = false;
  loadArtworks();
}

function showLogin() {
  loginView.hidden = false;
  dashboardView.hidden = true;
  csrfToken = '';
}

async function checkSession() {
  try {
    const result = await api('/api/session');
    if (result.authenticated) {
      csrfToken = result.csrfToken;
      showDashboard();
    } else showLogin();
  } catch {
    showLogin();
  }
}

$('#logoutButton').addEventListener('click', async () => {
  try { await api('/api/logout', { method: 'POST' }); } catch (error) { console.error(error); }
  showLogin();
});

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

async function loadArtworks() {
  const list = $('#artworkList');
  list.innerHTML = '<p class="empty-state">Collectie laden...</p>';
  try {
    artworks = await api('/api/artworks');
    $('#artworkCount').textContent = `${artworks.length} kunstwerk${artworks.length === 1 ? '' : 'en'}`;
    if (!artworks.length) {
      list.innerHTML = '<p class="empty-state">Er staan nog geen kunstwerken in de collectie.</p>';
      return;
    }
    list.innerHTML = artworks.map((artwork) => `
      <article class="artwork-row">
        <img src="${escapeHtml(artwork.img)}" alt="" loading="lazy">
        <div><div class="artwork-name">${escapeHtml(artwork.title)}</div>
          <div class="artwork-meta">${escapeHtml(artwork.price)} · ${escapeHtml(artwork.category)}</div></div>
        <div class="row-actions">
          <button type="button" data-edit="${artwork.id}">Bewerken</button>
          <button type="button" class="delete-button" data-delete="${artwork.id}">Verwijderen</button>
        </div>
      </article>`).join('');
  } catch (error) {
    list.innerHTML = `<p class="empty-state">${escapeHtml(error.message)}</p>`;
  }
}

$('#artworkList').addEventListener('click', async (event) => {
  const editButton = event.target.closest('[data-edit]');
  const deleteButton = event.target.closest('[data-delete]');
  if (editButton) {
    const artwork = artworks.find((item) => item.id === Number(editButton.dataset.edit));
    if (artwork) fillForm(artwork);
  }
  if (deleteButton) {
    const artwork = artworks.find((item) => item.id === Number(deleteButton.dataset.delete));
    if (!artwork || !confirm(`Weet je zeker dat je “${artwork.title}” wilt verwijderen?`)) return;
    try {
      await api(`/api/artworks/${artwork.id}`, { method: 'DELETE' });
      showNotice('Kunstwerk verwijderd.');
      if ($('#artworkId').value === String(artwork.id)) resetForm();
      await loadArtworks();
    } catch (error) {
      showError(error.message);
    }
  }
});

function fillForm(artwork) {
  $('#artworkId').value = artwork.id;
  $('#title').value = artwork.title;
  $('#price').value = artwork.price;
  $('#category').value = artwork.category;
  $('#desc').value = artwork.desc || '';
  $('#image').value = '';
  $('#imagePreview').src = artwork.img;
  $('#previewWrap').hidden = false;
  $('#imageHint').textContent = 'Huidige afbeelding (upload alleen als je deze wilt vervangen)';
  $('#formHeading').textContent = 'Kunstwerk bewerken';
  $('#saveButton').textContent = 'Wijzigingen opslaan';
  $('#cancelButton').hidden = false;
  $('#formError').textContent = '';
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function resetForm() {
  artworkForm.reset();
  $('#artworkId').value = '';
  $('#previewWrap').hidden = true;
  $('#imagePreview').removeAttribute('src');
  $('#formHeading').textContent = 'Nieuw kunstwerk';
  $('#saveButton').textContent = 'Kunstwerk toevoegen';
  $('#cancelButton').hidden = true;
  $('#formError').textContent = '';
}

$('#resetButton').addEventListener('click', resetForm);
$('#cancelButton').addEventListener('click', resetForm);
$('#refreshButton').addEventListener('click', loadArtworks);

$('#image').addEventListener('change', () => {
  const file = $('#image').files[0];
  if (!file) return;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    $('#formError').textContent = 'Kies een JPG-, PNG- of WebP-afbeelding.';
    $('#image').value = '';
    return;
  }
  $('#formError').textContent = '';
  $('#imagePreview').src = URL.createObjectURL(file);
  $('#previewWrap').hidden = false;
  $('#imageHint').textContent = 'Nieuwe afbeelding';
});

artworkForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  $('#formError').textContent = '';
  const id = $('#artworkId').value;
  const file = $('#image').files[0];
  if (!id && !file) {
    $('#formError').textContent = 'Upload een afbeelding voor het nieuwe kunstwerk.';
    return;
  }
  const data = new FormData();
  data.append('title', $('#title').value);
  data.append('price', $('#price').value);
  data.append('category', $('#category').value);
  data.append('desc', $('#desc').value);
  if (file) data.append('image', file);
  const button = $('#saveButton');
  button.disabled = true;
  button.textContent = 'Opslaan...';
  try {
    await api(id ? `/api/artworks/${id}` : '/api/artworks', {
      method: id ? 'PUT' : 'POST', body: data
    });
    showNotice(id ? 'Wijzigingen opgeslagen.' : 'Kunstwerk toegevoegd.');
    resetForm();
    await loadArtworks();
  } catch (error) {
    $('#formError').textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = $('#artworkId').value ? 'Wijzigingen opslaan' : 'Kunstwerk toevoegen';
  }
});

function showError(message) { $('#formError').textContent = message; }
function showNotice(message) {
  $('#notice').textContent = message;
  window.setTimeout(() => { $('#notice').textContent = ''; }, 3500);
}

const query = new URLSearchParams(window.location.search);
if (query.get('error') === 'not_allowed') {
  $('#loginError').textContent = 'Dit Google-account heeft geen toegang tot deze beheeromgeving.';
} else if (query.get('error') === 'google_login') {
  $('#loginError').textContent = 'Inloggen met Google is niet gelukt. Probeer het opnieuw.';
}
if (query.has('error') || query.has('login')) {
  window.history.replaceState({}, document.title, window.location.pathname);
}

checkSession();
