@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Mise a jour des probabilites de pole (quelques minutes)...
where python >nul 2>nul
if %errorlevel%==0 (
    set PY=python
) else (
    set PY="%USERPROFILE%\anaconda3\python.exe"
)
%PY% src\main.py --open
if errorlevel 1 (
    echo.
    echo Une erreur s'est produite. Verifie que Python est installe, puis lance :
    echo     pip install -r requirements.txt
)
pause
