@echo off
setlocal

:: ============================================================================
:: Project Setup Script
:: ============================================================================
:: This script will:
:: 1. Check for FFmpeg, Conda, and Python installations.
:: 2. Check if the 'yak-ffmpeg-env' Conda environment exists.
:: 3. If it doesn't exist, it creates it and installs Python requirements.
:: 4. Installs Node.js dependencies.
:: 5. Builds the TypeScript project.
:: ============================================================================

set "ENV_NAME=yak-ffmpeg-env"

echo.
echo [INFO] Starting environment setup...
echo =================================================

:: --- 1. Check for FFmpeg ---
echo [CHECK] Checking for FFmpeg...
where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] FFmpeg not found in your system's PATH.
    echo Please install it from https://ffmpeg.org/download.html and add it to your PATH.
    echo.
) else (
    echo [OK] FFmpeg is installed.
    echo.
)

:: --- 2. Check for Conda ---
echo [CHECK] Checking for Conda...
where conda >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Conda is not installed or not in your PATH.
    echo Please install Anaconda/Miniconda from https://www.anaconda.com/products/distribution
    pause
    exit /b 1
) else (
    echo [OK] Conda is installed.
    echo.
)

:: --- 3. Check for Python ---
echo [CHECK] Checking for a Python installation...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] No global Python found. This is usually fine as we will use a Conda environment.
    echo.
) else (
    echo [OK] A Python installation was found.
    echo.
)

:: --- 4. Check for and Create Conda Environment ---
echo [CHECK] Checking for Conda environment: %ENV_NAME%...
conda env list | findstr /C:"%ENV_NAME%" >nul
if %errorlevel% equ 0 (
    echo [OK] Conda environment '%ENV_NAME%' already exists. Skipping creation.
    echo.
) else (
    echo [INFO] Environment not found. Creating '%ENV_NAME%' now...
    conda create --name %ENV_NAME% python=3.10 -y
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create Conda environment.
        pause
        exit /b 1
    )
    echo [INFO] Environment created. Activating and installing Python packages...
    call conda.bat activate %ENV_NAME%
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install pip requirements.
        pause
        exit /b 1
    )
    call conda.bat deactivate
    echo [OK] Python requirements installed successfully.
    echo.
)

:: --- 5. Install Node.js Dependencies ---
echo [INFO] Installing Node.js dependencies...
npm install
if %errorlevel% neq 0 (
    echo [ERROR] 'npm install' failed. Please check your package.json and Node.js installation.
    pause
    exit /b 1
)
echo [OK] Node.js dependencies installed.
echo.

:: --- 6. Build the TypeScript Project ---
echo [INFO] Building the TypeScript project...
npm run build
if %errorlevel% neq 0 (
    echo [ERROR] 'npm run build' failed. Please check your TypeScript code for errors.
    pause
    exit /b 1
)
echo [OK] TypeScript project built successfully.
echo.

:: --- 7. Completion ---
echo =================================================
echo [SUCCESS] All setup steps completed successfully!
echo =================================================
echo.
pause