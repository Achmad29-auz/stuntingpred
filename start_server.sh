#!/bin/bash
echo "🩺 StuntingPred Server v2.0"
pip3 install flask flask-cors gunicorn --quiet --break-system-packages 2>/dev/null || \
pip3 install flask flask-cors gunicorn --quiet 2>/dev/null
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
echo "═══════════════════════════════════════"
echo "  Local  : http://127.0.0.1:5000"
echo "  Network: http://$LOCAL_IP:5000"
echo "  (Semua HP ke URL Network di atas)"
echo "═══════════════════════════════════════"
cd "$(dirname "$0")"
python3 server.py
