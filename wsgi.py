import sys
import os

# ── Tambahkan SEMUA kemungkinan path Python packages di PythonAnywhere ──
paths_to_add = [
    '/home/achmad29/.local/lib/python3.13/site-packages',
    '/home/achmad29/.local/lib/python3.12/site-packages',
    '/home/achmad29/.local/lib/python3.11/site-packages',
    '/home/achmad29/.local/lib/python3.10/site-packages',
    '/usr/local/lib/python3.13/dist-packages',
    '/usr/local/lib/python3.13/site-packages',
    '/home/achmad29/stuntingpred',
]
for p in paths_to_add:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

os.environ['SECRET_KEY'] = 'stuntingpred-ums-heri2025-lombok-ntb-secret-key'
os.environ['DB_PATH']    = '/home/achmad29/stuntingpred/stunting.db'

from server import app, init_db
init_db()
application = app
