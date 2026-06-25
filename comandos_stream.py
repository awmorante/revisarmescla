#!/usr/bin/env python3
"""
comandos_stream.py - Stream en vivo al canal de Telegram vía RTMP.

FLUJO CORRECTO:
  1. Usuario abre Telegram → su canal → Live → "Hacer stream con otras apps"
     → toca "Iniciar streaming"  (esto abre la sesión en Telegram)
  2. Recién después toca 🟢 Prender Vivo en el bot
     (FFmpeg se conecta a la sesión ya activa)
"""

import subprocess
import asyncio
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ── Configuración ─────────────────────────────────────────────
URL_RTSP        = "rtsp://admin:admin@192.168.0.16:554/12"
URL_RTMP_FILE   = Path.home() / ".amor" / "config" / "rtmp_url.txt"
URL_RTMP_DEFAULT = "rtmps://dc1-1.rtmp.t.me/s/4465676843:dTOPIQC7r5u715OMDj9faA"
STREAM_BOT      = Path.home() / "telegram-live" / "stream_bot.py"
VENV_PYTHON     = Path.home() / "telegram-live" / "venv" / "bin" / "python3"
LOG_STREAM      = Path("/tmp/stream.log")
DURACION_MAX    = 3600  # segundos (10 min)

# ── Estado global ──────────────────────────────────────────────
proceso_ffmpeg = None
tarea_apagado  = None
archivo_log    = None


def _leer_url_rtmp() -> str:
    """Lee la URL RTMP del archivo guardado por stream_bot.py, o usa la default."""
    if URL_RTMP_FILE.exists():
        url = URL_RTMP_FILE.read_text().strip()
        if url:
            return url
    return URL_RTMP_DEFAULT


async def _iniciar_live_telegram() -> bool:
    """Llama a stream_bot.py para arrancar el Live en Telegram. Devuelve True si OK."""
    if not STREAM_BOT.exists():
        return False  # no hay script, asumimos que el live ya está activo
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else "python3"
    try:
        result = subprocess.run(
            [python, str(STREAM_BOT)],
            capture_output=True, text=True, timeout=30
        )
        if "LIVE ACTIVO" in result.stdout or "Nota al crear live" in result.stdout:
            return True
        print(f"stream_bot output: {result.stdout[-300:]}")
        print(f"stream_bot stderr: {result.stderr[-200:]}")
        return False
    except Exception as e:
        print(f"Error al llamar stream_bot.py: {e}")
        return False


def _iniciar_live_telegram_sync() -> bool:
    """Versión sincrónica de _iniciar_live_telegram para run_in_executor."""
    if not STREAM_BOT.exists():
        return False
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else "python3"
    try:
        result = subprocess.run(
            [python, str(STREAM_BOT)],
            capture_output=True, text=True, timeout=30
        )
        return "LIVE ACTIVO" in result.stdout or "Nota al crear live" in result.stdout
    except Exception as e:
        print(f"Error stream_bot: {e}")
        return False


def _teclado_control():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🟢 Prender Vivo", callback_data="stream_on"),
        InlineKeyboardButton("🔴 Apagar Vivo",  callback_data="stream_off"),
    ]])


async def procesar_comando_stream(update, texto) -> bool:
    """Detecta pedidos de cámara en vivo y muestra las instrucciones correctas."""
    texto_l = texto.lower()

    # Frases directas → siempre son stream (sin necesitar "cámara")
    frases_directas = [
        "prender vivo", "prender el vivo", "encender vivo",
        "iniciar vivo", "iniciar stream", "arrancar vivo",
        "arrancar stream", "prender stream", "empezar vivo",
        "apagar vivo", "apagar stream", "apagar el vivo",
    ]
    # Palabras de stream que necesitan "cámara" para no confundirse
    palabras_stream = ["vivo", "transmisión", "transmision", "streaming", "en vivo"]

    es_stream = (
        any(f in texto_l for f in frases_directas)
        or (any(p in texto_l for p in palabras_stream)
            and any(c in texto_l for c in ["cámara", "camara"]))
    )

    if not es_stream:
        return False

    msg = (
        "📺 *Cámara en Vivo — dos pasos:*\n\n"
        "*Paso 1* — en Telegram:\n"
        "Abrí el canal → tocá el ícono 📹 → "
        "_Hacer stream con otras apps_ → *Iniciar streaming*\n\n"
        "*(Esto abre la sesión en los servidores de Telegram)*\n\n"
        "─────────────────────\n"
        "*Paso 2* — acá abajo:\n"
        "Tocá 🟢 *Prender Vivo* para conectar la cámara."
    )
    await update.message.reply_text(msg, parse_mode="Markdown",
                                    reply_markup=_teclado_control())
    return True


