@echo off
cd /d "%~dp0"

set "PY="
set "PYW="
where py >nul 2>&1 && set "PY=py"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PY=%LocalAppData%\Programs\Python\Python313\python.exe"

if exist "%LocalAppData%\Programs\Python\Python312\pythonw.exe" set "PYW=%LocalAppData%\Programs\Python\Python312\pythonw.exe"
if not defined PYW if exist "%LocalAppData%\Programs\Python\Python313\pythonw.exe" set "PYW=%LocalAppData%\Programs\Python\Python313\pythonw.exe"

if not defined PY (
  echo No se encontro Python. Instala Python 3.10+ desde https://www.python.org/downloads/
  echo Marca la opcion "Add python.exe to PATH" durante la instalacion.
  pause
  exit /b 1
)

"%PY%" -c "import customtkinter, pystray, PIL" >nul 2>&1
if errorlevel 1 (
  echo Instalando dependencias...
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Error al instalar dependencias.
    pause
    exit /b 1
  )
)

if defined PYW (
  start "" "%PYW%" "%~dp0main.py"
) else (
  start "" "%PY%" "%~dp0main.py"
)
