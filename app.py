from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import subprocess
import uuid
import re
import requests
import json
import time
import base64
import mimetypes
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import fitz
from PIL import Image

app = Flask(__name__)

# Configuración
UPLOAD_FOLDER = '/tmp/uploads'
OUTPUT_FOLDER = '/tmp/outputs'
ALLOWED_EXTENSIONS = {'pdf'}
DEFAULT_RENDER_DPI = 200
MAX_OCR_HEIGHT = 7600
PUBLIC_ASSET_TTL_SECONDS = int(os.getenv('PUBLIC_ASSET_TTL_SECONDS', '3600'))
DEFAULT_PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', '').strip().rstrip('/')
PROCESS_META_FILENAME = '_process_meta.json'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def resolve_public_base_url(req):
    explicit_base = req.form.get('public_base_url', '').strip().rstrip('/')
    if explicit_base:
        return explicit_base
    if DEFAULT_PUBLIC_BASE_URL:
        return DEFAULT_PUBLIC_BASE_URL
    forwarded_proto = req.headers.get('X-Forwarded-Proto', req.scheme)
    forwarded_host = req.headers.get('X-Forwarded-Host', req.host)
    proto = forwarded_proto.split(',')[0].strip()
    host = forwarded_host.split(',')[0].strip()
    return f"{proto}://{host}"


def build_convert_query_url(public_base_url, action, process_id, asset_path=None):
    params = {'action': action, 'process_id': process_id}
    if asset_path is not None:
        params['asset_path'] = asset_path
    return f"{public_base_url}/convert?{urlencode(params)}"


def build_public_asset_url(public_base_url, process_id, asset_path):
    return build_convert_query_url(
        public_base_url=public_base_url,
        action='asset',
        process_id=process_id,
        asset_path=asset_path
    )


def utcnow():
    return datetime.now(timezone.utc)


def dt_to_iso(dt):
    return dt.isoformat().replace('+00:00', 'Z')


def iso_to_dt(value):
    if not value:
        return None
    normalized = value.replace('Z', '+00:00')
    return datetime.fromisoformat(normalized)


def process_meta_path(output_dir):
    return os.path.join(output_dir, PROCESS_META_FILENAME)


