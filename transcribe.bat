@echo off
REM ---------------------------------------------------------------------------
REM  audio_transcriber - drag a recording onto this file, or just double-click it
REM  to transcribe everything sitting in the recordings folder.
REM ---------------------------------------------------------------------------

setlocal

set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "RECORDINGS=%ROOT%recordings"
set "OUTPUT=%ROOT%transcripts"

REM --- first run: create the virtual environment -----------------------------
if not exist "%VENV%\Scripts\python.exe" (
    echo First run detected. Creating virtual environment...
    python -m venv "%VENV%"
    if errorlevel 1 goto :no_python
    "%VENV%\Scripts\python.exe" -m pip install --upgrade pip
    "%VENV%\Scripts\python.exe" -m pip install -r "%ROOT%requirements.txt"
    echo.
)

REM --- ffmpeg is required for multi-track extraction -------------------------
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo WARNING: ffmpeg was not found on PATH.
    echo Multi-track recordings cannot be split without it.
    echo Download: https://ffmpeg.org/download.html
    echo.
)

REM --- files dropped onto the .bat take priority -----------------------------
if not "%~1"=="" (
    "%VENV%\Scripts\python.exe" "%ROOT%audio_transcriber.py" %* -o "%OUTPUT%"
    goto :done
)

REM --- otherwise process the whole recordings folder -------------------------
if not exist "%RECORDINGS%" mkdir "%RECORDINGS%"
"%VENV%\Scripts\python.exe" "%ROOT%audio_transcriber.py" "%RECORDINGS%" -o "%OUTPUT%"

:done
echo.
echo Transcripts are in: %OUTPUT%
pause
exit /b 0

:no_python
echo.
echo Python was not found. Install Python 3.10 or newer and tick
echo "Add Python to PATH" during setup: https://www.python.org/downloads/
pause
exit /b 1
