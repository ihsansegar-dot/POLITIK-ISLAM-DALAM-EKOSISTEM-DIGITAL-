@echo off
cd /d "%USERPROFILE%\Documents\politik-islam-digital"
powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\Documents\politik-islam-digital\jalankan_apify_build.ps1" > "%USERPROFILE%\Documents\politik-islam-digital\log_apify_build.txt" 2>&1
