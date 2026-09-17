# Start SustainZone EUDR Gateway locally (Windows PowerShell).
# If blocked, run once:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

docker info *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Docker is not running. Open Docker Desktop, wait for the engine to start, then run .\start.ps1 again." -ForegroundColor Yellow
  exit 1
}

Write-Host "Stopping any previous copy of the gateway..."
docker compose down *> $null

function Test-PortBusy([int]$p) {
  $c = New-Object System.Net.Sockets.TcpClient
  try { $c.Connect("127.0.0.1", $p); $c.Close(); return $true } catch { return $false }
}
$port = 8000
while (Test-PortBusy $port) {
  Write-Host "Port $port is used by another program - trying $($port + 1)."
  $port++
}
$env:APP_PORT = "$port"

Write-Host "Building and starting (first time takes a few minutes)..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Write-Host "Docker build failed - see messages above." -ForegroundColor Red; exit 1 }

Write-Host -NoNewline "Waiting for the app"
$ready = $false
for ($i = 0; $i -lt 120; $i++) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://localhost:$port/healthz/"
    if ($r.StatusCode -eq 200) { $ready = $true; break }
  } catch { }
  Write-Host -NoNewline "."
  Start-Sleep -Seconds 2
}
Write-Host ""
if (-not $ready) { Write-Host "App did not start. Logs:" -ForegroundColor Red; docker compose logs --tail 60 web; exit 1 }

$hasAdmin = (docker compose exec -T web python manage.py shell -c "from apps.accounts.models import User; print(User.objects.filter(role='sz_admin').exists())" | Select-Object -Last 1)
if ($hasAdmin -ne "True") {
  Write-Host "`nCreate your SustainZone Admin account:"
  $email = Read-Host "Email"
  $name = Read-Host "Full name"
  docker compose exec web python manage.py create_sz_admin --email $email --name $name
}

$url = "http://localhost:$port"
Write-Host "`nSustainZone EUDR Gateway is running at $url" -ForegroundColor Green
Write-Host "Stop it with .\stop.ps1"
Start-Process $url
