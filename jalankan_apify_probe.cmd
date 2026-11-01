@echo off
cd /d "%USERPROFILE%\Documents\politik-islam-digital"
powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\Documents\politik-islam-digital\jalankan_apify_probe.ps1" > "%USERPROFILE%\Documents\politik-islam-digital\log_apify_probe.txt" 2>&1
