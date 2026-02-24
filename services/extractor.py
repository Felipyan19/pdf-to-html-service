"""
Extracción de contenido de PDFs digitales.

Por cada página extrae:
- Bloques de texto con bounding box (x0, y0, x1, y1) en coordenadas fitz (origen top-left)
- Imágenes embebidas con bounding box, guardadas en output_dir y servidas como URLs públicas
"""
import os
import fitz
from PIL import Image
from utils.storage import build_public_asset_url

_RENDER_MAX_DIM = 4000  # límite seguro para Anthropic vision (máx 8000px)


def extract_pdf_content(
    pdf_path: str,
    output_dir: str,
    public_base_url: str,
    process_id: str
) -> dict:
    """
    Extrae textos e imágenes de todas las páginas del PDF.

    Returns dict con estructura:
    {
        "process_id": str,
        "page_count": int,
        "pages": [
            {
                "page_num": int,
                "page_width": float,
                "page_height": float,
                "texts": [...],
                "images": [...]
            }
        ]
    }
    """
    doc = fitz.open(pdf_path)
    pages = []
    img_counter = [0]

    for page_num, page in enumerate(doc):
        texts = _extract_page_texts(page)
        images = _extract_page_images(
            page, doc, output_dir, public_base_url, process_id, page_num, img_counter
        )
        pages.append({
            'page_num': page_num,
            'page_width': float(page.rect.width),
            'page_height': float(page.rect.height),
            'texts': texts,
            'images': images
        })

    doc.close()
    return {
        'process_id': process_id,
        'page_count': len(pages),
        'pages': pages
    }


def render_page_previews(
    pdf_path: str,
    output_dir: str,
    public_base_url: str,
    process_id: str,
    dpi: int = 150
) -> list:
    """
    Renderiza cada página del PDF como PNG a la resolución indicada y devuelve
    las URLs públicas en el mismo orden que las páginas.

    Returns lista de str (una URL por página).
    """
    doc = fitz.open(pdf_path)
    preview_urls = []
    mat = fitz.Matrix(dpi / 72, dpi / 72)

    for page_num, page in enumerate(doc):
        pix = page.get_pixmap(matrix=mat, alpha=False)
        filepath = os.path.join(output_dir, f"render_p{page_num:02d}.png")

        # Redimensionar si alguna dimensión supera el límite de la API de visión
        if pix.width > _RENDER_MAX_DIM or pix.height > _RENDER_MAX_DIM:
            scale = min(_RENDER_MAX_DIM / pix.width, _RENDER_MAX_DIM / pix.height)
            new_w = max(1, int(pix.width * scale))
            new_h = max(1, int(pix.height * scale))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            img.save(filepath)
        else:
            pix.save(filepath)

        filename = f"render_p{page_num:02d}.png"
        preview_urls.append(build_public_asset_url(public_base_url, process_id, filename))

    doc.close()
    return preview_urls


def _extract_page_texts(page: fitz.Page) -> list:
    """
    Extrae texto de una página agrupando spans de la misma línea en una sola entrada.
    Esto evita fragmentación palabra-a-palabra y reduce el tamaño del JSON.
    Coordenadas: origen top-left, Y crece hacia abajo (sistema nativo fitz).

    Returns lista de:
    {
        "content": str,
        "bbox": {"x0": float, "y0": float, "x1": float, "y1": float},
        "font_size": float,
        "font": str,
        "color_guess": str
    }
    """
    texts = []
    blocks = page.get_text('dict').get('blocks', [])

    for block in blocks:
        if block.get('type') != 0:  # 0 = text block
            continue
        for line in block.get('lines', []):
            spans = line.get('spans', [])
            if not spans:
                continue

            # Concatenar todos los spans de la línea en un único texto
            parts = [s.get('text', '') for s in spans]
            content = ' '.join(p for p in parts if p.strip()).strip()
            if not content:
                continue

            # Bbox que engloba todos los spans de la línea
            all_bboxes = [s.get('bbox', (0, 0, 0, 0)) for s in spans]
            x0 = min(b[0] for b in all_bboxes)
            y0 = min(b[1] for b in all_bboxes)
            x1 = max(b[2] for b in all_bboxes)
            y1 = max(b[3] for b in all_bboxes)

            # Usar atributos del primer span con contenido
            primary = next((s for s in spans if s.get('text', '').strip()), spans[0])
            color_int = primary.get('color', 0)
            color_guess = '#{:02x}{:02x}{:02x}'.format(
                (color_int >> 16) & 0xFF,
                (color_int >> 8) & 0xFF,
                color_int & 0xFF
            )

            texts.append({
                'content': content,
                'bbox': {
                    'x0': round(float(x0), 2),
                    'y0': round(float(y0), 2),
                    'x1': round(float(x1), 2),
                    'y1': round(float(y1), 2)
                },
                'font_size': round(float(primary.get('size', 0)), 2),
                'font': primary.get('font', ''),
                'color_guess': color_guess,
            })

    return texts


def _extract_page_images(
    page: fitz.Page,
    doc: fitz.Document,
    output_dir: str,
    public_base_url: str,
    process_id: str,
    page_num: int,
    img_counter: list
) -> list:
    """
    Extrae imágenes embebidas de una página, las guarda en output_dir y construye URLs públicas.
    Coordenadas: origen top-left (sistema nativo fitz).

    Returns lista de:
    {
        "url": str,
        "filename": str,
        "bbox": {"x0": float, "y0": float, "x1": float, "y1": float},
        "width": int,
        "height": int
    }
    """
    images = []

    for img in page.get_images(full=True):
        xref = img[0]
        extracted = doc.extract_image(xref)
        if not extracted:
            continue

        ext = extracted.get('ext', 'bin').lower()
        img_counter[0] += 1
        filename = f"p{page_num:02d}_img{img_counter[0]:03d}_xref{xref}.{ext}"
        img_path = os.path.join(output_dir, filename)

        with open(img_path, 'wb') as f:
            f.write(extracted['image'])

        # Obtener bbox en coordenadas fitz (top-left origin)
        rects = page.get_image_rects(xref)
        rect = rects[0] if rects else fitz.Rect(0, 0, 0, 0)

        url = build_public_asset_url(public_base_url, process_id, filename)

        images.append({
            'url': url,
            'filename': filename,
            'bbox': {
                'x0': round(float(rect.x0), 2),
                'y0': round(float(rect.y0), 2),
                'x1': round(float(rect.x1), 2),
                'y1': round(float(rect.y1), 2)
            },
            'width': extracted.get('width', 0),
            'height': extracted.get('height', 0)
        })

    return images
