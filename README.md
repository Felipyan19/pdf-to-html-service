# PDF Newsletter to HTML Service

Microservicio Flask minimal para el flujo n8n:
`extract -> claude -> render -> preview -> diff`.

## Endpoints activos

- `POST /extract`
- `GET /assets`
- `POST /render`
- `POST /preview`
- `POST /diff`

## Contratos

### POST /extract

Entrada:

- JSON: `{ "pdf_url": "https://..." }`
- o multipart con `file`

Salida:

```json
{
  "doc_id": "uuid",
  "page_count": 1,
  "expires_at": "2026-02-24T12:00:00Z",
  "pages": [
    {
      "page_index": 0,
      "width_pt": 620,
      "height_pt": 4791.4,
      "render_png_url": "https://host/assets?process_id=...&asset_path=render_p00.png",
      "texts": [
        {
          "id": "t_0",
          "text": "hola",
          "bbox": { "x0": 10, "y0": 20, "x1": 40, "y1": 30 }
        }
      ],
      "images": [
        {
          "id": "i_0",
          "url": "https://host/assets?process_id=...&asset_path=p00_img001_xref5.png",
          "url_publica": "https://host/assets?process_id=...&asset_path=p00_img001_xref5.png",
          "bbox": { "x0": 20, "y0": 50, "x1": 120, "y1": 150 },
          "w_px": 400,
          "h_px": 300
        }
      ]
    }
  ]
}
```

### POST /render

Entrada:

```json
{
  "page_index": 0,
  "render_ready_modules": []
}
```

Salida:

```json
{
  "html": "<!DOCTYPE html>...",
  "page_index": 0
}
```

### POST /preview

Entrada:

```json
{
  "html": "<!DOCTYPE html>..."
}
```

Salida:

```json
{
  "preview_png_url": "https://host/assets?process_id=...&asset_path=preview.png",
  "expires_at": "2026-02-24T12:00:00Z"
}
```

### POST /diff

Entrada:

```json
{
  "a_png": "https://...",
  "b_png": "https://..."
}
```

Salida:

```json
{
  "score": 0.87,
  "width": 1240,
  "height": 1754,
  "diffs": [
    { "row": 2, "col": 5, "diff_pct": 0.34 }
  ]
}
```

## Run

```bash
docker-compose up -d --build
```

Servidor:

- `http://localhost:5050`
