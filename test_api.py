#!/usr/bin/env python3
"""
Script de prueba para el servicio de conversión PDF a HTML
"""

import requests
import sys
import json

API_URL = "http://localhost:5050"

def test_health():
    """Prueba el endpoint de health check"""
    print("🔍 Probando health check...")
    response = requests.get(f"{API_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")
    return response.status_code == 200

def convert_pdf_to_html(pdf_path, return_format='json'):
    """
    Convierte un PDF a HTML

    Args:
        pdf_path: Ruta al archivo PDF
        return_format: 'json' para obtener JSON con HTML, 'file' para descargar HTML
    """
    print(f"📄 Convirtiendo PDF: {pdf_path}")
    print(f"   Formato de retorno: {return_format}\n")

    try:
        with open(pdf_path, 'rb') as f:
            files = {'file': (pdf_path.split('/')[-1], f, 'application/pdf')}
            data = {'format': return_format}

            response = requests.post(
                f"{API_URL}/convert",
                files=files,
                data=data
            )

        print(f"Status: {response.status_code}")

        if return_format == 'json':
            result = response.json()
            print(f"\n✅ Conversión exitosa!")
            print(f"   Filename: {result.get('filename')}")
            print(f"   Process ID: {result.get('process_id')}")
            print(f"   Archivos adicionales: {result.get('additional_files')}")
            print(f"   Tamaño del HTML: {len(result.get('html', ''))} caracteres")

            # Guardar HTML en archivo local
            output_file = f"output_{result.get('filename')}"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(result.get('html', ''))
            print(f"\n💾 HTML guardado en: {output_file}")

            return result
        else:
            # Guardar archivo descargado
            output_file = f"output_{pdf_path.split('/')[-1].replace('.pdf', '.html')}"
            with open(output_file, 'wb') as f:
                f.write(response.content)
            print(f"\n💾 HTML guardado en: {output_file}")
            return True

    except FileNotFoundError:
        print(f"❌ Error: No se encontró el archivo {pdf_path}")
        return None
    except requests.exceptions.ConnectionError:
        print(f"❌ Error: No se pudo conectar al servicio en {API_URL}")
        print("   Asegúrate de que el servicio esté corriendo (docker-compose up)")
        return None
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        if hasattr(e, 'response'):
            print(f"   Response: {e.response.text}")
        return None

def main():
    print("=" * 60)
    print("🧪 TEST: Servicio de Conversión PDF a HTML")
    print("=" * 60 + "\n")

    # Test 1: Health check
    if not test_health():
        print("❌ El servicio no está disponible. Ejecuta: docker-compose up -d")
        sys.exit(1)

    # Test 2: Convertir PDF
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        print("💡 Uso: python3 test_api.py <ruta-al-pdf>")
        print("   Ejemplo: python3 test_api.py sample.pdf")
        print("\n⚠️  No se especificó archivo PDF. Prueba el health check solamente.")
        return

    # Opción 1: Obtener JSON con HTML
    print("-" * 60)
    result = convert_pdf_to_html(pdf_path, return_format='json')

    # Opción 2: Descargar archivo HTML directamente
    # print("-" * 60)
    # convert_pdf_to_html(pdf_path, return_format='file')

    print("\n" + "=" * 60)
    print("✅ Pruebas completadas")
    print("=" * 60)

if __name__ == "__main__":
    main()
