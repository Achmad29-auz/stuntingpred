#!/usr/bin/env python3
"""
StuntingPred Bootstrap - Paste this into PA Files editor
Run once: python3 bootstrap.py
"""
import urllib.request, os, sys

print("Downloading StuntingPred v3.0...")
url = "https://raw.githubusercontent.com/Achmad29-auz/stuntingpred/main/server.py"
try:
    with urllib.request.urlopen(url) as r:
        content = r.read()
    with open(os.path.expanduser("~/stuntingpred/server.py"), "wb") as f:
        f.write(content)
    print("server.py updated:", len(content), "bytes")
    
    # Touch wsgi
    wsgi = "/var/www/achmad29_pythonanywhere_com_wsgi.py"
    if os.path.exists(wsgi):
        os.utime(wsgi, None)
        print("WSGI reloaded")
    print("DONE! Refresh browser.")
except Exception as e:
    print("Error:", e)
    print("Try manually: cd ~/stuntingpred && git pull")
