import os
import json
import hashlib
import hmac
import threading
import time
import uuid
from functools import wraps
from flask import Flask, request, redirect, render_template_string, Response, session

from chomik import ChomikUploader

BROWSE_FOLDER = '/app/browse'
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key-change-me')

PASSWORD_HASH = os.environ.get('PANEL_PASSWORD_HASH', '')
PANEL_PASSWORD = os.environ.get('PANEL_PASSWORD', '')

if PANEL_PASSWORD and not PASSWORD_HASH:
    PASSWORD_HASH = hashlib.sha256(PANEL_PASSWORD.encode()).hexdigest()

upload_status = {}
upload_lock = threading.Lock()

STATUS_TTL_SECONDS = 600
PROGRESS_THROTTLE_BYTES = 262144  # 256 KB
PROGRESS_THROTTLE_SECONDS = 0.25


def verify_password(password):
    if not PASSWORD_HASH:
        return False
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    return hmac.compare_digest(password_hash, PASSWORD_HASH)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function


def get_files_from_browse_folder(folder_path=''):
    files = []
    folders = []
    try:
        current_path = os.path.join(BROWSE_FOLDER, folder_path) if folder_path else BROWSE_FOLDER

        if not os.path.abspath(current_path).startswith(os.path.abspath(BROWSE_FOLDER)):
            return {'files': [], 'folders': [], 'current_path': ''}

        if os.path.exists(current_path) and os.path.isdir(current_path):
            try:
                items = os.listdir(current_path)
                for item in items:
                    item_path = os.path.join(current_path, item)
                    try:
                        if os.path.isdir(item_path):
                            folders.append({
                                'name': item,
                                'path': os.path.relpath(item_path, BROWSE_FOLDER),
                            })
                        elif os.path.isfile(item_path):
                            size = os.path.getsize(item_path)
                            files.append({
                                'name': item,
                                'path': os.path.relpath(item_path, BROWSE_FOLDER),
                                'full_path': item_path,
                                'size': size,
                            })
                    except Exception as e:
                        app.logger.warning('Error processing item: ' + str(e))
            except Exception as e:
                app.logger.error('Error listing directory: ' + str(e))
    except Exception as e:
        app.logger.error('Error reading browse folder: ' + str(e))

    return {
        'files': sorted(files, key=lambda x: x['name']),
        'folders': sorted(folders, key=lambda x: x['name']),
        'current_path': folder_path,
    }


def _sweep_status():
    now = time.time()
    with upload_lock:
        stale = [
            uid for uid, rec in upload_status.items()
            if rec.get('finished_at') and now - rec['finished_at'] > STATUS_TTL_SECONDS
        ]
        for uid in stale:
            upload_status.pop(uid, None)


def _run_upload(upload_id, filepath, filename, username, password, dest_path):
    last_progress = {'bytes': 0, 'time': 0.0}

    def on_progress(sent, total):
        now = time.time()
        if sent != total and sent - last_progress['bytes'] < PROGRESS_THROTTLE_BYTES \
                and now - last_progress['time'] < PROGRESS_THROTTLE_SECONDS:
            return
        last_progress['bytes'] = sent
        last_progress['time'] = now
        with upload_lock:
            rec = upload_status.get(upload_id)
            if rec is not None:
                rec['bytes_sent'] = sent
                if rec['status'] == 'queued':
                    rec['status'] = 'uploading'

    try:
        uploader = ChomikUploader(username, password)
        if not uploader.login():
            with upload_lock:
                rec = upload_status.get(upload_id)
                if rec is not None:
                    rec['status'] = 'error'
                    rec['message'] = 'Authentication with Chomikuj failed'
                    rec['finished_at'] = time.time()
            return

        ok, err = uploader.upload_file(
            filepath, dest_path, filename=filename, on_progress=on_progress
        )
        with upload_lock:
            rec = upload_status.get(upload_id)
            if rec is None:
                return
            rec['finished_at'] = time.time()
            if ok:
                rec['status'] = 'success'
                rec['bytes_sent'] = rec['total_bytes']
                rec['message'] = 'Uploaded'
            else:
                rec['status'] = 'error'
                rec['message'] = err or 'Upload failed'
    except Exception as e:
        with upload_lock:
            rec = upload_status.get(upload_id)
            if rec is not None:
                rec['status'] = 'error'
                rec['message'] = 'Worker exception: ' + str(e)
                rec['finished_at'] = time.time()


