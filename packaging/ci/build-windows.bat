@echo off
REM build-windows.bat — Build VinaStudio for Windows
REM
REM Produces:
REM   dist\vinastudio-X.Y.Z-setup.exe
REM
REM Prerequisites:
REM   - Python 3.12 (on PATH)
REM   - pnpm (for frontend build)
REM   - Inno Setup 6.3+ (ISCC.exe on PATH)
REM   - icon.ico in packaging\windows\
REM
REM Usage:
REM   packaging\ci\build-windows.bat

setlocal enabledelayedexpansion

cd /d "%~dp0\..\.."
echo ==> Building VinaStudio

REM ---------------------------------------------------------------------------
REM 1. Read version from pyproject.toml
REM ---------------------------------------------------------------------------
for /f "tokens=2 delims==" %%a in ('findstr /r "^version" pyproject.toml') do (
    set "RAW=%%a"
    set "VERSION=!RAW: =!"
    set "VERSION=!VERSION:"=!"
)
echo    Version: %VERSION%

REM ---------------------------------------------------------------------------
REM 2. Create virtual environment
REM ---------------------------------------------------------------------------
set "VENV_DIR=.venv-build"
if exist "%VENV_DIR%" (
    echo ==> Removing old build venv
    rmdir /s /q "%VENV_DIR%"
)

echo ==> Creating virtual environment in %VENV_DIR%
python -m venv "%VENV_DIR%"
call "%VENV_DIR%\Scripts\activate.bat"

REM ---------------------------------------------------------------------------
REM 3. Install Python dependencies + PyInstaller
REM ---------------------------------------------------------------------------
echo ==> Installing Python dependencies
pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
pip install pyinstaller

REM ---------------------------------------------------------------------------
REM 4. Build frontend
REM ---------------------------------------------------------------------------
echo ==> Building frontend
python scripts\build_web.py

REM ---------------------------------------------------------------------------
REM 5. Run PyInstaller
REM ---------------------------------------------------------------------------
echo ==> Running PyInstaller
pyinstaller ^
    --name vinastudio ^
    --onedir ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --noconsole ^
    --add-data "vinastudio\server\static;vinastudio\server\static" ^
    --add-data "vinastudio\resources;vinastudio\resources" ^
    --hidden-import "vinastudio.server.app" ^
    --hidden-import "uvicorn.logging" ^
    --hidden-import "uvicorn.loops" ^
    --hidden-import "uvicorn.loops.auto" ^
    --hidden-import "uvicorn.protocols" ^
    --hidden-import "uvicorn.protocols.http" ^
    --hidden-import "uvicorn.protocols.http.auto" ^
    --hidden-import "uvicorn.protocols.websockets" ^
    --hidden-import "uvicorn.protocols.websockets.auto" ^
    --hidden-import "uvicorn.lifespan" ^
    --hidden-import "uvicorn.lifespan.on" ^
    vinastudio\__main__.py

if %errorlevel% neq 0 (
    echo ERROR: PyInstaller failed
    exit /b 1
)

REM ---------------------------------------------------------------------------
REM 6. Generate icon.ico if missing
REM ---------------------------------------------------------------------------
if not exist "packaging\windows\icon.ico" (
    echo ==> Generating icon.ico from SVG
    pip install cairosvg Pillow
    python packaging\ci\generate_icons.py
)

REM ---------------------------------------------------------------------------
REM 7. Run Inno Setup Compiler
REM ---------------------------------------------------------------------------
echo ==> Running Inno Setup Compiler
set "ISCC=ISCC.exe"
where %ISCC% >nul 2>&1
if %errorlevel% neq 0 (
    REM Try common install location
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if not exist "!ISCC!" (
        echo ERROR: Inno Setup Compiler (ISCC.exe) not found on PATH
        echo        Install from https://jrsoftware.org/isdl.php
        exit /b 1
    )
)

"!ISCC!" /DVERSION=%VERSION% packaging\windows\vinastudio.iss

if %errorlevel% neq 0 (
    echo ERROR: Inno Setup compilation failed
    exit /b 1
)

REM ---------------------------------------------------------------------------
REM 8. Summary
REM ---------------------------------------------------------------------------
echo.
echo ==^> Build complete!
echo     dist\vinastudio-%VERSION%-setup.exe
echo.

deactivate
endlocal
