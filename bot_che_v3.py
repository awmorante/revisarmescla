#!/usr/bin/env python3
"""
bot_che_v3.py - CHE · Asistente personal multi-usuario con permisos, presencia, audio y streaming en vivo
"""

import os
import sys
import json
import time
import uuid
import subprocess
import requests
import asyncio
import importlib.util
from datetime import datetime
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

sys.path.append(str(Path(__file__).resolve().parent))
import acciones_archivos as archivos
import comandos_camara
import comandos_stream


# ══════════════════════════════════════════════════════════════
# CONFIGURACIÓN BASE
# ══════════════════════════════════════════════════════════════

BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GROQ_KEY   = os.environ.get("GROQ_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

BASE_DIR      = Path.home() / ".amor"
CONFIG_DIR    = BASE_DIR / "config"
USUARIOS_JSON = CONFIG_DIR / "usuarios.json"
ESTADO_JSON   = CONFIG_DIR / "estado.json"
USUARIOS_DIR  = BASE_DIR / "usuarios"

comandos_pendientes: dict = {}

PLUGINS_DIR = Path(__file__).resolve().parent / "plugins"
_plugins_cache: dict = {}

# ══════════════════════════════════════════════════════════════
# USUARIOS Y PERMISOS
# ══════════════════════════════════════════════════════════════

def leer_config() -> dict:
    if not USUARIOS_JSON.exists():
        _crear_config_default()
    try:
        return json.loads(USUARIOS_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error leyendo usuarios.json: {e}")
        return {}

def _crear_config_default():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = {
        "usuarios": {
            "7127341580": {
                "nombre": "Wen",
                "rol": "admin",
                "camaras": True,
                "ejecutar_comandos": True,
                "editar_archivos": True
            }
        },
        "permisos_familiares": {}
    }
    USUARIOS_JSON.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"✅ usuarios.json creado en {USUARIOS_JSON}")

def get_cfg(chat_id: int) -> dict:
    return leer_config().get("usuarios", {}).get(str(chat_id))

def get_permisos_familiares(chat_id: int) -> dict:
    return leer_config().get("permisos_familiares", {}).get(str(chat_id), {})

def es_admin(cfg: dict) -> bool:
    return cfg.get("rol") == "admin"

def get_admin_id() -> int:
    """Retorna el chat_id del primer admin que encuentre."""
    for uid, ucfg in leer_config().get("usuarios", {}).items():
        if ucfg.get("rol") == "admin":
            return int(uid)
    return None


# ══════════════════════════════════════════════════════════════
# ESTADO DE PRESENCIA
# ══════════════════════════════════════════════════════════════

ESTADO_DEFAULT = {
    "en_casa": None,
    "durmiendo": False,
    "ocupado": False,
    "modo": "normal",
    "ultimo_update": None
}

def leer_estado() -> dict:
    if not ESTADO_JSON.exists():
        return dict(ESTADO_DEFAULT)
    try:
        return json.loads(ESTADO_JSON.read_text(encoding="utf-8"))
    except:
        return dict(ESTADO_DEFAULT)

def guardar_estado(datos: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    datos["ultimo_update"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    ESTADO_JSON.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
    )

def actualizar_campo_estado(campo: str, valor):
    e = leer_estado()
    e[campo] = valor
    guardar_estado(e)

def estado_como_texto(estado: dict = None) -> str:
    e = estado or leer_estado()
    partes = []
    if e.get("en_casa") is True:
        partes.append("en casa")
    elif e.get("en_casa") is False:
        partes.append("fuera de casa")
    else:
        partes.append("ubicación desconocida")
    if e.get("durmiendo"):
        partes.append("durmiendo")
    if e.get("ocupado"):
        partes.append("ocupada")
    modo = e.get("modo", "normal")
    if modo != "normal":
        partes.append(f"modo {modo}")
    ts = e.get("ultimo_update")
    sufijo = f" (act. {ts})" if ts else ""
    return ", ".join(partes) + sufijo


# ══════════════════════════════════════════════════════════════
# MEMORIA POR USUARIO
# ══════════════════════════════════════════════════════════════

def _dir_u(chat_id: int) -> Path:
    d = USUARIOS_DIR / str(chat_id)
    d.mkdir(parents=True, exist_ok=True)
    return d

def leer_sesion(chat_id: int) -> str:
    f = _dir_u(chat_id) / "sesion.md"
    return f.read_text(encoding="utf-8")[-3000:] if f.exists() else ""

def leer_memoria(chat_id: int) -> str:
    f = _dir_u(chat_id) / "memoria.md"
    return f.read_text(encoding="utf-8")[:4000] if f.exists() else ""

def guardar_historial(chat_id: int, user_msg: str, bot_resp: str):
    hist = _dir_u(chat_id) / "historial.jsonl"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user_msg,
        "bot": bot_resp
    }
    with open(hist, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def guardar_sesion(chat_id: int, user_msg: str, bot_resp: str):
    f = _dir_u(chat_id) / "sesion.md"
    cfg = get_cfg(chat_id)
    nombre = cfg.get("nombre", str(chat_id)) if cfg else str(chat_id)
    ahora = datetime.now().strftime("%H:%M")
    txt = f"\n### 💬 [{ahora}] {nombre}\n{user_msg}\n\n🤖 **Che**:\n{bot_resp}\n"
    with open(f, "a", encoding="utf-8") as fp:
        fp.write(txt)

def leer_pendientes(chat_id: int) -> list:
    f = _dir_u(chat_id) / "pendientes.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except:
        return []

def guardar_pendientes(chat_id: int, pendientes: list):
    f = _dir_u(chat_id) / "pendientes.json"
    f.write_text(json.dumps(pendientes, ensure_ascii=False, indent=2), encoding="utf-8")


# ══════════════════════════════════════════════════════════════
# SYSTEM PROMPTS
# ══════════════════════════════════════════════════════════════

PROMPT_ADMIN = (
    "Sos Che, un asistente técnico y directo. "
    "Hablás en español rioplatense (usá el vos). Sin introducciones corteses. "
    "Tenés acceso a cámaras, archivos del sistema y podés sugerir comandos bash."
)

PROMPT_FAMILIA = (
    "Sos un asistente amable y paciente. "
    "Ayudás con recetas, salud, WhatsApp, turnos médicos y cosas del día a día. "
    "Hablás de manera clara y simple. "
    "No tenés acceso al sistema, archivos ni cámaras. "
    "Si te piden esas cosas, explicá amablemente que no podés."
)

def get_sys_prompt(cfg: dict, chat_id: int) -> str:
    if es_admin(cfg):
        estado_txt = estado_como_texto()
        return f"{PROMPT_ADMIN}\n\nEstado de presencia actual: {estado_txt}"
    return PROMPT_FAMILIA


# ══════════════════════════════════════════════════════════════
# COMANDOS ESPECIALES DEL ADMIN (!xxx)
# ══════════════════════════════════════════════════════════════

MAPA_ESTADO = {
    "!casa":       ("en_casa",   True,  "✅ Marcada como en casa."),
    "!fuera":      ("en_casa",   False, "🚶 Fuera de casa."),
    "!durmiendo":  ("durmiendo", True,  "🌙 Modo durmiendo activado."),
    "!despierta":  ("durmiendo", False, "☀️ Modo durmiendo desactivado."),
    "!ocupada":    ("ocupado",   True,  "🔴 Modo ocupada."),
    "!disponible": ("ocupado",   False, "🟢 Disponible."),
}

async def cmd_estado_set(update: Update, texto: str) -> bool:
    """Actualiza un campo del estado según el comando !xxx."""
    cmd = texto.strip().lower().split()[0]
    if cmd not in MAPA_ESTADO:
        return False
    campo, valor, msg = MAPA_ESTADO[cmd]
    actualizar_campo_estado(campo, valor)
    await update.message.reply_text(msg)
    return True

async def cmd_ver_estado(update: Update, texto: str) -> bool:
    """!estado → muestra el estado actual completo."""
    if texto.strip().lower() != "!estado":
        return False
    e = leer_estado()
    lineas = [
        "📍 Estado actual:",
        f"  en_casa:    {e.get('en_casa')}",
        f"  durmiendo:  {e.get('durmiendo')}",
        f"  ocupada:    {e.get('ocupado')}",
        f"  modo:       {e.get('modo', 'normal')}",
        f"  actualizado:{e.get('ultimo_update', 'nunca')}",
    ]
    await update.message.reply_text("\n".join(lineas))
    return True

async def cmd_pendientes(update: Update, texto: str, chat_id: int) -> bool:
    """!pendientes → lista mensajes urgentes y los limpia."""
    if texto.strip().lower() != "!pendientes":
        return False
    pendientes = leer_pendientes(chat_id)
    if not pendientes:
        await update.message.reply_text("📭 No hay pendientes.")
    else:
        lines = [f"📬 {len(pendientes)} pendiente(s):"]
        for i, p in enumerate(pendientes, 1):
            lines.append(
                f"\n{i}. [{p.get('tipo','?')}] De: {p.get('de','?')}\n"
                f"   \"{p.get('mensaje','')}\"\n"
                f"   {p.get('timestamp','')}"
            )
        await update.message.reply_text("\n".join(lines)[:4000])
        guardar_pendientes(chat_id, [])  # limpia después de leer
    return True

async def cmd_ayuda(update: Update, texto: str) -> bool:
    """!ayuda → lista comandos disponibles."""
    if texto.strip().lower() != "!ayuda":
        return False
    msg = (
        "🤖 *Comandos disponibles:*\n\n"
        "*Estado de presencia:*\n"
        "`!casa` · `!fuera`\n"
        "`!durmiendo` · `!despierta`\n"
        "`!ocupada` · `!disponible`\n\n"
        "*Info:*\n"
        "`!estado` → ver estado actual\n"
        "`!pendientes` → ver mensajes urgentes\n"
        "`!ayuda` → este menú\n\n"
        "*Cámara:*\n"
        "Escribí `foto`, `captura` o `cámara`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return True


# ══════════════════════════════════════════════════════════════
# CONSULTAS DE PRESENCIA (familia)
# ══════════════════════════════════════════════════════════════

PALABRAS_PRESENCIA = [
    "en casa", "está en casa", "donde está", "dónde está",
    "disponible", "durmiendo", "ocupada", "qué está haciendo"
]
PALABRAS_URGENCIA = [
    "urgente", "urgencia", "emergencia", "avisa", "avisale", "necesito hablar"
]

async def manejar_presencia_familia(update: Update, texto: str, chat_id: int) -> bool:
    """Maneja consultas de estado para usuarios familia."""
    texto_l = texto.lower()
    permisos = get_permisos_familiares(chat_id)
    if not permisos:
        return False

    # Urgente → deja aviso en pendientes del admin
    if any(p in texto_l for p in PALABRAS_URGENCIA) and permisos.get("puede_pedir_alarma_urgente"):
        admin_id = get_admin_id()
        if admin_id:
            cfg_yo = get_cfg(chat_id)
            nombre = cfg_yo.get("nombre", "Alguien") if cfg_yo else "Alguien"
            pendientes = leer_pendientes(admin_id)
            pendientes.append({
                "tipo": "urgente",
                "de": nombre,
                "mensaje": texto,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            guardar_pendientes(admin_id, pendientes)
            await update.message.reply_text(
                "⚠️ Le dejé un aviso urgente. Te va a contactar cuando pueda."
            )
            return True

    # Consulta de estado general
    if any(p in texto_l for p in PALABRAS_PRESENCIA) and permisos.get("puede_ver_estado_general"):
        await update.message.reply_text(f"📍 Wen está: {estado_como_texto()}")
        return True

    return False


# ══════════════════════════════════════════════════════════════
# MOTORES IA
# ══════════════════════════════════════════════════════════════

def _build_prompt(base: str, pregunta: str, chat_id: int) -> str:
    sesion      = leer_sesion(chat_id)
    memoria     = leer_memoria(chat_id)
    archivos_ctx = archivos.contexto_de_archivos(pregunta)
    p = f"{base}\n\n"
    if memoria:      p += f"═ MEMORIA ═\n{memoria}\n\n"
    if sesion:       p += f"═ SESIÓN HOY ═\n{sesion}\n\n"
    if archivos_ctx: p += f"═ ARCHIVOS ═\n{archivos_ctx}\n\n"
    p += f"Pregunta: {pregunta}"
    return p

def llamar_groq(pregunta: str, sys_prompt: str, chat_id: int):
    if not GROQ_KEY:
        return None, "Groq (No key)"
    url = "https://api.groq.com/openai/v1/chat/completions"
    prompt = _build_prompt(sys_prompt, pregunta, chat_id)
    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user",   "content": pregunta}
        ],
        "temperature": 0.5,
        "max_completion_tokens": 1024
    }
    try:
        r = requests.post(
            url, json=data,
            headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json"
            },
            timeout=20
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"], "Groq"
        print(f"Groq HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print(f"Groq error: {e}")
    return None, "Groq (Fallo)"

def llamar_gemini(pregunta: str, sys_prompt: str, chat_id: int):
    if not GEMINI_KEY:
        return None, "Gemini (No key)"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    )
    prompt = _build_prompt(sys_prompt, pregunta, chat_id)
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(url, json=data, headers={"Content-Type": "application/json"}, timeout=20)
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"], "Gemini"
        print(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print(f"Gemini error: {e}")
    return None, "Gemini (Fallo)"


# ══════════════════════════════════════════════════════════════
# DETECCIÓN BASH
# ══════════════════════════════════════════════════════════════

def extraer_comando(texto: str):
    if "```" not in texto:
        return None
    try:
        bloque = texto.split("```")[1]
        if bloque.startswith(("escribir:", "editar:")):
            return None
        for p in ["bash\n", "sh\n", "bash", "sh"]:
            if bloque.startswith(p):
                bloque = bloque[len(p):]
                break
        return bloque.strip() or None
    except:
        return None


# ══════════════════════════════════════════════════════════════
# SISTEMA DE PLUGINS HOT-RELOAD
# Cada .py en plugins/ debe exportar:
#   KEYWORDS: list[str]   — palabras que activan el plugin
#   async def procesar(update, texto, cfg) -> bool
#       Retorna True si el plugin manejó el mensaje (corta el flujo)
# ══════════════════════════════════════════════════════════════
 
def _cargar_plugins():
    """Escanea plugins/ y carga o recarga los archivos modificados."""
    if not PLUGINS_DIR.exists():
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        return
    for py_file in sorted(PLUGINS_DIR.glob("*.py")):
        if py_file.name.startswith("_"):
            continue  # ignorar __init__.py etc.
        try:
            mtime = py_file.stat().st_mtime
        except OSError:
            continue
        cached = _plugins_cache.get(py_file.name)
        if cached is not None and cached[0] == mtime:
            continue  # sin cambios
        try:
            spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _plugins_cache[py_file.name] = (mtime, mod)
            accion = "recargado" if cached else "cargado"
            print(f"🔌 Plugin {accion}: {py_file.name}")
        except Exception as e:
            print(f"❌ Error en plugin {py_file.name}: {e}")
 
 
async def _loop_plugins():
    """Tarea asyncio que re-escanea plugins/ cada 60 segundos."""
    while True:
        await asyncio.sleep(60)
        _cargar_plugins()
 
 
async def probar_plugins(update: Update, texto: str, cfg: dict) -> bool:
    """
    Itera los plugins cargados buscando coincidencia con KEYWORDS.
    Retorna True si alguno manejó el mensaje (para cortar el flujo).
    """
    texto_l = texto.lower()
    for nombre, (_, mod) in list(_plugins_cache.items()):
        keywords = getattr(mod, "KEYWORDS", [])
        if not any(k in texto_l for k in keywords):
            continue
        try:
            if await mod.procesar(update, texto, cfg):
                return True
        except Exception as e:
            print(f"❌ Error ejecutando plugin {nombre}: {e}")
    return False

# ══════════════════════════════════════════════════════════════
# HANDLERS TELEGRAM
# ══════════════════════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    cfg = get_cfg(chat_id)
    if not cfg:
        await update.message.reply_text("⛔ No autorizado.")
        return

    texto = update.message.text or ""

    # ── Cámara y Stream (solo si tiene permiso) ────────────────────────
    if cfg.get("camaras", False):
        # 1. Chequea si piden el video en vivo por chat/audio
        if await comandos_stream.procesar_comando_stream(update, texto):
            return
        # 2. Si no es video en vivo, chequea si es una foto normal
        if await comandos_camara.procesar_comando_camara(update, texto):
            return
    
    # ── Comandos especiales del admin ─────────────────────────
    if es_admin(cfg) and texto.startswith("!"):
        if await cmd_ayuda(update, texto):          return
        if await cmd_ver_estado(update, texto):     return
        if await cmd_pendientes(update, texto, chat_id): return
        if await cmd_estado_set(update, texto):     return

    # ── Consultas de presencia (solo familia) ─────────────────
    if not es_admin(cfg):
        if await manejar_presencia_familia(update, texto, chat_id):
            return
    if await probar_plugins(update, texto, cfg):
        return
    
    # ── IA ────────────────────────────────────────────────────
    await update.message.reply_text("⏳ Consultando...")
    sys_prompt = get_sys_prompt(cfg, chat_id)

    respuesta, motor = llamar_groq(texto, sys_prompt, chat_id)
    if not respuesta:
        respuesta, motor = llamar_gemini(texto, sys_prompt, chat_id)
    if not respuesta:
        await update.message.reply_text("❌ Todos los motores fallaron.")
        return

    guardar_historial(chat_id, texto, respuesta)
    guardar_sesion(chat_id, texto, respuesta)
    await update.message.reply_text(respuesta[:4000])

    # Bash solo para admin
    if cfg.get("ejecutar_comandos", False):
        cmd = extraer_comando(respuesta)
        if cmd:
            cmd_id = str(uuid.uuid4())[:8]
            comandos_pendientes[cmd_id] = cmd
            kb = [[
                InlineKeyboardButton("🚀 Ejecutar", callback_data=f"exec:{cmd_id}"),
                InlineKeyboardButton("❌ Cancelar", callback_data="cancel")
            ]]
            await update.message.reply_text(
                f"¿Ejecuto?\n`{cmd}`",
                reply_markup=InlineKeyboardMarkup(kb)
            )

    archivos.ofrecer_escritura_o_edicion(respuesta)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Cancelado.")
        
    # --- STREAM V1 --- Acciones de control de cámara ---
    elif query.data == "stream_on":
        await comandos_stream.iniciar_stream(query)
    elif query.data == "stream_off":
        await comandos_stream.detener_stream(query)
        
    # --- BASH COMMANDS --- Ejecución remota ---
    elif query.data.startswith("exec:"):
        cmd_id = query.data[5:]
        cmd = comandos_pendientes.pop(cmd_id, None)
        if not cmd:
            await query.edit_message_text("❌ Comando expirado.")
            return
        await query.edit_message_text(f"🚀 Ejecutando: {cmd}")
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            output = result.stdout or result.stderr or "(sin output)"
            # Evitamos problemas de parseo usando concatenación simple para las vallas de código
            valla_inicio = "```\n"
            valla_fin = "\n```"
            await query.message.reply_text(valla_inicio + str(output[:3500]) + valla_fin)
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Descarga el audio de voz, lo transcribe usando Groq Whisper y lo inyecta al flujo normal."""
    chat_id = update.effective_chat.id
    if not get_cfg(chat_id): return

    msg_temp = await update.message.reply_text("🎧 Escuchando audio...")
    
    # 1. Bajar el archivo de audio de Telegram
    file = await context.bot.get_file(update.message.voice.file_id)
    ruta_audio = Path(f"/tmp/{update.message.voice.file_id}.ogg")
    await file.download_to_drive(ruta_audio)

    # 2. Mandarlo a la API de Groq para transcribir con Whisper v3
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    try:
        with open(ruta_audio, "rb") as f:
            archivos_data = {"file": ("audio.ogg", f, "audio/ogg")}
            datos = {"model": "whisper-large-v3", "language": "es"}
            r = requests.post(url, headers={"Authorization": f"Bearer {GROQ_KEY}"}, files=archivos_data, data=datos)
        
        ruta_audio.unlink(missing_ok=True) # Borrar archivo temporal

        if r.status_code == 200:
            texto_transcrito = r.json()["text"]
            await msg_temp.edit_text(f"🎤 *Escuché:* _{texto_transcrito}_", parse_mode="Markdown")
            
            # 3. Inyectar el texto transcrito y procesar
            update.message.text = texto_transcrito
            await handle_message(update, context)
        else:
            await msg_temp.edit_text("❌ Error al entender el audio.")
    except Exception as e:
        await msg_temp.edit_text(f"❌ Falló el servicio de voz: {e}")


# ══════════════════════════════════════════════════════════════
# ERROR HANDLER
# ══════════════════════════════════════════════════════════════

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Loguea errores de Telegram sin tirar traceback al log."""
    print(f"❌ Error del bot: {context.error}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def _resetear_sesion_polling():
    """
    Fuerza el cierre de cualquier sesión de long-polling activa en Telegram.
    Cuando un bot anterior muere sin cerrar limpio la conexión HTTP, Telegram
    mantiene esa sesión viva hasta ~30 segundos. Esta llamada la 'roba',
    evitando el error Conflict al arrancar.
    """
    if not BOT_TOKEN:
        return
    try:
        requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            params={"timeout": 0, "offset": -1},
            timeout=5
        )
        time.sleep(1)
    except Exception:
        pass


def main():
    if not BOT_TOKEN:
        print("❌ Falta TELEGRAM_BOT_TOKEN")
        return

    # Inicializar estructura
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USUARIOS_DIR.mkdir(parents=True, exist_ok=True)

    if not USUARIOS_JSON.exists():
        _crear_config_default()

    if not ESTADO_JSON.exists():
        guardar_estado(dict(ESTADO_DEFAULT))

    print("🤖 bot_che v3 ✅")
    print(f"   Config:   {USUARIOS_JSON}")
    print(f"   Estado:   {ESTADO_JSON}")
    print(f"   Usuarios: {USUARIOS_DIR}")

    # app = Application.builder().token(BOT_TOKEN).build()


    
    async def _post_init(application):
        """Carga inicial de plugins y arranca el loop de recarga."""
        _cargar_plugins()
        asyncio.create_task(_loop_plugins())

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )

    # Manejadores de mensajes
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_error_handler(error_handler)

    print("⏳ Reseteando sesión de polling en Telegram...")
    _resetear_sesion_polling()

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
