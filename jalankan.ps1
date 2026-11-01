# Jalankan pipeline Politik Islam Digital di Windows (PowerShell).
# Cara: klik kanan file ini -> "Run with PowerShell", atau di PowerShell:
#   cd $HOME\Documents\politik-islam-digital\pipeline ; powershell -ExecutionPolicy Bypass -File ..\jalankan.ps1
$ErrorActionPreference = "Stop"
Set-Location "$HOME\Documents\politik-islam-digital\pipeline"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "Python belum terpasang. Pasang dari https://www.python.org/downloads/ (centang 'Add to PATH'), lalu jalankan lagi." -ForegroundColor Red
  exit 1
}
python -m pip install --quiet requests pyyaml pytest
python -m pytest -q tests

if (-not $env:SCRAPECREATORS_API_KEY) {
  $env:SCRAPECREATORS_API_KEY = Read-Host "Tempel API key ScrapeCreators (tidak disimpan ke file)"
}
if (-not $env:ANON_SALT) {
  $saltFile = "$HOME\Documents\politik-islam-digital\ANON_SALT_RAHASIA.txt"
  if (-not (Test-Path $saltFile)) {
    $bytes = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    [Convert]::ToBase64String($bytes) | Out-File -Encoding ascii $saltFile
    Write-Host "Salt anonimisasi baru dibuat: $saltFile  -> SIMPAN CADANGANNYA; jangan dibagikan." -ForegroundColor Yellow
  }
  $env:ANON_SALT = (Get-Content $saltFile -Raw).Trim()
}

Write-Host "`n[1/3] verify (±16 kredit)" -ForegroundColor Cyan
python sc_pipeline.py verify
$ok = Read-Host "Cek data\processed\account_verification.csv. Lanjut collect? (y/n)"
if ($ok -ne "y") { exit 0 }

Write-Host "`n[2/3] collect (batas kredit: lihat budget di config.yaml)" -ForegroundColor Cyan
python sc_pipeline.py collect
Write-Host "`n[3/3] build" -ForegroundColor Cyan
python sc_pipeline.py build
Write-Host "`nSelesai. Kirim ke Claude: data\processed\sna_explorer.csv dan data\processed\audit_build.md" -ForegroundColor Green
