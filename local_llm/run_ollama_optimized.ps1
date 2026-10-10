Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "    LAUNCHING OLLAMA WITH HIGH-CONTEXT OPTIMIZATIONS   " -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Force-kill background system tray apps cleanly
Write-Host "🔄 Stopping existing background Ollama processes to free port 11434..." -ForegroundColor Yellow
Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "ollama app" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# 2. Inject your hardware performance environment flags for this window
Write-Host "🚀 Injecting performance optimization flags..." -ForegroundColor Yellow
$env:OLLAMA_FLASH_ATTENTION="1"
$env:OMP_NUM_THREADS="2"

Write-Host "✨ Optimizations locked in!" -ForegroundColor Green
Write-Host "-------------------------------------------------------"
Write-Host "💻 Starting Ollama Engine Server... Keep this window open!"
Write-Host "-------------------------------------------------------"
Write-Host ""

# 3. Fire up the native engine server
ollama serve
