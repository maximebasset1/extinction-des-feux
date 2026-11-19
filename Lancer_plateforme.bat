@echo off
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (set PY=python) else (set PY="%USERPROFILE%\anaconda3\python.exe")
%PY% lancer.py
echo.
echo Fenetre a fermer (la plateforme est arretee).
pause
