# Apify: Instagram, YouTube, X (akun resmi partai). Mode: full
$ErrorActionPreference = "Continue"
$base = "$env:USERPROFILE\Documents\politik-islam-digital"
$env:PYTHONIOENCODING = "utf-8"
Set-Location "$base\pipeline"
Write-Output "[mulai] $(Get-Date -Format s)"
$tok = "$base\APIFY_TOKEN.txt"
if (-not (Test-Path $tok)) { Write-Output "BERHENTI: berkas APIFY_TOKEN.txt belum ada di $base (isi satu baris: token Apify)."; exit 1 }
$env:APIFY_TOKEN = (Get-Content $tok -Raw).Trim()
$env:ANON_SALT = (Get-Content "$base\ANON_SALT_RAHASIA.txt" -Raw).Trim()
python -m pip install --quiet --disable-pip-version-check apify-client pyyaml
Write-Output "[1/3] collect (batas biaya di config.yaml: apify.max_usd)"
python -u apify_collect.py collect
Write-Output "[2/3] build"
python -u apify_collect.py build
Write-Output "[3/3] sentimen"
& "$env:USERPROFILE\pid-venv\Scripts\python.exe" -u sentiment.py data\processed\sna_apify.csv data\processed\sna_apify_sentimen.csv
Write-Output "[SELESAI] $(Get-Date -Format s)"
