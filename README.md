# Recordatorios (Windows)

Aplicación de escritorio en Python para mostrar notificaciones en tu PC:

- Cada cierto intervalo (por ejemplo, cada 30 minutos)
- A una hora fija todos los días (por ejemplo, 15:00)

Al cerrar o minimizar la ventana, el programa **sigue en segundo plano** (icono en la bandeja del sistema, junto al reloj). Las notificaciones se detienen solo cuando eliges **Salir** desde ese icono.

## Requisitos

- Windows 10 u 11
- Python 3.10 o superior

## Instalación

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
2. Elige **Cada cierto tiempo** o **A una hora**.
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

## Nota

Mientras el programa esté cerrado del todo (opción **Salir**), no se mostrarán notificaciones. Ábrelo de nuevo y déjalo en la bandeja.
"# recordatorios" 
