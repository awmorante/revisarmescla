#!/usr/bin/env python3
"""
camara_captura.py - Captura periódica de cámara IP de la calle

Modos de uso:
  python3 camara_captura.py                    # solo captura (cron normal)
  python3 camara_captura.py --telegram         # captura + manda foto a Telegram
  python3 camara_captura.py --analizar         # captura + analiza con Groq vision
  python3 camara_captura.py --telegram --analizar   # captura + analiza + manda foto y descripción
  python3 camara_captura.py --solo-ultima --telegram --analizar  # usa última foto guardada
  python3 camara_captura.py --obtener-chat-id  # encontrar tu chat_id de Telegram
  python3 camara_captura.py --listar           # ver fotos guardadas

Cron básico:
  */10 * * * * python3 ~/compartido/amor/camara_captura.py >> ~/.amor/camara.log 2>&1
Con Telegram:
  */10 * * * * python3 ~/compartido/amor/camara_captura.py --telegram >> ~/.amor/camara.log 2>&1
"""

import requests
import os
import sys
import time
import argparse
import base64
from datetime import datetime
from pathlib import Path

# ─── Configuración ───────────────────────────────────────────────
CAMERA_BASE_URL   = "http://192.168.0.16:81/tmpfs/auto.jpg"
CAM_USER          = "admin"
CAM_PASS          = "admin"
OUTPUT_DIR        = Path.home() / ".amor" / "camaras"
MAX_FOTOS         = 144   # ~24h a razón de 1 foto cada 10 min
TIMEOUT_SEG       = 8

TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
# ─────────────────────────────────────────────────────────────────


def capturar(output_dir: Path, timeout: int):
    """Descarga una foto de la cámara. Retorna Path si OK, None si error."""
    ts_ms = int(time.time() * 1000)
    url   = f"{CAMERA_BASE_URL}?{ts_ms}"
    ahora = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        resp = requests.get(url, auth=(CAM_USER, CAM_PASS), timeout=timeout)
        resp.raise_for_status()

        if resp.content[:2] != b'\xff\xd8':
            print(f"[{ahora}] WARN: La respuesta no parece JPEG")

        output_dir.mkdir(parents=True, exist_ok=True)
        archivo = output_dir / f"calle_{ahora}.jpg"
        archivo.write_bytes(resp.content)

        kb = len(resp.content) / 1024
        print(f"[{ahora}] OK  → {archivo.name} ({kb:.1f} KB)")
        return archivo

    except requests.exceptions.ConnectionError:
        print(f"[{ahora}] ERROR: No se pudo conectar a la cámara")
    except requests.exceptions.Timeout:
        print(f"[{ahora}] ERROR: Timeout después de {timeout}s")
    except requests.exceptions.HTTPError as e:
        print(f"[{ahora}] ERROR HTTP: {e}")
    except Exception as e:
        print(f"[{ahora}] ERROR inesperado: {e}")
    return None


def analizar_imagen(foto_path: Path) -> str:
    """Usa Groq (LLaMA 4 Scout vision) para describir qué hay en la imagen."""
    if not GROQ_API_KEY:
        return "ERROR: falta GROQ_API_KEY en el entorno"

    with open(foto_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model": GROQ_VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                },
                {
                    "type": "text",
                    "text": (
                        "Describí brevemente qué ves en esta imagen de cámara de seguridad exterior. "
                        "¿Hay personas, vehículos, animales? ¿Es de día o de noche? "
                        "¿Hay algo inusual? Sé concisa, máximo 3 oraciones."
                    )
                }
            ]
        }],
        "max_tokens": 300
    }

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"ERROR al analizar: {e}"


