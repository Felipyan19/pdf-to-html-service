#!/bin/bash

echo "======================================"
echo "🧪 TEST: Servicio PDF a HTML con CURL"
echo "======================================"
echo ""

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

API_URL="http://localhost:5050"

# Test 1: Health check
echo "🔍 Test 1: Health Check"
echo "--------------------------------------"
response=$(curl -s -w "\n%{http_code}" "$API_URL/health")
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | head -n-1)

if [ "$http_code" = "200" ]; then
    echo -e "${GREEN}✅ Status: $http_code${NC}"
    echo "Response: $body"
else
    echo -e "${RED}❌ Status: $http_code${NC}"
    echo "Response: $body"
    echo ""
    echo "El servicio no está disponible. Ejecuta: docker-compose up -d"
    exit 1
fi

echo ""
echo ""

# Test 2: Convertir PDF a HTML (JSON response)
if [ -z "$1" ]; then
    echo -e "${YELLOW}💡 Uso: ./test_curl.sh <ruta-al-pdf>${NC}"
    echo "   Ejemplo: ./test_curl.sh sample.pdf"
    echo ""
    echo "⚠️  No se especificó archivo PDF. Solo se ejecutó health check."
    exit 0
fi

PDF_FILE="$1"

if [ ! -f "$PDF_FILE" ]; then
    echo -e "${RED}❌ Error: Archivo no encontrado: $PDF_FILE${NC}"
    exit 1
fi

echo "📄 Test 2: Convertir PDF a HTML (formato JSON)"
echo "--------------------------------------"
echo "Archivo: $PDF_FILE"
echo ""

response=$(curl -s -w "\n%{http_code}" -X POST \
    -F "file=@$PDF_FILE" \
    -F "format=json" \
    "$API_URL/convert")

http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | head -n-1)

if [ "$http_code" = "200" ]; then
    echo -e "${GREEN}✅ Status: $http_code${NC}"

    # Extraer información del JSON
    filename=$(echo "$body" | grep -o '"filename":"[^"]*"' | cut -d'"' -f4)
    process_id=$(echo "$body" | grep -o '"process_id":"[^"]*"' | cut -d'"' -f4)

    echo "Filename: $filename"
    echo "Process ID: $process_id"

    # Guardar HTML en archivo
    output_file="output_${filename}"
    echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin)['html'])" > "$output_file" 2>/dev/null

    if [ -f "$output_file" ]; then
        echo -e "${GREEN}💾 HTML guardado en: $output_file${NC}"
    fi
else
    echo -e "${RED}❌ Status: $http_code${NC}"
    echo "Response: $body"
fi

echo ""
echo ""

# Test 3: Descargar HTML como archivo
echo "📥 Test 3: Convertir PDF a HTML (descargar archivo)"
echo "--------------------------------------"

output_file="downloaded_output.html"
http_code=$(curl -s -w "%{http_code}" -X POST \
    -F "file=@$PDF_FILE" \
    -F "format=file" \
    "$API_URL/convert" \
    -o "$output_file")

if [ "$http_code" = "200" ]; then
    echo -e "${GREEN}✅ Status: $http_code${NC}"
    echo -e "${GREEN}💾 Archivo descargado: $output_file${NC}"
    file_size=$(wc -c < "$output_file")
    echo "Tamaño: $file_size bytes"
else
    echo -e "${RED}❌ Status: $http_code${NC}"
    rm -f "$output_file"
fi

echo ""
echo "======================================"
echo "✅ Pruebas completadas"
echo "======================================"
