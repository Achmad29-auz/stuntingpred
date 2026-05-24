import sys
import os

# flask-cors ada di ~/.local/lib/python3.13
USER_PKGS = '/home/achmad29/.local/lib/python3.13/site-packages'
if USER_PKGS not in sys.path:
    sys.path.insert(0, USER_PKGS)

# App path
APP_PATH = '/home/achmad29/stuntingpred'
if APP_PATH not in sys.path:
    sys.path.insert(0, APP_PATH)

os.environ['SECRET_KEY'] = 'stuntingpred-ums-heri2025-lombok-ntb-secret-key'
os.environ['DB_PATH']    = '/home/achmad29/stuntingpred/stunting.db'

from server import app, init_db
init_db()
application = app