HTML_LOGIN = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ChomikUploader - Login</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            width: 100%;
            max-width: 400px;
        }
        h1 { text-align: center; color: #333; margin: 0 0 30px 0; font-size: 28px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #555; font-weight: bold; }
        input[type="password"] {
            width: 100%; padding: 12px; border: 1px solid #ddd;
            border-radius: 4px; font-size: 16px; box-sizing: border-box;
        }
        input[type="password"]:focus {
            outline: none; border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        button {
            width: 100%; padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; border: none; border-radius: 4px;
            font-size: 16px; font-weight: bold; cursor: pointer;
        }
        button:hover { transform: translateY(-2px); }
        .error {
            background: #fee; color: #c33; padding: 12px;
            border-radius: 4px; margin-bottom: 20px; border-left: 4px solid #c33;
        }
        .info { text-align: center; color: #999; font-size: 14px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>ChomikUploader</h1>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <div class="form-group">
                <label for="password">Hasło:</label>
                <input type="password" id="password" name="password" required autofocus>
            </div>
            <button type="submit">Zaloguj się</button>
            <div class="info">Wpisz hasło panelu, aby uzyskać dostęp</div>
        </form>
    </div>
</body>
</html>
"""

HTML_FORM = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ChomikUploader</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
        h1 { margin: 0; color: #333; }
        .logout-btn { background: #dc3545; color: white; padding: 8px 16px; border: none; border-radius: 4px; text-decoration: none; font-size: 14px; }
        .logout-btn:hover { background: #c82333; }
        .container { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h2 { color: #555; margin-top: 30px; margin-bottom: 15px; font-size: 18px; }
        .info-box { background: #e3f2fd; padding: 15px; border-radius: 4px; margin-bottom: 20px; border-left: 4px solid #2196f3; }
        button, .retry-btn { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin: 5px 5px 5px 0; }
        button:hover, .retry-btn:hover { background: #0056b3; }
        button:disabled { background: #ccc; cursor: not-allowed; }
        .retry-btn { background: #ffc107; color: black; }
        .retry-btn:hover { background: #ffb300; }
        .breadcrumb { padding: 10px; background: #f9f9f9; border-radius: 4px; margin-bottom: 15px; font-size: 14px; }
        .breadcrumb a { color: #007bff; cursor: pointer; text-decoration: underline; }
        .breadcrumb a:hover { color: #0056b3; }
        .file-browser { max-height: 500px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px; margin: 20px 0; }
        .browser-item { padding: 12px; border-bottom: 1px solid #eee; display: flex; align-items: center; }
        .browser-item:hover { background: #f9f9f9; }
        .browser-item input[type="checkbox"] { margin-right: 12px; width: 18px; height: 18px; cursor: pointer; }
        .item-info { flex: 1; }
        .item-name { font-weight: 500; color: #333; word-break: break-all; }
        .folder-name { color: #007bff; cursor: pointer; text-decoration: underline; font-weight: 500; }
        .item-size { font-size: 12px; color: #666; margin-left: 15px; white-space: nowrap; }
        .select-all-row { padding: 12px; background: #f5f5f5; border-bottom: 2px solid #ddd; font-weight: bold; display: flex; align-items: center; }
        .select-all-row input { margin-right: 12px; width: 18px; height: 18px; }
        .file-list { margin-top: 30px; }
        .file-item { background: #f9f9f9; padding: 15px; margin: 10px 0; border-radius: 4px; border-left: 4px solid #007bff; }
        .file-item.success { border-left-color: #28a745; }
        .file-item.error { border-left-color: #dc3545; }
        .file-item.pending { border-left-color: #ffc107; }
        .file-name { font-weight: bold; margin-bottom: 8px; word-break: break-all; }
        .file-size { font-size: 12px; color: #999; margin-bottom: 8px; }
        .progress-bar { width: 100%; height: 25px; background: #e0e0e0; border-radius: 4px; overflow: hidden; margin: 8px 0; }
        .progress-fill { height: 100%; background: #28a745; width: 0%; transition: width 0.3s; display: flex; align-items: center; justify-content: center; color: white; font-size: 12px; font-weight: bold; }
        .status-text { font-size: 14px; color: #666; margin-top: 5px; }
        .status-success { color: #28a745; }
        .status-error { color: #dc3545; }
        .status-pending { color: #ffc107; }
        .messages { margin: 20px 0; }
        .alert { padding: 12px; margin: 10px 0; border-radius: 4px; border-left: 4px solid #ffc107; background: #fff3cd; color: #856404; }
        .retry-section { margin-top: 10px; display: none; }
        .retry-section.show { display: block; }
        .no-items { padding: 40px; text-align: center; color: #999; font-style: italic; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Wyślij pliki do Chomika</h1>
        <a href="/logout" class="logout-btn">Wyloguj się</a>
    </div>

    <div class="container">
        <div class="info-box">
            <strong>ℹ️ Informacja:</strong> Wybierz pliki z katalogu Synology, które chcesz wysłać na Chomika.
            Pliki nie są kopiowane - wysyłane są bezpośrednio z Twojego serwera.
        </div>

        <div id="messages" class="messages"></div>

        <h2>Przeglądaj i wybierz pliki:</h2>
        <div class="breadcrumb" id="breadcrumb"></div>

        <div class="file-browser" id="fileBrowser">
            <div class="select-all-row">
                <input type="checkbox" id="selectAll" onchange="toggleSelectAll()">
                <label for="selectAll" style="display: inline; cursor: pointer; margin: 0;">Zaznacz wszystkie pliki w tym folderze</label>
            </div>
            <div id="fileList"></div>
        </div>

        <div>
            <button id="uploadBtn" onclick="uploadSelected()" disabled>Wyślij zaznaczone pliki</button>
            <button onclick="deselectAll()">Usuń zaznaczenia</button>
        </div>

        <div class="file-list">
            <h2>Status uploadów:</h2>
            <div id="statusList"></div>
            <div id="retrySection" class="retry-section">
                <button type="button" onclick="retryFailed()" class="retry-btn">Spróbuj wysłać ponownie pliki, które się nie powiodły</button>
            </div>
        </div>
    </div>

    <script>
        let availableFiles = [];
        let failedFiles = [];
        let currentFolder = '';

        const POLL_INTERVAL_MS = 750;
        const POLL_HARD_TIMEOUT_MS = 30 * 60 * 1000;

        const statusList = document.getElementById('statusList');
        const messagesDiv = document.getElementById('messages');
        const uploadBtn = document.getElementById('uploadBtn');
        const retrySection = document.getElementById('retrySection');
        const fileListDiv = document.getElementById('fileList');
        const breadcrumbDiv = document.getElementById('breadcrumb');

        window.addEventListener('load', () => loadFiles(''));

        function loadFiles(folderPath) {
            currentFolder = folderPath;
            fetch('/api/files?path=' + encodeURIComponent(folderPath))
                .then(r => r.json())
                .then(data => {
                    availableFiles = data.files;
                    renderBreadcrumb(data.current_path);
                    renderFileList(data.files, data.folders);
                })
                .catch(err => showMessage('Błąd pobierania listy plików: ' + err.message, 'error'));
        }

        function renderBreadcrumb(path) {
            let html = '<a onclick="loadFiles(\\'\\')">Główny folder</a>';
            if (path) {
                const parts = path.split('/');
                let cur = '';
                parts.forEach((p, i) => {
                    cur += (i > 0 ? '/' : '') + p;
                    html += ' / <a onclick="loadFiles(\\''+cur+'\\')">' + p + '</a>';
                });
            }
            breadcrumbDiv.innerHTML = html;
        }

        function renderFileList(files, folders) {
            fileListDiv.innerHTML = '';
            if (!folders.length && !files.length) {
                fileListDiv.innerHTML = '<div class="no-items">Brak plików i folderów</div>';
                document.getElementById('selectAll').checked = false;
                updateUploadButton();
                return;
            }
            folders.forEach(folder => {
                const row = document.createElement('div');
                row.className = 'browser-item';
                row.innerHTML = `
                    <div class="item-info">
                        <div class="folder-name" onclick="loadFiles(\\'${escapeHtml(folder.path)}\\')">
                            📁 ${escapeHtml(folder.name)}
                        </div>
                    </div>`;
                fileListDiv.appendChild(row);
            });
            files.forEach((file, idx) => {
                const row = document.createElement('div');
                row.className = 'browser-item';
                const sizeMB = (file.size / 1024 / 1024).toFixed(2);
                const sizeKB = (file.size / 1024).toFixed(2);
                const sizeDisplay = file.size > 1024 * 1024 ? sizeMB + ' MB' : sizeKB + ' KB';
                row.innerHTML = `
                    <input type="checkbox" id="file-${idx}" onchange="updateUploadButton()" data-file-index="${idx}">
                    <div class="item-info"><div class="item-name">📄 ${escapeHtml(file.name)}</div></div>
                    <div class="item-size">${sizeDisplay}</div>`;
                fileListDiv.appendChild(row);
            });
            updateUploadButton();
        }

        function escapeHtml(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }

        function toggleSelectAll() {
            const all = document.getElementById('selectAll').checked;
            fileListDiv.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = all);
            updateUploadButton();
        }

        function deselectAll() {
            fileListDiv.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
            document.getElementById('selectAll').checked = false;
            updateUploadButton();
        }

        function updateUploadButton() {
            const any = Array.from(fileListDiv.querySelectorAll('input[type="checkbox"]')).some(cb => cb.checked);
            uploadBtn.disabled = !any;
        }

        function getSelectedFiles() {
            const sel = [];
            fileListDiv.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
                const idx = parseInt(cb.getAttribute('data-file-index'));
                if (!isNaN(idx)) sel.push(availableFiles[idx]);
            });
            return sel;
        }

        async function uploadSelected() {
            const sel = getSelectedFiles();
            if (!sel.length) { showMessage('Nie wybrano żadnych plików', 'error'); return; }
            messagesDiv.innerHTML = '';
            statusList.innerHTML = '';
            failedFiles = [];
            retrySection.classList.remove('show');
            sel.forEach(f => addFileStatus(f.name, f.size));
            for (const file of sel) {
                try { await uploadFile(file); }
                catch (e) {
                    updateFileStatus(file.name, 'error', 'Błąd: ' + e.message);
                    failedFiles.push(file.full_path);
                }
            }
            if (failedFiles.length) retrySection.classList.add('show');
        }

        function safeId(name) { return name.replace(/[^a-zA-Z0-9]/g, '_'); }

        function addFileStatus(name, size) {
            const item = document.createElement('div');
            item.className = 'file-item pending';
            item.id = 'status-' + safeId(name);
            const sizeMB = (size / 1024 / 1024).toFixed(2);
            const sizeKB = (size / 1024).toFixed(2);
            const sd = size > 1024 * 1024 ? sizeMB + ' MB' : sizeKB + ' KB';
            item.innerHTML = `
                <div class="file-name">${escapeHtml(name)}</div>
                <div class="file-size">Rozmiar: ${sd}</div>
                <div class="progress-bar"><div class="progress-fill" id="progress-${safeId(name)}">0%</div></div>
                <div class="status-text status-pending" id="text-${safeId(name)}">Oczekiwanie...</div>`;
            statusList.appendChild(item);
        }

        function updateFileStatus(name, status, message, pct) {
            const sid = safeId(name);
            const item = document.getElementById('status-' + sid);
            const text = document.getElementById('text-' + sid);
            const prog = document.getElementById('progress-' + sid);
            if (!item) return;
            if (typeof pct === 'number' && prog) {
                prog.style.width = pct + '%';
                prog.textContent = pct + '%';
            }
            if (status === 'uploading' || status === 'queued') {
                item.className = 'file-item pending';
                text.className = 'status-text status-pending';
                text.textContent = message;
            } else if (status === 'success') {
                item.className = 'file-item success';
                if (prog) { prog.style.width = '100%'; prog.textContent = '100%'; }
                text.className = 'status-text status-success';
                text.textContent = message;
            } else if (status === 'error') {
                item.className = 'file-item error';
                text.className = 'status-text status-error';
                text.textContent = message;
            }
        }

        function uploadFile(file) {
            return new Promise((resolve) => {
                updateFileStatus(file.name, 'uploading', 'Rozpoczynanie...', 0);
                fetch('/api/upload', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({filepath: file.full_path, filename: file.name})
                })
                .then(r => r.json())
                .then(data => {
                    if (!data.success || !data.upload_id) {
                        const msg = data.message || 'Nieznany błąd';
                        updateFileStatus(file.name, 'error', 'Błąd: ' + msg);
                        showMessage('✗ ' + file.name + ' - ' + msg, 'error');
                        if (!failedFiles.includes(file.full_path)) failedFiles.push(file.full_path);
                        resolve();
                        return;
                    }
                    pollUpload(file, data.upload_id, resolve);
                })
                .catch(err => {
                    updateFileStatus(file.name, 'error', 'Błąd połączenia');
                    showMessage('✗ ' + file.name + ' - Błąd połączenia', 'error');
                    if (!failedFiles.includes(file.full_path)) failedFiles.push(file.full_path);
                    resolve();
                });
            });
        }

        function pollUpload(file, uploadId, done) {
            const started = Date.now();
            const tick = () => {
                if (Date.now() - started > POLL_HARD_TIMEOUT_MS) {
                    clearInterval(handle);
                    updateFileStatus(file.name, 'error', 'Limit czasu polling przekroczony');
                    if (!failedFiles.includes(file.full_path)) failedFiles.push(file.full_path);
                    done();
                    return;
                }
                fetch('/api/upload/status/' + encodeURIComponent(uploadId))
                    .then(r => {
                        if (r.status === 404) {
                            clearInterval(handle);
                            updateFileStatus(file.name, 'error', 'Status uploadu nie znaleziony');
                            if (!failedFiles.includes(file.full_path)) failedFiles.push(file.full_path);
                            done();
                            return null;
                        }
                        return r.json();
                    })
                    .then(s => {
                        if (!s) return;
                        const pct = s.total_bytes > 0
                            ? Math.floor(100 * s.bytes_sent / s.total_bytes) : 0;
                        if (s.status === 'queued' || s.status === 'uploading') {
                            const sentMB = (s.bytes_sent / 1024 / 1024).toFixed(2);
                            const totMB = (s.total_bytes / 1024 / 1024).toFixed(2);
                            updateFileStatus(file.name, 'uploading',
                                `Wysyłanie ${sentMB} / ${totMB} MB`, pct);
                        } else if (s.status === 'success') {
                            clearInterval(handle);
                            updateFileStatus(file.name, 'success', 'Przesłano pomyślnie na Chomika!', 100);
                            showMessage('✓ ' + file.name + ' - przesłano pomyślnie', 'success');
                            failedFiles = failedFiles.filter(p => p !== file.full_path);
                            done();
                        } else if (s.status === 'error') {
                            clearInterval(handle);
                            updateFileStatus(file.name, 'error', 'Błąd: ' + (s.message || 'nieznany'));
                            showMessage('✗ ' + file.name + ' - ' + (s.message || 'błąd'), 'error');
                            if (!failedFiles.includes(file.full_path)) failedFiles.push(file.full_path);
                            done();
                        }
                    })
                    .catch(() => {});
            };
            const handle = setInterval(tick, POLL_INTERVAL_MS);
            tick();
        }

        function retryFailed() {
            showMessage('Ponowne wysyłanie ' + failedFiles.length + ' plików...', 'pending');
        }

        function showMessage(msg, type) {
            const e = document.createElement('div');
            e.className = 'alert';
            e.textContent = msg;
            messagesDiv.appendChild(e);
        }
    </script>
</body>
</html>
"""


def json_response(data, status_code=200):
    response = Response(json.dumps(data), mimetype='application/json', status=status_code)
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if verify_password(password):
            session['logged_in'] = True
            return redirect('/')
        else:
            error = 'Błędne hasło'
    return render_template_string(HTML_LOGIN, error=error)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect('/login')


@app.route('/', methods=['GET'])
@login_required
def index():
    return render_template_string(HTML_FORM)


@app.route('/api/files', methods=['GET'])
@login_required
def api_files():
    folder_path = request.args.get('path', '')
    return json_response(get_files_from_browse_folder(folder_path))


@app.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    _sweep_status()
    try:
        data = json.loads(request.data)
    except Exception:
        return json_response({'success': False, 'message': 'Nieprawidłowy JSON'}, 400)

    filepath = data.get('filepath')
    filename = data.get('filename')

    if not filepath or not filename:
        return json_response({'success': False, 'message': 'Brak ścieżki do pliku'}, 400)

    real_path = os.path.abspath(filepath)
    browse_path = os.path.abspath(BROWSE_FOLDER)
    if not real_path.startswith(browse_path):
        return json_response({'success': False, 'message': 'Nieprawidłowa ścieżka do pliku'}, 400)

    if not os.path.exists(filepath):
        return json_response({'success': False, 'message': 'Plik nie istnieje'}, 404)

    username = os.environ.get('CHOMIK_USERNAME')
    password = os.environ.get('CHOMIK_PASSWORD')
    dest_path = os.environ.get('CHOMIK_DEST', '/Moje_Uploady')

    if not username or not password:
        return json_response({
            'success': False,
            'message': 'Brak konfiguracji CHOMIK_USERNAME lub CHOMIK_PASSWORD',
        }, 500)

    upload_id = uuid.uuid4().hex
    total_bytes = os.path.getsize(filepath)
    with upload_lock:
        upload_status[upload_id] = {
            'status': 'queued',
            'bytes_sent': 0,
            'total_bytes': total_bytes,
            'filename': filename,
            'message': 'Queued',
            'started_at': time.time(),
            'finished_at': None,
        }

    t = threading.Thread(
        target=_run_upload,
        args=(upload_id, filepath, filename, username, password, dest_path),
        daemon=True,
    )
    t.start()

    return json_response({
        'success': True,
        'upload_id': upload_id,
        'total_bytes': total_bytes,
        'message': 'Upload started',
    }, 202)


@app.route('/api/upload/status/<upload_id>', methods=['GET'])
@login_required
def api_upload_status(upload_id):
    with upload_lock:
        rec = upload_status.get(upload_id)
        if rec is None:
            return json_response({'success': False, 'message': 'Unknown upload_id'}, 404)
        snapshot = dict(rec)
    return json_response(snapshot)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
