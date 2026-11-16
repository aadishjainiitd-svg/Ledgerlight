<#
  Ledgerlight one-command demo start (Windows PowerShell 5.1+).

    .\start.ps1                 start backend + frontend, open the browser
    .\start.ps1 -NoBrowser      do not open the browser
    .\start.ps1 -Dev            run the Next.js dev server instead of the production build
    .\start.ps1 -Rebuild        force a fresh frontend build
    .\start.ps1 -BackendPort 8010 -FrontendPort 3000

  Backend: FastAPI on 127.0.0.1:8010 (port 8000 is often taken, so 8010 is the default).
  Frontend: first free port from 3000 upward (or the -FrontendPort you pass).
  Ctrl+C stops both. Logs go to frontend\.logs\.
#>
param(
  [int]$BackendPort = 8010,
  [int]$FrontendPort = 0,
  [switch]$NoBrowser,
  [switch]$Dev,
  [switch]$Rebuild
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Logs = Join-Path $Frontend '.logs'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$ApiBase = "http://127.0.0.1:$BackendPort"

function Test-PortFree([int]$p) {
  $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
  return -not $c
}
function Wait-Http([string]$url, [int]$seconds) {
  $until = (Get-Date).AddSeconds($seconds)
  while ((Get-Date) -lt $until) {
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 3; if ($r.StatusCode -lt 500) { return $true } } catch { Start-Sleep -Milliseconds 500 }
  }
  return $false
}
function Stop-Tree($proc) { if ($proc -and -not $proc.HasExited) { & taskkill /PID $proc.Id /T /F 2>$null | Out-Null } }

$started = @()
try {
  # ---------- backend ----------
  $reuseBackend = $false
  try { $h = Invoke-RestMethod -Uri "$ApiBase/api/health" -TimeoutSec 2; if ($h.ok) { $reuseBackend = $true } } catch { }
  if ($reuseBackend) {
    Write-Host "Backend already running at $ApiBase (reusing it)." -ForegroundColor Yellow
  } else {
    if (-not (Test-PortFree $BackendPort)) { throw "Port $BackendPort is in use by something that is not Ledgerlight. Pass -BackendPort <free port>." }
    $py = Join-Path $Backend '.venv\Scripts\python.exe'
    if (-not (Test-Path $py)) {
      Write-Host 'Creating the backend virtual environment (first run only)...' -ForegroundColor Cyan
      & python -m venv (Join-Path $Backend '.venv')
      & $py -m pip install -q -r (Join-Path $Backend 'requirements.txt')
    }
    Write-Host "Starting backend on $ApiBase ..." -ForegroundColor Cyan
    $b = Start-Process -FilePath $py -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$BackendPort") `
      -WorkingDirectory $Backend -WindowStyle Hidden -PassThru `
      -RedirectStandardOutput (Join-Path $Logs 'backend.out.log') -RedirectStandardError (Join-Path $Logs 'backend.err.log')
    $started += $b
    if (-not (Wait-Http "$ApiBase/api/health" 60)) { throw "The backend did not come up. See $Logs\backend.err.log" }
  }
  $health = Invoke-RestMethod -Uri "$ApiBase/api/health"
  Write-Host ("Backend ready: extraction mode '{0}', {1} runs in the database." -f $health.extraction_mode, $health.runs) -ForegroundColor Green

  # ---------- frontend ----------
  if ($FrontendPort -le 0) { $FrontendPort = 3000; while (-not (Test-PortFree $FrontendPort)) { $FrontendPort++ } }
  elseif (-not (Test-PortFree $FrontendPort)) { throw "Port $FrontendPort is already in use. Pick another with -FrontendPort." }

  Push-Location $Frontend
  try {
    if (-not (Test-Path 'node_modules')) { Write-Host 'Installing frontend dependencies (first run only)...' -ForegroundColor Cyan; & npm install --no-audit --no-fund | Out-Null }
    $env:NEXT_PUBLIC_API_BASE = $ApiBase
    $stampFile = Join-Path $Frontend '.next\api-base.txt'
    $needBuild = $Rebuild -or -not (Test-Path (Join-Path $Frontend '.next\BUILD_ID')) -or -not (Test-Path $stampFile) -or ((Get-Content $stampFile -Raw).Trim() -ne $ApiBase)
    $nodeCmd = (Get-Command node).Source
    $nextJs = Join-Path $Frontend 'node_modules\next\dist\bin\next'
    if ($Dev) {
      $nextArgs = @($nextJs, 'dev', '-p', "$FrontendPort")
    } else {
      if ($needBuild) {
        Write-Host 'Building the frontend (takes about a minute)...' -ForegroundColor Cyan
        & npm run build 2>&1 | Out-File (Join-Path $Logs 'build.log')
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed. See $Logs\build.log" }
        Set-Content -Path $stampFile -Value $ApiBase
      }
      $nextArgs = @($nextJs, 'start', '-p', "$FrontendPort")
    }
    Write-Host "Starting frontend on http://127.0.0.1:$FrontendPort ..." -ForegroundColor Cyan
    $f = Start-Process -FilePath $nodeCmd -ArgumentList $nextArgs -WorkingDirectory $Frontend -WindowStyle Hidden -PassThru `
      -RedirectStandardOutput (Join-Path $Logs 'frontend.out.log') -RedirectStandardError (Join-Path $Logs 'frontend.err.log')
    $started += $f
  } finally { Pop-Location }
  $url = "http://127.0.0.1:$FrontendPort"
  if (-not (Wait-Http $url 90)) { throw "The frontend did not come up. See $Logs\frontend.err.log" }

  Write-Host ''
  Write-Host '  Ledgerlight is running' -ForegroundColor Green
  Write-Host "  App      $url"
  Write-Host "  API      $ApiBase   (docs: $ApiBase/docs)"
  Write-Host "  E2E      `$env:FRONTEND_URL='$url'; npm --prefix frontend run check"
  Write-Host '  Press Ctrl+C to stop.'
  Write-Host ''
  if (-not $NoBrowser) { Start-Process $url }
  while ($true) {
    Start-Sleep -Seconds 2
    foreach ($p in $started) { if ($p.HasExited) { throw "A server process exited unexpectedly (pid $($p.Id)). See $Logs." } }
  }
} finally {
  foreach ($p in $started) { Stop-Tree $p }
  Write-Host 'Stopped.' -ForegroundColor Yellow
}
