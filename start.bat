@echo off
echo Quiz Bot va Web Admin Panel ishga tushmoqda...

start cmd /k "venv\Scripts\python.exe main_flask.py"
timeout /t 2 /nobreak > nul
start cmd /k "venv\Scripts\python.exe main_bot.py"

echo Dasturlar alohida oynalarda ishga tushdi!
