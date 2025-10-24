# -*- coding: utf-8 -*-
import os
import json
import hashlib
import hmac
import threading
from functools import wraps
from flask import Flask, request, redirect, render_template_string, Response, session
import subprocess
import shlex

BROWSE_FOLDER = '/app/browse'  # Read-only folder mounted from Synology
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key-change-me')

# Password security setup
PASSWORD_HASH = os.environ.get('PANEL_PASSWORD_HASH', '')
PANEL_PASSWORD = os.environ.get('PANEL_PASSWORD', '')

if PANEL_PASSWORD and not PASSWORD_HASH:
    PASSWORD_HASH = hashlib.sha256(PANEL_PASSWORD.encode()).hexdigest()

upload_status = {}
upload_lock = threading.Lock()

def verify_password(password):
    """Verify password using constant-time comparison"""
    if not PASSWORD_HASH:
        return False
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    return hmac.compare_digest(password_hash, PASSWORD_HASH)

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

def get_files_from_browse_folder(folder_path=''):
    """Get list of files and folders from browse folder"""
    files = []
    folders = []
    try:
        current_path = os.path.join(BROWSE_FOLDER, folder_path) if folder_path else BROWSE_FOLDER
        
        # Security check - prevent directory traversal
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
                                'path': os.path.relpath(item_path, BROWSE_FOLDER)
                            })
                        elif os.path.isfile(item_path):
                            size = os.path.getsize(item_path)
                            files.append({
                                'name': item,
                                'path': os.path.relpath(item_path, BROWSE_FOLDER),
                                'full_path': item_path,
                                'size': size
                            })
                    except Exception as e:
                        app.logger.warning('Error processing item: ' + str(e))
            except Exception as e:
                app.logger.error('Error listing directory: ' + str(e))
    except Exception as e:
        app.logger.error('Error reading browse folder: ' + str(e))
    
    return {'files': files, 'folders': sorted(folders), 'current_path': folder_path}

HTML_LOGIN = u"""
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ChomikUploader - Login</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
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
        h1 {
            text-align: center;
            color: #333;
            margin: 0 0 30px 0;
            font-size: 28px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: bold;
        }
        input[type="password"] {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 16px;
            box-sizing: border-box;
            transition: border-color 0.3s;
        }
        input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
        }
        button:active {
            transform: translateY(0);
        }
        .error {
            background: #fee;
            color: #c33;
            padding: 12px;
            border-radius: 4px;
            margin-bottom: 20px;
            border-left: 4px solid #c33;
        }
        .info {
            text-align: center;
            color: #999;
            font-size: 14px;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>ChomikUploader</h1>
        {% if error %}
            <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <div class="form-group">
                <label for="password">Hasło:</label>
                <input type="password" id="password" name="password" required autofocus>
            </div>
            <button type="submit">Zaloguj się</button>
            <div class="info">
                Wpisz hasło panelu, aby uzyskać dostęp
            </div>
        </form>
    </div>
</body>
</html>
"""

