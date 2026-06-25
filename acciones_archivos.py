 
#!/usr/bin/env python3
"""
acciones_archivos.py - Módulo mejorado para che2.py y bot_che.py
"""

import re
from pathlib import Path

# ==================== CONFIGURACIÓN ====================
MAX_CHARS_ARCHIVO = 8000
MAX_ARCHIVOS_POR_PREGUNTA = 4
TAMANIO_MAXIMO_BYTES = 800_000

EXTENSIONES_TEXTO = {
    ".py", ".sh", ".md", ".txt", ".conf", ".cfg", ".json", ".yaml", ".yml",
    ".jsonl", ".ini", ".env", ".log", ".csv", ".toml", ".html", ".css", ".js"
}

DIRECTORIOS_PERMITIDOS = []  # vacío = sin restricción


def _dentro_de_permitidos(ruta: Path) -> bool:
    if not DIRECTORIOS_PERMITIDOS:
        return True
    ruta = ruta.resolve()
    return any(str(ruta).startswith(str(base.resolve())) for base in DIRECTORIOS_PERMITIDOS)


# ==================== DETECCIÓN ====================
PATRON_RUTA = re.compile(
    r"(?:\~|\.{0,2}/)?[\w\-./]+\.\w+"
    r"|\b[\w\-]+\.(?:py|sh|md|txt|conf|json|yaml|yml|log|csv)\b"
)

def extraer_rutas(pregunta):
    rutas = []
    for candidato in PATRON_RUTA.findall(pregunta):
        try:
            p = Path(candidato).expanduser()
            if p.exists() and p.is_file() and _dentro_de_permitidos(p):
                rutas.append(p)
        except:
            continue
    return rutas


# ==================== LECTURA ====================
def leer_archivo(ruta):
    try:
        p = Path(ruta).expanduser()
        if not p.exists() or not p.is_file():
            return None, f"no existe: {p}"
        if p.suffix.lower() not in EXTENSIONES_TEXTO:
            return None, f"extensión no soportada: {p.suffix}"

        if p.stat().st_size > TAMANIO_MAXIMO_BYTES:
            return None, f"archivo muy grande ({p.stat().st_size:,} bytes)"

        contenido = p.read_text(encoding="utf-8", errors="replace")
        truncado = len(contenido) > MAX_CHARS_ARCHIVO
        if truncado:
            contenido = contenido[:MAX_CHARS_ARCHIVO] + f"\n\n[... TRUNCADO - archivo completo tiene {p.stat().st_size:,} bytes ...]"

        return contenido, None
    except Exception as e:
        return None, str(e)


def contexto_de_archivos(pregunta):
    rutas = extraer_rutas(pregunta)
    if not rutas:
        return ""

    bloques = []
    for ruta in rutas[:MAX_ARCHIVOS_POR_PREGUNTA]:
        contenido, error = leer_archivo(ruta)
        if contenido:
            bloques.append(f"--- {ruta} ---\n{contenido}")
        else:
            bloques.append(f"--- {ruta} ---\n[Error: {error}]")
    return "\n\n".join(bloques)


# ==================== ESCRITURA Y EDICIÓN ====================

PATRON_ESCRIBIR = re.compile(r"```escribir:([^\n]+)\n(.*?)```", re.DOTALL)
PATRON_EDITAR   = re.compile(r"```editar:([^\n]+?)(?::(\d+)(?:-(\d+))?)?\n(.*?)```", re.DOTALL)

def ofrecer_escritura_o_edicion(respuesta):
    """Busca bloques de escribir o editar y ofrece la acción."""
    
    # Primero intentamos edición parcial
    match_edit = PATRON_EDITAR.search(respuesta)
    if match_edit:
        ruta_str = match_edit.group(1).strip()
        linea_inicio = int(match_edit.group(2) or 1)
        linea_fin = int(match_edit.group(3) or linea_inicio)
        nuevo_contenido = match_edit.group(4)

        ruta = Path(ruta_str).expanduser()
        if not _dentro_de_permitidos(ruta):
            print(f"⛔ {ruta} fuera de directorios permitidos.")
            return

        _ofrecer_edicion_parcial(ruta, linea_inicio, linea_fin, nuevo_contenido)
        return

    # Si no hay edición, probamos escritura completa
    match = PATRON_ESCRIBIR.search(respuesta)
    if match:
        ruta_str, contenido = match.group(1).strip(), match.group(2)
        ruta = Path(ruta_str).expanduser()

        if not _dentro_de_permitidos(ruta):
            print(f"⛔ {ruta} fuera de directorios permitidos.")
            return

        print("\n" + "─" * 50)
        aviso = "⚠️ SOBREESCRIBIRÁ el archivo existente" if ruta.exists() else "📄 Archivo nuevo"
        print(f"📝 {ruta}\n{aviso}")
        op = input("¿Guardar? (s/n): ").strip().lower()
        if op == "s":
            try:
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_text(contenido, encoding="utf-8")
                print(f"✅ Guardado correctamente: {ruta}")
            except Exception as e:
                print(f"❌ Error: {e}")
        else:
            print("❌ Cancelado.")


def _ofrecer_edicion_parcial(ruta: Path, inicio: int, fin: int, nuevo_texto: str):
    if not ruta.exists():
        print(f"❌ El archivo {ruta} no existe.")
        return

    lineas = ruta.read_text(encoding="utf-8").splitlines(keepends=True)
    total_lineas = len(lineas)

    # Ajustar rangos
    inicio = max(1, inicio)
    fin = min(total_lineas, fin or inicio)

    print("\n" + "─" * 50)
    print(f"✏️  Edición parcial en {ruta}")
    print(f"Líneas {inicio}-{fin} → {fin-inicio+1} líneas serán reemplazadas")
    print("\nVista previa del cambio:")
    print("".join(lineas[inicio-1:fin])[:500] + "..." if fin-inicio > 10 else "")

    op = input("¿Aplicar edición? (s/n): ").strip().lower()
    if op == "s":
        try:
            nuevo_texto = nuevo_texto.rstrip() + "\n"
            lineas[inicio-1:fin] = [nuevo_texto]
            ruta.write_text("".join(lineas), encoding="utf-8")
            print(f"✅ Edición aplicada en {ruta}")
        except Exception as e:
            print(f"❌ Error: {e}")
    else:
        print("❌ Cancelado.")