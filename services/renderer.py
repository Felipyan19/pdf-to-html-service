"""
Convierte render_ready_modules en HTML de email compatible con clientes de correo.

Módulos con ID del design system (campo _module_id):
  PH01  — Preheader oculto + "Ver en navegador"
  BP01  — Brand panel: logo + enlaces de cuenta
  HB03  — Hero de página completa con imagen de fondo (soporte VML para Outlook)
  TM01  — Cabecera de sección con fondo de color sólido
  HB08  — Dos columnas: imagen + bloque de texto (50/50)
  TM04  — Bloque de oferta / texto destacado
  SP01  — Separador / espacio vertical
  FM03  — Pie de página principal
  FM04  — Texto legal pequeño

Tipos genéricos (fallback cuando no hay _module_id):
  image | text | heading | divider | spacer | row | raw_html
"""

_EMAIL_WIDTH = 600  # ancho estándar del email en px


# ---------------------------------------------------------------------------
# Punto de entrada público
# ---------------------------------------------------------------------------

def render_modules_to_html(modules: list, page_width_px: int = _EMAIL_WIDTH) -> str:
    """Convierte una lista de módulos a un documento HTML de email completo."""
    w = int(page_width_px) if page_width_px else _EMAIL_WIDTH
    rows = '\n'.join(_render_module(m, w) for m in modules)
    return _email_shell(rows, w)


# ---------------------------------------------------------------------------
# Shell completo del email (boilerplate de compatibilidad con clientes)
# ---------------------------------------------------------------------------

