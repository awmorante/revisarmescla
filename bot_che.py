#!/usr/bin/env python3
"""
bot_che.py - Bot de Telegram con soporte de archivos y módulo de cámara
"""

import os
import sys
import json
import uuid
import subprocess
import requests
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

# Forzamos a Python a buscar módulos en el mismo directorio de este script
sys.path.append(str(Path(__file__).resolve().parent))

import acciones_archivos as archivos
import comandos_camara  # ← módulo de control de cámara


# ══════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════

BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GROQ_KEY   = os.environ.get("GROQ_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

# Tus IDs autorizados (PC, Celu actual y el de tu vieja Ani)
MIS_CHAT_IDS = {7127341580, 8695547311, 8820235343}

BASE_DIR    = Path.home() / ".amor"
HISTORIAL   = BASE_DIR / "historial.jsonl"
SESION_HOY  = BASE_DIR / "sesion_actual.md"
MEMORIA_SIS = BASE_DIR / "memoria_sistema.md"

# Memoria temporal para comandos largos (Telegram limita callback_data a 64 bytes)
comandos_pendientes = {}


# ══════════════════════════════════════════════════════════════
# MEMORIA
# ══════════════════════════════════════════════════════════════

def leer_sesion():
    if SESION_HOY.exists():
        return SESION_HOY.read_text(encoding="utf-8")[-3000:]
    return ""

def leer_memoria_sistema():
    if MEMORIA_SIS.exists():
        return MEMORIA_SIS.read_text(encoding="utf-8")[:4000]
    return ""

def guardar_historial(user_msg, bot_resp):
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user_msg,
        "bot": bot_resp
    }
    with open(HISTORIAL, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

def guardar_sesion(user_msg, bot_resp):
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    ahora = datetime.now().strftime("%H:%M")
    txt = f"\n### 💬 [{ahora}] Wen\n{user_msg}\n\n🤖 **Che**:\n{bot_resp}\n"
    with open(SESION_HOY, "a", encoding="utf-8") as f:
        f.write(txt)


# ══════════════════════════════════════════════════════════════
# DETECCIÓN DE COMANDOS BASH EN LA RESPUESTA
# ══════════════════════════════════════════════════════════════

def extraer_comando(texto):
    """Busca un bloque ```bash ... ``` (o ```sh```) en la respuesta de la IA.
    Ignora bloques ```escribir:...``` / ```editar:...``` que ya maneja
    acciones_archivos.py, para que no se pisen entre sí."""
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
        bloque = bloque.strip()
        return bloque or None
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════
# MOTORES IA (CASCADA)
# ══════════════════════════════════════════════════════════════

def llamar_groq(pregunta, sys_prompt):
    if not GROQ_KEY:
        return None, "Groq (No key)"
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json"
    }

    sesion_ctx = leer_sesion()
    memoria_ctx = leer_memoria_sistema()
    archivos_ctx = archivos.contexto_de_archivos(pregunta)

    prompt_completo = f"{sys_prompt}\n\n"
    if memoria_ctx:
        prompt_completo += f"═ MEMORIA DE LARGO PLAZO ═\n{memoria_ctx}\n\n"
    if sesion_ctx:
        prompt_completo += f"═ CHAT DE HOY (ÚLTIMOS MENSAJES) ═\n{sesion_ctx}\n\n"
    if archivos_ctx:
        prompt_completo += f"═ ARCHIVOS LOCALES LEÍDOS ═\n{archivos_ctx}\n\n"

    prompt_completo += f"Pregunta actual del usuario: {pregunta}"

    data = {
        # llama-3.3-70b-specdec está decomisionado en Groq desde abril 2025.
        # openai/gpt-oss-120b es el reemplazo recomendado actual.
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": prompt_completo},
            {"role": "user", "content": pregunta}
        ],
        "temperature": 0.5,
        "max_completion_tokens": 1024
    }
    try:
        r = requests.post(url, json=data, headers=headers, timeout=20)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"], "Groq (GPT-OSS 120B)"
        print(f"Groq HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print(f"Groq error: {e}")
    return None, "Groq (Fallo)"

def llamar_gemini(pregunta, sys_prompt):
    if not GEMINI_KEY:
        return None, "Gemini (No key)"
    # gemini-1.5-flash está retirado; gemini-3.5-flash es el modelo Flash
    # vigente al día de hoy (sin fecha de apagado anunciada).
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {"Content-Type": "application/json"}

    sesion_ctx = leer_sesion()
    memoria_ctx = leer_memoria_sistema()
    archivos_ctx = archivos.contexto_de_archivos(pregunta)

    prompt_completo = f"{sys_prompt}\n\n"
    if memoria_ctx:
        prompt_completo += f"═ MEMORIA FIJA ═\n{memoria_ctx}\n\n"
    if sesion_ctx:
        prompt_completo += f"═ HISTORIAL DE HOY ═\n{sesion_ctx}\n\n"
    if archivos_ctx:
        prompt_completo += f"═ ARCHIVOS LOCALES LEÍDOS ═\n{archivos_ctx}\n\n"

    prompt_completo += f"Pregunta: {pregunta}"

    data = {
        "contents": [{"parts": [{"text": prompt_completo}]}]
    }
    try:
        r = requests.post(url, json=data, headers=headers, timeout=20)
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"], "Gemini 3.5 Flash"
        print(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print(f"Gemini error: {e}")
    return None, "Gemini (Fallo)"


# ══════════════════════════════════════════════════════════════
# HANDLERS TELEGRAM
# ══════════════════════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id not in MIS_CHAT_IDS:
        await update.message.reply_text("⛔ No autorizado")
        return

    texto = update.message.text

    # ─── ATAJO MODULAR DE CÁMARA ──────────────────────────────
    # Le pasamos el control al módulo externo. Si maneja el comando, corta acá.
    if await comandos_camara.procesar_comando_camara(update, texto):
        return
    # ──────────────────────────────────────────────────────────

    await update.message.reply_text("⏳ Consultando...")

    sys_prompt = "Sos Che, un asistente directo, sin introducciones corteses, hablá en español rioplatense (usá el vos)."

    # Cascada de motores
    respuesta, motor = llamar_groq(texto, sys_prompt)
    if not respuesta:
        respuesta, motor = llamar_gemini(texto, sys_prompt)

    if not respuesta:
        await update.message.reply_text("❌ Todos los motores externos fallaron. Estoy mudo.")
        return

    guardar_historial(texto, respuesta)
    guardar_sesion(texto, respuesta)
    await update.message.reply_text(respuesta[:4000])

    cmd = extraer_comando(respuesta)
    if cmd:
        # Guardamos el comando completo en memoria y mandamos solo un ID
        # cortito en el botón: callback_data de Telegram tiene un tope de
        # 64 bytes, así que un comando largo metido directo ahí se corta
        # y al ejecutarlo corre roto.
        cmd_id = str(uuid.uuid4())[:8]
        comandos_pendientes[cmd_id] = cmd

        keyboard = [[
            InlineKeyboardButton("🚀 Ejecutar", callback_data=f"exec:{cmd_id}"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel")
        ]]
        await update.message.reply_text(f"¿Ejecuto?\n`{cmd}`", reply_markup=InlineKeyboardMarkup(keyboard))

    archivos.ofrecer_escritura_o_edicion(respuesta)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("❌ Cancelado.")
    elif query.data.startswith("exec:"):
        cmd_id = query.data[5:]
        cmd = comandos_pendientes.pop(cmd_id, None)

        if not cmd:
            await query.edit_message_text("❌ Error: el comando expiró o se perdió de la memoria.")
            return

        await query.edit_message_text(f"🚀 Ejecutando: {cmd}")
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            output = result.stdout or result.stderr or "(sin output)"
            await query.message.reply_text(f"```\n{output[:3500]}\n```")
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {e}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        print("❌ Falta TELEGRAM_BOT_TOKEN")
        return

    print("🤖 bot_che arrancado correctamente ✅")
    print("   Soporte de archivos y cámara activado")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    app.run_polling()


if __name__ == "__main__":
    main()
