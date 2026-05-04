from flask import Flask, request, send_file, render_template, jsonify
from flask_cors import CORS
import subprocess
import os
import uuid
import tempfile
import shutil

app = Flask(__name__)
CORS(app)

# ── Allowed file types ────────────────────────
ALLOWED_EXTENSIONS = {
    'doc', 'docx',
    'xls', 'xlsx',
    'ppt', 'pptx',
    'jpg', 'jpeg',
    'png', 'bmp',
    'webp', 'gif'
}

# ── Max file size 50MB ────────────────────────
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() \
        in ALLOWED_EXTENSIONS

def find_libreoffice():
    possible_paths = [
        'soffice',
        'libreoffice',
        r'C:\Program Files\LibreOffice\program\soffice.exe',
        r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
        '/usr/bin/libreoffice',
        '/usr/bin/soffice',
        '/usr/local/bin/libreoffice',
    ]
    for path in possible_paths:
        try:
            result = subprocess.run(
                [path, '--version'],
                capture_output=True,
                timeout=10
            )
            if result.returncode == 0:
                return path
        except Exception:
            continue
    return None

# ── Home page ─────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')

# ── Health check ──────────────────────────────
@app.route('/health')
def health():
    libreoffice = find_libreoffice()
    return jsonify({
        'status': 'ok',
        'libreoffice': libreoffice is not None,
        'libreoffice_path': libreoffice
    })

# ── Convert file to PDF ───────────────────────
@app.route('/convert', methods=['POST'])
def convert():

    # Check file in request
    if 'file' not in request.files:
        return jsonify({
            'error': 'No file uploaded'
        }), 400

    file = request.files['file']

    # Check file selected
    if file.filename == '' or file.filename is None:
        return jsonify({
            'error': 'No file selected'
        }), 400

    # Check file type
    if not allowed_file(file.filename):
        return jsonify({
            'error': 'File type not supported. ' +
                     'Use Word Excel PPT or Image files.'
        }), 400

    # Find LibreOffice
    libreoffice_path = find_libreoffice()
    if libreoffice_path is None:
        return jsonify({
            'error': 'LibreOffice not found. ' +
                     'Please install LibreOffice.'
        }), 500

    # Create temp directory
    temp_dir = tempfile.mkdtemp()

    try:
        # Save uploaded file with unique name
        unique_id  = str(uuid.uuid4())
        ext        = file.filename.rsplit('.', 1)[1].lower()
        input_path = os.path.join(
            temp_dir, f'{unique_id}.{ext}'
        )
        file.save(input_path)

        # Run LibreOffice to convert
        result = subprocess.run(
            [
                libreoffice_path,
                '--headless',
                '--convert-to', 'pdf',
                '--outdir', temp_dir,
                input_path
            ],
            capture_output=True,
            text=True,
            timeout=120
        )

        # Check PDF was created
        pdf_path = os.path.join(
            temp_dir, f'{unique_id}.pdf'
        )

        if not os.path.exists(pdf_path):
            return jsonify({
                'error': 'Conversion failed. ' +
                         result.stderr
            }), 500

        # Get original name for download
        original_name = file.filename.rsplit('.', 1)[0]
        pdf_filename  = f'{original_name}.pdf'

        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=pdf_filename,
            mimetype='application/pdf'
        )

    except subprocess.TimeoutExpired:
        return jsonify({
            'error': 'Conversion timed out. ' +
                     'File may be too large.'
        }), 500

    except Exception as e:
        return jsonify({
            'error': f'Error: {str(e)}'
        }), 500

    finally:
        # Clean up temp files
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

if __name__ == '__main__':
    print("Starting Zobu Converter...")
    print("Open browser and go to:")
    print("http://localhost:5000")
    app.run(debug=True, port=5000, host='0.0.0.0')