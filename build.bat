@echo off
REM ============================================================
REM  Build do DUDAIR-PDV: gera o executavel Windows com PyInstaller
REM  Uso: apenas de-clique duas vezes neste arquivo (ou rode no cmd)
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo ==================================================
echo   DUDAIR-PDV - Build do executavel
echo ==================================================
echo.

echo [1/5] Instalando dependencias (requirements.txt)...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo [2/5] Limpando builds antigos...
set "DATA_BACKUP=%TEMP%\DUDAIR-PDV-data-backup"
if exist "%DATA_BACKUP%" rmdir /s /q "%DATA_BACKUP%"
if exist "dist\DUDAIR-PDV\data" (
    echo     Preservando banco de dados portatil existente...
    mkdir "%DATA_BACKUP%" >nul 2>&1
    xcopy "dist\DUDAIR-PDV\data" "%DATA_BACKUP%\" /E /I /Y >nul
)
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "DUDAIR-PDV.spec" del /q "DUDAIR-PDV.spec"

echo.
echo [3/5] Gerando executavel com PyInstaller (isso pode demorar alguns minutos)...
python -m PyInstaller --noconfirm --windowed --name "DUDAIR-PDV" ^
    --icon "assets\icons\app.ico" ^
    --add-data "assets;assets" ^
    --add-data "webapp;webapp" ^
    --collect-all uvicorn ^
    --collect-all fastapi ^
    --collect-all starlette ^
    --collect-all websockets ^
    main.py
if errorlevel 1 goto :error

echo.
echo [4/5] Preparando pasta de dados portatil...
if not exist "dist\DUDAIR-PDV\data" mkdir "dist\DUDAIR-PDV\data"
if exist "%DATA_BACKUP%" (
    echo     Restaurando banco de dados portatil preservado...
    xcopy "%DATA_BACKUP%" "dist\DUDAIR-PDV\data\" /E /I /Y >nul
    rmdir /s /q "%DATA_BACKUP%"
)

echo.
echo [5/5] Build concluido com sucesso!
echo.
echo   Executavel: dist\DUDAIR-PDV\DUDAIR-PDV.exe
echo.
echo   MODO PORTATIL: copie a pasta "dist\DUDAIR-PDV" inteira para um
echo   pendrive e execute DUDAIR-PDV.exe em qualquer computador Windows.
echo.
echo   MODO INSTALADOR: abra installer\setup.iss no Inno Setup Compiler
echo   e clique em Compile para gerar "DUDAIR-PDV Setup.exe".
echo.
goto :eof

:error
echo.
if exist "%DATA_BACKUP%" (
    echo Restaurando banco de dados portatil preservado apos falha...
    if not exist "dist\DUDAIR-PDV\data" mkdir "dist\DUDAIR-PDV\data"
    xcopy "%DATA_BACKUP%" "dist\DUDAIR-PDV\data\" /E /I /Y >nul
    rmdir /s /q "%DATA_BACKUP%"
)
echo *** ERRO NO BUILD - verifique as mensagens acima ***
exit /b 1
