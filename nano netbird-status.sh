#!/bin/bash

echo "=== Netbird Status ==="

# Ejecuta el status
netbird status

echo ""
echo "IP actual: $(hostname -I | awk '{print $1}')"
echo "========================================"
