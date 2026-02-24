"""
Manejo de entrada de PDFs: validación, descarga remota y resolución de input.
"""
import os
import uuid
import requests
from urllib.parse import urlparse, unquote, quote
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'pdf'}
MAX_REMOTE_PDF_SIZE_MB = int(os.getenv('MAX_REMOTE_PDF_SIZE_MB', '50'))
MAX_REMOTE_PDF_SIZE_BYTES = MAX_REMOTE_PDF_SIZE_MB * 1024 * 1024
REMOTE_PDF_TIMEOUT_SECONDS = int(os.getenv('REMOTE_PDF_TIMEOUT_SECONDS', '45'))


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def infer_pdf_filename_from_url(pdf_url):
    parsed = urlparse(pdf_url)
    candidate = unquote(os.path.basename(parsed.path or '')).strip()
    if not candidate:
        return 'document.pdf'
    if not candidate.lower().endswith('.pdf'):
        return f"{candidate}.pdf"
    return candidate


def _sanitize_url(pdf_url):
    """Encodea espacios y caracteres no-ASCII en el path de la URL."""
    parsed = urlparse(pdf_url)
    safe_path = quote(unquote(parsed.path), safe='/:@!$&\'()*+,;=')
    return parsed._replace(path=safe_path).geturl()


def download_pdf_from_url(pdf_url, destination_path, timeout=REMOTE_PDF_TIMEOUT_SECONDS):
    """
    Descarga un PDF desde URL con validaciones de tamaño, content-type y cabecera PDF.
    """
    pdf_url = _sanitize_url(pdf_url)
    total_bytes = 0
    with requests.get(pdf_url, stream=True, timeout=timeout, allow_redirects=True) as response:
        response.raise_for_status()
        content_type = (response.headers.get('Content-Type') or '').lower()
        if content_type and ('pdf' not in content_type and 'octet-stream' not in content_type):
            raise ValueError(f"La URL no parece un PDF (Content-Type: {content_type})")
        with open(destination_path, 'wb') as out:
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if total_bytes > MAX_REMOTE_PDF_SIZE_BYTES:
                    raise ValueError(
                        f"El PDF remoto excede el máximo de {MAX_REMOTE_PDF_SIZE_MB} MB"
                    )
                out.write(chunk)

    if total_bytes == 0:
        raise ValueError('El PDF remoto está vacío')
    with open(destination_path, 'rb') as check:
        header = check.read(5)
    if header != b'%PDF-':
        raise ValueError('El archivo descargado no es un PDF válido')


def resolve_pdf_input(request, upload_folder):
    """
    Resuelve el PDF de entrada desde multipart/form-data o JSON con pdf_url.
    Returns: (pdf_path, original_filename, temp_paths_to_cleanup)
    """
    process_id = str(uuid.uuid4())
    temp_paths = []

    # Intentar desde archivo adjunto
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename and allowed_file(file.filename):
            original_filename = secure_filename(file.filename)
            pdf_path = os.path.join(upload_folder, f"{process_id}_{original_filename}")
            file.save(pdf_path)
            temp_paths.append(pdf_path)
            return pdf_path, original_filename, temp_paths, process_id

    # Intentar desde JSON con pdf_url
    payload = {}
    if request.is_json:
        payload = request.get_json() or {}
    pdf_url = payload.get('pdf_url') or request.form.get('pdf_url', '')
    if pdf_url:
        original_filename = infer_pdf_filename_from_url(pdf_url)
        pdf_path = os.path.join(upload_folder, f"{process_id}_{secure_filename(original_filename)}")
        download_pdf_from_url(pdf_url, pdf_path)
        temp_paths.append(pdf_path)
        return pdf_path, original_filename, temp_paths, process_id

    raise ValueError('Se requiere un archivo PDF (campo "file") o una URL PDF (campo "pdf_url")')
