from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import subprocess
import uuid
import shutil
import re
import requests
from pathlib import Path

app = Flask(__name__)

# Configuración
UPLOAD_FOLDER = '/tmp/uploads'
OUTPUT_FOLDER = '/tmp/outputs'
ALLOWED_EXTENSIONS = {'pdf'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_extractor_image_urls(extractor_base_url, session_id, timeout=10):
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
        fn = item.get("filename")
        if fn:
            urls.append(f"{images_base}/{fn}")
    for item in data.get("images", []):
        fn = item.get("filename")
        if fn:
            urls.append(f"{images_base}/{fn}")
    return urls


def rewrite_html_images_to_extractor(html_content, image_urls):
    """
    Reemplaza en el HTML las referencias a imágenes por las URLs del extractor,
    por orden de aparición (primera <img> -> image_urls[0], etc.).
    """
    if not image_urls:
        return html_content
    idx = [0]  # mutable para que el callback pueda incrementar

    def replace_src(match):
        if idx[0] < len(image_urls):
            new_src = image_urls[idx[0]]
            idx[0] += 1
            quote = match.group(2)
            return match.group(1) + quote + new_src + quote
        return match.group(0)

    # Reemplazar src="...", src='...' en tags <img
    pattern = re.compile(r'(<img[^>]*\ssrc=)(["\'])(?:[^"\']*)\2', re.IGNORECASE | re.DOTALL)
    return pattern.sub(replace_src, html_content)


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

@app.route('/convert', methods=['POST'])
def convert_pdf_to_html():
    """
    Convierte un PDF a HTML usando pdf2htmlEX
    Acepta: multipart/form-data con un archivo PDF
    Retorna: JSON con el HTML generado o archivo HTML
    """
    try:
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

        # Crear directorio de salida para este proceso
        output_dir = os.path.join(OUTPUT_FOLDER, process_id)
        os.makedirs(output_dir, exist_ok=True)

        # Obtener parámetro de página (opcional)
        page = request.form.get('page', None)

        # Si se especifica una página, extraer solo esa página
        if page:
            try:
                page_num = int(page)
                extracted_pdf = os.path.join(UPLOAD_FOLDER, f"{process_id}_page{page_num}.pdf")

                # Extraer página específica con pdfseparate
                extract_cmd = [
                    'pdfseparate',
                    '-f', str(page_num),  # First page
                    '-l', str(page_num),  # Last page
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
                    # Renombrar el archivo extraído
                    extracted_file = extracted_pdf.replace('.pdf', f'-{page_num}.pdf')
                    if os.path.exists(extracted_file):
                        os.rename(extracted_file, extracted_pdf)
                        pdf_path = extracted_pdf
            except (ValueError, Exception) as e:
                # Si falla la extracción, continuar con el PDF completo
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

        # Opcional: usar imágenes del pdf-image-extractor (servicio en ../pdf-image-extractor)
        extractor_base_url = request.form.get('extractor_base_url', '').strip()
        extractor_session_id = request.form.get('extractor_session_id', '').strip()
        if extractor_base_url and extractor_session_id:
            try:
                image_urls = get_extractor_image_urls(extractor_base_url, extractor_session_id)
                html_content = rewrite_html_images_to_extractor(html_content, image_urls)
            except ValueError as e:
                return jsonify({'error': str(e)}), 502
        else:
            # Sin extractor: reescribir rutas relativas a URLs de este servicio para poder montar HTML
            assets_base = request.host_url.rstrip('/') + f'/convert/assets/{process_id}'
            html_content = rewrite_html_relative_assets_to_base(html_content, assets_base)

        # Guardar HTML con mejoras
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

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
            assets_base_url = request.host_url.rstrip('/') + f'/convert/assets/{process_id}'
            return jsonify({
                'success': True,
                'html': html_content,
                'filename': html_filename,
                'process_id': process_id,
                'additional_files': additional_files,
                'assets_base_url': assets_base_url,
                'message': 'PDF convertido exitosamente'
            }), 200

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Timeout al convertir el PDF'}), 500
    except Exception as e:
        return jsonify({'error': f'Error interno: {str(e)}'}), 500
    finally:
        # Limpiar archivos temporales
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except:
            pass

@app.route('/convert/download/<process_id>', methods=['GET'])
def download_html(process_id):
    """Descarga el HTML completo con todos los recursos"""
    try:
        output_dir = os.path.join(OUTPUT_FOLDER, process_id)

        if not os.path.exists(output_dir):
            return jsonify({'error': 'Proceso no encontrado'}), 404

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


@app.route('/convert/assets/<process_id>/<path:asset_path>', methods=['GET'])
def serve_asset(process_id, asset_path):
    """
    Sirve un asset (imagen, CSS, fuentes) del proceso.
    Permite montar el HTML y que las rutas relativas del HTML carguen las imágenes desde este servicio.
    """
    try:
        output_dir = os.path.join(OUTPUT_FOLDER, process_id)
        if not os.path.exists(output_dir):
            return jsonify({'error': 'Proceso no encontrado'}), 404
        output_dir = os.path.abspath(output_dir)
        # Evitar path traversal: el archivo debe estar dentro de output_dir
        full_path = os.path.abspath(os.path.join(output_dir, asset_path))
        if not full_path.startswith(output_dir) or not os.path.isfile(full_path):
            return jsonify({'error': 'Asset no encontrado'}), 404
        return send_file(full_path, as_attachment=False, download_name=os.path.basename(asset_path))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
