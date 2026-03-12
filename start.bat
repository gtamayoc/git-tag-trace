@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo ╔══════════════════════════════════════════════════╗
echo ║      Git Analyzer — Setup y Arranque            ║
echo ╚══════════════════════════════════════════════════╝
echo.

:: ── Verificar Python
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python no está instalado o no está en el PATH.
    echo         Descárgalo desde https://python.org
    pause
    exit /b 1
)

:: ── Crear .env si no existe
if not exist ".env" (
    echo [INFO] Creando archivo .env con valores por defecto...
    (
        echo # Configuracion del analizador Git
        echo REPO_PATH=C:\ruta\al\repositorio
        echo OUTPUT_FILE=reporte.md
        echo VENV_DIR=.venv
    ) > .env
    echo [OK] Archivo .env creado. Edítalo antes de continuar.
    echo.
)

:: ── Leer .env
echo [INFO] Cargando variables desde .env...
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    set "line=%%A"
    if not "!line:~0,1!"=="#" (
        if not "%%A"=="" (
            set "%%A=%%B"
        )
    )
)

:: ── Validar REPO_PATH
if not defined REPO_PATH (
    echo [ERROR] REPO_PATH no está definido en .env
    pause
    exit /b 1
)

if not defined VENV_DIR set "VENV_DIR=.venv"
if not defined OUTPUT_FILE set "OUTPUT_FILE="

:: ── Crear entorno virtual si no existe
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [INFO] Creando entorno virtual en '%VENV_DIR%'...
    python -m venv "%VENV_DIR%"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
    echo [OK] Entorno virtual creado.
)

:: ── Activar entorno virtual
echo [INFO] Activando entorno virtual...
call "%VENV_DIR%\Scripts\activate.bat"

:: ── Instalar dependencias
echo [INFO] Instalando/verificando dependencias...
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] No se pudieron instalar las dependencias básicas.
    pause
    exit /b 1
)
echo [OK] Dependencias listas.

:: ── Verificar git (requerido por GitSearch para búsqueda avanzada)
where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] git no encontrado en el PATH. GitSearch operara en modo degradado.
) else (
    echo [OK] git disponible en el PATH.
)

:: ── Ejecutar el script
echo.
echo [INFO] Ejecutando análisis sobre: %REPO_PATH%
echo.

if defined OUTPUT_FILE (
    if not "%OUTPUT_FILE%"=="" (
        python main.py "%REPO_PATH%" --output "%OUTPUT_FILE%"
    ) else (
        python main.py "%REPO_PATH%"
    )
) else (
    python main.py "%REPO_PATH%"
)

echo.
if %ERRORLEVEL% equ 0 (
    echo [OK] Análisis completado exitosamente.
) else (
    echo [ERROR] El script finalizó con errores. Revisa la salida anterior.
)

pause
endlocal