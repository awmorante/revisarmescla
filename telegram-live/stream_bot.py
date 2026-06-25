#!/usr/bin/env python3
"""
stream_bot.py — Inicia el Live Stream del canal de Telegram vía Telethon
y devuelve la URL RTMP lista para FFmpeg.

Uso:
    source venv/bin/activate
    python3 stream_bot.py

Primera vez: pide tu número de teléfono y el código que te manda Telegram.
Guarda la sesión en sesion_stream.session — la próxima vez no pide nada.
"""

import os
from pathlib import Path
import re
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.phone import (
    CreateGroupCallRequest,
    GetGroupCallStreamRtmpUrlRequest,
)
from telethon.errors import ChatAdminRequiredError

load_dotenv()

API_ID       = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH     = os.getenv("TELEGRAM_API_HASH", "")
CHANNEL_REF  = os.getenv("TELEGRAM_CHANNEL", "")   # ver abajo
URL_RTSP     = "rtsp://admin:admin@192.168.0.16:554/12"

# TELEGRAM_CHANNEL puede ser cualquiera de estos formatos:
#   https://t.me/+fLSOb6Cq5bk1Yjhh   ← link de invitación
#   @nombre_del_canal                  ← username público
#   -1001234567890                     ← ID numérico (el más confiable)

SESSION_PATH = str(Path.home() / "telegram-live" / "sesion_stream")
client = TelegramClient(SESSION_PATH, API_ID, API_HASH)

async def resolver_canal(ref: str):
    """Resuelve el canal a una entidad de Telethon."""

    # Extraer hash de link de invitación (t.me/+ o joinchat/)
    match = re.search(r"[+/]([A-Za-z0-9_-]{10,})", ref)
    if match:
        invite_hash = match.group(1)
        try:
            from telethon.tl.functions.messages import CheckChatInviteRequest
            info = await client(CheckChatInviteRequest(hash=invite_hash))
            # Si ya sos miembro, info.chat tiene la entidad directa
            if hasattr(info, "chat"):
                return info.chat
        except Exception as e:
            print(f"Info invite check: {e}")

    # Intentar get_entity directo (funciona con @username e IDs numéricos)
    try:
        return await client.get_entity(ref)
    except Exception:
        pass

    # Último recurso: listar tus canales y mostrarlos
    print("\nNo pude resolver el canal. Tus canales disponibles:")
    async for dialog in client.iter_dialogs():
        if dialog.is_channel:
            print(f"  ID: {dialog.id}   Nombre: {dialog.name}")
    print("\nPonés el ID en TELEGRAM_CHANNEL del .env como: -100<id>")
    return None


async def main():
    await client.start()
    print("Conectado a Telegram OK\n")

    entity = await resolver_canal(CHANNEL_REF)
    if not entity:
        return

    print(f"Canal: {getattr(entity, 'title', entity)}")

    # ── 1. Crear/iniciar el Live con soporte RTMP ─────────────
    try:
        await client(CreateGroupCallRequest(
            peer=entity,
            rtmp_stream=True,
            title="Camara en Vivo"
        ))
        print("Live iniciado.")
    except Exception as e:
        # Si ya hay un live activo, esto falla pero está bien
        print(f"Nota al crear live: {e}")

    # ── 2. Obtener la URL RTMP ────────────────────────────────
    try:
        rtmp = await client(GetGroupCallStreamRtmpUrlRequest(
            peer=entity,
            revoke=False   # True = genera una clave nueva
        ))
        url_completa = f"{rtmp.url}{rtmp.key}"

        print("\n" + "=" * 50)
        print("LIVE ACTIVO")
        print("=" * 50)
        print(f"URL base : {rtmp.url}")
        print(f"Clave    : {rtmp.key}")
        print(f"\nURL completa para FFmpeg:")
        print(f"  {url_completa}")
        print("=" * 50)

        # ── 3. Guardar la URL para que el bot la use ──────────
        url_file = os.path.expanduser("~/.amor/config/rtmp_url.txt")
        os.makedirs(os.path.dirname(url_file), exist_ok=True)
        with open(url_file, "w") as f:
            f.write(url_completa)
        print(f"\nURL guardada en {url_file}")
        print("El bot la va a leer automáticamente la próxima vez.")

    except ChatAdminRequiredError:
        print("Error: necesitás ser admin del canal para hacer stream.")
    except Exception as e:
        print(f"Error obteniendo URL RTMP: {e}")


with client:
    client.loop.run_until_complete(main())
