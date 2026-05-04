from flask import (
    Flask,
    request,
    send_file,
    render_template,
    jsonify
)
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
app.config['MAX_CONTENT_LENGTH'] = \
    50 * 1024 * 1024


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() \
        in ALLOWED_EXTENSIONS


# ── Find LibreOffice on any system ────────────
# Works on Windows laptop AND Railway server
def find_libreoffice():
    possible_paths = [
        'libreoffice',
        'soffice',
        '/usr/bin/libreoffice',
        '/usr/bin/soffice',
        '/usr/local/bin/libreoffice',
        '/usr/local/bin/soffice',
        '/opt/libreoffice/program/soffice',
        '/opt/libreoffice7.6/program/soffice',
        '/opt/libreoffice7.5/program/soffice',
        '/opt/libreoffice7.4/program/soffice',
        '/opt/libreoffice7.3/program/soffice',
        '/snap/bin/libreoffice',
        r'C:\Program Files\LibreOffice\program\soffice.exe',
        r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
    ]

    for path in possible_paths:
        try:
            result = subprocess.run(
                [path, '--version'],
                capture_output=True,
                timeout=15
            )
            if result.returncode == 0:
                print(
                    f"Found LibreOffice at: {path}"
                )
                return path
        except Exception:
            continue

    # Last resort — search in common directories
    search_dirs = [
        '/usr', '/usr/local', '/opt',
        '/snap', '/home'
    ]
    for search_dir in search_dirs:
        for root, dirs, files in os.walk(
            search_dir
        ):
            for f in files:
                if f in ['soffice', 'libreoffice']:
                    full_path = os.path.join(root, f)
                    try:
                        result = subprocess.run(
                            [full_path, '--version'],
                            capture_output=True,
                            timeout=10
                        )
                        if result.returncode == 0:
                            print(
                                f"Found at: {full_path}"
                            )
                            return full_path
                    except Exception:
                        continue

    print("LibreOffice NOT found anywhere")
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
        'libreoffice_found': libreoffice is not None,
        'libreoffice_path': libreoffice,
        'python_version': os.sys.version,
        'message': 'Zobu Converter is running'
    })


# ── Debug route ───────────────────────────────
@app.route('/debug')
def debug():
    info = {
        'PATH': os.environ.get('PATH', 'not set'),
        'cwd': os.getcwd(),
        'files': os.listdir('.'),
    }

    # Try to find libreoffice
    libreoffice_path = find_libreoffice()
    info['libreoffice'] = libreoffice_path

    # Check common paths
    check_paths = [
        '/usr/bin/libreoffice',
        '/usr/bin/soffice',
        '/usr/local/bin/libreoffice',
        '/opt/libreoffice/program/soffice',
    ]
    path_exists = {}
    for p in check_paths:
        path_exists[p] = os.path.exists(p)
    info['path_checks'] = path_exists

    return jsonify(info)


