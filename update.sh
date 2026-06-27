#!/bin/bash
cd /home/ani/compartido/amor

echo "🔄 Actualizando desde GitHub..."
git pull

echo "🔧 Dando permisos..."
chmod +x *.sh

echo "✅ Listo!"
ls -l *.sh
