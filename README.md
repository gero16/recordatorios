# Recordatorios (Windows)

Aplicación de escritorio en Python para mostrar notificaciones en tu PC:

- Cada cierto intervalo (por ejemplo, cada 30 minutos)
- A una hora fija todos los días (por ejemplo, 15:00)
- En ciertos días y a ciertas horas (por ejemplo, lunes, miércoles y viernes a las 09:00 y 18:30)

Al cerrar o minimizar la ventana, el programa **sigue en segundo plano** (icono en la bandeja del sistema, junto al reloj). Las notificaciones se detienen solo cuando eliges **Salir** desde ese icono.

## Requisitos

- Windows 10 u 11
- Python 3.10 o superior

## Instalación rápida (con icono en el escritorio)

1. Instala [Python 3.10 o superior](https://www.python.org/downloads/). Durante la instalación marca la casilla **"Add python.exe to PATH"**.
2. Descarga el proyecto: en GitHub, pulsa **Code → Download ZIP** y descomprímelo en una carpeta fija (por ejemplo `Documentos\recordatorios`). También puedes usar `git clone https://github.com/gero16/recordatorios.git`.
3. Entra en la carpeta y haz doble clic en **`instalar.bat`**.
4. Cuando termine, tendrás el icono **Recordatorios** en el escritorio. Haz doble clic en él para abrir el programa.

El instalador hace tres cosas: instala las dependencias, genera el icono (`icono.ico`) y crea el acceso directo en el escritorio.

**Importante:** el acceso directo apunta a la carpeta donde está el proyecto. Si mueves o renombras la carpeta, vuelve a ejecutar `instalar.bat`.

**Abrir al iniciar Windows (opcional):** pulsa `Win + R`, escribe `shell:startup` y copia ahí el acceso directo del escritorio.

## Instalación manual

1. Abre una terminal en esta carpeta.
2. Instala las dependencias:

```bash
python -m pip install -r requirements.txt
```

Si `python` no funciona, prueba:

```bash
py -m pip install -r requirements.txt
```

## Uso

```bash
python main.py
```

o:

```bash
py main.py
```

1. Escribe el mensaje del recordatorio.
2. Elige **Cada cierto tiempo**, **Todos los días a una hora** o **Ciertos días y horas**.
3. Pulsa **Guardar recordatorio**.
4. Puedes **Pausar**, **Activar** o **Eliminar** cada aviso.
5. Usa **Probar notificación** para ver cómo se verá el toast.
6. Al cerrar la ventana, busca el icono azul en la bandeja → clic derecho → **Mostrar** o **Salir**.

## Archivos

| Archivo | Rol |
|---------|-----|
| `main.py` | Ventana principal |
| `scheduler.py` | Temporizadores |
| `notifier.py` | Toasts de Windows |
| `tray.py` | Icono de bandeja |
| `storage.py` | Guardado en JSON |
| `data/reminders.json` | Tus recordatorios |
| `instalar.bat` | Instala dependencias y crea el icono en el escritorio |
| `iniciar.bat` | Abre el programa sin crear acceso directo |

## Nota

Mientras el programa esté cerrado del todo (opción **Salir**), no se mostrarán notificaciones. Ábrelo de nuevo y déjalo en la bandeja.
"# recordatorios" 
