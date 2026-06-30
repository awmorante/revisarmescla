#!/bin/bash
# Reinicia el bot de forma segura desde el propio bot
sleep 5
pkill -f bot_che_v3.py
sleep 4
nohup python3 /home/ani/compartido/amor/bot_che_v3.py >> /home/ani/.amor/bot.log 2>&1 &
echo $! > /home/ani/.amor/bot.pid
