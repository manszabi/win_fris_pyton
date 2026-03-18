@echo off
echo ========================================
echo  RefreshSwitcher - Build
echo ========================================
echo.

:: Ellenorzes: PyInstaller telepitve van-e
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo PyInstaller nincs telepitve. Telepites...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo HIBA: Nem sikerult telepiteni a PyInstaller-t!
        pause
        exit /b 1
    )
)

echo PyInstaller build indul...
echo.

pyinstaller ^
    --onefile ^
    --noconsole ^
    --name "RefreshSwitcher" ^
    --add-data "config.json;." ^
    tray.py

if %errorlevel% neq 0 (
    echo.
    echo HIBA: A build nem sikerult!
    pause
    exit /b 1
)

:: config.json masolasa a dist mappaba
copy /Y config.json dist\config.json >nul

echo.
echo ========================================
echo  Build KESZ!
echo ========================================
echo.
echo A fajlok itt talalhatoak:
echo   dist\RefreshSwitcher.exe
echo   dist\config.json
echo.
echo Masold mindkettot egy mappaba es futtasd
echo a RefreshSwitcher.exe-t!
echo.
pause
