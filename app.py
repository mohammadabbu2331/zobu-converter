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
import io
import sys

app = Flask(__name__)
CORS(app)

ALLOWED_EXTENSIONS = {
    'doc', 'docx',
    'xls', 'xlsx',
    'ppt', 'pptx',
    'jpg', 'jpeg',
    'png', 'bmp',
    'webp', 'gif'
}

app.config['MAX_CONTENT_LENGTH'] = \
    50 * 1024 * 1024


def install_libreoffice():
    print("Attempting to install LibreOffice...")
    try:
        subprocess.run(
            ['apt-get', 'update', '-y'],
            capture_output=True,
            timeout=120
        )
        result = subprocess.run(
            [
                'apt-get', 'install',
                '-y', '--no-install-recommends',
                'libreoffice'
            ],
            capture_output=True,
            timeout=300
        )
        if result.returncode == 0:
            print("LibreOffice installed successfully")
            return True
        else:
            print(
                f"Install failed: {result.stderr}"
            )
            return False
    except Exception as e:
        print(f"Install error: {e}")
        return False


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
                print(f"LibreOffice found: {path}")
                return path
        except Exception:
            continue

    # Search in directories
    search_dirs = [
        '/usr/bin',
        '/usr/local/bin',
        '/opt',
        '/snap/bin'
    ]
    for d in search_dirs:
        if os.path.exists(d):
            for f in os.listdir(d):
                if 'libreoffice' in f.lower() or \
                   f == 'soffice':
                    full = os.path.join(d, f)
                    try:
                        r = subprocess.run(
                            [full, '--version'],
                            capture_output=True,
                            timeout=10
                        )
                        if r.returncode == 0:
                            print(
                                f"Found: {full}"
                            )
                            return full
                    except Exception:
                        continue

    return None


# Try to find LibreOffice on startup
# If not found try to install it
LIBREOFFICE_PATH = find_libreoffice()
if LIBREOFFICE_PATH is None:
    print("LibreOffice not found. Installing...")
    if install_libreoffice():
        LIBREOFFICE_PATH = find_libreoffice()


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() \
        in ALLOWED_EXTENSIONS


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/health')
def health():
    lo = find_libreoffice()
    return jsonify({
        'status': 'ok',
        'libreoffice_found': lo is not None,
        'libreoffice_path': lo,
        'python_version': sys.version,
        'message': 'Zobu Converter is running'
    })


@app.route('/debug')
def debug():
    lo = find_libreoffice()
    path_env = os.environ.get('PATH', '')
    checks = {}
    check_list = [
        '/usr/bin/libreoffice',
        '/usr/bin/soffice',
        '/usr/local/bin/libreoffice',
        '/opt/libreoffice/program/soffice',
    ]
    for p in check_list:
        checks[p] = os.path.exists(p)

    usr_bin = []
    if os.path.exists('/usr/bin'):
        usr_bin = [
            f for f in os.listdir('/usr/bin')
            if 'libre' in f.lower() or
               f == 'soffice'
        ]

    return jsonify({
        'libreoffice': lo,
        'PATH': path_env,
        'path_checks': checks,
        'usr_bin_matches': usr_bin,
        'cwd': os.getcwd(),
    })


@app.route('/install-libreoffice')
def trigger_install():
    success = install_libreoffice()
    lo = find_libreoffice()
    return jsonify({
        'install_success': success,
        'libreoffice_found': lo is not None,
        'libreoffice_path': lo
    })


@app.route('/convert', methods=['POST'])
def convert():

    if 'file' not in request.files:
        return jsonify({
            'error': 'No file uploaded.'
        }), 400

    file = request.files['file']

    if not file.filename:
        return jsonify({
            'error': 'No file selected.'
        }), 400

    if not allowed_file(file.filename):
        return jsonify({
            'error': 'File type not supported. '
                     'Use Word Excel PPT or Image.'
        }), 400

    # Find LibreOffice
    libreoffice_path = find_libreoffice()

    # If not found try install then find again
    if libreoffice_path is None:
        print("LibreOffice not found. Trying install...")
        install_libreoffice()
        libreoffice_path = find_libreoffice()

    if libreoffice_path is None:
        return jsonify({
            'error': 'LibreOffice is not available. '
                     'Please try again in 5 minutes '
                     'while the server sets up.'
        }), 500

    temp_dir = tempfile.mkdtemp()

    try:
        unique_id  = str(uuid.uuid4())
        ext        = file.filename.rsplit(
            '.', 1
        )[1].lower()
        input_path = os.path.join(
            temp_dir, f'{unique_id}.{ext}'
        )
        file.save(input_path)
        print(f"File saved: {input_path}")

        env          = os.environ.copy()
        env['HOME']  = temp_dir
        env['TMPDIR'] = temp_dir

        print(f"Converting with: {libreoffice_path}")

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
        if result.stderr:
            print(f"Stderr: {result.stderr}")

        pdf_path = os.path.join(
            temp_dir, f'{unique_id}.pdf'
        )

        if not os.path.exists(pdf_path):
            for f_name in os.listdir(temp_dir):
                if f_name.endswith('.pdf'):
                    pdf_path = os.path.join(
                        temp_dir, f_name
                    )
                    print(
                        f"Found PDF: {pdf_path}"
                    )
                    break

        if not os.path.exists(pdf_path):
            return jsonify({
                'error': 'Conversion failed. '
                         f'{result.stderr}'
            }), 500

        original_name = file.filename.rsplit(
            '.', 1
        )[0]
        pdf_filename = f'{original_name}.pdf'

        with open(pdf_path, 'rb') as pdf_file:
            pdf_data = pdf_file.read()

        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

        pdf_io = io.BytesIO(pdf_data)
        pdf_io.seek(0)

        print(
            f"Sending PDF: {pdf_filename} "
            f"({len(pdf_data)} bytes)"
        )

        return send_file(
            pdf_io,
            as_attachment=True,
            download_name=pdf_filename,
            mimetype='application/pdf'
        )

    except subprocess.TimeoutExpired:
        return jsonify({
            'error': 'Conversion timed out. '
                     'Try a smaller file.'
        }), 500

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({
            'error': f'Error: {str(e)}'
        }), 500

    finally:
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception:
            pass


@app.errorhandler(413)
def too_large(e):
    return jsonify({
        'error': 'File too large. Max 50MB.'
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


if __name__ == '__main__':
    print("=" * 50)
    print("Zobu Converter Starting...")
    print("=" * 50)
    lo = find_libreoffice()
    if lo:
        print(f"✅ LibreOffice: {lo}")
    else:
        print("❌ LibreOffice not found")
        print("Trying to install...")
        install_libreoffice()
    print("=" * 50)
    print("http://localhost:5000")
    print("=" * 50)
    app.run(
        debug=True,
        port=5000,
        host='0.0.0.0'
    )