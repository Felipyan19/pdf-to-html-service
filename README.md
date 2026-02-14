# 📄 Microservicio PDF a HTML

Microservicio que convierte archivos PDF a HTML usando **pdf2htmlEX**, manteniendo el formato visual idéntico al PDF original.

## 🚀 Características

- ✅ API REST simple y fácil de usar
- ✅ Conversión de alta fidelidad (mantiene el formato exacto del PDF)
- ✅ Respuestas en JSON o descarga directa del archivo HTML
- ✅ Dockerizado con Docker Compose
- ✅ Health check endpoint
- ✅ Manejo de errores robusto

## 📋 Requisitos

- Docker
- Docker Compose

## 🏃 Inicio Rápido

### 1. Construir y ejecutar el servicio

```bash
docker-compose up -d --build
```

### 2. Verificar que el servicio está corriendo

```bash
curl http://localhost:5000/health
```

Deberías ver:
```json
{
  "status": "healthy",
  "service": "pdf-to-html"
}
```

### 3. Convertir un PDF

**Opción A: Con curl (respuesta JSON)**
```bash
curl -X POST \
  -F "file=@tu-archivo.pdf" \
  -F "format=json" \
  http://localhost:5000/convert
```

**Opción B: Con curl (descargar HTML directamente)**
```bash
curl -X POST \
  -F "file=@tu-archivo.pdf" \
  -F "format=file" \
  http://localhost:5000/convert \
  -o output.html
```

**Opción C: Con el script de prueba incluido**
```bash
# Dar permisos de ejecución
chmod +x test_curl.sh

# Ejecutar
./test_curl.sh tu-archivo.pdf
```

**Opción D: Con Python**
```bash
python3 test_api.py tu-archivo.pdf
```

## 📡 API Endpoints

### GET /health
Health check del servicio.

**Respuesta:**
```json
{
  "status": "healthy",
  "service": "pdf-to-html"
}
```

### POST /convert
Convierte un PDF a HTML.

**Parámetros:**
- `file` (required): Archivo PDF (multipart/form-data)
- `format` (optional): `json` (default) o `file`
- `extractor_base_url` (optional): URL base del servicio [pdf-image-extractor](../pdf-image-extractor) (ej. `http://pdf-image-extractor:5050`) para usar sus imágenes extraídas en el HTML
- `extractor_session_id` (optional): Session ID devuelto por el extractor al extraer imágenes del mismo PDF (solo tiene efecto si se envía `extractor_base_url`)

**Respuesta (format=json):**
```json
{
  "success": true,
  "html": "<html>...</html>",
  "filename": "documento.html",
  "process_id": "uuid-del-proceso",
  "additional_files": ["documento.css", "fonts/..."],
  "assets_base_url": "http://host/convert/assets/uuid-del-proceso",
  "message": "PDF convertido exitosamente"
}
```

El HTML generado usa **URLs absolutas** para imágenes y CSS (bien desde este servicio, bien desde el extractor si se indicó), de modo que al montar o abrir el HTML las imágenes cargan correctamente.

**Respuesta (format=file):**
Descarga directa del archivo HTML.

### GET /convert/download/<process_id>
Descarga el HTML generado usando el process_id retornado por `/convert`.

### GET /convert/assets/<process_id>/<path:asset_path>
Sirve un asset (imagen, CSS, fuentes) del proceso. Permite montar el HTML y que las rutas relativas del PDF convertido carguen las imágenes desde este servicio. Ejemplo: `GET /convert/assets/{process_id}/doc-png/page-1.png`.

## 🧪 Pruebas

### Método 1: Script Bash
```bash
chmod +x test_curl.sh
./test_curl.sh sample.pdf
```

### Método 2: Script Python
```bash
pip install requests
python3 test_api.py sample.pdf
```

### Método 3: Postman o Insomnia
1. Crear una petición POST a `http://localhost:5000/convert`
2. Tipo: multipart/form-data
3. Agregar campo `file` con tu PDF
4. Agregar campo `format` con valor `json` o `file`
5. Enviar

## 🐳 Comandos Docker

```bash
# Iniciar el servicio
docker-compose up -d

# Ver logs
docker-compose logs -f

# Detener el servicio
docker-compose down

# Reconstruir después de cambios
docker-compose up -d --build

# Ver estado
docker-compose ps
```

## 🔗 Integración con pdf-image-extractor

