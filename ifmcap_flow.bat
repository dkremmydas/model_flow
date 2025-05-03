@echo off
:: ifmcap_flow.bat - Python wrapper for IFMCAP Flow
:: Usage: ifmcap_flow [command] [arguments]

setlocal

:: Configure Python executable (edit if needed)
set PYTHON_EXE=python

:: Verify Python is available
%PYTHON_EXE% --version >nul 2>&1 || (
    echo Error: Python not found at %PYTHON_EXE%
    echo Please either:
    echo 1. Edit PYTHON_EXE in this script, or
    echo 2. Add Python to your system PATH
    pause
    exit /b 1
)

:: Pass all arguments to the Python module
%PYTHON_EXE% -m ifmcap_flow %*

:: Preserve the exit code
exit /b %ERRORLEVEL%