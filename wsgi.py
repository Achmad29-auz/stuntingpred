import sys
import os

# Add app directory to path
path = os.path.expanduser('~/stuntingpred')
if path not in sys.path:
    sys.path.insert(0, path)

# Set environment variables
os.environ['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'stuntingpred-ums-heri2025-lombok-ntb-secret-key')
os.environ['DB_PATH'] = os.path.expanduser('~/stuntingpred/stunting.db')

from server import app, init_db

# Initialize database on startup
init_db()

application = app
