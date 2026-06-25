 
#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

async def procesar_comando_camara(update, texto):
    """
    Procesa las peticiones de cámara buscando destinos dinámicos en tele.json.
    """
    texto_limpio = texto.lower().strip()
    
    # 1. Verificamos si el mensaje es para la cámara
    if not any(p in texto_limpio for p in ["foto", "captura", "camara", "cámara"]):
        return False

    ruta_secretos = Path.home() / "compartido" / "secret" / "tele.json"
    
    # 2. Leer los IDs dinámicos del JSON
    try:
        with open(ruta_secretos, "r", encoding="utf-8") as f:
            ids_secretos = json.load(f)
    except Exception as e:
        await update.message.reply_text(f"❌ Error al leer secretos en tele.json: {e}")
        return True

    # 3. Buscar destino dinámico basado en las claves del JSON
    destino_id = None
    target_name = ""

    # Recorremos las claves ("wen", "mama", etc.) que guardaste en tu archivo
    for nombre_clave in ids_secretos.keys():
        if nombre_clave.lower() in texto_limpio:
            destino_id = ids_secretos[nombre_clave]
            target_name = f"a {nombre_clave} 🚀"
            break

    # Si no especificaste a nadie del JSON, por defecto te lo mandás a vos mismo
    if not destino_id:
        destino_id = update.effective_chat.id
        target_name = "a vos mismo 📱"

    # 4. Determinar el Modo (Liviano o con IA)
    usar_ia = any(p in texto_limpio for p in ["analiz", "descrip", "detall", "grok", "ia"])
    flags = "--telegram"
    
    if usar_ia:
        flags += " --analizar"
        await update.message.reply_text(f"📸 Capturando y analizando con Groq Vision {target_name}...")
    else:
        await update.message.reply_text(f"📸 Enviando captura rápida liviana {target_name}...")

    # 5. Ejecutar tu script de captura original
    script_path = Path.home() / "compartido" / "amor" / "camara_captura.py"
    cmd = f"python3 {script_path} {flags} --chat-id {destino_id}"

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=40)
        if result.returncode != 0:
            await update.message.reply_text(f"❌ Falló el script:\n```\n{result.stderr}\n```")
        else:
            await update.message.reply_text("✅ ¡Comando ejecutado con éxito!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error de ejecución: {e}")

    return True
