"""
Gestión de almacenamiento: metadatos de procesos, TTL, limpieza y construcción de URLs de assets.
"""
import os
import json
import shutil
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

PROCESS_META_FILENAME = '_process_meta.json'
OUTPUT_FOLDER = '/tmp/outputs'


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


def write_process_meta(output_dir, process_id, public_base_url, ttl_seconds):
    """
    Escribe metadata de proceso con TTL. No incluye html_filename (extractor no genera HTML).
    """
    created_at = utcnow()
    expires_at = created_at + timedelta(seconds=ttl_seconds)
    meta = {
        'process_id': process_id,
        'created_at': dt_to_iso(created_at),
        'expires_at': dt_to_iso(expires_at),
        'asset_url_template': build_public_asset_url(public_base_url, process_id, '{asset_path}'),
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


def build_public_asset_url(public_base_url, process_id, asset_path):
    """Construye URL pública para acceder a un asset por process_id y nombre de archivo."""
    params = urlencode({'process_id': process_id, 'asset_path': asset_path})
    return f"{public_base_url}/assets?{params}"
