import json
import logging
import os
import shutil
import sys
import uuid

from flask import Flask, jsonify, request, send_file

from services.differ import visual_diff
from services.extractor import extract_pdf_content, render_page_previews
from services.previewer import html_to_png
from services.renderer import render_modules_to_html
from utils.http_helpers import resolve_public_base_url
from utils.pdf_input import resolve_pdf_input
from utils.storage import (
    OUTPUT_FOLDER,
    cleanup_expired_outputs,
    is_output_expired,
    write_process_meta,
)

UPLOAD_FOLDER = "/tmp/uploads"
PUBLIC_ASSET_TTL_SECONDS = int(os.getenv("PUBLIC_ASSET_TTL_SECONDS", "3600"))

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
if LOG_LEVEL not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
    LOG_LEVEL = "INFO"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
    force=True,
)

app = Flask(__name__)
app.logger.setLevel(getattr(logging, LOG_LEVEL))
logging.getLogger("werkzeug").setLevel(getattr(logging, LOG_LEVEL))
service_logger = logging.getLogger("pdf_to_html_service")
service_logger.setLevel(getattr(logging, LOG_LEVEL))


@app.before_request
def log_request_start():
    service_logger.info(
        "Request start method=%s path=%s remote=%s",
        request.method,
        request.path,
        request.remote_addr,
    )


@app.after_request
def log_request_end(response):
    service_logger.info(
        "Request end method=%s path=%s status=%s",
        request.method,
        request.path,
        response.status_code,
    )
    return response


def _build_rich_pages(result: dict, preview_urls: list[str]) -> list[dict]:
    rich_pages = []
    for i, page in enumerate(result.get("pages", [])):
        page_width = page["page_width"]
        page_height = page["page_height"]

        texts = [
            {
                "id": f"t_{idx}",
                "text": text["content"],
                "bbox": text["bbox"],
                "font_guess": text.get("font", ""),
                "size_guess": text.get("font_size", 0),
                "color_guess": text.get("color_guess", "#000000"),
            }
            for idx, text in enumerate(page.get("texts", []))
        ]

        images = []
        for idx, image in enumerate(page.get("images", [])):
            url = image.get("url")
            images.append(
                {
                    "id": f"i_{idx}",
                    "url": url,
                    "url_publica": url,
                    "bbox": {
                        "x0": max(0.0, image["bbox"]["x0"]),
                        "y0": max(0.0, image["bbox"]["y0"]),
                        "x1": min(page_width, image["bbox"]["x1"]),
                        "y1": min(page_height, image["bbox"]["y1"]),
                    },
                    "w_px": image.get("width", 0),
                    "h_px": image.get("height", 0),
                }
            )

        rich_pages.append(
            {
                "page_index": page["page_num"],
                "width_pt": page_width,
                "height_pt": page_height,
                "render_png_url": preview_urls[i] if i < len(preview_urls) else None,
                "texts": texts,
                "images": images,
            }
        )

    return rich_pages