def read_process_meta(output_dir):
    meta_path = process_meta_path(output_dir)
    if not os.path.isfile(meta_path):
        return None
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def write_process_meta(output_dir, process_id, html_filename, public_base_url, ttl_seconds):
    created_at = utcnow()
    expires_at = created_at + timedelta(seconds=ttl_seconds)
    meta = {
        'process_id': process_id,
        'html_filename': html_filename,
        'created_at': dt_to_iso(created_at),
        'expires_at': dt_to_iso(expires_at),
        'assets_base_url': build_convert_query_url(public_base_url, 'asset', process_id),
        'asset_url_template': build_public_asset_url(public_base_url, process_id, '{asset_path}'),
        'public_html_url': build_convert_query_url(public_base_url, 'view', process_id),
        'public_download_url': build_convert_query_url(public_base_url, 'download', process_id)
    }
    with open(process_meta_path(output_dir), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


def is_output_expired(output_dir):
    meta = read_process_meta(output_dir)
    if not meta:
        return False, None
    expires_at = iso_to_dt(meta.get('expires_at'))
    if not expires_at:
        return False, meta
    return utcnow() >= expires_at, meta


def cleanup_expired_outputs():
    if not os.path.isdir(OUTPUT_FOLDER):
        return
    for item in os.listdir(OUTPUT_FOLDER):
        output_dir = os.path.join(OUTPUT_FOLDER, item)
        if not os.path.isdir(output_dir):
            continue
        expired, _ = is_output_expired(output_dir)
        if expired:
            shutil.rmtree(output_dir, ignore_errors=True)


def rewrite_html_img_sources(html_content, source_values):
    """
    Reemplaza src de cada <img> por los valores indicados, en orden.
    """
    if not source_values:
        return html_content
    idx = [0]

    def replace_src(match):
        if idx[0] < len(source_values):
            new_src = source_values[idx[0]]
            idx[0] += 1
            quote = match.group(2)
            return match.group(1) + quote + new_src + quote
        return match.group(0)

    pattern = re.compile(r'(<img[^>]*\ssrc=)(["\'])(?:[^"\']*)\2', re.IGNORECASE | re.DOTALL)
    return pattern.sub(replace_src, html_content)


def file_to_data_uri(file_path):
    mime_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
    with open(file_path, 'rb') as f:
        encoded = base64.b64encode(f.read()).decode('ascii')
    return f"data:{mime_type};base64,{encoded}"


def url_to_data_uri(url, timeout=20):
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    content_type = r.headers.get('Content-Type', '').split(';')[0].strip()
    mime_type = content_type or mimetypes.guess_type(url)[0] or 'application/octet-stream'
    encoded = base64.b64encode(r.content).decode('ascii')
    return f"data:{mime_type};base64,{encoded}"


def extract_images_and_renders(pdf_path, output_dir, render_dpi=DEFAULT_RENDER_DPI, max_ocr_height=MAX_OCR_HEIGHT):
    """
    Extrae renders + imágenes embebidas con PyMuPDF y genera metadata estilo extractor.
    """
    started_at = time.time()
    doc = fitz.open(pdf_path)
    ordered_files = []
    renders = []
    images = []
    scale = render_dpi / 72.0
    matrix = fitz.Matrix(scale, scale)

    for page_index, page in enumerate(doc, start=1):
        # Render principal de página
        render_filename = f"page{page_index:03d}_render.png"
        render_path = os.path.join(output_dir, render_filename)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pix.save(render_path)
        ordered_files.append(render_path)

        # Render para OCR (redimensionado si excede altura máxima)
        ocr_filename = f"page{page_index:03d}_render_ocr.png"
        ocr_path = os.path.join(output_dir, ocr_filename)
        with Image.open(render_path) as render_img:
            ocr_img = render_img
            resized = False
            if render_img.height > max_ocr_height:
                ratio = max_ocr_height / float(render_img.height)
                new_width = max(1, int(render_img.width * ratio))
                resample = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
                ocr_img = render_img.resize((new_width, max_ocr_height), resample=resample)
                resized = True
            ocr_img.save(ocr_path, format='PNG')

        render_size = os.path.getsize(render_path)
        ocr_size = os.path.getsize(ocr_path)
        with Image.open(ocr_path) as ocr_img_size:
            ocr_width = ocr_img_size.width
            ocr_height = ocr_img_size.height

        renders.append({
            'filename': render_filename,
            'page_number': page_index,
            'width': pix.width,
            'height': pix.height,
            'format': 'png',
            'size_bytes': render_size,
            'url': None,
            'ocr_filename': ocr_filename,
            'ocr_width': ocr_width,
            'ocr_height': ocr_height,
            'ocr_size_bytes': ocr_size,
            'ocr_url': None,
            'ocr_resized': resized
        })

        # Imágenes embebidas del PDF con bbox aproximada por página
        page_height = page.rect.height
        for image_index, img in enumerate(page.get_images(full=True), start=1):
            xref = img[0]
            extracted = doc.extract_image(xref)
            if not extracted:
                continue
            ext = extracted.get('ext', 'bin').lower()
            image_filename = f"page{page_index:03d}_img{image_index:02d}_xref{xref}.{ext}"
            image_path = os.path.join(output_dir, image_filename)
            with open(image_path, 'wb') as image_file:
                image_file.write(extracted['image'])
            ordered_files.append(image_path)

            rects = page.get_image_rects(xref)
            rect = rects[0] if rects else fitz.Rect(0, 0, 0, 0)
            # Conversión a coordenadas PDF (origen abajo-izquierda)
            pdf_x0 = float(rect.x0)
            pdf_x1 = float(rect.x1)
            pdf_y0 = float(page_height - rect.y1)
            pdf_y1 = float(page_height - rect.y0)

            images.append({
                'filename': image_filename,
                'page_number': page_index,
                'width': extracted.get('width'),
                'height': extracted.get('height'),
                'format': ext,
                'size_bytes': os.path.getsize(image_path),
                'color_space': str(img[5]) if len(img) > 5 else 'unknown',
                'x0': pdf_x0,
                'y0': pdf_y0,
                'x1': pdf_x1,
                'y1': pdf_y1,
                'bbox_width': float(max(0, pdf_x1 - pdf_x0)),
                'bbox_height': float(max(0, pdf_y1 - pdf_y0)),
                'url': None
            })

    metadata = {
        'pdf_file': os.path.basename(pdf_path),
        'total_pages': len(doc),
        'total_renders': len(renders),
        'total_images': len(images),
        'extraction_time': round(time.time() - started_at, 4),
        'render_dpi': render_dpi,
        'note': 'Coordinates are in PDF points (72 points = 1 inch). Origin (0,0) is at bottom-left of page.',
        'render_png_url': None,
        'render_ocr_png_url': None,
        'renders': renders,
        'images': images,
        'session_id': None,
        'base_url': None,
        'expires_at': None
    }
    doc.close()
    return metadata, ordered_files

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_extractor_image_urls(extractor_base_url, session_id, timeout=10, only_first_page=False):
    """
    Obtiene la lista de URLs de imágenes de una sesión del pdf-image-extractor.
    Referencia: servicio pdf-image-extractor en ../pdf-image-extractor
    """
    base = extractor_base_url.rstrip('/')
    url = f"{base}/api/v1/sessions/{session_id}/metadata"
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise ValueError(f"No se pudo obtener metadata del extractor: {e}") from e
    images_base = f"{base}/api/v1/images/{session_id}"
    # Orden: primero renders de página, luego imágenes embebidas (mismo orden que en metadata)
    urls = []
    for item in data.get("renders", []):
        if only_first_page and item.get("page_number") not in (1, "1"):
            continue
        item_url = item.get("url")
        fn = item.get("filename")
        if item_url:
            urls.append(item_url)
        elif fn:
            urls.append(f"{images_base}/{fn}")
    for item in data.get("images", []):
        if only_first_page and item.get("page_number") not in (1, "1"):
            continue
        item_url = item.get("url")
        fn = item.get("filename")
        if item_url:
            urls.append(item_url)
        elif fn:
            urls.append(f"{images_base}/{fn}")
    return urls


def rewrite_html_images_to_extractor(html_content, image_urls):
    """
    Reemplaza en el HTML las referencias a imágenes por las URLs del extractor,
    por orden de aparición (primera <img> -> image_urls[0], etc.).
    """
    return rewrite_html_img_sources(html_content, image_urls)


def rewrite_html_images_to_embedded_data_uris(html_content, image_urls):
    """
    Descarga imágenes por URL y reemplaza <img src> por data URI en orden.
    """
    if not image_urls:
        return html_content
    data_uris = []
    for image_url in image_urls:
        try:
            data_uris.append(url_to_data_uri(image_url))
        except Exception:
            continue
    return rewrite_html_img_sources(html_content, data_uris)


def rewrite_html_relative_assets_to_base(html_content, assets_base_url):
    """
    Convierte rutas relativas en src y href a URLs absolutas con assets_base_url,
    para que al montar/abrir el HTML las imágenes y CSS se carguen desde este servicio.
    """
    if not assets_base_url:
        return html_content
    base = assets_base_url.rstrip('/')

    def replace_relative(match):
        prefix, quote, path = match.group(1), match.group(2), match.group(3).strip()
        if path.startswith(('http://', 'https://', '//', 'data:')):
            return match.group(0)
        if path.startswith('/'):
            path = path.lstrip('/')
        new_url = f"{base}/{path}" if path else base
        return prefix + quote + new_url + quote

    # src="ruta" o src='ruta'
    html_content = re.sub(
        r'(<img[^>]*\ssrc=)(["\'])([^"\']*)\2',
        replace_relative,
        html_content,
        flags=re.IGNORECASE
    )
    # href="ruta" en link (CSS, etc.)
    html_content = re.sub(
        r'(<link[^>]*\shref=)(["\'])([^"\']*)\2',
        replace_relative,
        html_content,
        flags=re.IGNORECASE
    )
    return html_content


def rewrite_html_relative_assets_to_public_urls(html_content, public_base_url, process_id):
    """
    Convierte rutas relativas de src/href a URLs públicas sobre /convert?action=asset.
    """
    if not public_base_url or not process_id:
        return html_content

    def replace_relative(match):
        prefix, quote, path = match.group(1), match.group(2), match.group(3).strip()
        if path.startswith(('http://', 'https://', '//', 'data:')):
            return match.group(0)
        if path.startswith('/'):
            path = path.lstrip('/')
        new_url = build_public_asset_url(public_base_url, process_id, path)
        return prefix + quote + new_url + quote

    html_content = re.sub(
        r'(<img[^>]*\ssrc=)(["\'])([^"\']*)\2',
        replace_relative,
        html_content,
        flags=re.IGNORECASE
    )
    html_content = re.sub(
        r'(<link[^>]*\shref=)(["\'])([^"\']*)\2',
        replace_relative,
        html_content,
        flags=re.IGNORECASE
    )
    return html_content


def improve_html_rendering(html_content):
    """
    Mejora el rendering del HTML sin cambiar colores
    Solo agrega CSS para mejor visualización
    """
    # CSS mejoras para mejor renderizado (SIN cambiar colores del PDF)
    css_improvements = """
<style>
/* === MEJORAS DE RENDERIZADO === */
body {
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
}

/* === MEJORAS DE CONTRASTE Y TIPOGRAFÍA === */
p {
    font-feature-settings: "kern" 1;
}

/* === RESPONSIVE === */
@media (max-width: 768px) {
    body {
        zoom: 0.8;
    }
}
</style>
"""

    # Agregar CSS antes de </head>
    if '</head>' in html_content:
        html_content = html_content.replace('</head>', css_improvements + '\n</head>')

    return html_content

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'pdf-to-html'}), 200

