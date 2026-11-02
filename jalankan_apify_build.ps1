# Apify: build ulang + sentimen (tanpa pengambilan data baru)
$ErrorActionPreference = "Continue"
$base = "$env:USERPROFILE\Documents\politik-islam-digital"
$env:PYTHONIOENCODING = "utf-8"
Set-Location "$base\pipeline"
Write-Output "[mulai] $(Get-Date -Format s)"
$env:ANON_SALT = (Get-Content "$base\ANON_SALT_RAHASIA.txt" -Raw).Trim()
python -u apify_collect.py build
& "$env:USERPROFILE\pid-venv\Scripts\python.exe" -u sentiment.py data\processed\sna_apify.csv data\processed\sna_apify_sentimen.csv
Write-Output "[SELESAI] $(Get-Date -Format s)"
