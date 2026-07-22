# Script para iniciar o servidor backend de forma robusta
# Uso: .\start_server.ps1

Write-Host "🏛️  Iniciando servidor Visão Patrimônios..." -ForegroundColor Cyan

# 1. Mata qualquer processo na porta 8000
$port = 8000
$processes = netstat -ano | Select-String ":$port " | ForEach-Object {
    $parts = $_ -split '\s+'
    $pid = $parts[-1]
    if ($pid -match '^\d+$') { $pid }
} | Get-Unique

foreach ($pid in $processes) {
    try {
        Stop-Process -Id $pid -Force -ErrorAction Stop
        Write-Host "  ✅ Processo PID $pid finalizado" -ForegroundColor Yellow
    } catch {
        # Ignora se não conseguir
    }
}

Start-Sleep -Seconds 1

# 2. Ativa ambiente virtual e inicia servidor
$venvPath = Join-Path (Get-Location).Path "..\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPath)) {
    $venvPath = Join-Path (Get-Location).Path ".venv\Scripts\python.exe"
}
if (-not (Test-Path $venvPath)) {
    $venvPath = "..\.venv\Scripts\python.exe"
}

Write-Host "  🐍 Python: $venvPath" -ForegroundColor Gray
Write-Host "  📡 Servidor: http://localhost:$port" -ForegroundColor Green
Write-Host "  📚 Docs: http://localhost:$port/docs" -ForegroundColor Green
Write-Host ""

# 3. Inicia servidor com tratamento de erro
try {
    & $venvPath app/main.py
} catch {
    Write-Host "❌ Erro ao iniciar servidor: $_" -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
}