def enviar_foto_telegram(foto_path: Path, caption: str = "", chat_id: str = "") -> bool:
    """Envía una foto al chat de Telegram."""
    cid = chat_id or TELEGRAM_CHAT_ID
    if not TELEGRAM_TOKEN:
        print("ERROR: falta TELEGRAM_BOT_TOKEN en el entorno")
        return False
    if not cid:
        print("ERROR: falta TELEGRAM_CHAT_ID — corré con --obtener-chat-id para encontrarlo")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        with open(foto_path, "rb") as f:
            resp = requests.post(
                url,
                data={"chat_id": cid, "caption": caption},
                files={"photo": ("foto.jpg", f, "image/jpeg")},
                timeout=30
            )
        if resp.ok:
            print(f"Foto enviada a Telegram ✓")
            return True
        else:
            print(f"ERROR Telegram {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"ERROR Telegram: {e}")
        return False


def obtener_chat_id():
    """Muestra los chat IDs disponibles del bot para elegir cuál usar."""
    if not TELEGRAM_TOKEN:
        print("ERROR: falta TELEGRAM_BOT_TOKEN en el entorno")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()

        if not data.get("result"):
            print("No hay mensajes recientes.")
            print("→ Mandá cualquier mensaje a tu bot desde Telegram y volvé a correr esto.")
            return

        chats = {}
        for update in data["result"]:
            msg  = update.get("message") or update.get("channel_post") or {}
            chat = msg.get("chat", {})
            if chat:
                cid  = chat.get("id")
                name = (chat.get("title") or chat.get("username")
                        or chat.get("first_name") or "desconocido")
                chats[cid] = name

        if not chats:
            print("No se encontraron chats. Mandá un mensaje al bot y reintentá.")
            return

        print("\n─── Chats encontrados ───────────────────────")
        for cid, name in chats.items():
            print(f"  {name:30s} → {cid}")

        print("\nAgregá a ~/.bashrc la línea que corresponda:")
        for cid, name in chats.items():
            print(f'  export TELEGRAM_CHAT_ID="{cid}"  # {name}')
        print("Luego: source ~/.bashrc")

    except Exception as e:
        print(f"ERROR: {e}")


def ultima_foto(output_dir: Path):
    """Retorna la foto más reciente guardada, o None si no hay."""
    fotos = sorted(output_dir.glob("calle_*.jpg"))
    return fotos[-1] if fotos else None


def rotar_fotos(output_dir: Path, max_fotos: int):
    """Elimina las fotos más viejas si se supera el límite."""
    fotos = sorted(output_dir.glob("calle_*.jpg"))
    if len(fotos) > max_fotos:
        for f in fotos[:len(fotos) - max_fotos]:
            f.unlink()
            print(f"[rotación] Eliminada: {f.name}")


def listar_fotos(output_dir: Path):
    """Muestra un resumen de las fotos guardadas."""
    if not output_dir.exists():
        print("No hay fotos guardadas todavía.")
        return
    fotos = sorted(output_dir.glob("calle_*.jpg"))
    if not fotos:
        print("No hay fotos guardadas todavía.")
        return
    total_mb = sum(f.stat().st_size for f in fotos) / (1024 * 1024)
    print(f"\nFotos en {output_dir}:")
    print(f"  Total:   {len(fotos)} fotos")
    print(f"  Primera: {fotos[0].name}")
    print(f"  Última:  {fotos[-1].name}")
    print(f"  Espacio: {total_mb:.1f} MB")


def main():
    parser = argparse.ArgumentParser(
        description="Captura y monitoreo de cámara IP de la calle",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--telegram",        action="store_true", help="Enviar foto a Telegram")
    parser.add_argument("--analizar",        action="store_true", help="Analizar imagen con Groq vision")
    parser.add_argument("--solo-ultima",     action="store_true", help="No capturar, usar la última foto guardada")
    parser.add_argument("--obtener-chat-id", action="store_true", help="Mostrar chat IDs disponibles del bot")
    parser.add_argument("--listar",          action="store_true", help="Ver resumen de fotos guardadas")
    parser.add_argument("--max-fotos",  type=int,  default=MAX_FOTOS,   help=f"Máximo de fotos a conservar (default: {MAX_FOTOS})")
    parser.add_argument("--chat-id",    type=str,  default="",          help="Chat ID manual (override de TELEGRAM_CHAT_ID)")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR,  help=f"Directorio de salida (default: {OUTPUT_DIR})")
    args = parser.parse_args()

    # ── Helpers sin captura ───────────────────────────────────────
    if args.obtener_chat_id:
        obtener_chat_id()
        return

    if args.listar:
        listar_fotos(args.output_dir)
        return

    # ── Obtener foto ──────────────────────────────────────────────
    if args.solo_ultima:
        foto = ultima_foto(args.output_dir)
        if not foto:
            print("No hay fotos guardadas. Corré sin --solo-ultima para capturar una.")
            sys.exit(1)
        print(f"Usando última foto: {foto.name}")
    else:
        foto = capturar(args.output_dir, TIMEOUT_SEG)
        if not foto:
            sys.exit(1)
        if args.max_fotos > 0:
            rotar_fotos(args.output_dir, args.max_fotos)

    # ── Análisis con visión ───────────────────────────────────────
    descripcion = ""
    if args.analizar:
        print("Analizando imagen con Groq vision...")
        descripcion = analizar_imagen(foto)
        print(f"→ {descripcion}")

    # ── Envío a Telegram ──────────────────────────────────────────
    if args.telegram:
        ahora   = datetime.now().strftime("%d/%m/%Y %H:%M")
        caption = f"📷 Cámara calle — {ahora}"
        if descripcion:
            caption += f"\n\n{descripcion}"
        enviar_foto_telegram(foto, caption=caption, chat_id=args.chat_id)


if __name__ == "__main__":
    main()
