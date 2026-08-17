@echo off
title Radar Fundamentalista B3
cd /d "%~dp0"

echo ============================================
echo  Radar Fundamentalista B3
echo ============================================
echo.
echo 1/2 Atualizando data.json com dados locais (VPA, ...) sem API...
python src/pipeline.py --generate-only
echo.

echo 2/2 Iniciando servidor em http://localhost:8000
echo Pressione CTRL+C para parar
echo.

timeout /t 2 >nul
start http://localhost:8000/

python src/server.py