HTML_FORM = u"""
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ChomikUploader</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
        }
        h1 {
            margin: 0;
            color: #333;
        }
        .logout-btn {
            background: #dc3545;
            color: white;
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            text-decoration: none;
            font-size: 14px;
            display: inline-block;
        }
        .logout-btn:hover {
            background: #c82333;
        }
        .container {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h2 {
            color: #555;
            margin-top: 30px;
            margin-bottom: 15px;
            font-size: 18px;
        }
        .info-box {
            background: #e3f2fd;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
            border-left: 4px solid #2196f3;
        }
        .button-group {
            margin: 15px 0;
        }
        button, .retry-btn {
            background: #007bff;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            margin: 5px 5px 5px 0;
            transition: all 0.3s;
        }
        button:hover, .retry-btn:hover {
            background: #0056b3;
        }
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .retry-btn {
            background: #ffc107;
            color: black;
        }
        .retry-btn:hover {
            background: #ffb300;
        }
        .breadcrumb {
            padding: 10px;
            background: #f9f9f9;
            border-radius: 4px;
            margin-bottom: 15px;
            font-size: 14px;
        }
        .breadcrumb a {
            color: #007bff;
            cursor: pointer;
            text-decoration: underline;
        }
        .breadcrumb a:hover {
            color: #0056b3;
        }
        .file-browser {
            max-height: 500px;
            overflow-y: auto;
            border: 1px solid #ddd;
            border-radius: 4px;
            margin: 20px 0;
        }
        .browser-item {
            padding: 12px;
            border-bottom: 1px solid #eee;
            display: flex;
            align-items: center;
            transition: background 0.2s;
        }
        .browser-item:hover {
            background: #f9f9f9;
        }
        .browser-item input[type="checkbox"] {
            margin-right: 12px;
            width: 18px;
            height: 18px;
            cursor: pointer;
        }
        .browser-item input[type="checkbox"]:disabled {
            cursor: not-allowed;
            opacity: 0.5;
        }
        .item-info {
            flex: 1;
        }
        .item-name {
            font-weight: 500;
            color: #333;
            word-break: break-all;
        }
        .folder-name {
            color: #007bff;
            cursor: pointer;
            text-decoration: underline;
        }
        .item-path {
            font-size: 12px;
            color: #999;
            margin-top: 4px;
        }
        .item-size {
            font-size: 12px;
            color: #666;
            margin-left: 15px;
            white-space: nowrap;
        }
        .select-all-row {
            padding: 12px;
            background: #f5f5f5;
            border-bottom: 2px solid #ddd;
            font-weight: bold;
            display: flex;
            align-items: center;
        }
        .select-all-row input {
            margin-right: 12px;
            width: 18px;
            height: 18px;
        }
        .file-list {
            margin-top: 30px;
        }
        .file-item {
            background: #f9f9f9;
            padding: 15px;
            margin: 10px 0;
            border-radius: 4px;
            border-left: 4px solid #007bff;
        }
        .file-item.success {
            border-left-color: #28a745;
        }
        .file-item.error {
            border-left-color: #dc3545;
        }
        .file-item.pending {
            border-left-color: #ffc107;
        }
        .file-name {
            font-weight: bold;
            margin-bottom: 8px;
            word-break: break-all;
        }
        .file-size {
            font-size: 12px;
            color: #999;
            margin-bottom: 8px;
        }
        .progress-bar {
            width: 100%;
            height: 25px;
            background: #e0e0e0;
            border-radius: 4px;
            overflow: hidden;
            margin: 8px 0;
        }
        .progress-fill {
            height: 100%;
            background: #28a745;
            width: 0%;
            transition: width 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 12px;
            font-weight: bold;
        }
        .status-text {
            font-size: 14px;
            color: #666;
            margin-top: 5px;
        }
        .status-success {
            color: #28a745;
        }
        .status-error {
            color: #dc3545;
        }
        .status-pending {
            color: #ffc107;
        }
        .messages {
            margin: 20px 0;
        }
        .alert {
            padding: 12px;
            margin: 10px 0;
            border-radius: 4px;
            border-left: 4px solid #ffc107;
            background: #fff3cd;
            color: #856404;
        }
        .retry-section {
            margin-top: 10px;
            display: none;
        }
        .retry-section.show {
            display: block;
        }
        .no-items {
            padding: 40px;
            text-align: center;
            color: #999;
            font-style: italic;
        }
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
                <label for="selectAll" style="display: inline; cursor: pointer; margin: 0;">Zaznacz wszystkie pliki</label>
            </div>
            <div id="fileList"></div>
        </div>
        
        <div class="button-group">
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
        
        const statusList = document.getElementById('statusList');
        const messagesDiv = document.getElementById('messages');
        const uploadBtn = document.getElementById('uploadBtn');
        const retrySection = document.getElementById('retrySection');
        const fileListDiv = document.getElementById('fileList');
        const breadcrumbDiv = document.getElementById('breadcrumb');

        window.addEventListener('load', () => {
            loadFiles('');
        });

        function loadFiles(folderPath) {
            currentFolder = folderPath;
            fetch('/api/files?path=' + encodeURIComponent(folderPath))
                .then(response => response.json())
                .then(data => {
                    availableFiles = data.files;
                    renderBreadcrumb(data.current_path);
                    renderFileList(data.files, data.folders);
                })
                .catch(error => {
                    showMessage('Błąd pobierania listy plików: ' + error.message, 'error');
                });
        }

        function renderBreadcrumb(path) {
            let html = '<a onclick="loadFiles(\\'\\')">Główny folder</a>';
            if (path) {
                const parts = path.split('/');
                let currentPath = '';
                parts.forEach((part, index) => {
                    currentPath += (index > 0 ? '/' : '') + part;
                    html += ' / <a onclick="loadFiles(\\''+currentPath+'\\')">' + part + '</a>';
                });
            }
            breadcrumbDiv.innerHTML = html;
        }

        function renderFileList(files, folders) {
            fileListDiv.innerHTML = '';
            
            if (folders.length === 0 && files.length === 0) {
                fileListDiv.innerHTML = '<div class="no-items">Brak plików i folderów</div>';
                return;
            }

            // Render folders
            folders.forEach((folder) => {
                const row = document.createElement('div');
                row.className = 'browser-item';
                row.innerHTML = `
                    <div class="item-info" style="flex: 1;">
                        <div class="folder-name" onclick="loadFiles('${folder.path}')">📁 ${folder.name}</div>
                    </div>
                `;
                fileListDiv.appendChild(row);
            });

            // Render files
            files.forEach((file, index) => {
                const row = document.createElement('div');
                row.className = 'browser-item';
                const sizeKB = (file.size / 1024).toFixed(2);
                const sizeMB = (file.size / 1024 / 1024).toFixed(2);
                const sizeDisplay = file.size > 1024 * 1024 ? sizeMB + ' MB' : sizeKB + ' KB';
                
                row.innerHTML = `
                    <input type="checkbox" id="file-${index}" onchange="updateUploadButton()" data-file-index="${index}">
                    <div class="item-info">
                        <div class="item-name">${file.name}</div>
                        <div class="item-path">${file.path}</div>
                    </div>
                    <div class="item-size">${sizeDisplay}</div>
                `;
                fileListDiv.appendChild(row);
            });
            
            updateUploadButton();
        }

        function toggleSelectAll() {
            const selectAll = document.getElementById('selectAll');
            const checkboxes = fileListDiv.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach(cb => {
                cb.checked = selectAll.checked;
            });
            updateUploadButton();
        }

        function deselectAll() {
            const checkboxes = fileListDiv.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach(cb => {
                cb.checked = false;
            });
            document.getElementById('selectAll').checked = false;
            updateUploadButton();
        }

        function updateUploadButton() {
            const checkboxes = fileListDiv.querySelectorAll('input[type="checkbox"]');
            const anyChecked = Array.from(checkboxes).some(cb => cb.checked);
            uploadBtn.disabled = !anyChecked;
        }

        function getSelectedFiles() {
            const selected = [];
            const checkboxes = fileListDiv.querySelectorAll('input[type="checkbox"]:checked');
            checkboxes.forEach((cb) => {
                const index = parseInt(cb.getAttribute('data-file-index'));
                if (!isNaN(index)) {
                    selected.push(availableFiles[index]);
                }
            });
            return selected;
        }

        async function uploadSelected() {
            const selectedFiles = getSelectedFiles();
            
            if (selectedFiles.length === 0) {
                showMessage('Nie wybrano żadnych plików', 'error');
                return;
            }

            messagesDiv.innerHTML = '';
            statusList.innerHTML = '';
            failedFiles = [];
            retrySection.classList.remove('show');

            for (let file of selectedFiles) {
                addFileStatus(file.name, file.size);
            }

            for (let file of selectedFiles) {
                try {
                    await uploadFile(file);
                } catch (error) {
                    updateFileStatus(file.name, 'error', 'Błąd: ' + error.message);
                    failedFiles.push(file.full_path);
                }
            }

            if (failedFiles.length > 0) {
                retrySection.classList.add('show');
            }
        }

        function addFileStatus(fileName, fileSize) {
            const statusItem = document.createElement('div');
            statusItem.className = 'file-item pending';
            statusItem.id = 'status-' + fileName.replace(/[^a-zA-Z0-9]/g, '_');
            const sizeKB = (fileSize / 1024).toFixed(2);
            const sizeMB = (fileSize / 1024 / 1024).toFixed(2);
            const sizeDisplay = fileSize > 1024 * 1024 ? sizeMB + ' MB' : sizeKB + ' KB';
            
            statusItem.innerHTML = `
                <div class="file-name">${fileName}</div>
                <div class="file-size">Rozmiar: ${sizeDisplay}</div>
                <div class="progress-bar">
                    <div class="progress-fill" id="progress-${fileName.replace(/[^a-zA-Z0-9]/g, '_')}">0%</div>
                </div>
                <div class="status-text status-pending" id="text-${fileName.replace(/[^a-zA-Z0-9]/g, '_')}">Oczekiwanie...</div>
            `;
            statusList.appendChild(statusItem);
        }

        function updateFileStatus(fileName, status, message) {
            const safeFileName = fileName.replace(/[^a-zA-Z0-9]/g, '_');
            const statusItem = document.getElementById('status-' + safeFileName);
            const textEl = document.getElementById('text-' + safeFileName);
            const progressEl = document.getElementById('progress-' + safeFileName);
            
            if (!statusItem) return;

            if (status === 'uploading') {
                statusItem.className = 'file-item pending';
                textEl.className = 'status-text status-pending';
                textEl.textContent = message;
            } else if (status === 'success') {
                statusItem.className = 'file-item success';
                progressEl.style.width = '100%';
                progressEl.textContent = '100%';
                textEl.className = 'status-text status-success';
                textEl.textContent = message;
            } else if (status === 'error') {
                statusItem.className = 'file-item error';
                textEl.className = 'status-text status-error';
                textEl.textContent = message;
            }
        }

        function uploadFile(file) {
            return new Promise((resolve, reject) => {
                updateFileStatus(file.name, 'uploading', 'Wysyłanie na Chomika...');
                
                fetch('/api/upload', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        filepath: file.full_path,
                        filename: file.name
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        updateFileStatus(file.name, 'success', 'Przesłano pomyślnie na Chomika!');
                        showMessage('✓ ' + file.name + ' - przesłano pomyślnie', 'success');
                        failedFiles = failedFiles.filter(f => f !== file.full_path);
                    } else {
                        updateFileStatus(file.name, 'error', 'Błąd: ' + (data.message || 'Nieznany błąd'));
                        showMessage('✗ ' + file.name + ' - ' + (data.message || 'Błąd uploadu'), 'error');
                        if (!failedFiles.includes(file.full_path)) {
                            failedFiles.push(file.full_path);
                        }
                    }
                    resolve();
                })
                .catch(error => {
                    updateFileStatus(file.name, 'error', 'Błąd połączenia: ' + error.message);
                    showMessage('✗ ' + file.name + ' - Błąd połączenia', 'error');
                    if (!failedFiles.includes(file.full_path)) {
                        failedFiles.push(file.full_path);
                    }
                    reject(error);
                });
            });
        }

        function retryFailed() {
            showMessage('Ponowne wysyłanie ' + failedFiles.length + ' plików...', 'pending');
            // Implementation for retry
        }

        function showMessage(message, type) {
            const msgEl = document.createElement('div');
            msgEl.className = 'alert';
            msgEl.textContent = message;
            messagesDiv.appendChild(msgEl);
        }
    </script>
</body>
</html>
"""

