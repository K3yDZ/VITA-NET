# Tek tikla VITA-NET (PowerShell)
Set-Location $PSScriptRoot
$py = if (Test-Path "venv\Scripts\python.exe") { "venv\Scripts\python.exe" }
      elseif (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" }
      else { "python" }
& $py start.py
if ($LASTEXITCODE -ne 0) { Read-Host "Hata ile bitti — kapatmak icin Enter" }
