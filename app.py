# -*- coding: utf-8 -*-
import os
import json
import hashlib
import hmac
import threading
from functools import wraps
from flask import Flask, request, redirect, render_template_string, Response, session
import subprocess
import shutil

UPLOAD_FOLDER = 'uploads'
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key-change-me')

# Password security setup
PASSWORD_HASH = os.environ.get('PANEL_PASSWORD_HASH', '')
PANEL_PASSWORD = os.environ.get('PANEL_PASSWORD', '')

# If plain password is set, we hash it on startup
if PANEL_PASSWORD and not PASSWORD_HASH:
    PASSWORD_HASH = hashlib.sha256(PANEL_PASSWORD.encode()).hexdigest()

upload_status = {}
upload_lock = threading.Lock()

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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
            max-width: 900px;
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
            font-size: 18px;
        }
        .upload-area {
            border: 2px dashed #ccc;
            border-radius: 8px;
            padding: 30px;
            text-align: center;
            cursor: pointer;
            margin: 20px 0;
            transition: all 0.3s;
            background: #fafafa;
        }
        .upload-area:hover {
            border-color: #666;
            background: #f0f0f0;
        }
        .upload-area.drag-over {
            border-color: #007bff;
            background: #e7f3ff;
        }
        input[type="file"] {
            display: none;
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
        .selected-files {
            background: #f9f9f9;
            padding: 15px;
            border-radius: 4px;
            margin: 20px 0;
            border: 1px solid #ddd;
            min-height: 40px;
        }
        .file-chip {
            display: inline-block;
            background: #e3f2fd;
            border: 1px solid #90caf9;
            border-radius: 20px;
            padding: 8px 12px;
            margin: 5px 5px 5px 0;
            font-size: 14px;
        }
        .file-chip .remove {
            cursor: pointer;
            margin-left: 8px;
            color: #d32f2f;
            font-weight: bold;
        }
        .file-chip .remove:hover {
            color: #b71c1c;
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
        .no-files-text {
            color: #999;
            font-style: italic;
            font-size: 14px;
        }
        .retry-section {
            margin-top: 10px;
            display: none;
        }
        .retry-section.show {
            display: block;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Wyślij pliki do Chomika</h1>
        <a href="/logout" class="logout-btn">Wyloguj się</a>
    </div>
    
    <div class="container">
        <div id="messages" class="messages"></div>
        
        <form id="uploadForm" enctype="multipart/form-data">
            <div class="upload-area" id="uploadArea">
                <p><strong>Kliknij tutaj lub przeciągnij pliki</strong></p>
                <p style="font-size: 12px; color: #999;">Możesz wybrać wiele plików naraz</p>
                <input type="file" id="fileInput" name="files" multiple>
            </div>
            
            <h2>Wybrane pliki do wysłania:</h2>
            <div id="selectedFiles" class="selected-files">
                <span class="no-files-text">Nie wybrano żadnych plików</span>
            </div>
            
            <div class="button-group">
                <button type="submit" id="submitBtn" disabled>Wyślij pliki</button>
                <button type="button" id="clearBtn" onclick="clearSelection()">Wyczyść wybór</button>
            </div>
        </form>
        
        <div class="file-list">
            <h2>Status uploadów:</h2>
            <div id="statusList"></div>
            <div id="retrySection" class="retry-section">
                <button type="button" onclick="retryFailed()" class="retry-btn">Spróbuj wysłać ponownie pliki, które się nie powiodły</button>
            </div>
        </div>
    </div>

    <script>
        let failedFiles = [];
        
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const uploadForm = document.getElementById('uploadForm');
        const statusList = document.getElementById('statusList');
        const messagesDiv = document.getElementById('messages');
        const selectedFilesDiv = document.getElementById('selectedFiles');
        const submitBtn = document.getElementById('submitBtn');
        const retrySection = document.getElementById('retrySection');

        uploadArea.addEventListener('click', () => fileInput.click());
        
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('drag-over');
        });
        
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('drag-over');
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');
            fileInput.files = e.dataTransfer.files;
            updateSelectedFiles();
        });

        fileInput.addEventListener('change', updateSelectedFiles);

        function updateSelectedFiles() {
            const files = fileInput.files;
            selectedFilesDiv.innerHTML = '';
            
            if (files.length === 0) {
                selectedFilesDiv.innerHTML = '<span class="no-files-text">Nie wybrano żadnych plików</span>';
                submitBtn.disabled = true;
            } else {
                submitBtn.disabled = false;
                for (let file of files) {
                    const chip = document.createElement('div');
                    chip.className = 'file-chip';
                    const sizeKB = (file.size / 1024).toFixed(2);
                    chip.innerHTML = `
                        ${file.name} (${sizeKB} KB)
                        <span class="remove" onclick="removeFile('${file.name}')">✕</span>
                    `;
                    selectedFilesDiv.appendChild(chip);
                }
            }
        }

        function removeFile(fileName) {
            const files = Array.from(fileInput.files).filter(f => f.name !== fileName);
            const dataTransfer = new DataTransfer();
            files.forEach(file => dataTransfer.items.add(file));
            fileInput.files = dataTransfer.files;
            updateSelectedFiles();
        }

        function clearSelection() {
            fileInput.value = '';
            updateSelectedFiles();
        }

        uploadForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const files = fileInput.files;
            if (files.length === 0) {
                showMessage('Nie wybrano żadnych plików', 'error');
                return;
            }

            messagesDiv.innerHTML = '';
            statusList.innerHTML = '';
            failedFiles = [];
            retrySection.classList.remove('show');

            for (let file of files) {
                addFileStatus(file.name, file.size);
            }

            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                const formData = new FormData();
                formData.append('file', file);
                
                try {
                    await uploadFile(file.name, formData, i, files.length);
                } catch (error) {
                    updateFileStatus(file.name, 'error', 'Błąd: ' + error.message);
                    failedFiles.push(file.name);
                }
            }

            if (failedFiles.length > 0) {
                retrySection.classList.add('show');
            }

            fileInput.value = '';
            updateSelectedFiles();
        });

        function addFileStatus(fileName, fileSize) {
            const statusItem = document.createElement('div');
            statusItem.className = 'file-item pending';
            statusItem.id = 'status-' + fileName;
            const sizeKB = (fileSize / 1024).toFixed(2);
            statusItem.innerHTML = `
                <div class="file-name">${fileName}</div>
                <div class="file-size">Rozmiar: ${sizeKB} KB</div>
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

        function uploadFile(fileName, formData, index, total) {
            return new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        const percentComplete = Math.round((e.loaded / e.total) * 100);
                        updateProgress(fileName, percentComplete);
                        updateFileStatus(fileName, 'uploading', 'Upload: ' + percentComplete + '%');
                    }
                });

                xhr.addEventListener('load', () => {
                    if (xhr.status === 200) {
                        try {
                            const response = JSON.parse(xhr.responseText);
                            if (response.success) {
                                updateFileStatus(fileName, 'success', 'Przesłano pomyślnie na Chomika!');
                                showMessage('✓ ' + fileName + ' - przesłano pomyślnie', 'success');
                                failedFiles = failedFiles.filter(f => f !== fileName);
                            } else {
                                updateFileStatus(fileName, 'error', 'Błąd: ' + (response.message || 'Nieznany błąd'));
                                showMessage('✗ ' + fileName + ' - ' + (response.message || 'Błąd uploadu'), 'error');
                                if (!failedFiles.includes(fileName)) {
                                    failedFiles.push(fileName);
                                }
                            }
                        } catch (e) {
                            updateFileStatus(fileName, 'error', 'Błąd parsowania odpowiedzi');
                            showMessage('✗ ' + fileName + ' - Błąd parsowania odpowiedzi', 'error');
                            if (!failedFiles.includes(fileName)) {
                                failedFiles.push(fileName);
                            }
                        }
                    } else {
                        updateFileStatus(fileName, 'error', 'Błąd: ' + xhr.statusText);
                        showMessage('✗ ' + fileName + ' - Błąd HTTP ' + xhr.status, 'error');
                        if (!failedFiles.includes(fileName)) {
                            failedFiles.push(fileName);
                        }
                    }
                    resolve();
                });

                xhr.addEventListener('error', () => {
                    updateFileStatus(fileName, 'error', 'Błąd połączenia');
                    showMessage('✗ ' + fileName + ' - Błąd połączenia', 'error');
                    if (!failedFiles.includes(fileName)) {
                        failedFiles.push(fileName);
                    }
                    reject(new Error('Network error'));
                });

                xhr.addEventListener('abort', () => {
                    updateFileStatus(fileName, 'error', 'Upload anulowany');
                    if (!failedFiles.includes(fileName)) {
                        failedFiles.push(fileName);
                    }
                    reject(new Error('Upload aborted'));
                });

                xhr.open('POST', '/upload', true);
                xhr.send(formData);
            });
        }

        async function retryFailed() {
            if (failedFiles.length === 0) {
                showMessage('Brak plików do ponownego wysłania', 'error');
                return;
            }

            messagesDiv.innerHTML = '';
            const filesToRetry = [...failedFiles];
            failedFiles = [];

            showMessage('Ponowne wysyłanie ' + filesToRetry.length + ' plików...', 'pending');

            for (let fileName of filesToRetry) {
                const statusItem = document.getElementById('status-' + fileName);
                if (statusItem) {
                    statusItem.remove();
                }
                addFileStatus(fileName, 0);
                
                const formData = new FormData();
                const fileBlob = new Blob();
                formData.append('file', fileBlob, fileName);
                
                try {
                    await uploadFileRetry(fileName, formData);
                } catch (error) {
                    updateFileStatus(fileName, 'error', 'Błąd: ' + error.message);
                    if (!failedFiles.includes(fileName)) {
                        failedFiles.push(fileName);
                    }
                }
            }

            if (failedFiles.length === 0) {
                retrySection.classList.remove('show');
                showMessage('Wszystkie pliki przesłano pomyślnie!', 'success');
            } else {
                retrySection.classList.add('show');
                showMessage('Nadal ' + failedFiles.length + ' plików się nie powiodło', 'error');
            }
        }

        function uploadFileRetry(fileName, formData) {
            return new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                
                xhr.addEventListener('load', () => {
                    if (xhr.status === 200) {
                        try {
                            const response = JSON.parse(xhr.responseText);
                            if (response.success) {
                                updateFileStatus(fileName, 'success', 'Przesłano pomyślnie na Chomika! (retry)');
                                showMessage('✓ ' + fileName + ' - przesłano pomyślnie (retry)', 'success');
                                failedFiles = failedFiles.filter(f => f !== fileName);
                            } else {
                                updateFileStatus(fileName, 'error', 'Błąd: ' + (response.message || 'Nieznany błąd'));
                                showMessage('✗ ' + fileName + ' - ' + (response.message || 'Błąd uploadu'), 'error');
                                if (!failedFiles.includes(fileName)) {
                                    failedFiles.push(fileName);
                                }
                            }
                        } catch (e) {
                            updateFileStatus(fileName, 'error', 'Błąd parsowania odpowiedzi');
                            if (!failedFiles.includes(fileName)) {
                                failedFiles.push(fileName);
                            }
                        }
                    } else {
                        updateFileStatus(fileName, 'error', 'Błąd: ' + xhr.statusText);
                        if (!failedFiles.includes(fileName)) {
                            failedFiles.push(fileName);
                        }
                    }
                    resolve();
                });

                xhr.addEventListener('error', () => {
                    updateFileStatus(fileName, 'error', 'Błąd połączenia');
                    if (!failedFiles.includes(fileName)) {
                        failedFiles.push(fileName);
                    }
                    reject(new Error('Network error'));
                });

                xhr.open('POST', '/upload', true);
                xhr.send(formData);
            });
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

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        return redirect('/')
    return render_template_string(HTML_FORM)

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    try:
        if 'file' not in request.files:
            return json_response({'success': False, 'message': u'Brak pliku w żądaniu'}, 400)
        
        file = request.files['file']
        if file.filename == '':
            return json_response({'success': False, 'message': u'Nie wybrano pliku'}, 400)
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        username = os.environ.get('CHOMIK_USERNAME')
        password = os.environ.get('CHOMIK_PASSWORD')
        dest_path = os.environ.get('CHOMIK_DEST', u'/Moje_Uploady')

        if not username or not password:
            return json_response({'success': False, 'message': u'Błąd: Brak konfiguracji CHOMIK_USERNAME lub CHOMIK_PASSWORD'}, 500)

        # Wywołaj chomik CLI
        proc = subprocess.Popen([
            "chomik", "-l", username, "-p", password, "-u", dest_path, filepath
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        out, err = proc.communicate()
        
        # Usuń plik po uploadzie
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            app.logger.warning('Could not delete file: ' + str(e))
        
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