def json_response(data, status_code=200):
    """Ręczna generacja JSON bez problemu z Flask 0.12 w Python 2.7"""
    response = Response(json.dumps(data), mimetype='application/json', status=status_code)
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
            error = u'Błędne hasło'
    
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
    """Return list of files from browse folder"""
    folder_path = request.args.get('path', '')
    result = get_files_from_browse_folder(folder_path)
    return json_response(result)

@app.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    """Upload file from browse folder to Chomikuj"""
    try:
        data = json.loads(request.data)
        filepath = data.get('filepath')
        filename = data.get('filename')
        
        if not filepath or not filename:
            return json_response({'success': False, 'message': u'Brak ścieżki do pliku'}, 400)
        
        # Verify file exists and is within browse folder
        if not os.path.abspath(filepath).startswith(os.path.abspath(BROWSE_FOLDER)):
            return json_response({'success': False, 'message': u'Nieprawidłowa ścieżka do pliku'}, 400)
        
        if not os.path.exists(filepath):
            return json_response({'success': False, 'message': u'Plik nie istnieje'}, 404)

        username = os.environ.get('CHOMIK_USERNAME')
        password = os.environ.get('CHOMIK_PASSWORD')
        dest_path = os.environ.get('CHOMIK_DEST', u'/Moje_Uploady')

        if not username or not password:
            return json_response({'success': False, 'message': u'Błąd: Brak konfiguracji CHOMIK_USERNAME lub CHOMIK_PASSWORD'}, 500)

        # Properly escape filepath for shell - handles spaces and special characters
        proc = subprocess.Popen([
            "chomik", "-l", username, "-p", password, "-u", dest_path, filepath
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        out, err = proc.communicate()
        
        if proc.returncode == 0:
            return json_response({'success': True, 'message': u'Plik przesłany pomyślnie na Chomika!'})
        else:
            error_msg = err.decode() if err else u'Nieznany błąd'
            app.logger.error('ChomikUploader error: ' + error_msg)
            return json_response({'success': False, 'message': u'Błąd uploadu: ' + error_msg}, 500)
    
    except Exception as e:
        app.logger.error('Upload error: ' + str(e))
        return json_response({'success': False, 'message': u'Błąd: ' + str(e)}, 500)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
