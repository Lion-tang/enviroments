@echo off
REM Enviroments - Build Script for Windows
REM Prerequisites: Python 3.9+, Node.js, pnpm, and backend/requirements-build.txt

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 (
    echo ERROR: Python 3.9 or newer is required.
    exit /b 1
)

echo Building frontend...
cd /d "%~dp0frontend"
call pnpm install
call pnpm run build

echo Building Windows executable...
cd /d "%~dp0backend"
python -m PyInstaller Enviroments.spec --noconfirm --clean --distpath "%~dp0dist" --workpath "%~dp0build"
cd /d "%~dp0"

echo.
echo ========================================
echo Build complete!
echo Output: dist\Enviroments\
echo.
echo Run: dist\Enviroments\Enviroments.exe
echo ========================================
