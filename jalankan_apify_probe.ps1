# Apify: Instagram, YouTube, X (akun resmi partai). Mode: probe
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
python -u apify_collect.py probe
Write-Output "[SELESAI] $(Get-Date -Format s)"