# ── Convert file to PDF ───────────────────────
@app.route('/convert', methods=['POST'])
def convert():

    # Check file in request
    if 'file' not in request.files:
        return jsonify({
            'error': 'No file uploaded. '
                     'Please select a file.'
        }), 400

    file = request.files['file']

    # Check file selected
    if not file.filename:
        return jsonify({
            'error': 'No file selected. '
                     'Please choose a file.'
        }), 400

    # Check file type allowed
    if not allowed_file(file.filename):
        ext = file.filename.rsplit(
            '.', 1
        )[-1] if '.' in file.filename else 'unknown'
        return jsonify({
            'error': f'File type .{ext} is not '
                     f'supported. Use Word Excel '
                     f'PowerPoint or Image files.'
        }), 400

    # Find LibreOffice
    libreoffice_path = find_libreoffice()
    if libreoffice_path is None:
        return jsonify({
            'error': 'LibreOffice is not installed '
                     'on the server. Please contact '
                     'administrator.'
        }), 500

    # Create temp directory for processing
    temp_dir = tempfile.mkdtemp()
    print(f"Temp dir: {temp_dir}")

    try:
        # Save uploaded file with unique name
        unique_id  = str(uuid.uuid4())
        ext        = file.filename.rsplit(
            '.', 1
        )[1].lower()
        input_path = os.path.join(
            temp_dir, f'{unique_id}.{ext}'
        )
        file.save(input_path)
        print(f"Saved input: {input_path}")

        # Set up environment for LibreOffice
        env = os.environ.copy()
        env['HOME'] = temp_dir
        env['TMPDIR'] = temp_dir

        # Run LibreOffice to convert to PDF
        print(
            f"Running: {libreoffice_path} "
            f"--headless --convert-to pdf "
            f"--outdir {temp_dir} {input_path}"
        )

        result = subprocess.run(
            [
                libreoffice_path,
                '--headless',
                '--norestore',
                '--nofirststartwizard',
                '--convert-to', 'pdf',
                '--outdir', temp_dir,
                input_path
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env=env
        )

        print(f"Return code: {result.returncode}")
        print(f"Stdout: {result.stdout}")
        print(f"Stderr: {result.stderr}")

        # Check if PDF was created
        pdf_path = os.path.join(
            temp_dir, f'{unique_id}.pdf'
        )

        if not os.path.exists(pdf_path):
            # Check with alternative name
            for f_name in os.listdir(temp_dir):
                if f_name.endswith('.pdf'):
                    pdf_path = os.path.join(
                        temp_dir, f_name
                    )
                    break

        if not os.path.exists(pdf_path):
            return jsonify({
                'error': 'Conversion failed. '
                         'Could not create PDF. '
                         f'Error: {result.stderr}'
            }), 500

        print(f"PDF created: {pdf_path}")

        # Get original name for download
        original_name = file.filename.rsplit(
            '.', 1
        )[0]
        pdf_filename = f'{original_name}.pdf'

        # Read PDF into memory before sending
        # so we can clean up temp files
        with open(pdf_path, 'rb') as pdf_file:
            pdf_data = pdf_file.read()

        # Clean up temp files now
        try:
            shutil.rmtree(temp_dir)
        except Exception as cleanup_err:
            print(
                f"Cleanup warning: {cleanup_err}"
            )

        # Send PDF as download
        import io
        pdf_io = io.BytesIO(pdf_data)
        pdf_io.seek(0)

        return send_file(
            pdf_io,
            as_attachment=True,
            download_name=pdf_filename,
            mimetype='application/pdf'
        )

    except subprocess.TimeoutExpired:
        return jsonify({
            'error': 'Conversion timed out. '
                     'File may be too large '
                     'or complex. Try a '
                     'smaller file.'
        }), 500

    except Exception as e:
        print(f"Conversion error: {str(e)}")
        return jsonify({
            'error': f'Conversion error: {str(e)}'
        }), 500

    finally:
        # Make sure temp files are cleaned up
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception:
            pass


# ── Error handlers ────────────────────────────
@app.errorhandler(413)
def too_large(e):
    return jsonify({
        'error': 'File too large. '
                 'Maximum size is 50MB.'
    }), 413


@app.errorhandler(404)
def not_found(e):
    return jsonify({
        'error': 'Page not found.'
    }), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({
        'error': 'Server error. Please try again.'
    }), 500


# ── Start server ──────────────────────────────
if __name__ == '__main__':
    print("=" * 50)
    print("Starting Zobu Converter...")
    print("=" * 50)

    # Check LibreOffice on startup
    lo_path = find_libreoffice()
    if lo_path:
        print(f"✅ LibreOffice found: {lo_path}")
    else:
        print("❌ LibreOffice NOT found!")
        print(
            "Install LibreOffice to enable "
            "document conversion"
        )

    print("=" * 50)
    print("Open browser and go to:")
    print("http://localhost:5000")
    print("=" * 50)

    app.run(
        debug=True,
        port=5000,
        host='0.0.0.0'
    )