#!/bin/bash
echo "=== StuntingPred Fix All ==="
cd ~/stuntingpred

echo "[1/5] Git pull terbaru..."
git fetch origin
git reset --hard origin/main
echo "Git: OK"

echo "[2/5] Cek flask-cors..."
python3 -c "
import sys
sys.path.insert(0,'/home/achmad29/.local/lib/python3.13/site-packages')
sys.path.insert(0,'/usr/local/lib/python3.13/site-packages')
import flask_cors
print('flask_cors OK:', flask_cors.__file__)
"

echo "[3/5] Test app load..."
python3 -c "
import sys,os
sys.path.insert(0,'/home/achmad29/.local/lib/python3.13/site-packages')
sys.path.insert(0,'/usr/local/lib/python3.13/site-packages')
sys.path.insert(0,'/home/achmad29/stuntingpred')
os.environ['SECRET_KEY']='stuntingpred-ums-heri2025-lombok-ntb-secret-key'
os.environ['DB_PATH']='/home/achmad29/stuntingpred/stunting.db'
from server import app, init_db
init_db()
print('Flask app: OK')
print('DB: OK')
"

echo "[4/5] Update WSGI..."
cp ~/stuntingpred/wsgi.py /var/www/achmad29_pythonanywhere_com_wsgi.py
echo "WSGI copied: OK"

echo "[5/5] Reload web app..."
touch /var/www/achmad29_pythonanywhere_com_wsgi.py
echo ""
echo "=== SELESAI ==="
echo "Tunggu 10 detik lalu refresh browser"
echo "Buka: https://achmad29.pythonanywhere.com"
