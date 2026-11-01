# Media online 2024-kini: sitemap resmi media -> GDELT 3 bulan terakhir -> ambil teks (Scrapling) -> ekspor
$ErrorActionPreference = "Continue"
Set-Location "$env:USERPROFILE\Documents\politik-islam-digital\pipeline"
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py).Source }
Write-Output "[mulai] $(Get-Date -Format s)"
Write-Output "[1/4] sitemaps (8 media paralel, +-1 jam)"
& $py -u news_scrapling.py sitemaps
Write-Output "[2/4] GDELT 3 bulan terakhir"
& $py -u news_scrapling.py discover
Write-Output "[3/4] fetch teks (sampel 15/partai/bulan)"
& $py -u news_scrapling.py fetch
Write-Output "[4/4] export"
& $py -u news_scrapling.py export
Write-Output "[SELESAI] $(Get-Date -Format s)"
