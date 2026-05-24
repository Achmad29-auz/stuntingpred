# 🚀 Cara Deploy StuntingPred Online (Gratis, Domain Tetap)

## Opsi Terbaik: Render.com (Recommended)
**Domain:** `https://stuntingpred.onrender.com` (gratis, HTTPS otomatis)

### Langkah Deploy ke Render.com:

**1. Push ke GitHub (sekali)**
```bash
# Install Git: git-scm.com
git init
git add .
git commit -m "StuntingPred v2.0"
# Buat repo baru di github.com (gratis)
git remote add origin https://github.com/USERNAME/stuntingpred.git
git push -u origin main
```

**2. Deploy di Render.com**
1. Buka https://render.com → Sign up gratis
2. **New** → **Web Service**
3. Connect GitHub repo Anda
4. Isi konfigurasi:
   - **Name:** `stuntingpred` (jadi URL: stuntingpred.onrender.com)
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn server:app --workers 2 --bind 0.0.0.0:$PORT --timeout 120`
5. **Environment Variables** (tab Env Vars):
   - `SECRET_KEY` = (generate random, min 32 karakter)
   - `DB_PATH` = `/data/stunting.db`
6. **Disk** (tab Disk) → Add Disk:
   - Name: `stunting-data`
   - Mount Path: `/data`
   - Size: 1 GB
7. Klik **Create Web Service** → tunggu ~3 menit
8. URL Anda: `https://stuntingpred.onrender.com`

**⚠️ Penting:** Free tier Render sleep setelah 15 menit tidak aktif.
Upgrade ke $7/bulan untuk always-on, ATAU gunakan Koyeb (benar-benar gratis, tidak sleep).

---

## Opsi 2: Koyeb.com (Gratis, TIDAK Sleep)
**Domain:** `https://stuntingpred-xxx.koyeb.app`

1. Buka https://koyeb.com → Sign up gratis
2. **Create App** → **GitHub** → pilih repo
3. Settings:
   - Run command: `gunicorn server:app --workers 2 --bind 0.0.0.0:$PORT`
   - Port: `8000`
4. Environment: `SECRET_KEY=xxxxx`, `PORT=8000`
5. **Note:** Free tier tidak punya persistent disk → data hilang saat restart
   → Solusi: gunakan Railway (punya persistent volume)

---

## Opsi 3: Railway.app ($5 credit gratis, lalu ~$5/bulan)
**Domain:** `https://stuntingpred.railway.app`

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

---

## Setelah Deploy Online

### Update APK agar connect ke server online:
Edit file `www/index.html` baris:
```javascript
var BASE_URL = '';
// Ubah menjadi:
var BASE_URL = 'https://stuntingpred.onrender.com';
```
Lalu rebuild APK atau gunakan aplikasi lewat browser HP.

### Set Environment Variables (WAJIB untuk keamanan):
| Variable | Value |
|----------|-------|
| `SECRET_KEY` | String acak min 32 karakter |
| `DB_PATH` | `/data/stunting.db` (Render) atau biarkan default |
| `PORT` | Biasanya sudah otomatis dari platform |

### Akun Default (ganti password setelah deploy!):
| NIK | Password | Role |
|-----|----------|------|
| superadmin | admin123 | Admin |
| kader001 | kader123 | Kader (wajib ganti) |
| kader002 | kader123 | Kader (wajib ganti) |
| 1901234567890001 | peneliti123 | Peneliti |

---

## Fitur Keamanan v2.0

| Fitur | Detail |
|-------|--------|
| Password hashed | SHA-256, tidak tersimpan plain text |
| Wajib ganti password | Kader baru wajib ganti saat login pertama |
| Admin reset password | Admin bisa reset password kader |
| Token HMAC-SHA256 | Berlaku 60 hari |
| Role-based access | Kader hanya akses zona kerjanya |
| Activity log | Semua aksi tercatat di database |
| Soft delete user | Nonaktif, tidak hapus data |

---

*StuntingPred v2.0 — Heri Bahtiar · UMS 2025*
