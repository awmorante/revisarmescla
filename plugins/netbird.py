"""
plugins/netbird.py — Plugin NetBird VPN para Che
=================================================
Permite revisar y controlar la VPN NetBird desde Telegram
sin contraseña de sudo y sin abrir el navegador.

SETUP ÚNICO (hacerlo UNA VEZ en la máquina local):
---------------------------------------------------
1. Averiguar dónde está el binario:
       which netbird

2. Crear el archivo sudoers (reemplazar /usr/bin/netbird por lo que devolvió which):
       echo "ani ALL=(ALL) NOPASSWD: /usr/bin/netbird up, /usr/bin/netbird down, /usr/bin/netbird status" \
           | sudo tee /etc/sudoers.d/netbird-ani
       sudo chmod 440 /etc/sudoers.d/netbird-ani

3. Probar que funciona sin contraseña:
       sudo netbird status

Si el bot ya puede ejecutar comandos bash (tiene ejecutar_comandos: true en usuarios.json),
podés hacer el setup enviándole estos comandos desde Telegram y usando el botón "Ejecutar".

PALABRAS CLAVE que activan el plugin:
  netbird, vpn, tunnel, red vpn
"""

import shutil
import asyncio
import subprocess
from telegram import Update

# ── Palabras que activan este plugin ──────────────────────────────
KEYWORDS = ["netbird", "vpn", "tunnel", "red vpn", "tunel"]

# ── Encontrar el binario de netbird en el sistema ─────────────────
NETBIRD_BIN = shutil.which("netbird") or "/usr/bin/netbird"

AYUDA = (
    "🌐 *NetBird VPN* — comandos disponibles:\n\n"
    "• `netbird status` — ver estado de la VPN\n"
    "• `netbird up` — levantar / conectar\n"
    "• `netbird down` — bajar / desconectar\n"
    "• `netbird peers` — ver peers conectados\n"
    "• `netbird ip` — ver IP asignada por netbird"
)

# ── Grupos de palabras por intención ──────────────────────────────
_PALABRAS_STATUS = [
    "status", "estado", "cómo está", "como esta", "como está",
    "revisar", "chequear", "chequeá", "revisá", "funciona",
    "está andando", "esta andando", "conectada", "activa"
]
_PALABRAS_UP = [
    "up", "levantá", "levanta", "levantar", "conectá", "conectar",
    "activa", "activar", "encender", "iniciar", "subir",
    "conect", "arrancá", "arrancar", "prendé", "prende"
]
_PALABRAS_DOWN = [
    "down", "bajá", "bajar", "desconectá", "desconectar",
    "desactivar", "apagar", "parar", "detener", "cerrar"
]
_PALABRAS_PEERS = ["peers", "peer", "dispositivos", "conectados", "quien está"]
_PALABRAS_IP    = ["ip", "dirección", "direccion", "qué ip", "que ip", "mi ip"]


def _run(args: list, timeout: int = 20) -> str:
    """Ejecuta un comando y devuelve stdout+stderr como string."""
    try:
        r = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        salida = (r.stdout or "") + (r.stderr or "")
        return salida.strip() or "(sin output)"
    except subprocess.TimeoutExpired:
        return "⏱ Timeout — el comando tardó demasiado."
    except FileNotFoundError:
        return f"❌ No se encontró el binario: {args[0]}"
    except Exception as e:
        return f"❌ Error inesperado: {e}"


def _resumir_status(raw: str) -> str:
    """
    Parsea la salida de 'netbird status' y arma un resumen
    más legible para Telegram.
    """
    lineas = raw.splitlines()
    resumen = []
    for l in lineas:
        l = l.strip()
        if not l:
            continue
        # Líneas importantes
        if any(k in l.lower() for k in [
            "daemon", "management", "signal", "relays",
            "fqdn", "netbird ip", "interface", "peers count",
            "status", "connected", "disconnected"
        ]):
            resumen.append(l)
    return "\n".join(resumen) if resumen else raw


async def procesar(update: Update, texto: str, cfg: dict) -> bool:
    """
    Entry point del plugin. Retorna True si manejó el mensaje.
    cfg es el dict del usuario desde usuarios.json.
    """
    t = texto.lower().strip()

    # Requiere que sea admin (para no exponer control de red a familia)
    if cfg.get("rol") != "admin":
        # Si la familia pregunta por VPN, dar respuesta amable sin detalles
        if any(k in t for k in KEYWORDS):
            await update.message.reply_text(
                "🌐 La VPN es cosa de Wen, yo no tengo acceso a eso 😊"
            )
            return True
        return False

    # ── IP asignada ──────────────────────────────────────────
    if any(p in t for p in _PALABRAS_IP):
        out = _run(["sudo", NETBIRD_BIN, "status"])
        ip_line = next(
            (l for l in out.splitlines() if "netbird ip" in l.lower()),
            None
        )
        msg = ip_line if ip_line else "No pude detectar la IP de NetBird.\n\n" + out[:500]
        await update.message.reply_text(f"🌐 {msg}")
        return True

    # ── Peers ─────────────────────────────────────────────────
    if any(p in t for p in _PALABRAS_PEERS):
        out = _run(["sudo", NETBIRD_BIN, "status", "--detail"])
        await update.message.reply_text(
            f"👥 NetBird peers:\n```\n{out[:3000]}\n```",
            parse_mode="Markdown"
        )
        return True

    # ── Status ────────────────────────────────────────────────
    if any(p in t for p in _PALABRAS_STATUS):
        out = _run(["sudo", NETBIRD_BIN, "status"])
        resumen = _resumir_status(out)
        await update.message.reply_text(
            f"🌐 NetBird status:\n```\n{resumen}\n```",
            parse_mode="Markdown"
        )
        return True

    # ── Up ────────────────────────────────────────────────────
    if any(p in t for p in _PALABRAS_UP):
        msg_espera = await update.message.reply_text("⏳ Levantando NetBird VPN...")
        out = _run(["sudo", NETBIRD_BIN, "up"], timeout=30)
        # Esperar un poco y verificar estado
        await asyncio.sleep(3)
        status = _run(["sudo", NETBIRD_BIN, "status"])
        resumen = _resumir_status(status)
        await msg_espera.edit_text(
            f"🟢 NetBird up — resultado:\n```\n{out[:800]}\n```\n\n"
            f"📡 Estado actual:\n```\n{resumen}\n```",
            parse_mode="Markdown"
        )
        return True

    # ── Down ──────────────────────────────────────────────────
    if any(p in t for p in _PALABRAS_DOWN):
        out = _run(["sudo", NETBIRD_BIN, "down"])
        await update.message.reply_text(
            f"🔴 NetBird down:\n```\n{out[:800]}\n```",
            parse_mode="Markdown"
        )
        return True

    # Mención de vpn/netbird sin comando claro → mostrar ayuda
    await update.message.reply_text(AYUDA, parse_mode="Markdown")
    return True
