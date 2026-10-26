
$ErrorActionPreference = "Stop"

Write-Host "=========================================="
Write-Host "   LIBRETA DE FIADOS INTELIGENTE"
Write-Host "=========================================="

# Verificar que Docker esté disponible
try {
    docker info | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker no está disponible."
    }
}
catch {
    Write-Host "ERROR: Abre Docker Desktop y espera a que inicie."
    exit 1
}

# Crear .env si no existe
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "Se creó .env desde .env.example."
        Write-Host "Configura GEMINI_API_KEY en .env y vuelve a ejecutar."
        exit 1
    }

    Write-Host "ERROR: No se encontró .env.example."
    exit 1
}

# Verificar que GEMINI_API_KEY esté configurada
$envContent = Get-Content ".env"
$apiKeyLine = $envContent | Where-Object {
    $_ -match '^GEMINI_API_KEY=.+\S'
}

if (-not $apiKeyLine) {
    Write-Host "ERROR: GEMINI_API_KEY está vacía en .env."
    exit 1
}

# Verificar Docker Compose
docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker Compose no está disponible."
    exit 1
}

Write-Host ""
Write-Host "Iniciando aplicación en http://localhost:8000"
Write-Host "Presiona Ctrl+C para detenerla."
Write-Host ""

docker compose up --build
