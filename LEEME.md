# CHE v2 — Guía de instalación

## Qué hay en este zip

```
bot_che_v2.py          ← bot principal (reemplaza bot_che.py)
acciones_archivos.py   ← sin cambios, copiado para tener todo junto
comandos_camara.py     ← sin cambios, copiado para tener todo junto
config/
  usuarios.json        ← configuración de usuarios y permisos
  estado.json          ← estado de presencia (se actualiza solo)
```

---

## Instalación

### 1. Copiar los archivos Python

Reemplazá `bot_che.py` con `bot_che_v2.py` en el mismo directorio donde
tenés el bot actual. Los otros dos `.py` ya los tenés, no necesitás
reemplazarlos (pero están incluidos por si los reorganizás).

### 2. Copiar la carpeta config

```bash
mkdir -p ~/.amor/config
cp config/usuarios.json ~/.amor/config/
cp config/estado.json   ~/.amor/config/
```

### 3. Editar usuarios.json

Abrí `~/.amor/config/usuarios.json` y verificá que los IDs sean correctos.
Los que ya están son los de tu bot actual (los tres que tenías en MIS_CHAT_IDS).

Cambiá el nombre "Wen (celu)" si es otro dispositivo tuyo.
Cambiá "Mamá" por el nombre real o como quieras.

### 4. Lanzar

```bash
python3 bot_che_v2.py
```

El bot crea solo `~/.amor/usuarios/<chat_id>/` para cada persona la primera
vez que hablan. No borra nada del `~/.amor/` anterior.

---

## Nueva estructura de directorios

```
~/.amor/
├── config/
│   ├── usuarios.json    ← quién puede hacer qué
│   └── estado.json      ← tu estado de presencia actual
└── usuarios/
    ├── 7127341580/      ← tu memoria (PC)
    │   ├── sesion.md
    │   ├── memoria.md
    │   ├── historial.jsonl
    │   └── pendientes.json
    ├── 8695547311/      ← tu memoria (celu)
    │   └── ...
    └── 8820235343/      ← memoria de mamá (separada)
        └── ...
```

La memoria vieja en `~/.amor/historial.jsonl`, `sesion_actual.md` y
`memoria_sistema.md` queda intacta, no se toca.

---

## Comandos de estado (solo admin, empiezan con !)

| Comando        | Efecto                        |
|----------------|-------------------------------|
| `!casa`        | Marcás que estás en casa      |
| `!fuera`       | Marcás que saliste            |
| `!durmiendo`   | Activás modo durmiendo        |
| `!despierta`   | Desactivás modo durmiendo     |
| `!ocupada`     | Marcás que estás ocupada      |
| `!disponible`  | Marcás que estás disponible   |
| `!estado`      | Ver el estado actual completo |
| `!pendientes`  | Ver mensajes urgentes de mamá |
| `!ayuda`       | Lista de comandos             |

---

## Qué puede hacer mamá

Según `permisos_familiares` en `usuarios.json`, mamá puede:

- Preguntar si estás en casa → el bot responde según `estado.json`
- Mandar un mensaje urgente → te queda guardado en `!pendientes`

No puede:
- Ver las cámaras
- Ejecutar comandos
- Ver tus archivos
- Ver tu historial

Podés cambiar cualquier permiso editando `usuarios.json` directamente,
o eventualmente diciéndole al bot que lo cambie.

---

## Para agregar un usuario nuevo

Editá `~/.amor/config/usuarios.json` y agregá una entrada:

```json
"ID_TELEGRAM": {
  "nombre": "Nombre",
  "rol": "familia",
  "camaras": false,
  "ejecutar_comandos": false,
  "editar_archivos": false
}
```

Y si querés darle permisos de presencia, agregalo en `permisos_familiares`.

---

## Diferencias respecto a v1

- `MIS_CHAT_IDS` desaparece → reemplazado por `usuarios.json`
- Memoria separada por usuario (ya no se mezclan sesiones)
- Mamá tiene prompt distinto (amable, sin acceso técnico)
- Comandos `!` para gestionar estado de presencia
- Sistema de mensajes urgentes (`!pendientes`)
- El estado actual se incluye en el contexto de la IA admin
