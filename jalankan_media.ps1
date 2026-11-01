# Media online tentang PKS, PKB, PPP, PAN (Jan 2024 - sekarang) dengan GDELT + Scrapling.
# Klik kanan -> Run with PowerShell. Bisa dihentikan dan dijalankan ulang; kemajuan disimpan.
$ErrorActionPreference = "Stop"
Set-Location "$HOME\Documents\politik-islam-digital\pipeline"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-Host "Python belum terpasang: https://www.python.org/downloads/ (centang Add to PATH)" -ForegroundColor Red; exit 1 }
python -m pip install --quiet "scrapling[fetchers]" requests pyyaml
Write-Host "[1/3] discover: GDELT, 4 partai x bulan (+-15 menit karena jeda wajib 6 detik)" -ForegroundColor Cyan
python news_scrapling.py discover
Write-Host "[2/3] fetch: teks artikel (sampel 15/partai/bulan, jeda 3 detik per situs; bisa beberapa jam)" -ForegroundColor Cyan
python news_scrapling.py fetch
Write-Host "[3/3] export" -ForegroundColor Cyan
python news_scrapling.py export
Write-Host "Selesai. Tulis 'media selesai' ke Claude untuk memasang data ke dashboard." -ForegroundColor Green
