@echo off
rem Збірка "Накази ШКОЛА": build.bat [notest] [trust] [noinstaller]
chcp 65001 >nul
cd /d "%~dp0"
python tools/build.py %*
exit /b %errorlevel%
