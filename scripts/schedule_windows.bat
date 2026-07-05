@echo off
REM ============================================================
REM  Schedule daily pipeline execution via Windows Task Scheduler
REM ============================================================
echo.
echo ===================================================
echo  Agendando Pipeline B3 - Windows Task Scheduler
echo ===================================================
echo.

:: Find Python in the virtual environment
set "PYTHON_EXE=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python virtual environment not found at:
    echo        %PYTHON_EXE%
    echo.
    echo Please create it first:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

set "PIPELINE_SCRIPT=%~dp0..\src\pipeline.py"
set "TASK_NAME=B3ScreenerPipeline"

echo Python:    %PYTHON_EXE%
echo Script:    %PIPELINE_SCRIPT%
echo Task Name: %TASK_NAME%
echo.
echo This will schedule the pipeline to run daily at 08:00.
echo.

schtasks /Create /F ^
    /TN "%TASK_NAME%" ^
    /TR "\"%PYTHON_EXE%\" \"%PIPELINE_SCRIPT%\"" ^
    /SC DAILY ^
    /ST 08:00 ^
    /RL HIGHEST

if %ERRORLEVEL% equ 0 (
    echo.
    echo ✅ Task scheduled successfully!
    echo    The pipeline will run daily at 08:00.
    echo.
    echo To verify:  schtasks /Query /TN "%TASK_NAME%"
    echo To remove:  schtasks /Delete /TN "%TASK_NAME%" /F
) else (
    echo.
    echo ❌ Failed to schedule task. Try running as Administrator.
)

pause
