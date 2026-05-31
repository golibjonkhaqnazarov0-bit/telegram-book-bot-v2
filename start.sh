#!/bin/bash

# Loop indefinitely to keep the bot running
while true
do
    echo "$(date): Starting bot.py..."
    python3 bot.py
    echo "$(date): Bot crashed. Restarting in 5 seconds..."
    sleep 5
done
