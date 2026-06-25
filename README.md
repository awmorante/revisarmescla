# CHE — Asistente personal en Telegram

Bot de Telegram multi-usuario corriendo en Linux local (Dell).

## Módulos
- `bot_che_v3.py` — bot principal
- `acciones_archivos.py` — lectura/escritura de archivos
- `comandos_camara.py` — fotos desde cámara IP
- `comandos_stream.py` — live stream vía RTMP + Telethon
- `che_manager.sh` — gestión de procesos

## Requisitos
- Python 3.12+
- ffmpeg
- Telethon (en venv separado `~/telegram-live/`)

## Configuración
Copiar `.env.example` a `.env` y completar las variables.
Ver `config/usuarios.json` para gestión de usuarios y permisos.

## Uso
```bash
./che_manager.sh        # menú interactivo
./che_manager.sh start  # arrancar en background
```
