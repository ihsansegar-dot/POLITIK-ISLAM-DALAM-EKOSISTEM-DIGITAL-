# Instagram, YouTube, X (Jan 2024 - sekarang) via ScrapeCreators -> build -> sentimen. Tanpa TikTok & media online.
# Batas: 400 kredit per akun (IG, YT), X = 1 panggilan per akun; total maks 4.800 kredit. Bisa dijalankan ulang.
$ErrorActionPreference = "Continue"
$base = "$env:USERPROFILE\Documents\politik-islam-digital"
$env:PYTHONIOENCODING = "utf-8"
Set-Location "$base\pipeline"
Write-Output "[mulai] $(Get-Date -Format s)"
$keyFile = "$base\SCRAPECREATORS_KEY.txt"
if (-not (Test-Path $keyFile)) { Write-Output "BERHENTI: berkas SCRAPECREATORS_KEY.txt belum ada di $base (isi satu baris: API key)."; exit 1 }
$env:SCRAPECREATORS_API_KEY = (Get-Content $keyFile -Raw).Trim()
$env:ANON_SALT = (Get-Content "$base\ANON_SALT_RAHASIA.txt" -Raw).Trim()   # salt sama -> ID pseudonim konsisten dengan sampel TikTok
python -m pip install --quiet --disable-pip-version-check requests pyyaml
Write-Output "[1/3] collect-monthly: X (tweet populer) + feed IG/YT + sampel 5 post/bulan + komentar"
python -u sc_pipeline.py collect-monthly
Write-Output "[2/3] build"
python -u sc_pipeline.py build
Write-Output "[3/3] sentimen (IndoBERT + RoBERTa)"
& "$env:USERPROFILE\pid-venv\Scripts\python.exe" -u sentiment.py data\processed\sna_explorer.csv data\processed\sna_sosmed_sentimen.csv
Write-Output "[SELESAI] $(Get-Date -Format s)"
