"""
Helpers HTTP: resolución de URL base pública, conversión a data URIs.
"""
import os
import base64
import mimetypes
import requests

DEFAULT_PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', '').strip().rstrip('/')


def resolve_public_base_url(req, payload=None):
    """
    Resuelve la URL base pública en orden de prioridad:
    1. Parámetro explicit en payload JSON
    2. Campo de formulario public_base_url
    3. Variable de entorno DEFAULT_PUBLIC_BASE_URL
    4. Auto-detección desde cabeceras X-Forwarded-* o req.host
    """
    explicit_base = ''
    if isinstance(payload, dict):
        explicit_base = str(payload.get('public_base_url', '')).strip().rstrip('/')
    if not explicit_base:
        explicit_base = req.form.get('public_base_url', '').strip().rstrip('/')
    if explicit_base:
        return explicit_base
    if DEFAULT_PUBLIC_BASE_URL:
        return DEFAULT_PUBLIC_BASE_URL
    forwarded_proto = req.headers.get('X-Forwarded-Proto', req.scheme)
    forwarded_host = req.headers.get('X-Forwarded-Host', req.host)
    proto = forwarded_proto.split(',')[0].strip()
    host = forwarded_host.split(',')[0].strip()
    return f"{proto}://{host}"


def file_to_data_uri(file_path):
    mime_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
    with open(file_path, 'rb') as f:
        encoded = base64.b64encode(f.read()).decode('ascii')
    return f"data:{mime_type};base64,{encoded}"


def url_to_data_uri(url, timeout=20):
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    content_type = r.headers.get('Content-Type', '').split(';')[0].strip()
    mime_type = content_type or mimetypes.guess_type(url)[0] or 'application/octet-stream'
    encoded = base64.b64encode(r.content).decode('ascii')
    return f"data:{mime_type};base64,{encoded}"
