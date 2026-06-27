#!/bin/bash

echo "========================================"
echo "¡Hola Mundo!"
echo "========================================"
echo "Hora actual: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Dirección IP: $(hostname -I | awk '{print $1}')"
echo "========================================"
