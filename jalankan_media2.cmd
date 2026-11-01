@echo off
cd /d "%USERPROFILE%\Documents\politik-islam-digital"
powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\Documents\politik-islam-digital\jalankan_media2.ps1" > "%USERPROFILE%\Documents\politik-islam-digital\log_media2.txt" 2>&1
echo Selesai. Lihat log_media2.txt
