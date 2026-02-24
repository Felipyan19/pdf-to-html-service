"""
Comparación visual pixel-based entre dos imágenes PNG.

Algoritmo:
1. Cargar ambas imágenes (URL o data URI)
2. Redimensionar img_b al tamaño de img_a (imagen de referencia = PDF render)
3. Diff píxel a píxel con PIL ImageChops.difference
4. Score global = 1 − (píxeles_distintos / total_píxeles)   [0=distinto, 1=idéntico]
5. Grid 8×8: reportar cada celda con >1 % de diferencia como región de diff
"""
import base64
import io
import mimetypes
import os
import urllib.parse

import requests
from PIL import Image, ImageChops, ImageFilter

from utils.storage import OUTPUT_FOLDER

# Umbral por canal: variación ≤ THRESHOLD se considera "igual"
_THRESHOLD = 15
# Mínimo porcentaje de píxeles distintos en una celda para reportarla
_CELL_MIN_PCT = 0.01
# Número de filas/columnas del grid de regiones
_GRID = 8


def visual_diff(url_a: str, url_b: str, public_base_url: str = '') -> dict:
    """
    Compara dos imágenes por URL (o data URI).

    Returns:
        {
          "score": float,           # 0.0 = completamente distinto, 1.0 = idéntico
          "width":  int,            # ancho de referencia (img_a)
          "height": int,            # alto de referencia (img_a)
          "diffs": [
            { "row": int, "col": int, "diff_pct": float },  # celdas con diferencias
            ...
          ]
        }
    """
    img_a = _load_image(url_a, public_base_url).convert('RGB')
    img_b = _load_image(url_b, public_base_url).convert('RGB')

    # Normalizar ambas imágenes al ancho menor para evitar artefactos de escala.
    # El PDF render (a) puede ser ~1240px; el HTML preview (b) ~600px.
    # Reducir ambas al ancho menor preserva la calidad del diff.
    w_a, h_a = img_a.size
    w_b, h_b = img_b.size
    target_w = min(w_a, w_b)
    if w_a != target_w:
        img_a = img_a.resize((target_w, round(h_a * target_w / w_a)), Image.LANCZOS)
    if w_b != target_w:
        img_b = img_b.resize((target_w, round(h_b * target_w / w_b)), Image.LANCZOS)

    # Igualar alto (recortar o añadir padding blanco) para que el diff sea válido
    h_a2, h_b2 = img_a.size[1], img_b.size[1]
    target_h = max(h_a2, h_b2)
    if h_a2 < target_h:
        canvas = Image.new('RGB', (target_w, target_h), (255, 255, 255))
        canvas.paste(img_a, (0, 0))
        img_a = canvas
    if h_b2 < target_h:
        canvas = Image.new('RGB', (target_w, target_h), (255, 255, 255))
        canvas.paste(img_b, (0, 0))
        img_b = canvas

    w, h = target_w, target_h

    # Suavizado leve para reducir ruido de compresión JPEG/PNG
    diff = ImageChops.difference(img_a, img_b)
    diff_blur = diff.filter(ImageFilter.GaussianBlur(radius=1))

    # Score global
    total_px = w * h
    diff_count = sum(
        1 for r, g, b in diff_blur.getdata()
        if max(r, g, b) > _THRESHOLD
    )
    score = round(1.0 - diff_count / total_px, 4) if total_px else 1.0

    # Grid 8×8 de regiones
    cell_w = max(1, w // _GRID)
    cell_h = max(1, h // _GRID)
    diffs = []

    diff_rgb = diff_blur  # ya es RGB
    for row in range(_GRID):
        for col in range(_GRID):
            box = (
                col * cell_w,
                row * cell_h,
                min((col + 1) * cell_w, w),
                min((row + 1) * cell_h, h),
            )
            cell = diff_rgb.crop(box)
            cell_data = list(cell.getdata())
            cell_total = len(cell_data)
            if cell_total == 0:
                continue
            cell_diff = sum(1 for r, g, b in cell_data if max(r, g, b) > _THRESHOLD)
            pct = round(cell_diff / cell_total, 4)
            if pct > _CELL_MIN_PCT:
                diffs.append({'row': row, 'col': col, 'diff_pct': pct})

    return {
        'score':  score,
        'width':  w,
        'height': h,
        'diffs':  diffs,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_image(source: str, public_base_url: str = '') -> Image.Image:
    """Carga imagen desde URL pública, URL de asset interno o data URI."""
    if source.startswith('data:'):
        _, b64 = source.split(',', 1)
        data = base64.b64decode(b64)
        return Image.open(io.BytesIO(data))

    # Resolver URLs de assets propios directamente desde disco (evita HTTP interno)
    base = public_base_url.rstrip('/')
    if (base and source.startswith(base + '/assets')) or '/assets?' in source:
        parsed = urllib.parse.urlparse(source)
        qs = urllib.parse.parse_qs(parsed.query)
        pid = (qs.get('process_id') or [''])[0]
        apath = (qs.get('asset_path') or [''])[0]
        if pid and apath:
            file_path = os.path.join(OUTPUT_FOLDER, pid, os.path.basename(apath))
            if os.path.isfile(file_path):
                return Image.open(file_path)

    resp = requests.get(source, timeout=30)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content))
