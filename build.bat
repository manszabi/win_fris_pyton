@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo  RefreshSwitcher - Build
echo ========================================
echo.

REM Ha van virtualis kornyezet (telepites.bat), abban dolgozunk -- igy a
REM build ugyanazokat a csomagverziokat hasznalja, mint a futo program.
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
echo Hasznalt Python: %PY%
echo.

"%PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if errorlevel 1 (
    echo HIBA: Python 3.10 vagy ujabb szukseges.
    echo Futtasd eloszor a telepites.bat fajlt.
    pause
    exit /b 1
)

echo Fuggosegek ellenorzese...
"%PY%" -m pip install --quiet --upgrade pip
"%PY%" -m pip install --quiet -r requirements.txt pyinstaller
if errorlevel 1 (
    echo HIBA: Nem sikerult telepiteni a fuggosegeket!
    pause
    exit /b 1
)

echo Tesztek futtatasa...
"%PY%" -m pytest -q
if errorlevel 1 (
    echo.
    echo FIGYELEM: a tesztek nem futottak le hibatlanul.
    choice /c IN /m "Folytatod a buildet? [I]gen / [N]em"
    if errorlevel 2 exit /b 1
)

echo.
echo PyInstaller build indul...
rmdir /s /q build 2>nul
"%PY%" -m PyInstaller --noconfirm --clean RefreshSwitcher.spec
if errorlevel 1 (
    echo.
    echo HIBA: A build nem sikerult!
    pause
    exit /b 1
)

:: A meglevo config.json-t NEM irjuk felul - az a felhasznalo beallitasa.
if not exist "dist\config.json" (
    copy /Y config.json "dist\config.json" >nul
    echo Alapertelmezett config.json kimasolva a dist mappaba.
) else (
    echo A dist\config.json mar letezik, valtozatlanul hagyva.
)

echo.
echo ========================================
echo  Build KESZ!
echo ========================================
echo.
echo   dist\RefreshSwitcher.exe
echo   dist\config.json
echo.
echo Masold mindkettot egy irhato mappaba (NE a Program Files ala),
echo es futtasd a RefreshSwitcher.exe-t.
echo.
pause
