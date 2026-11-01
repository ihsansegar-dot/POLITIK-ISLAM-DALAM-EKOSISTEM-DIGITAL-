# Analisis sentimen IndoBERT (+ RoBERTa pembanding). Memakai virtual env di jalur pendek
# (%USERPROFILE%\pid-venv) karena jalur Python Microsoft Store terlalu panjang untuk berkas PyTorch.
$ErrorActionPreference = "Continue"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$env:PYTHONIOENCODING = "utf-8"
$venv = "$env:USERPROFILE\pid-venv"
Write-Output "[mulai] $(Get-Date -Format s)"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
  Write-Output "[1/3] membuat virtual env $venv"
  python -m venv $venv
}
$py = "$venv\Scripts\python.exe"
Write-Output "[2/3] pasang PyTorch (CPU) + transformers ke venv"
& $py -m pip install --quiet --disable-pip-version-check --upgrade pip
& $py -m pip install --quiet --disable-pip-version-check torch --index-url https://download.pytorch.org/whl/cpu
& $py -m pip install --quiet --disable-pip-version-check transformers
& $py -c "import torch, transformers; print('torch', torch.__version__, '| transformers', transformers.__version__)"
Write-Output "[3/3] klasifikasi (unduh 2 model +-1 GB pada run pertama)"
Set-Location "$env:USERPROFILE\Documents\politik-islam-digital\pipeline"
& $py -u sentiment.py data\processed\dashboard_input.csv data\processed\dashboard_sentimen.csv
Write-Output "[SELESAI] $(Get-Date -Format s)"
