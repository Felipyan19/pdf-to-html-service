"""
Convierte render_ready_modules (lista de módulos estructurados) en HTML de email.

Tipos de módulo soportados:
  image     — imagen con src, alt, width, height, link opcional
  text      — párrafo con content, color, font_size, align, padding, etc.
  heading   — encabezado (level 1-6) con content
  divider   — separador horizontal
  spacer    — espacio vertical
  row       — fila multi-columna con lista de "columns"
  raw_html  — passthrough de HTML literal

Todos los módulos aceptan background_color y style (CSS raw) como overrides.

El HTML generado es table-based (600 px por defecto) e inline-styled,
compatible con la mayoría de clientes de email.
"""


def render_modules_to_html(modules: list, page_width_px: int = 600) -> str:
    """
    Convierte una lista de módulos a un documento HTML de email completo.
    """
    rows = '\n'.join(_render_module(m, page_width_px) for m in modules)
    return _email_shell(rows, page_width_px)


# ---------------------------------------------------------------------------
# Shell / wrapper
# ---------------------------------------------------------------------------

def _email_shell(body: str, width: int) -> str:
    return (
        '<!DOCTYPE html>\n'
        '<html lang="es">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<style>'
        'body{margin:0;padding:0;background:#f4f4f4;font-family:Arial,Helvetica,sans-serif;}'
        'img{border:0;outline:none;text-decoration:none;}'
        '</style>\n'
        '</head>\n'
        '<body>\n'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"'
        ' style="background:#f4f4f4;">\n'
        '<tr><td align="center" style="padding:20px 0;">\n'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"'
        f' width="{width}" style="background:#ffffff;max-width:{width}px;">\n'
        f'{body}\n'
        '</table>\n'
        '</td></tr>\n'
        '</table>\n'
        '</body>\n'
        '</html>'
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _render_module(module: dict, width: int) -> str:
    t = str(module.get('type', 'raw_html')).lower()
    dispatch = {
        'image':    _render_image,
        'text':     _render_text,
        'paragraph': _render_text,
        'heading':  _render_heading,
        'divider':  _render_divider,
        'spacer':   _render_spacer,
        'row':      _render_row,
        'raw_html': _render_raw,
    }
    fn = dispatch.get(t, _render_raw)
    return fn(module, width) if t == 'row' else fn(module)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Módulos individuales
# ---------------------------------------------------------------------------

def _render_image(m: dict, _w=None) -> str:
    src    = m.get('src', '')
    alt    = m.get('alt', '')
    img_w  = m.get('width', 600)
    img_h  = m.get('height', '')
    link   = m.get('link', '')
    padding = m.get('padding', '0')
    bg      = m.get('background_color', '')

    h_attr  = f' height="{img_h}"' if img_h else ''
    img_tag = (
        f'<img src="{src}" alt="{alt}" width="{img_w}"{h_attr}'
        f' style="display:block;max-width:100%;height:auto;">'
    )
    if link:
        img_tag = f'<a href="{link}" target="_blank" style="display:block;">{img_tag}</a>'

    td_style = f'padding:{padding};'
    if bg:
        td_style += f'background-color:{bg};'
    if m.get('style'):
        td_style += m['style']

    return f'<tr><td align="center" style="{td_style}">{img_tag}</td></tr>'


def _render_text(m: dict, _w=None) -> str:
    content     = str(m.get('content', '')).replace('\n', '<br>')
    color       = m.get('color', '#333333')
    font_size   = m.get('font_size', 14)
    font_weight = m.get('font_weight', 'normal')
    align       = m.get('align', 'left')
    padding     = m.get('padding', '8px 16px')
    line_height = m.get('line_height', '1.5')

    p_style = (
        f'color:{color};font-size:{font_size}px;font-weight:{font_weight};'
        f'text-align:{align};line-height:{line_height};'
        f'padding:{padding};margin:0;'
    )
    if m.get('background_color'):
        p_style += f"background-color:{m['background_color']};"
    if m.get('style'):
        p_style += m['style']

    return f'<tr><td><p style="{p_style}">{content}</p></td></tr>'


def _render_heading(m: dict, _w=None) -> str:
    content  = str(m.get('content', ''))
    level    = max(1, min(6, int(m.get('level', 2))))
    defaults = {1: 28, 2: 22, 3: 18, 4: 16, 5: 14, 6: 12}
    font_size = m.get('font_size', defaults[level])
    color   = m.get('color', '#111111')
    align   = m.get('align', 'left')
    padding = m.get('padding', '16px 16px 8px')

    h_style = (
        f'color:{color};font-size:{font_size}px;font-weight:bold;'
        f'text-align:{align};padding:{padding};margin:0;'
    )
    if m.get('background_color'):
        h_style += f"background-color:{m['background_color']};"
    if m.get('style'):
        h_style += m['style']

    return f'<tr><td><h{level} style="{h_style}">{content}</h{level}></td></tr>'


def _render_divider(m: dict, _w=None) -> str:
    color     = m.get('color', '#e0e0e0')
    thickness = m.get('thickness', 1)
    padding   = m.get('padding', '0 16px')
    return (
        f'<tr><td style="padding:{padding};">'
        f'<hr style="border:0;border-top:{thickness}px solid {color};margin:0;">'
        f'</td></tr>'
    )


def _render_spacer(m: dict, _w=None) -> str:
    h = int(m.get('height', 16))
    return f'<tr><td style="height:{h}px;line-height:{h}px;font-size:0;">&nbsp;</td></tr>'


def _render_raw(m: dict, _w=None) -> str:
    html = m.get('html', '')
    return f'<tr><td>{html}</td></tr>'


def _render_row(m: dict, total_width: int) -> str:
    columns = m.get('columns', [])
    if not columns:
        return ''

    cells = ''
    for col in columns:
        w_pct  = col.get('width_pct', 100 // len(columns))
        col_w  = int(total_width * w_pct / 100)
        valign = col.get('valign', 'top')
        inner  = '\n'.join(_render_module(cm, col_w) for cm in col.get('modules', []))
        cells += (
            f'<td width="{col_w}" valign="{valign}" style="padding:0;">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'{inner}</table>'
            f'</td>'
        )

    bg = m.get('background_color', '')
    tr_style = f'background-color:{bg};' if bg else ''
    return f'<tr style="{tr_style}">{cells}</tr>'
