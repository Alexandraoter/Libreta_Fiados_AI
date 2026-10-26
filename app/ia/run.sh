
#!/usr/bin/env bash
set -euo pipefail

# Entrar a la carpeta raíz del proyecto
cd "$(dirname "$0")"

echo "=========================================="
echo "   LIBRETA DE FIADOS INTELIGENTE"
echo "=========================================="

# 1. Verificar que Docker esté disponible
if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: No se encontró Docker."
    echo "Abre Docker Desktop y verifica su instalación."
    exit 1
fi

# 2. Verificar conexión con Docker
if ! docker info >/dev/null 2>&1; then
    echo "ERROR: No se puede conectar con Docker."
    echo "Abre Docker Desktop y espera a que termine de iniciar."
    echo "Si usas WSL, verifica la integración de Docker Desktop."
    exit 1
fi

# 3. Crear el archivo .env si no existe
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "Se creó el archivo .env desde .env.example."
        echo "Configura GEMINI_API_KEY en el archivo .env."
        exit 1
    else
        echo "ERROR: No se encontró .env.example."
        exit 1
    fi
fi

# 4. Comprobar que GEMINI_API_KEY tenga un valor
if ! grep -qE '^GEMINI_API_KEY=.+[^[:space:]]' .env; then
    echo "ERROR: GEMINI_API_KEY está vacía en .env."
    echo "Configura tu clave de Gemini antes de continuar."
    exit 1
fi

# 5. Comprobar que exista Docker Compose
if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: Docker Compose no está disponible."
    exit 1
fi

# 6. Iniciar la aplicación
echo ""
echo "Iniciando la aplicación..."
echo "Dirección: http://localhost:8000"
echo "Para detenerla, presiona Ctrl+C."
echo ""

docker compose up --build
