# -*- coding: utf-8 -*-
import os
import json
import hashlib
import hmac
import threading
from functools import wraps
from flask import Flask, request, redirect, render_template_string, Response, session
import subprocess

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

def get_files_from_browse_folder():
    """Get list of files from browse folder"""
    files = []
    try:
        if os.path.exists(BROWSE_FOLDER):
            for root, dirs, filenames in os.walk(BROWSE_FOLDER):
                for filename in filenames:
                    filepath = os.path.join(root, filename)
                    relative_path = os.path.relpath(filepath, BROWSE_FOLDER)
                    try:
                        size = os.path.getsize(filepath)
                        files.append({
                            'name': filename,
                            'path': relative_path,
                            'full_path': filepath,
                            'size': size
                        })
                    except:
                        pass
    except Exception as e:
        app.logger.error('Error reading browse folder: ' + str(e))
    return files

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
        .file-browser {
            max-height: 400px;
            overflow-y: auto;
            border: 1px solid #ddd;
            border-radius: 4px;
            margin: 20px 0;
        }
        .file-row {
            padding: 12px;
            border-bottom: 1px solid #eee;
            display: flex;
            align-items: center;
            transition: background 0.2s;
        }
        .file-row:hover {
            background: #f9f9f9;
        }
        .file-row input[type="checkbox"] {
            margin-right: 12px;
            width: 18px;
            height: 18px;
            cursor: pointer;
        }
        .file-info {
            flex: 1;
        }
        .file-name-browser {
            font-weight: 500;
            color: #333;
            word-break: break-all;
        }
        .file-path {
            font-size: 12px;
            color: #999;
            margin-top: 4px;
        }
        .file-size-browser {
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
        .no-files {
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
        
        <h2>Dostępne pliki na Synology:</h2>
        <div class="file-browser" id="fileBrowser">
            <div class="select-all-row">
                <input type="checkbox" id="selectAll" onchange="toggleSelectAll()">
                <label for="selectAll" style="display: inline; cursor: pointer;">Zaznacz wszystkie</label>
            </div>
            <div id="fileList"></div>
        </div>
        
        <div class="button-group">
            <button id="uploadBtn" onclick="uploadSelected()" disabled>Wyślij zaznaczone pliki</button>
            <button onclick="refreshFileList()">Odśwież listę</button>
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
        
        const statusList = document.getElementById('statusList');
        const messagesDiv = document.getElementById('messages');
        const uploadBtn = document.getElementById('uploadBtn');
        const retrySection = document.getElementById('retrySection');
        const fileListDiv = document.getElementById('fileList');

        // Load files on page load
        window.addEventListener('load', () => {
            refreshFileList();
        });

        function refreshFileList() {
            fetch('/api/files')
                .then(response => response.json())
                .then(data => {
                    availableFiles = data.files;
                    renderFileList();
                })
                .catch(error => {
                    showMessage('Błąd pobierania listy plików: ' + error.message, 'error');
                });
        }

        function renderFileList() {
            fileListDiv.innerHTML = '';
            
            if (availableFiles.length === 0) {
                fileListDiv.innerHTML = '<div class="no-files">Brak plików w katalogu</div>';
                return;
            }

            availableFiles.forEach((file, index) => {
                const row = document.createElement('div');
                row.className = 'file-row';
                const sizeKB = (file.size / 1024).toFixed(2);
                const sizeMB = (file.size / 1024 / 1024).toFixed(2);
                const sizeDisplay = file.size > 1024 * 1024 ? sizeMB + ' MB' : sizeKB + ' KB';
                
                row.innerHTML = `
                    <input type="checkbox" id="file-${index}" onchange="updateUploadButton()">
                    <div class="file-info">
                        <div class="file-name-browser">${file.name}</div>
                        <div class="file-path">${file.path}</div>
                    </div>
                    <div class="file-size-browser">${sizeDisplay}</div>
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

        function updateUploadButton() {
            const checkboxes = fileListDiv.querySelectorAll('input[type="checkbox"]');
            const anyChecked = Array.from(checkboxes).some(cb => cb.checked);
            uploadBtn.disabled = !anyChecked;
        }

        function getSelectedFiles() {
            const selected = [];
            const checkboxes = fileListDiv.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach((cb, index) => {
                if (cb.checked) {
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
                    failedFiles.push(file.name);
                }
            }

            if (failedFiles.length > 0) {
                retrySection.classList.add('show');
            }
        }

        function addFileStatus(fileName, fileSize) {
            const statusItem = document.createElement('div');
            statusItem.className = 'file-item pending';
            statusItem.id = 'status-' + fileName;
            const sizeKB = (fileSize / 1024).toFixed(2);
            const sizeMB = (fileSize / 1024 / 1024).toFixed(2);
            const sizeDisplay = fileSize > 1024 * 1024 ? sizeMB + ' MB' : sizeKB + ' KB';
            
            statusItem.innerHTML = `
                <div class="file-name">${fileName}</div>
                <div class="file-size">Rozmiar: ${sizeDisplay}</div>
                <div class="progress-bar">
                    <div class="progress-fill" id="progress-${fileName}">0%</div>
                </div>
                <div class="status-text status-pending" id="text-${fileName}">Oczekiwanie...</div>
            `;
            statusList.appendChild(statusItem);
        }

        function updateFileStatus(fileName, status, message) {
            const statusItem = document.getElementById('status-' + fileName);
            const textEl = document.getElementById('text-' + fileName);
            const progressEl = document.getElementById('progress-' + fileName);
            
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

        function updateProgress(fileName, percent) {
            const progressEl = document.getElementById('progress-' + fileName);
            if (progressEl) {
                progressEl.style.width = percent + '%';
                progressEl.textContent = percent + '%';
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
                        failedFiles = failedFiles.filter(f => f !== file.name);
                    } else {
                        updateFileStatus(file.name, 'error', 'Błąd: ' + (data.message || 'Nieznany błąd'));
                        showMessage('✗ ' + file.name + ' - ' + (data.message || 'Błąd uploadu'), 'error');
                        if (!failedFiles.includes(file.name)) {
                            failedFiles.push(file.name);
                        }
                    }
                    resolve();
                })
                .catch(error => {
                    updateFileStatus(file.name, 'error', 'Błąd połączenia: ' + error.message);
                    showMessage('✗ ' + file.name + ' - Błąd połączenia', 'error');
                    if (!failedFiles.includes(file.name)) {
                        failedFiles.push(file.name);
                    }
                    reject(error);
                });
            });
        }

        function retryFailed() {
            // Retry implementation for failed files
            showMessage('Funkcja retry w rozwoju', 'info');
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
    files = get_files_from_browse_folder()
    return json_response({'files': files})

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
        if not filepath.startswith(BROWSE_FOLDER):
            return json_response({'success': False, 'message': u'Nieprawidłowa ścieżka do pliku'}, 400)
        
        if not os.path.exists(filepath):
            return json_response({'success': False, 'message': u'Plik nie istnieje'}, 404)

        username = os.environ.get('CHOMIK_USERNAME')
        password = os.environ.get('CHOMIK_PASSWORD')
        dest_path = os.environ.get('CHOMIK_DEST', u'/Moje_Uploady')

        if not username or not password:
            return json_response({'success': False, 'message': u'Błąd: Brak konfiguracji CHOMIK_USERNAME lub CHOMIK_PASSWORD'}, 500)

        # Wywołaj chomik CLI bezpośrednio na pliku z browse folder
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
