@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

chcp 65001 >nul 2>&1

echo.
echo ========================================================
echo    Git Tag Trace - Setup y Arranque
echo ========================================================
echo.

:: -- Verificar Python
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    echo.
    echo Presiona una tecla para salir...
    pause >nul
    exit /b 1
)
echo [OK] Python encontrado.

:: -- Verificar/Install uv
python -m pip show uv >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] Instalando uv...
    pip install --quiet uv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] No se pudo instalar uv.
        echo.
        echo Presiona una tecla para salir...
        pause >nul
        exit /b 1
    )
    echo [OK] uv instalado.
)
echo [OK] uv disponible.

:: -- Crear .env si no existe
if not exist ".env" (
    echo [INFO] Creando archivo .env con valores por defecto...
    (
        echo # Configuracion del analizador Git
        echo REPO_PATH=C:\ruta\al\repositorio
        echo OUTPUT_FILE=reporte.md
    ) > .env
    echo [OK] Archivo .env creado. Editalo antes de continuar.
    echo.
    echo Presiona una tecla para salir...
    pause >nul
    exit /b 0
)

:: -- Leer .env
echo [INFO] Cargando variables desde .env...
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    set "line=%%A"
    if not "!line:~0,1!"=="#" (
        if not "%%A"=="" (
            set "%%A=%%B"
        )
    )
)

:: -- Validar REPO_PATH
if not defined REPO_PATH (
    echo [ERROR] REPO_PATH no esta definido en .env
    echo.
    echo Presiona una tecla para salir...
    pause >nul
    exit /b 1
)

if not defined OUTPUT_FILE set "OUTPUT_FILE="

:: -- Instalar sincronizar dependencias con uv
echo [INFO] Sincronizando dependencias con uv...
python -m uv sync --all-groups
if %ERRORLEVEL% neq 0 (
    echo [ERROR] No se pudieron instalar las dependencias.
    echo.
    echo Presiona una tecla para salir...
    pause >nul
    exit /b 1
)
echo [OK] Dependencias listas.

:: -- Verificar git
where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] git no encontrado en el PATH.
) else (
    echo [OK] git disponible en el PATH.
)

:: -- Ejecutar el script
echo.
echo [INFO] Ejecutando analisis sobre: %REPO_PATH%
echo.
echo ----------------------------------------------------
echo.

if defined OUTPUT_FILE (
    if not "%OUTPUT_FILE%"=="" (
        python -m uv run git-tag-trace "%REPO_PATH%" --output "%OUTPUT_FILE%"
    ) else (
        python -m uv run git-tag-trace "%REPO_PATH%"
    )
) else (
    python -m uv run git-tag-trace "%REPO_PATH%"
)

echo.
echo ----------------------------------------------------
echo.

if %ERRORLEVEL% equ 0 (
    echo [OK] Analisis completado exitosamente.
) else (
    echo [ERROR] El script finalizo con errores.
)

echo.
echo Presiona una tecla para salir...
pause >nul
endlocal