@app.route('/convert', methods=['POST', 'GET'])
def convert_pdf_to_html():
    """
    Convierte un PDF a HTML usando pdftohtml
    Acepta: multipart/form-data con un archivo PDF
    Retorna: JSON con el HTML generado o archivo HTML
    """
    if request.method == 'GET':
        action = request.args.get('action', '').strip().lower()
        process_id = request.args.get('process_id', '').strip()
        if action == 'download' and process_id:
            return download_html(process_id)
        if action == 'view' and process_id:
            return view_html(process_id)
        if action == 'asset' and process_id:
            asset_path = request.args.get('asset_path', '').strip()
            if not asset_path:
                return jsonify({'error': 'asset_path es requerido para action=asset'}), 400
            return serve_asset(process_id, asset_path)
        return jsonify({
            'error': "GET /convert requiere action=download|view|asset y process_id"
        }), 400

    pdf_path = None
    temp_paths = []
    try:
        cleanup_expired_outputs()

        # Verificar que se envió un archivo
        if 'file' not in request.files:
            return jsonify({'error': 'No se envió ningún archivo'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'Nombre de archivo vacío'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'Solo se permiten archivos PDF'}), 400

        # Generar ID único para este proceso
        process_id = str(uuid.uuid4())

        # Guardar archivo PDF
        filename = secure_filename(file.filename)
        pdf_path = os.path.join(UPLOAD_FOLDER, f"{process_id}_{filename}")
        file.save(pdf_path)
        temp_paths.append(pdf_path)

        # Crear directorio de salida para este proceso
        output_dir = os.path.join(OUTPUT_FOLDER, process_id)
        os.makedirs(output_dir, exist_ok=True)

        extractor_base_url = request.form.get('extractor_base_url', '').strip()
        extractor_session_id = request.form.get('extractor_session_id', '').strip()
        requested_strategy = request.form.get('image_strategy', '').strip().lower()
        if requested_strategy:
            image_strategy = requested_strategy
        elif extractor_base_url and extractor_session_id:
            image_strategy = 'extractor_urls'
        else:
            image_strategy = 'assets_urls'
        public_base_url = resolve_public_base_url(request)
        try:
            render_dpi = int(request.form.get('render_dpi', str(DEFAULT_RENDER_DPI)))
            if render_dpi <= 0:
                raise ValueError('render_dpi debe ser mayor a 0')
        except ValueError:
            return jsonify({'error': 'render_dpi debe ser un entero positivo'}), 400

        # Procesar siempre solo la primera página
        try:
            page_num = 1
            extracted_pdf = os.path.join(UPLOAD_FOLDER, f"{process_id}_page{page_num}.pdf")
            extract_cmd = [
                'pdfseparate',
                '-f', str(page_num),
                '-l', str(page_num),
                pdf_path,
                extracted_pdf.replace('.pdf', '-%d.pdf')
            ]
            extract_result = subprocess.run(
                extract_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            if extract_result.returncode == 0:
                extracted_file = extracted_pdf.replace('.pdf', f'-{page_num}.pdf')
                if os.path.exists(extracted_file):
                    os.rename(extracted_file, extracted_pdf)
                    pdf_path = extracted_pdf
                    temp_paths.append(extracted_pdf)
        except Exception:
            # Si falla la extracción de la primera página, continuar con el PDF original
            pass

        # Nombre del archivo HTML de salida
        html_filename = f"{Path(filename).stem}.html"
        html_path = os.path.join(output_dir, html_filename)

        # Usar pdftohtml con parámetros optimizados
        cmd = [
            'pdftohtml',
            '-c',              # Complex output (mantiene colores y layout)
            '-s',              # Single HTML page
            '-noframes',       # No frames
            '-fontfullname',   # Nombres completos de fuentes
            '-enc', 'UTF-8',   # Codificación UTF-8
            '-zoom', '1.3',    # Zoom óptimo para visualización
            pdf_path,
            html_path
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            return jsonify({
                'error': 'Error al convertir PDF',
                'details': result.stderr
            }), 500

        # Verificar que se generó el HTML

        if not os.path.exists(html_path):
            return jsonify({'error': 'No se generó el archivo HTML'}), 500

        # Leer el HTML generado
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # Mejorar rendering del HTML (sin cambiar colores originales)
        html_content = improve_html_rendering(html_content)

        extraction_metadata = None
        embedded_images = 0

        if image_strategy == 'pymupdf_embed':
            extraction_metadata, ordered_files = extract_images_and_renders(
                pdf_path=pdf_path,
                output_dir=output_dir,
                render_dpi=render_dpi,
                max_ocr_height=MAX_OCR_HEIGHT
            )
            metadata_path = os.path.join(output_dir, 'metadata.json')
            with open(metadata_path, 'w', encoding='utf-8') as metadata_file:
                json.dump(extraction_metadata, metadata_file, ensure_ascii=False, indent=2)

            data_uris = []
            for image_file in ordered_files:
                try:
                    data_uris.append(file_to_data_uri(image_file))
                except Exception:
                    continue

            embedded_images = len(data_uris)
            html_content = rewrite_html_img_sources(html_content, data_uris)

        elif image_strategy == 'extractor_embed':
            if not extractor_base_url or not extractor_session_id:
                return jsonify({
                    'error': "Para 'extractor_embed' debes enviar extractor_base_url y extractor_session_id"
                }), 400
            try:
                image_urls = get_extractor_image_urls(
                    extractor_base_url,
                    extractor_session_id,
                    only_first_page=True
                )
                embedded_images = len(image_urls)
                html_content = rewrite_html_images_to_embedded_data_uris(html_content, image_urls)
            except ValueError as e:
                return jsonify({'error': str(e)}), 502
            except requests.RequestException as e:
                return jsonify({'error': f'No se pudieron descargar imágenes del extractor: {e}'}), 502

        elif image_strategy == 'extractor_urls':
            if not extractor_base_url or not extractor_session_id:
                return jsonify({
                    'error': "Para 'extractor_urls' debes enviar extractor_base_url y extractor_session_id"
                }), 400
            try:
                image_urls = get_extractor_image_urls(
                    extractor_base_url,
                    extractor_session_id,
                    only_first_page=True
                )
                html_content = rewrite_html_images_to_extractor(html_content, image_urls)
            except ValueError as e:
                return jsonify({'error': str(e)}), 502

        elif image_strategy == 'assets_urls':
            pass
        else:
            return jsonify({
                'error': "image_strategy no soportado. Usa: pymupdf_embed, extractor_embed, extractor_urls o assets_urls"
            }), 400

        # En cualquier estrategia, normalizar rutas relativas (CSS / fuentes / imágenes remanentes)
        html_content = rewrite_html_relative_assets_to_public_urls(
            html_content=html_content,
            public_base_url=public_base_url,
            process_id=process_id
        )

        # Guardar HTML con mejoras
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        process_meta = write_process_meta(
            output_dir=output_dir,
            process_id=process_id,
            html_filename=html_filename,
            public_base_url=public_base_url,
            ttl_seconds=PUBLIC_ASSET_TTL_SECONDS
        )

        # Obtener formato de respuesta deseado
        return_format = request.form.get('format', 'json')

        if return_format == 'file':
            # Devolver el archivo HTML directamente
            return send_file(
                html_path,
                mimetype='text/html',
                as_attachment=True,
                download_name=html_filename
            )
        else:
            # Devolver JSON con el contenido HTML
            # Recopilar archivos adicionales (CSS, fuentes, imágenes generadas por pdftohtml)
            additional_files = []
            for item in os.listdir(output_dir):
                if item != html_filename:
                    additional_files.append(item)

            # URL base para montar HTML + assets (imágenes, CSS, etc.) desde este servicio
            response_payload = {
                'success': True,
                'html': html_content,
                'filename': html_filename,
                'process_id': process_id,
                'additional_files': additional_files,
                'assets_base_url': process_meta.get('assets_base_url'),
                'asset_url_template': process_meta.get('asset_url_template'),
                'image_strategy': image_strategy,
                'embedded_images': embedded_images,
                'processed_page': 1,
                'public_html_url': process_meta.get('public_html_url'),
                'public_download_url': process_meta.get('public_download_url'),
                'expires_at': process_meta.get('expires_at'),
                'message': 'PDF convertido exitosamente'
            }
            if extraction_metadata is not None:
                response_payload['metadata'] = extraction_metadata
                response_payload['metadata_filename'] = 'metadata.json'
            return jsonify(response_payload), 200

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Timeout al convertir el PDF'}), 500
    except Exception as e:
        return jsonify({'error': f'Error interno: {str(e)}'}), 500
    finally:
        # Limpiar archivos temporales
        for temp_path in set([p for p in temp_paths if p]):
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

@app.route('/convert/download/<process_id>', methods=['GET'])
def download_html(process_id):
    """Descarga el HTML completo con todos los recursos"""
    try:
        cleanup_expired_outputs()
        output_dir = os.path.join(OUTPUT_FOLDER, process_id)

        if not os.path.exists(output_dir):
            return jsonify({'error': 'Proceso no encontrado'}), 404

        expired, _ = is_output_expired(output_dir)
        if expired:
            shutil.rmtree(output_dir, ignore_errors=True)
            return jsonify({'error': 'Proceso expirado (TTL 1 hora)'}), 410

        # Buscar el archivo HTML principal
        html_files = [f for f in os.listdir(output_dir) if f.endswith('.html')]

        if not html_files:
            return jsonify({'error': 'HTML no encontrado'}), 404

        html_path = os.path.join(output_dir, html_files[0])

        return send_file(
            html_path,
            mimetype='text/html',
            as_attachment=True,
            download_name=html_files[0]
        )
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500


@app.route('/convert/view/<process_id>', methods=['GET'])
def view_html(process_id):
    """Muestra el HTML públicamente sin forzar descarga"""
    try:
        cleanup_expired_outputs()
        output_dir = os.path.join(OUTPUT_FOLDER, process_id)
        if not os.path.exists(output_dir):
            return jsonify({'error': 'Proceso no encontrado'}), 404

        expired, meta = is_output_expired(output_dir)
        if expired:
            shutil.rmtree(output_dir, ignore_errors=True)
            return jsonify({'error': 'Proceso expirado (TTL 1 hora)'}), 410

        html_filename = (meta or {}).get('html_filename')
        if html_filename:
            html_path = os.path.join(output_dir, html_filename)
            if os.path.isfile(html_path):
                return send_file(html_path, mimetype='text/html', as_attachment=False)

        html_files = [f for f in os.listdir(output_dir) if f.endswith('.html')]
        if not html_files:
            return jsonify({'error': 'HTML no encontrado'}), 404
        html_path = os.path.join(output_dir, html_files[0])
        return send_file(html_path, mimetype='text/html', as_attachment=False)
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500


@app.route('/convert/assets/<process_id>/<path:asset_path>', methods=['GET'])
def serve_asset(process_id, asset_path):
    """
    Sirve un asset (imagen, CSS, fuentes) del proceso.
    Permite montar el HTML y que las rutas relativas del HTML carguen las imágenes desde este servicio.
    """
    try:
        cleanup_expired_outputs()
        output_dir = os.path.join(OUTPUT_FOLDER, process_id)
        if not os.path.exists(output_dir):
            return jsonify({'error': 'Proceso no encontrado'}), 404

        expired, _ = is_output_expired(output_dir)
        if expired:
            shutil.rmtree(output_dir, ignore_errors=True)
            return jsonify({'error': 'Proceso expirado (TTL 1 hora)'}), 410

        output_dir = os.path.abspath(output_dir)
        # Evitar path traversal: el archivo debe estar dentro de output_dir
        full_path = os.path.abspath(os.path.join(output_dir, asset_path))
        if not full_path.startswith(output_dir) or not os.path.isfile(full_path):
            return jsonify({'error': 'Asset no encontrado'}), 404
        response = send_file(full_path, as_attachment=False, download_name=os.path.basename(asset_path))
        response.headers['Cache-Control'] = f'public, max-age={PUBLIC_ASSET_TTL_SECONDS}'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
