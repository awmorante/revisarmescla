#!/usr/bin/env python3
"""
che.py - Asistente CLI con memoria persistente y cascada de modelos
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Uso:   che tu pregunta sin comillas
Alias: alias che='python3 ~/compartido/amor/che.py'

CASCADA DE MOTORES (en orden de prioridad):
  1. Groq / Llama 3.3 70B  ← primero, gratis, rápido, muy capaz
  2. Gemini Flash           ← fallback si Groq falla o se agota
  3. Asus local (Phi-3)     ← fallback si no hay internet
  4. Dell local (Qwen 0.5B) ← último recurso, siempre disponible

KEYS necesarias en ~/.bashrc:
  export GROQ_API_KEY="gsk_..."
  export GEMINI_API_KEY="AI..."
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import sys
import os
import json
import requests
import subprocess
from datetime import datetime
from pathlib import Path


# ══════════════════════════════════════════════════════════════
# SECCIÓN 1: CONFIGURACIÓN
# Lee las API keys del .bashrc y define rutas de hardware local
# ══════════════════════════════════════════════════════════════

GROQ_KEY     = os.environ.get("GROQ_API_KEY", "")
GEMINI_KEY   = os.environ.get("GEMINI_API_KEY", "")
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")  # opcional, para más adelante

# Asus en red local (LM Studio o similar corriendo ahí)
ASUS_IP      = "192.168.0.5"
PORT         = "1234"
URL_ASUS     = f"http://{ASUS_IP}:{PORT}/v1/chat/completions"

# Modelo local en la Dell (llama.cpp)
LLAMA_CLI    = "/home/ani/llama.cpp/build/bin/llama-cli"
MODELO_LOCAL = "/home/ani/modelos-gguf/qwen2.5-0.5b-instruct-q4_k_m.gguf"


# ══════════════════════════════════════════════════════════════
# SECCIÓN 2: RUTAS DE MEMORIA
# Todo se guarda en ~/.amor/ para no mezclar con el proyecto
# ══════════════════════════════════════════════════════════════

BASE_DIR      = Path.home() / ".amor"
HISTORIAL     = BASE_DIR / "historial.jsonl"   # registro permanente de todo
MEMORIA_SIS   = BASE_DIR / "memoria_sistema.md" # info del sistema, se actualiza 1x/día
SESION_HOY    = BASE_DIR / "sesion_actual.md"   # conversación de hoy, da contexto al modelo
RESUMENES_DIR = BASE_DIR / "resumenes"          # resúmenes generados por amor-resumen.py

BASE_DIR.mkdir(exist_ok=True)
RESUMENES_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════════
# SECCIÓN 3: LEER MEMORIA
# Funciones para leer los archivos de contexto
# ══════════════════════════════════════════════════════════════

def leer_memoria_sistema():
    """Lee la info del sistema guardada (máx 3000 chars para no inflar el prompt)."""
    if MEMORIA_SIS.exists():
        return MEMORIA_SIS.read_text(encoding="utf-8")[:3000]
    return ""

def leer_sesion_actual():
    """Lee las últimas interacciones de hoy para dar contexto de conversación."""
    if SESION_HOY.exists():
        return SESION_HOY.read_text(encoding="utf-8")[-2000:]
    return ""


# ══════════════════════════════════════════════════════════════
# SECCIÓN 4: GUARDAR MEMORIA
# Funciones para persistir lo que pasa en cada interacción
# ══════════════════════════════════════════════════════════════

def guardar_historial(pregunta, respuesta, motor):
    """Guarda CADA intercambio en historial.jsonl (registro permanente)."""
    entrada = {
        "ts":    datetime.now().isoformat(),
        "q":     pregunta,
        "a":     respuesta,
        "motor": motor
    }
    with open(HISTORIAL, "a", encoding="utf-8") as f:
        f.write(json.dumps(entrada, ensure_ascii=False) + "\n")

def guardar_sesion(pregunta, respuesta, motor):
    """Actualiza el archivo de sesión de hoy (da contexto a la próxima pregunta)."""
    linea = (
        f"\n[{datetime.now().strftime('%H:%M')}] ({motor})\n"
        f"Wen: {pregunta}\n"
        f"Che: {respuesta}\n"
    )
    with open(SESION_HOY, "a", encoding="utf-8") as f:
        f.write(linea)


# ══════════════════════════════════════════════════════════════
# SECCIÓN 5: ACTUALIZAR INFO DEL SISTEMA
# Se ejecuta automáticamente, pero solo si pasaron más de 24hs
# ══════════════════════════════════════════════════════════════

def actualizar_memoria_sistema():
    """Recolecta info del sistema y la guarda. Solo corre 1 vez por día."""
    if MEMORIA_SIS.exists():
        edad_horas = (datetime.now().timestamp() - MEMORIA_SIS.stat().st_mtime) / 3600
        if edad_horas < 24:
            return  # está fresca, no tocar

    print("📋 Actualizando memoria del sistema (1 vez por día)...")

    secciones = {
        "Sistema":          "neofetch --stdout 2>/dev/null || uname -a",
        "IP local":         "ip addr show | grep 'inet ' | awk '{print $2}'",
        "IP pública":       "curl -s --max-time 4 ifconfig.me || echo 'sin acceso externo'",
        "Disco":            "df -h --output=target,used,avail,pcent 2>/dev/null | head -6",
        "Memoria RAM":      "free -h | head -3",
        "Interfaces red":   "ip link show | grep '^[0-9]' | awk -F': ' '{print $2}'",
        "Python":           "python3 --version && pip3 --version",
        "Paquetes pip":     "pip3 list --format=columns 2>/dev/null | head -20",
        "Servicios activos":"systemctl list-units --type=service --state=running --no-pager 2>/dev/null | head -15 || echo 'no disponible'",
        "Variables entorno":"env | grep -v 'KEY\\|TOKEN\\|SECRET\\|PASS' | sort | head -20",
    }

    contenido = f"# Memoria del Sistema — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    for nombre, cmd in secciones.items():
        salida = subprocess.getoutput(cmd)
        contenido += f"## {nombre}\n```\n{salida}\n```\n\n"

    MEMORIA_SIS.write_text(contenido, encoding="utf-8")
    print(f"✅ Guardado en {MEMORIA_SIS}\n")


# ══════════════════════════════════════════════════════════════
# SECCIÓN 6: DETECCIÓN DE CONTEXTO Y AMBIGÜEDAD
# Decide qué info adicional incluir en el prompt según la pregunta
# ══════════════════════════════════════════════════════════════

CONTEXTOS = {
    "sistema": ["pantalla", "bloqueo", "audio", "teclado", "mouse", "disco",
                "memoria", "hardware", "driver", "error", "xfce", "display", "monitor",
                "batería", "energía", "suspender", "hibernar"],
    "red":     ["vpn", "ip", "ping", "red", "interfaz", "ssh", "firewall",
                "iptables", "router", "dns", "puerto", "socket", "wireshark", "nmcli",
                "ethernet", "wifi", "hostapd", "dnsmasq"],
    "python":  ["python", "pip", "librería", "script", "importar", "módulo", "venv",
                "instalar", "paquete"],
}

def detectar_contextos(prompt):
    """Retorna lista de categorías relevantes para la pregunta."""
    p = prompt.lower()
    return [cat for cat, palabras in CONTEXTOS.items() if any(w in p for w in palabras)]

def es_ambiguo(prompt):
    """Solo pide aclaración si la pregunta es de 1 sola palabra o usa pronombres sin referente."""
    palabras = prompt.strip().split()
    muy_corto = len(palabras) < 2
    vago = any(v in prompt.lower() for v in ["eso", "lo mismo", "aquello", "el tema"])
    return muy_corto or vago


# ══════════════════════════════════════════════════════════════
# SECCIÓN 7: CONSTRUIR EL PROMPT DEL SISTEMA
# Arma el contexto que recibe el modelo antes de tu pregunta
# SIEMPRE incluye la sesión de hoy para que entienda el hilo
# ══════════════════════════════════════════════════════════════

def construir_prompt_sistema(contextos):
    """
    Construye el system prompt con el contexto relevante.
    La sesión de hoy SIEMPRE se incluye → así el modelo recuerda
    lo que se habló antes en la misma sesión.
    """
    base = (
        "Sos 'Che', un asistente de terminal experto en Linux, redes y Python. "
        "Respondé siempre en español rioplatense, ultra corto y al hueso. "
        "Cuando des un comando de terminal, ponelo SIEMPRE en bloque ```bash\\ncomando\\n```. "
        "Si necesitás más contexto para responder bien, hacé UNA sola pregunta concreta."
    )

    extras = []

    # ← SIEMPRE incluir la sesión de hoy (aunque no haya keywords de "sesion")
    # Esto es lo que permite que las preguntas de seguimiento tengan contexto
    sesion = leer_sesion_actual()
    if sesion:
        extras.append(f"=== CONVERSACIÓN DE ESTA SESIÓN ===\n{sesion}")

    # Info del sistema solo si la pregunta es sobre sistema o red
    if "sistema" in contextos or "red" in contextos:
        mem = leer_memoria_sistema()
        if mem:
            extras.append(f"=== INFO DE LA MÁQUINA ===\n{mem}")

    return base + ("\n\n" + "\n\n".join(extras) if extras else "")


# ══════════════════════════════════════════════════════════════
# SECCIÓN 8: MOTORES DE IA
# Cada función intenta un motor y retorna (respuesta, nombre_motor)
# Si falla retorna (None, None) → la cascada prueba el siguiente
# ══════════════════════════════════════════════════════════════

def llamar_groq(pregunta, sys_prompt):
    """
    MOTOR 1 — Groq / Llama 3.3 70B
    Gratis, sin tarjeta, muy rápido. Motor principal para todo.
    Límite free: 14.400 req/día, 30 req/min.
    """
    if not GROQ_KEY:
        return None, None
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user",   "content": pregunta}
                ],
                "temperature": 0.1,
                "max_tokens": 400
            },
            timeout=12
        )
        if r.status_code == 200:
            return r.json()['choices'][0]['message']['content'].strip(), "Groq/Llama3.3-70B ⚡"
        print(f"⚠️ Groq HTTP {r.status_code}")
    except Exception as e:
        print(f"⚠️ Groq falló: {e}")
    return None, None


def llamar_gemini(pregunta, sys_prompt):
    """
    MOTOR 2 — Gemini (fallback de Groq)
    Prueba modelos en orden hasta que uno funcione.
    Si uno da error de cuota, intenta el siguiente automáticamente.
    """
    if not GEMINI_KEY:
        return None, None

    # Prueba estos modelos en orden (el primero que ande gana)
    modelos = [
        "gemini-2.0-flash",       # el más capaz del free tier
        "gemini-2.0-flash-lite",  # más liviano, límites más generosos
        "gemini-1.5-flash",       # versión anterior, por si acaso
    ]

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_KEY)

        for modelo in modelos:
            try:
                r = client.models.generate_content(
                    model=modelo,
                    contents=f"{sys_prompt}\n\nUsuario: {pregunta}"
                )
                return r.text.strip(), f"Gemini ({modelo}) 🌌"
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                    print(f"⚠️ {modelo} sin cuota, probando siguiente...")
                    continue  # intenta el siguiente modelo
                else:
                    print(f"⚠️ Gemini {modelo} falló: {e}")
                    break  # error distinto, no tiene sentido seguir probando
    except Exception as e:
        print(f"⚠️ Gemini no disponible: {e}")

    return None, None


def llamar_asus(pregunta, sys_prompt):
    """
    MOTOR 3 — Asus en red local (Phi-3 vía LM Studio)
    Solo funciona cuando la Asus está prendida y en la misma red.
    """
    try:
        print("💻 Intentando Asus local...")
        r = requests.post(URL_ASUS, json={
            "model": "phi-3-mini-128k-instruct-imatrix-smashed",
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user",   "content": pregunta}
            ],
            "temperature": 0.1,
            "max_tokens": 200
        }, timeout=8)
        if r.status_code == 200:
            return r.json()['choices'][0]['message']['content'].strip(), "Asus Local (Phi-3) 💻"
        print(f"⚠️ Asus HTTP {r.status_code}")
    except Exception as e:
        print(f"⚠️ Asus falló: {e}")
    return None, None


def llamar_local(pregunta, sys_prompt):
    """
    MOTOR 4 — Qwen 0.5B en la Dell vía llama.cpp
    Último recurso. Sin internet, sin red. Siempre disponible.
    Es el más limitado pero mejor que nada.
    """
    print("📴 Despertando Qwen local en la Dell...")
    try:
        res = subprocess.run([
            LLAMA_CLI, "-m", MODELO_LOCAL,
            "-p", (
                f"<|im_start|>system\n{sys_prompt}<|im_end|>\n"
                f"<|im_start|>user\n{pregunta}<|im_end|>\n"
                f"<|im_start|>assistant\n"
            ),
            "-n", "128", "--quiet"
        ], capture_output=True, text=True)
        return res.stdout.strip(), "Llama.cpp/Qwen-0.5B 🛠️"
    except Exception as e:
        print(f"❌ Local falló: {e}")
    return None, None


# ══════════════════════════════════════════════════════════════
# SECCIÓN 9: EXTRAER Y OFRECER EJECUCIÓN DEL COMANDO
# Si la respuesta tiene un bloque ```bash, pregunta si ejecutar
# ══════════════════════════════════════════════════════════════

def ofrecer_ejecucion(respuesta):
    """Extrae el primer bloque bash de la respuesta y ofrece ejecutarlo."""
    if "```" not in respuesta:
        return
    try:
        bloque = respuesta.split("```")[1]
        for prefijo in ["bash\n", "sh\n", "bash", "sh"]:
            if bloque.startswith(prefijo):
                bloque = bloque[len(prefijo):]
                break
        cmd = bloque.strip()
        if not cmd:
            return
        print("\n" + "─" * 40)
        op = input(f"¿Ejecuto: '{cmd}'? (s/n): ").strip().lower()
        if op == "s":
            print("🚀 Mandándole mecha...")
            os.system(cmd)
        else:
            print("❌ Cancelado.")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# SECCIÓN 10: VOZ
# Lee la respuesta en voz alta (ignora el bloque de código)
# Falla silenciosamente si gtts-cli o mpv no están instalados
# ══════════════════════════════════════════════════════════════

def hablar(texto):
    """Lee la parte de texto de la respuesta (sin el código bash)."""
    try:
        t = texto.split("```")[0].strip()[:200].replace('"', '').replace("'", "")
        if t:
            os.system(
                f'gtts-cli "{t}" --lang es --tld com.ar --output /tmp/che.mp3 2>/dev/null'
                f' && mpv /tmp/che.mp3 > /dev/null 2>&1'
                f' && rm -f /tmp/che.mp3'
            )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# SECCIÓN 11: MAIN
# Punto de entrada. Orquesta todo el flujo.
# ══════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Che, faltó la pregunta. Ej: che como veo mis procesos")
        sys.exit(1)

    # Une todos los argumentos → podés escribir sin comillas
    pregunta = " ".join(sys.argv[1:])

    # ── Paso 1: actualizar info del sistema si hace más de 24hs ──
    actualizar_memoria_sistema()

    # ── Paso 2: pedir aclaración solo si la pregunta es de 1 palabra o muy vaga ──
    if es_ambiguo(pregunta):
        extra = input("❓ Medio vaga la pregunta, ¿me das más detalle? ").strip()
        if extra:
            pregunta = f"{pregunta}. Contexto: {extra}"

    # ── Paso 3: detectar qué contexto extra incluir en el prompt ──
    contextos = detectar_contextos(pregunta)
    if contextos:
        print(f"🔍 Contexto detectado: {', '.join(contextos)}")

    # ── Paso 4: armar el system prompt con contexto relevante ──
    sys_prompt = construir_prompt_sistema(contextos)

    # ── Paso 5: cascada de motores (prueba en orden, usa el primero que responde) ──
    respuesta, motor = llamar_groq(pregunta, sys_prompt)

    if not respuesta:
        respuesta, motor = llamar_gemini(pregunta, sys_prompt)

    if not respuesta:
        respuesta, motor = llamar_asus(pregunta, sys_prompt)

    if not respuesta:
        respuesta, motor = llamar_local(pregunta, sys_prompt)

    # ── Paso 6: mostrar resultado y guardar en memoria ──
    print(f"\n🤖 [{motor}]:")
    if respuesta:
        print(respuesta)
        guardar_historial(pregunta, respuesta, motor)
        guardar_sesion(pregunta, respuesta, motor)
        hablar(respuesta)
        ofrecer_ejecucion(respuesta)
    else:
        print("No hubo amor. Ningún motor pudo responder.")
        guardar_historial(pregunta, "SIN RESPUESTA", "ninguno")


if __name__ == "__main__":
    main()
