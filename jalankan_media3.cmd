@echo off
cd /d "%USERPROFILE%\Documents\politik-islam-digital"
powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\Documents\politik-islam-digital\jalankan_media3.ps1" > "%USERPROFILE%\Documents\politik-islam-digital\log_media3.txt" 2>&1
