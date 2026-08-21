@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  RefreshSwitcher - Eltavolitas
echo ========================================
echo.

set "VPY=.venv\Scripts\python.exe"
if exist "%VPY%" goto run
REM venv nelkul is mukodik: az eltavolitashoz nem kell egyetlen kulso csomag sem.
set "VPY=python"

:run
"%VPY%" -m refreshswitcher remove
echo.
echo A .venv mappa es a config.json megmaradt.
echo Ha ezeket is torolni akarod, egyszeruen tordold a projekt mappat.
echo.
pause