@app.route("/extract", methods=["POST"])
def extract_pdf():
    cleanup_expired_outputs()

    try:
        pdf_path, original_filename, temp_paths, process_id = resolve_pdf_input(
            request, UPLOAD_FOLDER
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    output_dir = os.path.join(OUTPUT_FOLDER, process_id)
    os.makedirs(output_dir, exist_ok=True)
    public_base_url = resolve_public_base_url(request)

    try:
        service_logger.info(
            "Extract start doc_id=%s filename=%s", process_id, original_filename
        )
        result = extract_pdf_content(pdf_path, output_dir, public_base_url, process_id)
        preview_urls = render_page_previews(pdf_path, output_dir, public_base_url, process_id)
        meta = write_process_meta(
            output_dir, process_id, public_base_url, PUBLIC_ASSET_TTL_SECONDS
        )
        result["expires_at"] = meta["expires_at"]

        extraction_path = os.path.join(output_dir, "_extraction.json")
        with open(extraction_path, "w", encoding="utf-8") as output_file:
            json.dump(result, output_file, ensure_ascii=False)

        rich_pages = _build_rich_pages(result, preview_urls)
        return (
            jsonify(
                {
                    "doc_id": process_id,
                    "page_count": result["page_count"],
                    "expires_at": meta["expires_at"],
                    "pages": rich_pages,
                }
            ),
            200,
        )
    except Exception as exc:
        service_logger.exception("Extract error doc_id=%s: %s", process_id, exc)
        shutil.rmtree(output_dir, ignore_errors=True)
        return jsonify({"error": f"Error procesando el PDF: {str(exc)}"}), 500
    finally:
        for temp_path in temp_paths:
            if os.path.exists(temp_path):
                os.remove(temp_path)


@app.route("/assets", methods=["GET"])
def serve_asset():
    process_id = request.args.get("process_id", "").strip()
    asset_path = request.args.get("asset_path", "").strip()

    if not process_id or not asset_path:
        return jsonify({"error": "Se requieren process_id y asset_path"}), 400

    output_dir = os.path.join(OUTPUT_FOLDER, process_id)
    expired, _ = is_output_expired(output_dir)
    if expired:
        return jsonify({"error": "El proceso ha expirado"}), 410

    safe_asset = os.path.basename(asset_path)
    file_path = os.path.join(output_dir, safe_asset)
    real_path = os.path.realpath(file_path)
    real_output = os.path.realpath(output_dir)

    if not real_path.startswith(real_output + os.sep) and real_path != real_output:
        return jsonify({"error": "Acceso no permitido"}), 403

    if not os.path.isfile(file_path):
        return jsonify({"error": "Asset no encontrado"}), 404

    return send_file(file_path)


@app.route("/render", methods=["POST"])
def render_html():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": 'Se requiere JSON con "render_ready_modules"'}), 400

    modules = payload.get("render_ready_modules")
    if not isinstance(modules, list):
        return jsonify({"error": '"render_ready_modules" debe ser una lista'}), 400

    page_index = payload.get("page_index", 0)
    page_width = int(payload.get("page_width_px", 600))

    try:
        html = render_modules_to_html(modules, page_width_px=page_width)
        return jsonify({"html": html, "page_index": page_index}), 200
    except Exception as exc:
        service_logger.exception("Render error: %s", exc)
        return jsonify({"error": f"Error al renderizar: {str(exc)}"}), 500


@app.route("/preview", methods=["POST"])
def preview_html():
    payload = request.get_json(silent=True)
    if not payload or not payload.get("html"):
        return jsonify({"error": 'Se requiere JSON con "html"'}), 400

    html_content = payload["html"]
    viewport_width = int(payload.get("viewport_width", 600))
    dpi = max(72, min(int(payload.get("dpi", 150)), 300))

    process_id = uuid.uuid4().hex
    output_dir = os.path.join(OUTPUT_FOLDER, process_id)
    os.makedirs(output_dir, exist_ok=True)
    public_base_url = resolve_public_base_url(request)

    try:
        preview_url = html_to_png(
            html_content,
            output_dir,
            public_base_url,
            process_id,
            viewport_width=viewport_width,
            dpi=dpi,
        )
        meta = write_process_meta(
            output_dir, process_id, public_base_url, PUBLIC_ASSET_TTL_SECONDS
        )
        return jsonify({"preview_png_url": preview_url, "expires_at": meta["expires_at"]}), 200
    except Exception as exc:
        service_logger.exception("Preview error process_id=%s: %s", process_id, exc)
        shutil.rmtree(output_dir, ignore_errors=True)
        return jsonify({"error": f"Error al renderizar HTML: {str(exc)}"}), 500


@app.route("/diff", methods=["POST"])
def diff_images():
    payload = request.get_json(silent=True)
    if not payload or not payload.get("a_png") or not payload.get("b_png"):
        return jsonify({"error": 'Se requieren "a_png" y "b_png"'}), 400

    try:
        public_base_url = resolve_public_base_url(request, payload)
        result = visual_diff(payload["a_png"], payload["b_png"], public_base_url)
        return jsonify(result), 200
    except Exception as exc:
        service_logger.exception("Diff error: %s", exc)
        return jsonify({"error": f"Error al comparar imágenes: {str(exc)}"}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
