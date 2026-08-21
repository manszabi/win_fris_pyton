@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  RefreshSwitcher - Telepites
echo ========================================
echo.

set "VENV=.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "FORCE="
set "ELEVATED="

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="frissit"  set "FORCE=1"
if /i "%~1"=="admin"    set "ELEVATED=--elevated"
shift
goto parse_args
:args_done

REM --- 1. Python megkeresese --------------------------------------------
REM A "py" launcher az elsodleges: a puszta "python" a Microsoft Store
REM helyorzoje lehet, ami megnyitja a Store-t es nem csinal semmit.
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto python_ok

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto python_ok

echo HIBA: nem talalhato Python 3.10 vagy ujabb.
echo.
echo Toltsd le innen: https://www.python.org/downloads/
echo Telepiteskor jelold be az "Add Python to PATH" opciot.
echo.
pause
exit /b 1
:python_ok
echo [1/4] Python megvan.

REM --- 2. Virtualis kornyezet -------------------------------------------
REM Sajat .venv mappa: a csomagok nem keverednek mas programokeval, es a
REM rendszer Pythonja erintetlen marad.
if not exist "%VPY%" goto venv_create

REM A meglevo venv is lehet hasznalhatatlan (pl. ha a rendszer Pythonjat
REM azota eltavolitottad vagy frissitetted) -- ilyenkor ujraepitjuk.
"%VPY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto venv_ok
echo [2/4] A meglevo virtualis kornyezet hasznalhatatlan, ujraepites...
if exist "%VENV%\Scripts" rmdir /s /q "%VENV%"
goto venv_create_quiet

:venv_create
echo [2/4] Virtualis kornyezet letrehozasa a(z) %VENV% mappaban...
:venv_create_quiet
%PY% -m venv "%VENV%"
if errorlevel 1 goto venv_failed
if not exist "%VPY%" goto venv_failed
goto venv_ok

:venv_failed
echo.
echo HIBA: nem sikerult letrehozni a virtualis kornyezetet a(z)
echo   %CD%\%VENV%
echo mappaban. Ha a projekt OneDrive ala esik, vagy a mappa csak olvashato,
echo helyezd at egy sima helyi mappaba (pl. C:\RefreshSwitcher).
echo.
pause
exit /b 1

:venv_ok
echo [2/4] Virtualis kornyezet keszen all.

REM --- 3. Fuggosegek ----------------------------------------------------
if defined FORCE goto install_deps
"%VPY%" -c "import psutil, pystray, PIL, win32api" >nul 2>&1
if not errorlevel 1 goto deps_ok
:install_deps
echo [3/4] Fuggosegek telepitese (elso alkalommal eltarthat egy percig)...
"%VPY%" -m pip install --upgrade --quiet pip
"%VPY%" -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto deps_failed

:deps_ok
REM A pywin32 kulon ellenorzest erdemel: a DLL-jei nem mindig toltodnek be
REM elsore, es enelkul a program nem tudja allitani a kijelzot.
"%VPY%" -c "import win32api" >nul 2>&1
if errorlevel 1 goto pywin32_failed
echo [3/4] Fuggosegek rendben.
goto do_install

:deps_failed
echo.
echo HIBA: nem sikerult telepiteni a fuggosegeket.
echo Ellenorizd az internetkapcsolatot, majd futtasd ujra ezt a fajlt.
echo.
pause
exit /b 1

:pywin32_failed
echo.
echo HIBA: a pywin32 nem toltodott be. Probald meg ezt a parancsot:
echo   "%VPY%" -m pywin32_postinstall -install
echo.
pause
exit /b 1

REM --- 4. Automatikus inditas -------------------------------------------
:do_install
echo [4/4] Task Scheduler feladat letrehozasa es inditas...
echo.
REM A venv Pythonjaval futtatjuk, ezert az utemezett feladat is a venv
REM pythonw.exe-jere fog mutatni -- nem a rendszer Pythonjara.
"%VPY%" -m refreshswitcher install %ELEVATED%
if errorlevel 1 goto task_failed

echo.
echo ========================================
echo  KESZ
echo ========================================
echo.
echo A RefreshSwitcher fut, es minden bejelentkezeskor elindul.
echo Az ora melletti tray ikonon lathato a jelenlegi Hz.
echo.
echo Beallitasok:  config.json  (a program menet kozben ujraolvassa)
echo Eltavolitas:  eltavolitas.bat
echo.
pause
exit /b 0

:task_failed
echo.
echo A feladat letrehozasa nem sikerult.
echo Ha "Access is denied" hibat lattal, inditsd ezt a fajlt
echo jobb klikk -^> "Futtatas rendszergazdakent" modon.
echo.
pause
exit /b 1