En la misma carpeta de microservicios existe el servicio [pdf-image-extractor](../pdf-image-extractor), que extrae imágenes de un PDF (PyMuPDF). Para que el HTML generado por este servicio use esas imágenes en lugar de las generadas por pdftohtml:

1. Sube el PDF al **pdf-image-extractor** (`POST /api/v1/extract`) y anota el header `X-Session-ID`.
2. Convierte el mismo PDF con este servicio pasando en el form:
   - `extractor_base_url`: URL del extractor (ej. `http://localhost:5050` si corre en el mismo host).
   - `extractor_session_id`: valor de `X-Session-ID`.

El HTML resultante tendrá las etiquetas `<img>` apuntando a las URLs del extractor (`/api/v1/images/{session_id}/{filename}`), de modo que al montar el HTML se usan las imágenes extraídas por ese servicio.

## 📁 Estructura del Proyecto

```
pdf-to-html-service/
├── app.py                 # API Flask
├── Dockerfile            # Imagen Docker con pdf2htmlEX
├── docker-compose.yml    # Orquestación
├── requirements.txt      # Dependencias Python
├── test_api.py          # Script de prueba Python
├── test_curl.sh         # Script de prueba Bash
├── README.md            # Esta documentación
└── outputs/             # Directorio para archivos generados (creado automáticamente)
```

## ⚙️ Configuración

El servicio se ejecuta en el puerto **5000** por defecto. Para cambiarlo, edita `docker-compose.yml`:

```yaml
ports:
  - "TU_PUERTO:5000"
```

## 🔧 Personalización

### Ajustar parámetros de conversión

Edita `app.py` en la sección del comando pdf2htmlEX:

```python
cmd = [
    'pdf2htmlEX',
    '--zoom', '1.3',           # Factor de zoom
    '--dest-dir', output_dir,
    pdf_path,
    html_filename
]
```

Parámetros útiles de pdf2htmlEX:
- `--zoom`: Factor de escala (default: 1.3)
- `--fit-width`: Ajustar al ancho de la página
- `--embed-css`: Incrustar CSS en el HTML (default: 1)
- `--embed-font`: Incrustar fuentes (default: 1)
- `--embed-image`: Incrustar imágenes (default: 1)

## 🔒 Producción

Para producción, considera:

1. **Agregar autenticación** (API keys, JWT, etc.)
2. **Límites de tamaño de archivo**
3. **Rate limiting**
4. **HTTPS con reverse proxy** (nginx, traefik)
5. **Monitoreo y logs**
6. **Limpieza automática de archivos temporales**

## 🐛 Troubleshooting

### El servicio no inicia
```bash
# Ver logs
docker-compose logs

# Verificar que el puerto 5000 no esté en uso
lsof -i :5000
```

### Error al convertir PDF
- Verifica que el PDF no esté corrupto
- Algunos PDFs con seguridad pueden fallar
- Revisa los logs: `docker-compose logs`

### Timeout en conversión
Para PDFs grandes, aumenta el timeout en `docker-compose.yml`:
```yaml
environment:
  - GUNICORN_TIMEOUT=300
```

## 📝 Ejemplo de Uso en Código

### Python
```python
import requests

url = "http://localhost:5000/convert"
files = {"file": open("documento.pdf", "rb")}
data = {"format": "json"}

response = requests.post(url, files=files, data=data)
result = response.json()

# Guardar HTML
with open("output.html", "w") as f:
    f.write(result["html"])
```

### JavaScript/Node.js
```javascript
const FormData = require('form-data');
const fs = require('fs');
const axios = require('axios');

const form = new FormData();
form.append('file', fs.createReadStream('documento.pdf'));
form.append('format', 'json');

axios.post('http://localhost:5000/convert', form, {
  headers: form.getHeaders()
})
.then(response => {
  fs.writeFileSync('output.html', response.data.html);
  console.log('Convertido!');
})
.catch(error => console.error(error));
```

### cURL
```bash
curl -X POST \
  -F "file=@documento.pdf" \
  -F "format=json" \
  http://localhost:5000/convert | jq -r '.html' > output.html
```

## 📄 Licencia

Este proyecto es de código abierto y está disponible bajo la licencia MIT.

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor:
1. Haz fork del proyecto
2. Crea una rama para tu feature
3. Commit tus cambios
4. Push a la rama
5. Abre un Pull Request

## 📞 Soporte

Si encuentras algún problema o tienes sugerencias, por favor abre un issue en el repositorio.