def _email_shell(body: str, width: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="es" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="UTF-8">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="format-detection" content="telephone=no,date=no,address=no,email=no">
<!--[if gte mso 9]><xml>
<o:OfficeDocumentSettings>
  <o:AllowPNG/>
  <o:PixelsPerInch>96</o:PixelsPerInch>
</o:OfficeDocumentSettings>
</xml><![endif]-->
<style>
/* Reset */
body,table,td,a{{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;}}
table,td{{mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;}}
img{{-ms-interpolation-mode:bicubic;border:0;height:auto;line-height:100%;outline:none;text-decoration:none;}}
body{{height:100%!important;margin:0!important;padding:0!important;width:100%!important;background-color:#f4f4f4;}}
a{{color:inherit;}}
a[x-apple-data-detectors]{{color:inherit!important;text-decoration:none!important;font-size:inherit!important;font-family:inherit!important;font-weight:inherit!important;line-height:inherit!important;}}
/* Mobile */
@media screen and (max-width:600px){{
  .email-container{{width:100%!important;max-width:100%!important;}}
  .fluid{{max-width:100%!important;height:auto!important;}}
  .col-half{{display:block!important;width:100%!important;max-width:100%!important;}}
  .hide-mobile{{display:none!important;max-height:0!important;overflow:hidden!important;mso-hide:all;}}
  .center-mobile{{text-align:center!important;}}
  .pad-mobile{{padding:12px!important;}}
  .hero-text{{font-size:22px!important;}}
}}
</style>
</head>
<body style="margin:0;padding:0;background-color:#f4f4f4;">
<!--[if gte mso 9]>
<v:background xmlns:v="urn:schemas-microsoft-com:vml" fill="t">
  <v:fill type="tile" color="#f4f4f4"/>
</v:background>
<![endif]-->
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" bgcolor="#f4f4f4">
<tr><td align="center" style="padding:20px 10px;">
<!--[if gte mso 9]><table role="presentation" cellspacing="0" cellpadding="0" border="0" width="{width}"><tr><td><![endif]-->
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="{width}"
  class="email-container"
  style="margin:auto;max-width:{width}px;background-color:#ffffff;">
{body}
</table>
<!--[if gte mso 9]></td></tr></table><![endif]-->
</td></tr>
</table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Dispatcher principal
# ---------------------------------------------------------------------------

def _render_module(module: dict, width: int) -> str:
    module_id = str(module.get('_module_id') or '').upper()
    dispatch_by_id = {
        'PH01': _render_ph01,
        'BP01': _render_bp01,
        'HB03': _render_hb03,
        'TM01': _render_tm01,
        'HB08': _render_hb08,
        'TM04': _render_tm04,
        'SP01': _render_sp01,
        'FM03': _render_fm03,
        'FM04': _render_fm04,
    }
    if module_id in dispatch_by_id:
        return dispatch_by_id[module_id](module, width)

    # Fallback: dispatch por tipo genérico
    t = str(module.get('type', 'raw_html')).lower()
    dispatch_by_type = {
        'image':     _render_image,
        'text':      _render_text,
        'paragraph': _render_text,
        'heading':   _render_heading,
        'divider':   _render_divider,
        'spacer':    _render_spacer,
        'row':       _render_row,
        'raw_html':  _render_raw,
    }
    fn = dispatch_by_type.get(t, _render_raw)
    return fn(module, width)


# ---------------------------------------------------------------------------
# Módulos del design system (PH01 … FM04)
# ---------------------------------------------------------------------------

def _render_ph01(m: dict, width: int) -> str:
    """Preheader oculto + enlace 'Ver en navegador'."""
    text = m.get('content') or m.get('text') or ''
    link = m.get('link') or '#'
    return (
        f'<tr><td style="display:none;max-height:0;overflow:hidden;mso-hide:all;">'
        f'{text}'
        f'</td></tr>\n'
        f'<tr><td align="center" bgcolor="#f0f0f0"'
        f' style="padding:8px;font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#666666;">'
        f'¿Problemas para ver este email? '
        f'<a href="{link}" style="color:#0066cc;text-decoration:underline;">Ver en navegador</a>'
        f'</td></tr>'
    )


def _render_bp01(m: dict, width: int) -> str:
    """Brand panel: logo centrado + enlace opcional (ej. "Iniciar sesión")."""
    logo_src  = m.get('src') or m.get('logo_src') or m.get('image_url') or ''
    logo_alt  = m.get('alt') or m.get('logo_alt') or ''
    logo_w    = int(m.get('width') or 180)
    logo_h    = m.get('height') or ''
    link      = m.get('link') or m.get('cta_link') or '#'
    cta_label = m.get('cta_label') or m.get('button_text') or ''
    bg        = m.get('background_color') or '#006FCF'
    text_col  = m.get('color') or '#ffffff'

    h_attr = f' height="{int(logo_h)}"' if logo_h else ''
    logo_html = (
        f'<img src="{logo_src}" alt="{logo_alt}" width="{logo_w}"{h_attr}'
        f' style="display:block;height:auto;border:0;">'
    ) if logo_src else ''

    cta_html = ''
    if cta_label:
        cta_html = (
            f'<tr><td align="center" style="padding:0 0 16px;">'
            f'<a href="{link}" target="_blank"'
            f' style="display:inline-block;padding:10px 24px;background-color:{text_col};'
            f'color:{bg};font-family:Arial,Helvetica,sans-serif;font-size:13px;'
            f'font-weight:bold;text-decoration:none;border-radius:3px;">'
            f'{cta_label}</a></td></tr>'
        )

    return (
        f'<tr><td align="center" bgcolor="{bg}" style="padding:16px;">'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">'
        f'<tr><td align="center" style="padding-bottom:12px;">{logo_html}</td></tr>'
        f'{cta_html}'
        f'</table>'
        f'</td></tr>'
    )


def _render_hb03(m: dict, width: int) -> str:
    """Hero de página completa con imagen de fondo y texto superpuesto.

    Usa VML para que Outlook muestre la imagen de fondo.
    Si no hay imagen de fondo, renderiza una imagen normal full-width.
    """
    bg_src    = m.get('src') or m.get('background_src') or m.get('image_url') or m.get('url') or ''
    alt       = m.get('alt') or ''
    img_h     = int(m.get('height') or 320)
    bg_color  = m.get('background_color') or '#004b87'
    title     = m.get('title') or m.get('content') or ''
    subtitle  = m.get('subtitle') or ''
    text_col  = m.get('color') or '#ffffff'
    cta_label = m.get('cta_label') or m.get('button_text') or ''
    cta_link  = m.get('link') or m.get('cta_link') or '#'

    title_html    = (
        f'<p class="hero-text" style="margin:0 0 8px;font-family:Arial,Helvetica,sans-serif;'
        f'font-size:28px;font-weight:bold;color:{text_col};line-height:1.2;">{title}</p>'
    ) if title else ''
    subtitle_html = (
        f'<p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:16px;'
        f'color:{text_col};line-height:1.4;">{subtitle}</p>'
    ) if subtitle else ''
    cta_html = (
        f'<p style="margin:16px 0 0;"><a href="{cta_link}" target="_blank"'
        f' style="display:inline-block;padding:12px 28px;background-color:#ffffff;'
        f'color:{bg_color};font-family:Arial,Helvetica,sans-serif;font-size:14px;'
        f'font-weight:bold;text-decoration:none;border-radius:3px;">{cta_label}</a></p>'
    ) if cta_label else ''

    inner_text = title_html + subtitle_html + cta_html

    if not bg_src:
        # Sin imagen: fondo sólido con texto
        return (
            f'<tr><td align="center" bgcolor="{bg_color}"'
            f' style="padding:40px 32px;text-align:center;">'
            f'{inner_text}'
            f'</td></tr>'
        )

    # Con imagen de fondo: VML para Outlook + CSS para el resto
    overlay_style = (
        f'background-image:url(\'{bg_src}\');background-size:cover;'
        f'background-position:center center;background-repeat:no-repeat;'
    ) if inner_text else ''

    return f"""<tr><td>
<!--[if gte mso 9]>
<v:rect xmlns:v="urn:schemas-microsoft-com:vml" fill="true" stroke="false"
  style="width:{width}pt;height:{img_h}pt;">
  <v:fill type="frame" src="{bg_src}" color="{bg_color}" size="1,1" aspect="atleast"/>
  <v:textbox inset="0,0,0,0">
<![endif]-->
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
<tr><td align="center" valign="middle" height="{img_h}"
  style="{overlay_style}padding:40px 32px;text-align:center;background-color:{bg_color};">
{inner_text if inner_text else f'<img src="{bg_src}" alt="{alt}" width="{width}" style="display:block;width:100%;height:auto;max-width:{width}px;">'}
</td></tr>
</table>
<!--[if gte mso 9]>
  </v:textbox>
</v:rect>
<![endif]-->
</td></tr>"""


def _render_tm01(m: dict, width: int) -> str:
    """Cabecera de sección con fondo de color."""
    content   = m.get('content') or m.get('title') or m.get('text') or ''
    bg        = m.get('background_color') or '#006FCF'
    text_col  = m.get('color') or '#ffffff'
    font_size = int(m.get('font_size') or 18)
    align     = m.get('align') or 'center'
    padding   = m.get('padding') or '14px 20px'
    subtitle  = m.get('subtitle') or ''

    sub_html = (
        f'<p style="margin:6px 0 0;font-family:Arial,Helvetica,sans-serif;'
        f'font-size:13px;color:{text_col};line-height:1.4;">{subtitle}</p>'
    ) if subtitle else ''

    return (
        f'<tr><td align="{align}" bgcolor="{bg}"'
        f' style="padding:{padding};">'
        f'<p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:{font_size}px;'
        f'font-weight:bold;color:{text_col};line-height:1.3;">{content}</p>'
        f'{sub_html}'
        f'</td></tr>'
    )


def _render_hb08(m: dict, width: int) -> str:
    """Dos columnas: imagen a la izquierda + bloque de texto a la derecha (50/50)."""
    # Columna imagen
    img_src   = m.get('src') or m.get('image_url') or m.get('image_src') or ''
    img_alt   = m.get('alt') or ''
    img_link  = m.get('image_link') or m.get('link') or ''
    img_w     = int(m.get('img_width') or width // 2)

    # Columna texto
    title     = m.get('title') or m.get('heading') or ''
    body_text = m.get('content') or m.get('text') or m.get('body') or ''
    cta_label = m.get('cta_label') or m.get('button_text') or ''
    cta_link  = m.get('cta_link') or m.get('link') or '#'
    bg        = m.get('background_color') or '#ffffff'
    text_col  = m.get('color') or '#333333'
    accent    = m.get('accent_color') or '#006FCF'

    # Revisar si las columnas vienen explícitas en el módulo
    columns = m.get('columns')
    if isinstance(columns, list) and len(columns) == 2:
        return _render_row(m, width)

    col_w = width // 2

    img_tag = (
        f'<img src="{img_src}" alt="{img_alt}" width="{col_w}"'
        f' class="fluid"'
        f' style="display:block;width:100%;height:auto;max-width:{col_w}px;border:0;">'
    ) if img_src else ''
    if img_tag and img_link:
        img_tag = f'<a href="{img_link}" target="_blank" style="display:block;">{img_tag}</a>'

    title_html = (
        f'<p style="margin:0 0 8px;font-family:Arial,Helvetica,sans-serif;font-size:16px;'
        f'font-weight:bold;color:{text_col};line-height:1.3;">{title}</p>'
    ) if title else ''
    body_html = (
        f'<p style="margin:0 0 12px;font-family:Arial,Helvetica,sans-serif;font-size:14px;'
        f'color:{text_col};line-height:1.5;">{body_text}</p>'
    ) if body_text else ''
    cta_html = (
        f'<p style="margin:0;"><a href="{cta_link}" target="_blank"'
        f' style="display:inline-block;padding:10px 20px;background-color:{accent};'
        f'color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-size:13px;'
        f'font-weight:bold;text-decoration:none;border-radius:3px;">{cta_label}</a></p>'
    ) if cta_label else ''

    return f"""<tr><td bgcolor="{bg}" style="padding:0;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
<tr>
<td class="col-half" width="{col_w}" valign="top" style="padding:0;">
{img_tag}
</td>
<td class="col-half" width="{col_w}" valign="middle"
  style="padding:20px;font-family:Arial,Helvetica,sans-serif;">
{title_html}{body_html}{cta_html}
</td>
</tr>
</table>
</td></tr>"""


def _render_tm04(m: dict, width: int) -> str:
    """Bloque de oferta/texto destacado: badge de descuento + descripción + CTA."""
    badge     = m.get('badge') or m.get('discount') or m.get('offer') or ''
    title     = m.get('title') or m.get('heading') or ''
    content   = m.get('content') or m.get('text') or m.get('description') or ''
    cta_label = m.get('cta_label') or m.get('button_text') or ''
    cta_link  = m.get('cta_link') or m.get('link') or '#'
    bg        = m.get('background_color') or '#ffffff'
    text_col  = m.get('color') or '#333333'
    accent    = m.get('accent_color') or '#006FCF'
    align     = m.get('align') or 'left'
    padding   = m.get('padding') or '20px 24px'

    badge_html = (
        f'<p style="margin:0 0 8px;font-family:Arial,Helvetica,sans-serif;font-size:28px;'
        f'font-weight:bold;color:{accent};line-height:1;">{badge}</p>'
    ) if badge else ''
    title_html = (
        f'<p style="margin:0 0 8px;font-family:Arial,Helvetica,sans-serif;font-size:16px;'
        f'font-weight:bold;color:{text_col};line-height:1.3;">{title}</p>'
    ) if title else ''
    body_html = (
        f'<p style="margin:0 0 12px;font-family:Arial,Helvetica,sans-serif;font-size:14px;'
        f'color:{text_col};line-height:1.5;">{content}</p>'
    ) if content else ''
    cta_html = (
        f'<p style="margin:0;"><a href="{cta_link}" target="_blank"'
        f' style="display:inline-block;padding:10px 20px;background-color:{accent};'
        f'color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-size:13px;'
        f'font-weight:bold;text-decoration:none;border-radius:3px;">{cta_label}</a></p>'
    ) if cta_label else ''

    return (
        f'<tr><td align="{align}" bgcolor="{bg}" style="padding:{padding};">'
        f'{badge_html}{title_html}{body_html}{cta_html}'
        f'</td></tr>'
    )


def _render_sp01(m: dict, width: int) -> str:
    """Separador: espacio vertical + línea opcional."""
    h       = int(m.get('height') or 20)
    divider = m.get('divider') or m.get('show_line') or False
    color   = m.get('color') or '#e0e0e0'
    bg      = m.get('background_color') or '#ffffff'

    line_html = (
        f'<tr><td style="padding:0 20px;">'
        f'<hr style="border:0;border-top:1px solid {color};margin:0;">'
        f'</td></tr>'
    ) if divider else ''

    return (
        f'<tr><td bgcolor="{bg}" style="height:{h}px;line-height:{h}px;font-size:0;">&nbsp;</td></tr>'
        f'{line_html}'
    )


def _render_fm03(m: dict, width: int) -> str:
    """Pie de página principal: logo pequeño + links de gestión."""
    content  = m.get('content') or m.get('text') or ''
    links    = m.get('links') or []   # lista de {"label":..., "href":...}
    logo_src = m.get('src') or m.get('logo_src') or ''
    logo_alt = m.get('alt') or m.get('logo_alt') or ''
    logo_w   = int(m.get('logo_width') or 100)
    bg       = m.get('background_color') or '#f0f0f0'
    text_col = m.get('color') or '#666666'
    align    = m.get('align') or 'center'

    logo_html = (
        f'<p style="margin:0 0 12px;">'
        f'<img src="{logo_src}" alt="{logo_alt}" width="{logo_w}"'
        f' style="display:inline-block;height:auto;border:0;">'
        f'</p>'
    ) if logo_src else ''

    links_html = ''
    if isinstance(links, list) and links:
        items = ' &nbsp;|&nbsp; '.join(
            f'<a href="{lnk.get("href","#")}" style="color:{text_col};text-decoration:underline;">'
            f'{lnk.get("label","")}</a>'
            for lnk in links if isinstance(lnk, dict)
        )
        links_html = (
            f'<p style="margin:8px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;'
            f'color:{text_col};">{items}</p>'
        )

    body_html = (
        f'<p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:13px;'
        f'color:{text_col};line-height:1.5;">{content}</p>'
    ) if content else ''

    return (
        f'<tr><td align="{align}" bgcolor="{bg}" style="padding:20px;">'
        f'{logo_html}{body_html}{links_html}'
        f'</td></tr>'
    )


def _render_fm04(m: dict, width: int) -> str:
    """Texto legal: tipografía pequeña, color gris."""
    content  = m.get('content') or m.get('text') or m.get('legal') or ''
    bg       = m.get('background_color') or '#ffffff'
    text_col = m.get('color') or '#999999'
    align    = m.get('align') or 'center'
    padding  = m.get('padding') or '12px 24px 20px'

    return (
        f'<tr><td align="{align}" bgcolor="{bg}" style="padding:{padding};">'
        f'<p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:10px;'
        f'color:{text_col};line-height:1.5;">{content}</p>'
        f'</td></tr>'
    )


# ---------------------------------------------------------------------------
# Módulos genéricos (fallback)
# ---------------------------------------------------------------------------

def _render_image(m: dict, width: int) -> str:
    src     = m.get('src') or ''
    alt     = m.get('alt') or ''
    img_w   = int(m.get('width') or width)
    img_h   = m.get('height') or ''
    link    = m.get('link') or ''
    padding = m.get('padding') or '0'
    bg      = m.get('background_color') or ''

    h_attr  = f' height="{int(img_h)}"' if img_h else ''
    img_tag = (
        f'<img src="{src}" alt="{alt}" width="{img_w}"{h_attr}'
        f' class="fluid"'
        f' style="display:block;height:auto;max-width:100%;border:0;">'
    )
    if link:
        img_tag = f'<a href="{link}" target="_blank" style="display:block;">{img_tag}</a>'

    td_style = f'padding:{padding};'
    if bg:
        td_style += f'background-color:{bg};'
    if m.get('style'):
        td_style += m['style']

    return f'<tr><td align="center" style="{td_style}">{img_tag}</td></tr>'


def _render_text(m: dict, width: int) -> str:
    content     = str(m.get('content') or '').replace('\n', '<br>')
    color       = m.get('color') or '#333333'
    font_size   = int(m.get('font_size') or 14)
    font_weight = m.get('font_weight') or 'normal'
    align       = m.get('align') or 'left'
    padding     = m.get('padding') or '8px 20px'
    line_height = m.get('line_height') or '1.5'
    bg          = m.get('background_color') or ''

    p_style = (
        f'margin:0;font-family:Arial,Helvetica,sans-serif;'
        f'font-size:{font_size}px;font-weight:{font_weight};'
        f'color:{color};text-align:{align};line-height:{line_height};'
    )
    td_style = f'padding:{padding};'
    if bg:
        td_style += f'background-color:{bg};'
    if m.get('style'):
        td_style += m['style']

    return f'<tr><td style="{td_style}"><p style="{p_style}">{content}</p></td></tr>'


def _render_heading(m: dict, width: int) -> str:
    content   = str(m.get('content') or m.get('title') or '')
    level     = max(1, min(6, int(m.get('level') or 2)))
    defaults  = {1: 28, 2: 22, 3: 18, 4: 16, 5: 14, 6: 12}
    font_size = int(m.get('font_size') or defaults[level])
    color     = m.get('color') or '#111111'
    align     = m.get('align') or 'left'
    padding   = m.get('padding') or '16px 20px 8px'
    bg        = m.get('background_color') or ''

    h_style = (
        f'margin:0;font-family:Arial,Helvetica,sans-serif;font-size:{font_size}px;'
        f'font-weight:bold;color:{color};text-align:{align};line-height:1.2;'
    )
    td_style = f'padding:{padding};'
    if bg:
        td_style += f'background-color:{bg};'
    if m.get('style'):
        td_style += m['style']

    return f'<tr><td style="{td_style}"><h{level} style="{h_style}">{content}</h{level}></td></tr>'


def _render_divider(m: dict, width: int) -> str:
    color     = m.get('color') or '#e0e0e0'
    thickness = int(m.get('thickness') or 1)
    padding   = m.get('padding') or '0 20px'
    return (
        f'<tr><td style="padding:{padding};">'
        f'<hr style="border:0;border-top:{thickness}px solid {color};margin:0;">'
        f'</td></tr>'
    )


def _render_spacer(m: dict, width: int) -> str:
    h = int(m.get('height') or 16)
    return f'<tr><td style="height:{h}px;line-height:{h}px;font-size:0;">&nbsp;</td></tr>'


def _render_raw(m: dict, width: int) -> str:
    html = m.get('html') or m.get('content') or ''
    return f'<tr><td>{html}</td></tr>'


def _render_row(m: dict, width: int) -> str:
    """Fila multi-columna con soporte para stack en móvil."""
    columns = m.get('columns') or []
    if not columns:
        return ''

    n = len(columns)
    bg = m.get('background_color') or ''
    td_rows = ''

    for col in columns:
        w_pct = int(col.get('width_pct') or (100 // n))
        col_w = int(width * w_pct / 100)
        valign = col.get('valign') or 'top'
        inner  = '\n'.join(_render_module(cm, col_w) for cm in (col.get('modules') or []))
        td_rows += (
            f'<td class="col-half" width="{col_w}" valign="{valign}"'
            f' style="padding:0;vertical-align:{valign};">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
            f'{inner}'
            f'</table>'
            f'</td>'
        )

    bg_style = f'background-color:{bg};' if bg else ''
    return (
        f'<tr style="{bg_style}">'
        f'<td>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">'
        f'<tr>{td_rows}</tr>'
        f'</table>'
        f'</td>'
        f'</tr>'
    )
