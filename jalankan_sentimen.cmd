@echo off
cd /d "%USERPROFILE%\Documents\politik-islam-digital"
powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\Documents\politik-islam-digital\jalankan_sentimen.ps1" > "%USERPROFILE%\Documents\politik-islam-digital\log_sentimen.txt" 2>&1