async def iniciar_stream(query):
    """Arranca FFmpeg hacia la sesión activa de Telegram."""
    global proceso_ffmpeg, tarea_apagado, archivo_log

    if proceso_ffmpeg and proceso_ffmpeg.poll() is None:
        await query.message.reply_text("⚠️ El vivo ya está transmitiendo.")
        return

    # Iniciar el Live en Telegram vía Telethon
    await query.message.reply_text("📡 Iniciando sesión de Live en Telegram...")
    ok = await asyncio.get_event_loop().run_in_executor(None, lambda: _iniciar_live_telegram_sync())
    if not ok:
        await query.message.reply_text(
            "⚠️ No pude iniciar el Live en Telegram automáticamente.\n"
            "Si ya está activo (lo iniciaste vos), igual puedo conectar la cámara.\n"
            "Intentando conectar FFmpeg..."
        )

    # Cerrar log anterior si quedó abierto
    if archivo_log:
        try:
            archivo_log.close()
        except Exception:
            pass

    url_rtmp = _leer_url_rtmp()
    cmd = (
        f'ffmpeg -fflags +genpts -rtsp_transport tcp -i "{URL_RTSP}" '
        f'-vcodec copy -acodec aac -af aresample=async=1 '
        f'-f flv -flvflags no_duration_filesize "{url_rtmp}"'
    )

    archivo_log = open(LOG_STREAM, "w")
    proceso_ffmpeg = subprocess.Popen(
        cmd, shell=True, stdout=archivo_log, stderr=subprocess.STDOUT
    )

    # Esperar 3 segundos y verificar que FFmpeg sigue vivo
    await asyncio.sleep(3)

    if proceso_ffmpeg.poll() is not None:
        # Murió rápido → leer el log y reportar
        archivo_log.flush()
        try:
            log_txt = LOG_STREAM.read_text(errors="replace")[-800:]
        except Exception:
            log_txt = "(sin log)"
        await query.message.reply_text(
            f"❌ FFmpeg falló al conectar.\n\n"
            f"¿Hiciste el *Paso 1* en Telegram (Iniciar streaming)?\n\n"
            f"```\n{log_txt}\n```",
            parse_mode="Markdown",
            reply_markup=_teclado_control()
        )
        proceso_ffmpeg = None
        return

    await query.message.reply_text(
        "🟢 *Transmisión iniciada.* Entrá al canal a verla.\n"
        f"_(Se apaga sola en {DURACION_MAX//60} minutos)_",
        parse_mode="Markdown",
        reply_markup=_teclado_control()
    )

    if tarea_apagado:
        tarea_apagado.cancel()
    tarea_apagado = asyncio.create_task(_auto_apagar(query))


async def detener_stream(query):
    """Detiene FFmpeg y cierra el log."""
    global proceso_ffmpeg, tarea_apagado, archivo_log

    if proceso_ffmpeg and proceso_ffmpeg.poll() is None:
        proceso_ffmpeg.terminate()
        proceso_ffmpeg = None
        if archivo_log:
            try:
                archivo_log.close()
            except Exception:
                pass
        await query.message.reply_text(
            "🔴 Transmisión apagada.",
            reply_markup=_teclado_control()
        )
    else:
        await query.message.reply_text(
            "La transmisión ya estaba apagada.",
            reply_markup=_teclado_control()
        )


async def _auto_apagar(query):
    """Apaga el stream automáticamente después de DURACION_MAX segundos."""
    await asyncio.sleep(DURACION_MAX)
    global proceso_ffmpeg, archivo_log
    if proceso_ffmpeg and proceso_ffmpeg.poll() is None:
        proceso_ffmpeg.terminate()
        proceso_ffmpeg = None
        if archivo_log:
            try:
                archivo_log.close()
            except Exception:
                pass
        await query.message.reply_text(
            f"⏱️ Pasaron {DURACION_MAX//60} minutos. Apagué el vivo.",
            reply_markup=_teclado_control()
        )
