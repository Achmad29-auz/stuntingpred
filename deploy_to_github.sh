#!/bin/bash
# ╔══════════════════════════════════════════════════════╗
# ║  StuntingPred — Push to GitHub for Koyeb Deploy     ║
# ║  Jalankan sekali: bash deploy_to_github.sh          ║
# ╚══════════════════════════════════════════════════════╝

echo ""
echo "🩺 StuntingPred v2.0 — Deploy ke GitHub + Koyeb"
echo "════════════════════════════════════════════════"

# ── Minta input ──────────────────────────────────────
echo ""
read -p "GitHub Username  : " GH_USER
read -p "GitHub Token     : " GH_TOKEN
read -p "Nama repo GitHub (contoh: stuntingpred): " REPO_NAME
REPO_NAME=${REPO_NAME:-stuntingpred}

# ── Buat repo di GitHub via API ──────────────────────
echo ""
echo "[1/4] Membuat repo GitHub '$REPO_NAME'..."
CREATE=$(curl -s -X POST "https://api.github.com/user/repos" \
  -H "Authorization: token $GH_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$REPO_NAME\",\"private\":false,\"description\":\"StuntingPred - Prediksi Stunting Lombok Tengah\"}")

if echo "$CREATE" | grep -q '"full_name"'; then
  echo "    ✅ Repo berhasil dibuat"
else
  # Repo mungkin sudah ada
  echo "    ℹ️  Repo sudah ada atau error — melanjutkan push..."
fi

# ── Init git dan push ────────────────────────────────
echo "[2/4] Inisialisasi git..."
cd "$(dirname "$0")"

# Remove old DB files from commit
rm -f stunting.db stunting.db-shm stunting.db-wal

git init -q
git config user.email "deploy@stuntingpred.app"
git config user.name "StuntingPred Deploy"

# Make sure .gitignore is set
cat > .gitignore << 'GITEOF'
*.db
*.db-shm
*.db-wal
__pycache__/
*.pyc
.env
*.log
GITEOF

echo "[3/4] Commit semua file..."
git add -A
git commit -q -m "StuntingPred v2.0 - Deploy ke Koyeb"

echo "[4/4] Push ke GitHub..."
git remote remove origin 2>/dev/null || true
git remote add origin "https://$GH_USER:$GH_TOKEN@github.com/$GH_USER/$REPO_NAME.git"
git branch -M main
git push -u origin main --force

echo ""
echo "════════════════════════════════════════════════"
echo "✅ BERHASIL! Repo tersedia di:"
echo "   https://github.com/$GH_USER/$REPO_NAME"
echo ""
echo "════════════════════════════════════════════════"
echo "LANGKAH SELANJUTNYA — Deploy ke Koyeb:"
echo ""
echo "1. Buka: https://app.koyeb.com"
echo "2. Sign up / Login"
echo "3. Create App → GitHub → pilih repo: $REPO_NAME"
echo "4. Konfigurasi:"
echo "   • Run command: gunicorn server:app --workers 1 --bind 0.0.0.0:\$PORT"
echo "   • Port: 8000"
echo "   • Instance: Free"
echo "5. Environment Variables:"
echo "   • SECRET_KEY = (string acak min 32 karakter)"
echo "   • PORT = 8000"  
echo "6. Deploy → dapat URL: https://xxx.koyeb.app"
echo ""
echo "7. Update APK: ubah BASE_URL di www/index.html"
echo "   var BASE_URL = 'https://xxx.koyeb.app';"
echo "════════════════════════════════════════════════"
