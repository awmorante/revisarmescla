"""
plugins/netbird.py — Plugin NetBird VPN para Che (v2)
Cambios: keywords más específicas, sin sudo para status/peers/ip,
up/down intentan sin sudo primero.
"""
 
import shutil
import asyncio
import subprocess
from telegram import Update
 
# ── Keywords más específicas — no intercepta comandos de sistema ──
# Requiere intención explícita, no solo que "netbird" aparezca en el texto
KEYWORDS = ["netbird up", "netbird down", "netbird status", "netbird peers",
            "netbird ip", "levantá vpn", "levanta vpn", "levantar vpn",
            "bajá vpn", "bajar vpn", "vpn status", "vpn arriba", "vpn abajo",
            "subir vpn", "subir netbird", "bajar netbird", "chequear vpn",
            "revisar vpn", "estado vpn", "conectar vpn", "desconectar vpn"]
 
NETBIRD_BIN = shutil.which("netbird") or "/usr/bin/netbird"
 
AYUDA = (
    "🌐 *NetBird VPN* — comandos:\n\n"
    "• `netbird status` — ver estado\n"
    "• `netbird up` — conectar\n"
    "• `netbird down` — desconectar\n"
    "• `netbird peers` — ver peers\n"
    "• `netbird ip` — ver IP"
)
 
_PALABRAS_STATUS = [
    "netbird status", "vpn status", "estado vpn", "chequear vpn",
    "revisar vpn", "cómo está la vpn", "como esta la vpn", "vpn funciona"
]
_PALABRAS_UP = [
    "netbird up", "levantá vpn", "levanta vpn", "levantar vpn",
    "subir vpn", "subir netbird", "conectar vpn", "vpn arriba",
    "conectá vpn", "prendé vpn"
]
_PALABRAS_DOWN = [
    "netbird down", "bajá vpn", "bajar vpn", "bajar netbird",
    "desconectar vpn", "vpn abajo", "apagar vpn"
]
_PALABRAS_PEERS = ["netbird peers", "peers vpn", "dispositivos vpn"]
_PALABRAS_IP    = ["netbird ip", "ip vpn", "ip de netbird"]
 
 
def _run(args: list, timeout: int = 20) -> tuple[str, bool]:
    """Ejecuta comando. Retorna (output, éxito)."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        out = ((r.stdout or "") + (r.stderr or "")).strip() or "(sin output)"
        return out, r.returncode == 0
    except subprocess.TimeoutExpired:
        return "⏱ Timeout.", False
    except FileNotFoundError:
        return f"❌ No encontré el binario: {args[0]}", False
    except Exception as e:
        return f"❌ Error: {e}", False
 
 
def _run_netbird(subcmd: list, timeout: int = 20) -> str:
    """
    Intenta el comando SIN sudo primero.
    Si falla por permisos, reintenta CON sudo (sin contraseña interactiva).
    """
    out, ok = _run([NETBIRD_BIN] + subcmd, timeout=timeout)
    if ok:
        return out
    # Si falló por permisos, intentar con sudo -n (no-interactivo)
    if any(p in out.lower() for p in ["permission", "not permitted", "operation not permitted"]):
        out2, _ = _run(["sudo", "-n", NETBIRD_BIN] + subcmd, timeout=timeout)
        return out2
    return out
 
 
def _resumir_status(raw: str) -> str:
    lineas = raw.splitlines()
    resumen = []
    for l in lineas:
        l = l.strip()
        if not l:
            continue
        if any(k in l.lower() for k in [
            "daemon", "management", "signal", "fqdn", "netbird ip",
            "interface", "peers count", "status", "connected", "disconnected"
        ]):
            resumen.append(l)
    return "\n".join(resumen) if resumen else raw
 
 
async def procesar(update: Update, texto: str, cfg: dict) -> bool:
    t = texto.lower().strip()
 
    if cfg.get("rol") != "admin":
        await update.message.reply_text("🌐 La VPN es cosa de Wen 😊")
        return True
 
    if any(p in t for p in _PALABRAS_IP):
        out = _run_netbird(["status"])
        ip_line = next((l for l in out.splitlines() if "netbird ip" in l.lower()), None)
        await update.message.reply_text(f"🌐 {ip_line or out[:500]}")
        return True
 
    if any(p in t for p in _PALABRAS_PEERS):
        out = _run_netbird(["status", "--detail"])
        await update.message.reply_text(
            f"👥 NetBird peers:\n```\n{out[:3000]}\n```", parse_mode="Markdown"
        )
        return True
 
    if any(p in t for p in _PALABRAS_STATUS):
        out = _run_netbird(["status"])
        resumen = _resumir_status(out)
        await update.message.reply_text(
            f"🌐 NetBird status:\n```\n{resumen}\n```", parse_mode="Markdown"
        )
        return True
 
    if any(p in t for p in _PALABRAS_UP):
        msg = await update.message.reply_text("⏳ Levantando NetBird...")
        out = _run_netbird(["up"], timeout=30)
        await asyncio.sleep(3)
        status = _run_netbird(["status"])
        resumen = _resumir_status(status)
        await msg.edit_text(
            f"🟢 NetBird up:\n```\n{out[:600]}\n```\n📡 Estado:\n```\n{resumen}\n```",
            parse_mode="Markdown"
        )
        return True
 
    if any(p in t for p in _PALABRAS_DOWN):
        out = _run_netbird(["down"])
        await update.message.reply_text(
            f"🔴 NetBird down:\n```\n{out[:600]}\n```", parse_mode="Markdown"
        )
        return True
 
    await update.message.reply_text(AYUDA, parse_mode="Markdown")
    return True
 
