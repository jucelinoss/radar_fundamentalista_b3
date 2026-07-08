@echo off
echo ===================================================
echo   Radar Fundamentalista B3 - Inicializador
echo ===================================================
echo.

:: Check if virtual environment exists
if not exist ".venv" (
    echo [ERROR] Ambiente virtual .venv nao encontrado!
    echo Por favor, crie o ambiente virtual e instale as dependencias primeiro:
    echo python -m venv .venv
    echo .\.venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo 1/2 Atualizando data.json com dados locais (VPA, ...) sem API...
.\.venv\Scripts\python.exe src/pipeline.py --generate-only
echo.

echo 2/2 Iniciando o servidor local na porta 8000...
echo Acesse: http://127.0.0.1:8000/index.html
echo.

:: Open browser after a short delay (2 seconds) to let server start
start /b cmd /c "timeout /t 2 >nul && start http://127.0.0.1:8000/index.html"

:: Run the server using python in .venv
.\.venv\Scripts\python.exe src/server.py

pause
