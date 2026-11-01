# Media online 2024-kini (tanpa media sosial):
#   arsip halaman indeks per tanggal -> sitemap (terbaru) -> GDELT 3 bulan terakhir -> teks sampel (Scrapling) -> ekspor
$ErrorActionPreference = "Continue"
Set-Location "$env:USERPROFILE\Documents\politik-islam-digital\pipeline"
Write-Output "[mulai] $(Get-Date -Format s)"
python -m pip install --quiet --disable-pip-version-check protego "scrapling[fetchers]" requests pyyaml
# sekali: hapus catatan sitemap dari run 2 Nov 01:12 (robots.txt salah baca); artikel tetap
python -c "import json,pathlib; p=pathlib.Path('data/media_state.json'); s=json.loads(p.read_text(encoding='utf-8')); s.pop('sitemap_seen',None); p.write_text(json.dumps(s,ensure_ascii=False),encoding='utf-8'); print('[reset] sitemap_seen dihapus')"
Write-Output "[1/5] indeks arsip: liputan6, detik, cnnindonesia, kompas (4 hari sampel/bulan, +-2 jam)"
python -u news_scrapling.py indeks
Write-Output "[2/5] sitemaps (artikel terbaru)"
python -u news_scrapling.py sitemaps
Write-Output "[3/5] GDELT 3 bulan terakhir"
python -u news_scrapling.py discover
Write-Output "[4/5] fetch teks (sampel 15/partai/bulan)"
python -u news_scrapling.py fetch
Write-Output "[5/5] export"
python -u news_scrapling.py export
Write-Output "[SELESAI] $(Get-Date -Format s)"
