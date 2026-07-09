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

start /B "" python src/server.py

timeout /t 3 >nul
start http://localhost:8000/index-v2.html

python src/server.py
