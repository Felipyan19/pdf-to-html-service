# PDF to HTML Service

Microservicio Flask para convertir PDF a HTML usando `pdftohtml`, con extraccion alternativa de imagenes via PyMuPDF + Pillow para incrustarlas como `data:` URI.

## Features

- Endpoint `POST /convert` para convertir PDF a HTML.
- Estrategia por defecto basada en URL:
  - `extractor_urls` si envias `extractor_base_url` + `extractor_session_id`.
  - `assets_urls` en caso contrario.
  - El HTML final queda con `<img src=\"https://.../convert?action=asset&...\">`.
- Publicacion temporal por 1 hora (TTL) para HTML + assets.
- Estrategias opcionales con `pdf-image-extractor` externo.
- Endpoint `GET /health`.
- Endpoint `GET /convert/download/<process_id>` para descargar HTML final.
- Endpoint `GET /convert?action=view&process_id=...` para abrir HTML publico.
- Endpoint `GET /convert?action=asset&process_id=...&asset_path=...` para servir assets.

## Run

```bash
docker-compose up -d --build
curl http://localhost:5050/health
```

## API

### GET /health

Respuesta:

```json
{
  "status": "healthy",
  "service": "pdf-to-html"
}
```

### POST /convert

`multipart/form-data`:

- `file` (required): archivo PDF.
- `format` (optional): `json` (default) o `file`.
- `image_strategy` (optional):
  - `pymupdf_embed`: usa PyMuPDF + Pillow y embebe imagenes.
  - `extractor_embed`: usa `pdf-image-extractor` y embebe imagenes descargadas.
  - `extractor_urls`: usa `pdf-image-extractor` y deja URLs remotas en `<img>`.
  - `assets_urls`: mantiene assets locales servidos por `/convert?action=asset&...`.
  - Si no envias `image_strategy`, se elige automaticamente `extractor_urls` o `assets_urls`.
- `render_dpi` (optional): DPI para `pymupdf_embed` (default: `200`).
- `extractor_base_url` (required para `extractor_embed` y `extractor_urls`).
- `extractor_session_id` (required para `extractor_embed` y `extractor_urls`).
- `public_base_url` (optional): base publica para construir URLs absolutas, por ejemplo `https://tu-dominio.com`.
- `PUBLIC_BASE_URL` (env optional): base publica por defecto si no envias `public_base_url`.
- `PUBLIC_ASSET_TTL_SECONDS` (env optional): TTL de publicacion (default `3600`).
- El servicio procesa siempre solo la pagina 1 del PDF para generar HTML e imagenes.

Respuesta `format=json` (ejemplo):

```json
{
  "success": true,
  "html": "<html>...</html>",
  "filename": "documento.html",
  "process_id": "uuid-del-proceso",
  "additional_files": ["documento.css", "fonts/..."],
  "assets_base_url": "https://docs.149-130-164-187.sslip.io/convert?action=asset&process_id=uuid-del-proceso",
  "asset_url_template": "https://docs.149-130-164-187.sslip.io/convert?action=asset&process_id=uuid-del-proceso&asset_path={asset_path}",
  "public_html_url": "https://docs.149-130-164-187.sslip.io/convert?action=view&process_id=uuid-del-proceso",
  "public_download_url": "https://docs.149-130-164-187.sslip.io/convert?action=download&process_id=uuid-del-proceso",
  "expires_at": "2026-02-14T19:00:00Z",
  "image_strategy": "extractor_urls",
  "embedded_images": 0,
  "processed_page": 1,
  "message": "PDF convertido exitosamente"
}
```

Cuando `image_strategy=pymupdf_embed`, se agrega `metadata` en la respuesta JSON y se guarda `metadata.json` en el output del proceso.

### GET /convert/download/<process_id>

Descarga el HTML generado.

### GET /convert?action=view&process_id=<process_id>

Muestra el HTML generado sin forzar descarga (URL publica).

### GET /convert?action=asset&process_id=<process_id>&asset_path=<path>

Sirve assets del proceso (imagenes, css, fuentes). Expira junto al proceso (TTL 1 hora).

## Integracion con pdf-image-extractor

Flujo recomendado:

1. Enviar PDF al extractor (`POST /api/v1/extract`) y guardar `X-Session-ID`.
2. Enviar el mismo PDF a este servicio con:
   - `extractor_base_url`
   - `extractor_session_id`
   - `image_strategy=extractor_embed` (o `extractor_urls`).

## Local test

```bash
python test_api.py sample.pdf
```

## Project files

- `app.py`: API Flask.
- `requirements.txt`: dependencias Python.
- `Dockerfile`: imagen runtime.
- `docker-compose.yml`: ejecucion local.
- `test_api.py`: prueba Python.
- `test_curl.sh`: prueba curl.
