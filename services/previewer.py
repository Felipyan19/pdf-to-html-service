"""
Renderiza HTML a PNG para preview/comparación visual.

Flujo: HTML → weasyprint → PDF bytes en memoria → PyMuPDF → PNG
Sin dependencias de browser headless; usa las libs ya presentes (fitz) más weasyprint.

URL fetcher personalizado: las URLs /assets?process_id=...&asset_path=... se resuelven
directamente desde disco (sin HTTP), evitando problemas de acceso interno al contenedor.
"""
import io
import mimetypes
import os
import urllib.parse

import fitz
import weasyprint

from utils.storage import OUTPUT_FOLDER, build_public_asset_url


def _make_asset_fetcher(public_base_url: str):
    """
    Devuelve un url_fetcher para weasyprint que resuelve los assets del propio
    servicio leyendo archivos del disco en lugar de hacer HTTP.
    """
    base = public_base_url.rstrip('/')

    def fetcher(url: str):
        # Si la URL corresponde a nuestro endpoint /assets, leer del disco
        if url.startswith(base + '/assets') or '/assets?' in url:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            pid = (qs.get('process_id') or [''])[0]
            apath = (qs.get('asset_path') or [''])[0]
            if pid and apath:
                file_path = os.path.join(OUTPUT_FOLDER, pid, os.path.basename(apath))
                if os.path.isfile(file_path):
                    mime = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
                    with open(file_path, 'rb') as f:
                        # WeasyPrint expects either "string" (bytes) or "file_obj".
                        return {
                            'string': f.read(),
                            'mime_type': mime,
                            'redirected_url': url,
                        }
        # Fallback: descarga normal de weasyprint
        return weasyprint.default_url_fetcher(url)

    return fetcher


def html_to_png(
    html_content: str,
    output_dir: str,
    public_base_url: str,
    process_id: str,
    viewport_width: int = 600,
    dpi: int = 150,
) -> str:
    """
    Convierte html_content a PNG y lo guarda en output_dir.

    Devuelve la URL pública del PNG generado.
    Las URLs de assets del propio servicio se leen directamente del disco.
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = 'preview.png'
    png_path = os.path.join(output_dir, filename)

    css = weasyprint.CSS(string=(
        f'@page {{ size: {viewport_width}px auto; margin: 0; }}'
        'body { margin: 0; padding: 0; }'
    ))
    fetcher = _make_asset_fetcher(public_base_url)

    # HTML → PDF en memoria
    pdf_bytes = weasyprint.HTML(
        string=html_content, url_fetcher=fetcher
    ).write_pdf(stylesheets=[css])

    # PDF en memoria → primera página → PNG
    doc = fitz.open('pdf', pdf_bytes)
    if len(doc) == 0:
        doc.close()
        raise ValueError('weasyprint produjo un PDF vacío')

    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = doc[0].get_pixmap(matrix=mat, alpha=False)
    pix.save(png_path)
    doc.close()

    return build_public_asset_url(public_base_url, process_id, filename)
