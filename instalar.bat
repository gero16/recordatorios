@echo off
setlocal
cd /d "%~dp0"

echo === Instalador de Recordatorios ===
echo.

set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY where python >nul 2>&1 && set "PY=python"

if not defined PY (
  echo No se encontro Python. Instala Python 3.10+ desde https://www.python.org/downloads/
  echo Marca la opcion "Add python.exe to PATH" durante la instalacion.
  pause
  exit /b 1
)

set "PYEXE="
for /f "delims=" %%i in ('%PY% -c "import sys; print(sys.executable)"') do set "PYEXE=%%i"
for %%i in ("%PYEXE%") do set "PYW=%%~dpipythonw.exe"
if not exist "%PYW%" set "PYW=%PYEXE%"

echo [1/3] Instalando dependencias en %PYEXE% ...
"%PYEXE%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Error al instalar dependencias.
  pause
  exit /b 1
)

echo.
echo [2/3] Generando icono...
"%PYEXE%" -c "from tray import _create_icon_image as f; f().resize((256, 256)).save('icono.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)])"
if errorlevel 1 (
  echo Error al generar el icono.
  pause
  exit /b 1
)

echo.
echo [3/3] Creando acceso directo en el escritorio...
set "APPDIR=%~dp0"
if "%APPDIR:~-1%"=="\" set "APPDIR=%APPDIR:~0,-1%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$lnk = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Recordatorios.lnk');" ^
  "$lnk.TargetPath = $env:PYW;" ^
  "$lnk.Arguments = '\"' + $env:APPDIR + '\main.py\"';" ^
  "$lnk.WorkingDirectory = $env:APPDIR;" ^
  "$lnk.IconLocation = $env:APPDIR + '\icono.ico,0';" ^
  "$lnk.Save()"
if errorlevel 1 (
  echo Error al crear el acceso directo.
  pause
  exit /b 1
)

echo.
echo Listo. Ya tienes el icono "Recordatorios" en el escritorio.
pause
