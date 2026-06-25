#!/bin/bash
# ══════════════════════════════════════════════════════
# che_manager.sh — Gestor del bot Che
# Uso:  ./che_manager.sh [start|console|stop|restart|log|status]
#       ./che_manager.sh          → menu interactivo
# ══════════════════════════════════════════════════════

BOT_SCRIPT="$HOME/compartido/amor/bot_che_v3.py"
PID_FILE="$HOME/.amor/bot.pid"
LOG_FILE="$HOME/.amor/bot.log"
LOG_MAX_MB=5

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'
C='\033[0;36m'; B='\033[1m'; N='\033[0m'

# ── Helpers ──────────────────────────────────────────

_pid_vivo() {
    [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

_liberar_telegram() {
    local token
    token=$(grep -oP "(?<=TELEGRAM_BOT_TOKEN=)['\"]?[^'\"[:space:]]+" ~/.bashrc | tr -d "'\"" | head -1)
    if [[ -n "$token" ]]; then
        curl -s "https://api.telegram.org/bot${token}/getUpdates?offset=-1&limit=1" > /dev/null 2>&1
        curl -s "https://api.telegram.org/bot${token}/deleteWebhook?drop_pending_updates=true" > /dev/null 2>&1
    fi
}

_matar() {
    if _pid_vivo; then
        local pid
        pid=$(cat "$PID_FILE")
        kill "$pid" 2>/dev/null
        echo -e "${R}Bot detenido (PID $pid)${N}"
        rm -f "$PID_FILE"
    fi
    pkill -f "bot_che" 2>/dev/null
    echo -e "${Y}Liberando sesion en Telegram...${N}"
    _liberar_telegram
    echo -e "${Y}Esperando que Telegram libere la conexion...${N}"
    sleep 8
}

_rotar_log() {
    if [[ -f "$LOG_FILE" ]]; then
        local size_mb
        size_mb=$(du -m "$LOG_FILE" | cut -f1)
        if [[ "$size_mb" -ge "$LOG_MAX_MB" ]]; then
            mv "$LOG_FILE" "${LOG_FILE}.anterior"
            echo -e "${Y}Log rotado (era ${size_mb}MB)${N}"
        fi
    fi
}

_status() {
    if _pid_vivo; then
        local pid
        pid=$(cat "$PID_FILE")
        local uptime
        uptime=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')
        echo -e "${G}${B}Bot corriendo${N} — PID ${C}$pid${N} — uptime ${C}$uptime${N}"
    else
        echo -e "${R}Bot detenido${N}"
    fi
}

# ── Comandos ─────────────────────────────────────────

cmd_start() {
    _matar
    _rotar_log
    mkdir -p "$(dirname "$PID_FILE")"
    nohup python3 "$BOT_SCRIPT" >> "$LOG_FILE" 2>&1 &
    local pid=$!
    echo $pid > "$PID_FILE"
    sleep 2
    if _pid_vivo; then
        echo -e "${G}${B}Bot iniciado en background${N} — PID ${C}$pid${N}"
        echo -e "   Log en vivo: ${C}tail -f $LOG_FILE${N}"
    else
        echo -e "${R}El bot no arranco. Ultimas lineas del log:${N}"
        tail -20 "$LOG_FILE"
        rm -f "$PID_FILE"
    fi
}

cmd_console() {
    _matar
    echo -e "${C}Iniciando en consola — Ctrl+C para detener${N}"
    echo ""
    python3 "$BOT_SCRIPT"
}

cmd_stop() {
    if _pid_vivo; then
        _matar
    else
        echo -e "${Y}El bot ya estaba detenido${N}"
        rm -f "$PID_FILE"
    fi
}

cmd_restart() {
    echo -e "${Y}Reiniciando...${N}"
    _matar
    cmd_start
}

cmd_diagnostico() {
    echo -e "${C}Procesos Python corriendo ahora:${N}"
    echo ""
    ps aux | grep -E "[p]ython" | awk '{printf "  PID %-7s CMD: %s\n", $2, substr($0, index($0,$11))}'
    echo ""
    echo -e "${C}Especificamente bot_che:${N}"
    local encontrados
    encontrados=$(pgrep -fa "bot_che" 2>/dev/null)
    if [[ -n "$encontrados" ]]; then
        echo "$encontrados" | awk '{print "  PID " $1 ": " $2, $3, $4}'
    else
        echo "  (ninguno)"
    fi
}

cmd_log() {
    if [[ -f "$LOG_FILE" ]]; then
        echo -e "${C}Log: $LOG_FILE (Ctrl+C para salir)${N}"
        echo ""
        tail -f "$LOG_FILE"
    else
        echo -e "${Y}Sin log todavia (el bot nunca corrio en background)${N}"
    fi
}

# ── Menu interactivo ──────────────────────────────────

menu() {
    while true; do
        echo ""
        echo -e "${C}+----------------------------------+${N}"
        echo -e "${C}|     CHE MANAGER                  |${N}"
        echo -e "${C}+----------------------------------+${N}"
        echo ""
        _status
        echo ""
        echo -e "  ${B}1)${N} Iniciar en background"
        echo -e "  ${B}2)${N} Iniciar en consola"
        echo -e "  ${B}3)${N} Detener"
        echo -e "  ${B}4)${N} Reiniciar"
        echo -e "  ${B}5)${N} Ver log en vivo"
        echo -e "  ${B}6)${N} Status"
        echo -e "  ${B}7)${N} Diagnostico"
        echo -e "  ${B}0)${N} Salir"
        echo ""
        read -rp "  Opcion: " OPT
        echo ""
        case "$OPT" in
            1) cmd_start ;;
            2) cmd_console ;;
            3) cmd_stop ;;
            4) cmd_restart ;;
            5) cmd_log ;;
            6) _status ;;
            7) cmd_diagnostico ;;
            0) exit 0 ;;
            *) echo -e "${Y}Opcion invalida${N}" ;;
        esac
    done
}

# ── Despacho ──────────────────────────────────────────

case "${1:-}" in
    start)   cmd_start ;;
    console) cmd_console ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    log)     cmd_log ;;
    status)  _status ;;
    *)       menu ;;
esac
