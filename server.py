#!/usr/bin/env python3
"""
StuntingPred Backend Server v2.0
Peneliti: Heri Bahtiar | University of Malaysia Sabah (UMS) | 2025
Flask REST API + SQLite3 — Online, Multi-Device, Realtime
"""
import sqlite3, json, os, hashlib, hmac, time, datetime, secrets
from functools import wraps
from flask import Flask, request, jsonify, g, send_from_directory
from flask_cors import CORS

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.environ.get('DB_PATH',  os.path.join(APP_DIR, 'stunting.db'))
WEB_DIR  = os.path.join(APP_DIR, 'www')
SECRET   = os.environ.get('SECRET_KEY', 'stuntingpred-ums-2025-heri-bahtiar-secret')
PORT     = int(os.environ.get('PORT', 5000))

app = Flask(__name__, static_folder=WEB_DIR)
CORS(app, origins="*", supports_credentials=True,
     allow_headers=["Content-Type","Authorization"],
     methods=["GET","POST","PUT","DELETE","OPTIONS"])

# ══════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════
def hash_pwd(pwd):
    """SHA-256 hash password for secure storage"""
    return hashlib.sha256(pwd.encode('utf-8')).hexdigest()

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()

def q(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    get_db().commit()
    if one: return cur.fetchone()
    return cur.fetchall()

def row2dict(row):
    return dict(row) if row else None

def rows2list(rows):
    return [dict(r) for r in rows]

def ok(data=None, msg=None, **kw):
    r = {'success': True}
    if data is not None: r['data'] = data
    if msg: r['message'] = msg
    r.update(kw)
    return jsonify(r)

def err(msg, code=400):
    return jsonify({'success': False, 'error': msg}), code

def now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# ══════════════════════════════════════════════════════
# DATABASE INIT
# ══════════════════════════════════════════════════════
def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    cur = db.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        nik         TEXT    UNIQUE NOT NULL,
        name        TEXT    NOT NULL,
        password    TEXT    NOT NULL,
        role        TEXT    NOT NULL DEFAULT 'kader',
        puskesmas   TEXT    DEFAULT '',
        zone        TEXT    DEFAULT 'all',
        phone       TEXT    DEFAULT '',
        email       TEXT    DEFAULT '',
        active      INTEGER DEFAULT 1,
        must_change_pwd INTEGER DEFAULT 0,
        created_at  TEXT    DEFAULT (datetime('now','localtime')),
        updated_at  TEXT    DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS toddlers (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        nik_balita      TEXT,
        name            TEXT    NOT NULL,
        birth_date      TEXT    NOT NULL,
        gender          TEXT    NOT NULL DEFAULT 'male',
        birth_weight    REAL,
        birth_height    REAL,
        zone            TEXT    DEFAULT 'lowlands',
        village         TEXT    DEFAULT '',
        subdistrict     TEXT    DEFAULT '',
        mother_name     TEXT    NOT NULL,
        mother_nik      TEXT    DEFAULT '',
        mother_age      INTEGER,
        mother_height   REAL,
        mother_edu      TEXT    DEFAULT 'sma',
        mother_illness  INTEGER DEFAULT 0,
        mother_ctps     INTEGER DEFAULT 1,
        father_name     TEXT    DEFAULT '',
        father_edu      TEXT    DEFAULT 'sma',
        father_job      TEXT    DEFAULT '',
        family_income   INTEGER,
        family_members  INTEGER,
        water_source    TEXT    DEFAULT 'well',
        toilet_type     TEXT    DEFAULT 'own',
        waste_mgmt      TEXT    DEFAULT 'collected',
        floor_type      TEXT    DEFAULT 'cement',
        sanitation_score INTEGER DEFAULT 0,
        excl_breastfeed INTEGER DEFAULT 0,
        imd             INTEGER DEFAULT 0,
        infection_hist  INTEGER DEFAULT 0,
        registered_by   INTEGER REFERENCES users(id),
        created_at      TEXT    DEFAULT (datetime('now','localtime')),
        updated_at      TEXT    DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS measurements (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        toddler_id      INTEGER NOT NULL REFERENCES toddlers(id) ON DELETE CASCADE,
        measured_by     INTEGER REFERENCES users(id),
        measure_date    TEXT    NOT NULL DEFAULT (date('now','localtime')),
        age_months      INTEGER NOT NULL,
        height_cm       REAL    NOT NULL,
        weight_kg       REAL,
        head_circ_cm    REAL,
        arm_circ_cm     REAL,
        z_score_hfa     REAL,
        stunting_status TEXT,
        risk_level      TEXT,
        risk_prob       REAL,
        notes           TEXT    DEFAULT '',
        intervention    TEXT    DEFAULT '',
        created_at      TEXT    DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS qualitative_data (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        toddler_id          INTEGER REFERENCES toddlers(id) ON DELETE CASCADE,
        respondent_code     TEXT    NOT NULL,
        interview_date      TEXT    NOT NULL,
        interviewed_by      INTEGER REFERENCES users(id),
        interview_type      TEXT    DEFAULT 'idi',
        food_taboo          TEXT    DEFAULT '',
        decision_maker      TEXT    DEFAULT '',
        breastfeed_knowledge INTEGER DEFAULT 0,
        stunting_knowledge  TEXT    DEFAULT '',
        posyandu_freq       TEXT    DEFAULT '',
        health_barriers     TEXT    DEFAULT '',
        water_src_qual      TEXT    DEFAULT '',
        toilet_usage        TEXT    DEFAULT '',
        mpasi_practice      TEXT    DEFAULT '',
        cultural_beliefs    TEXT    DEFAULT '',
        community_practices TEXT    DEFAULT '',
        verbatim_notes      TEXT    DEFAULT '',
        theme_codes         TEXT    DEFAULT '',
        sentiment           TEXT    DEFAULT '',
        created_at          TEXT    DEFAULT (datetime('now','localtime')),
        updated_at          TEXT    DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS sync_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER,
        action      TEXT,
        table_name  TEXT,
        record_id   INTEGER,
        detail      TEXT    DEFAULT '',
        created_at  TEXT    DEFAULT (datetime('now','localtime'))
    );

    CREATE INDEX IF NOT EXISTS idx_t_zone   ON toddlers(zone);
    CREATE INDEX IF NOT EXISTS idx_m_tid    ON measurements(toddler_id);
    CREATE INDEX IF NOT EXISTS idx_m_date   ON measurements(measure_date);
    CREATE INDEX IF NOT EXISTS idx_q_tid    ON qualitative_data(toddler_id);
    CREATE INDEX IF NOT EXISTS idx_log_uid  ON sync_log(user_id);
    """)
    db.commit()

    # Migrate: add columns if missing (for existing DBs)
    def add_col(table, col, coldef):
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coldef}")
            db.commit()
        except: pass

    add_col('users', 'active',          'INTEGER DEFAULT 1')
    add_col('users', 'must_change_pwd', 'INTEGER DEFAULT 0')
    add_col('users', 'phone',           "TEXT DEFAULT ''")
    add_col('users', 'email',           "TEXT DEFAULT ''")
    add_col('sync_log', 'detail',       "TEXT DEFAULT ''")

    # Migrate passwords to hashed if still plain text
    rows = db.execute("SELECT id, password FROM users").fetchall()
    for row in rows:
        pwd = row['password']
        # Plain passwords are short; hashes are 64 chars
        if len(pwd) < 64:
            hashed = hash_pwd(pwd)
            db.execute("UPDATE users SET password=? WHERE id=?", (hashed, row['id']))
    db.commit()

    # Seed default users if empty
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        users = [
            ('superadmin', 'Administrator',     'admin123',    'admin',      'Dinkes Lombok Tengah',  'all',      0),
            ('kader001',   'Siti Rahayu',        'kader123',    'kader',      'Puskesmas Praya',       'lowlands', 0),
            ('kader002',   'Ahmad Firdaus',      'kader123',    'kader',      'Puskesmas Praya Barat', 'hills',    1),
            ('kader003',   'Nurhayati',          'kader123',    'kader',      'Puskesmas Pujut',       'coastal',  1),
            ('1901234567890001','Heri Bahtiar',  'peneliti123', 'researcher', 'UMS Research Team',     'all',      0),
        ]
        for nik, name, pwd, role, pusk, zone, must in users:
            db.execute(
                "INSERT INTO users (nik,name,password,role,puskesmas,zone,must_change_pwd) VALUES (?,?,?,?,?,?,?)",
                (nik, name, hash_pwd(pwd), role, pusk, zone, must))
        db.commit()
        print("[DB] Default users seeded (passwords hashed)")

    # Seed demo toddlers if empty
    if db.execute("SELECT COUNT(*) FROM toddlers").fetchone()[0] == 0:
        today = datetime.date.today().isoformat()
        demo = [
            ('BL001','Ahmad Fauzi',      '2024-01-15','male',  2.8,48,  'hills',   'Selebung', 'Fatimah',32,147,'smp','sd', 1200000,'well', 'none',  'dump','dirt',  2,0,1,0,1),
            ('BL002','Putri Nisa Amalia','2023-06-20','female',3.1,50,  'coastal', 'Kuta',     'Rahmi',  26,153,'sma','sma',2500000,'pam',  'own',   'collected','tile',7,1,0,0,1),
            ('BL003','Rizki Maulana',    '2023-11-10','male',  2.5,46.5,'lowlands','Praya',    'Nurul',  28,149,'sd', 'sd', 900000, 'river','shared','burned','cement',1,0,1,1,0),
            ('BL004','Lailatul Fitri',   '2022-08-05','female',3.3,51,  'lowlands','Jonggat',  'Sari',   24,156,'sma','pt', 3500000,'pam',  'own',   'collected','tile',9,1,0,0,1),
            ('BL005','Bagas Prasetyo',   '2024-03-22','male',  2.2,45,  'hills',   'Batukliang','Dewi',  38,145,'none','sd',700000, 'river','none',  'dump','dirt',  0,0,1,1,0),
            ('BL006','Siti Aisyah',      '2023-09-05','female',3.0,49,  'coastal', 'Gerupuk',  'Maryam', 29,151,'smp','smp',1500000,'well', 'shared','burned','cement',3,0,0,0,1),
            ('BL007','Muhammad Raffi',   '2024-05-10','male',  2.7,47,  'hills',   'Aik Berik','Rohani', 35,146,'sd', 'sd', 800000, 'river','none',  'dump','dirt',  1,0,1,1,0),
            ('BL008','Nadia Putri',      '2022-12-01','female',3.2,50.5,'lowlands','Mantang',  'Suharti',27,154,'sma','sma',2200000,'pam',  'own',   'collected','tile',8,1,0,0,1),
        ]
        for d in demo:
            cur2 = db.execute("""
                INSERT INTO toddlers
                (nik_balita,name,birth_date,gender,birth_weight,birth_height,zone,village,
                 mother_name,mother_age,mother_height,mother_edu,father_edu,family_income,
                 water_source,toilet_type,waste_mgmt,floor_type,sanitation_score,
                 excl_breastfeed,infection_hist,mother_illness,mother_ctps,registered_by)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""", d)
            tid = cur2.lastrowid
            bd  = datetime.date.fromisoformat(d[2])
            td  = datetime.date.today()
            age = min(59, max(0, (td.year-bd.year)*12+(td.month-bd.month)))
            h   = round(d[5] + age*0.9, 1)
            db.execute("""
                INSERT INTO measurements
                (toddler_id,measured_by,measure_date,age_months,height_cm,weight_kg,
                 stunting_status,risk_level,risk_prob)
                VALUES (?,1,?,?,?,?,?,?,?)""",
                (tid, today, age, h, round(d[4]+age*0.22, 1),
                 'Stunted' if d[18]<4 else 'Normal',
                 'Tinggi'  if d[18]<3 else ('Sedang' if d[18]<6 else 'Rendah'),
                 0.72 if d[18]<3 else (0.45 if d[18]<6 else 0.22)))
        db.commit()
        print("[DB] Demo toddlers seeded")

    db.close()
    print(f"[DB] Ready: {DB_PATH}")

# ══════════════════════════════════════════════════════
# TOKEN AUTH (HMAC-SHA256)
# ══════════════════════════════════════════════════════
def make_token(user_id, nik, role):
    ts      = int(time.time())
    payload = f"{user_id}:{nik}:{role}:{ts}"
    sig     = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]
    import base64
    return base64.b64encode(f"{payload}:{sig}".encode()).decode()

def verify_token(token):
    try:
        import base64
        decoded = base64.b64decode(token.encode()).decode()
        *parts, sig = decoded.split(':')
        payload = ':'.join(parts)
        expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(sig, expected): return None
        p  = payload.split(':')
        ts = int(p[3])
        if time.time() - ts > 86400 * 60: return None   # 60 days
        return {'user_id': int(p[0]), 'nik': p[1], 'role': p[2]}
    except: return None

def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization','').replace('Bearer ','').strip()
        if not token: token = request.args.get('token','')
        info = verify_token(token)
        if not info: return err('Unauthorized — silakan login ulang', 401)
        g.auth = info
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @auth_required
        def decorated(*args, **kwargs):
            if g.auth['role'] not in roles:
                return err('Akses ditolak — role tidak memiliki izin', 403)
            return f(*args, **kwargs)
        return decorated
    return decorator

def _log(uid, action, table, record_id, detail=''):
    try:
        get_db().execute(
            "INSERT INTO sync_log (user_id,action,table_name,record_id,detail) VALUES (?,?,?,?,?)",
            (uid, action, table, record_id, detail))
        get_db().commit()
    except: pass

# ══════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ══════════════════════════════════════════════════════
@app.route('/api/auth/login', methods=['POST'])
def login():
    d   = request.get_json() or {}
    nik = (d.get('nik') or '').strip()
    pwd = (d.get('password') or '').strip()
    if not nik or not pwd: return err('NIK dan password wajib diisi')

    user = row2dict(q(
        "SELECT * FROM users WHERE nik=? AND active=1", (nik,), one=True))
    if not user: return err('NIK atau password salah')

    # Support both hashed and plain (migration)
    stored = user['password']
    if len(stored) == 64:   # hashed
        match = hmac.compare_digest(stored, hash_pwd(pwd))
    else:                   # plain (old DB)
        match = (stored == pwd)
        if match:           # upgrade to hash on the fly
            q("UPDATE users SET password=? WHERE id=?", (hash_pwd(pwd), user['id']))

    if not match: return err('NIK atau password salah')

    token = make_token(user['id'], user['nik'], user['role'])
    _log(user['id'], 'LOGIN', 'users', user['id'])
    user.pop('password', None)
    return ok({
        'user':           user,
        'token':          token,
        'must_change_pwd': bool(user.get('must_change_pwd', 0)),
    })

@app.route('/api/auth/me', methods=['GET'])
@auth_required
def me():
    user = row2dict(q(
        "SELECT id,nik,name,role,puskesmas,zone,phone,email,active,must_change_pwd FROM users WHERE id=?",
        (g.auth['user_id'],), one=True))
    return ok(user)

@app.route('/api/auth/change-password', methods=['POST'])
@auth_required
def change_password():
    d       = request.get_json() or {}
    old_pwd = (d.get('old_password') or '').strip()
    new_pwd = (d.get('new_password') or '').strip()

    if not old_pwd or not new_pwd:
        return err('Password lama dan baru wajib diisi')
    if len(new_pwd) < 6:
        return err('Password baru minimal 6 karakter')
    if old_pwd == new_pwd:
        return err('Password baru harus berbeda dari password lama')

    user = row2dict(q("SELECT * FROM users WHERE id=?", (g.auth['user_id'],), one=True))
    if not user: return err('User tidak ditemukan', 404)

    stored = user['password']
    if len(stored) == 64:
        match = hmac.compare_digest(stored, hash_pwd(old_pwd))
    else:
        match = (stored == old_pwd)

    if not match: return err('Password lama tidak cocok')

    q("UPDATE users SET password=?, must_change_pwd=0, updated_at=? WHERE id=?",
      (hash_pwd(new_pwd), now(), g.auth['user_id']))
    _log(g.auth['user_id'], 'CHANGE_PWD', 'users', g.auth['user_id'])
    return ok(msg='Password berhasil diubah')

@app.route('/api/auth/profile', methods=['PUT'])
@auth_required
def update_profile():
    d = request.get_json() or {}
    q("UPDATE users SET name=?,phone=?,email=?,updated_at=? WHERE id=?",
      (d.get('name',''), d.get('phone',''), d.get('email',''), now(), g.auth['user_id']))
    return ok(msg='Profil diperbarui')

# ══════════════════════════════════════════════════════
# USER MANAGEMENT (Admin only)
# ══════════════════════════════════════════════════════
@app.route('/api/users', methods=['GET'])
@role_required('admin', 'researcher')
def get_users():
    users = rows2list(q("""
        SELECT id,nik,name,role,puskesmas,zone,phone,email,active,must_change_pwd,created_at
        FROM users ORDER BY role, name"""))
    # Remove passwords
    return ok(users)

@app.route('/api/users', methods=['POST'])
@role_required('admin')
def create_user():
    d = request.get_json() or {}
    nik  = (d.get('nik') or '').strip()
    name = (d.get('name') or '').strip()
    pwd  = (d.get('password') or '').strip()

    if not nik or not name:
        return err('NIK dan nama wajib diisi')
    if not pwd:
        pwd = 'kader123'          # default password if not set
    if len(pwd) < 6:
        return err('Password minimal 6 karakter')

    existing = q("SELECT id FROM users WHERE nik=?", (nik,), one=True)
    if existing: return err('NIK sudah terdaftar — gunakan NIK yang berbeda')

    must_change = int(d.get('must_change_pwd', 1))   # default: kader harus ganti password
    cur = get_db().execute(
        "INSERT INTO users (nik,name,password,role,puskesmas,zone,phone,email,must_change_pwd) VALUES (?,?,?,?,?,?,?,?,?)",
        (nik, name, hash_pwd(pwd), d.get('role','kader'),
         d.get('puskesmas',''), d.get('zone','lowlands'),
         d.get('phone',''), d.get('email',''), must_change))
    get_db().commit()
    new_id = cur.lastrowid
    _log(g.auth['user_id'], 'CREATE_USER', 'users', new_id, f"role={d.get('role','kader')}")
    return ok({'id': new_id, 'message': f'Akun {name} berhasil dibuat', 'default_password': pwd}), 201

@app.route('/api/users/<int:uid>', methods=['GET'])
@role_required('admin')
def get_user(uid):
    u = row2dict(q("SELECT id,nik,name,role,puskesmas,zone,phone,email,active,must_change_pwd FROM users WHERE id=?", (uid,), one=True))
    if not u: return err('User tidak ditemukan', 404)
    return ok(u)

@app.route('/api/users/<int:uid>', methods=['PUT'])
@role_required('admin')
def update_user(uid):
    d = request.get_json() or {}
    q("""UPDATE users SET name=?,role=?,puskesmas=?,zone=?,phone=?,email=?,
         active=?,must_change_pwd=?,updated_at=? WHERE id=?""",
      (d.get('name',''), d.get('role','kader'), d.get('puskesmas',''),
       d.get('zone','lowlands'), d.get('phone',''), d.get('email',''),
       int(d.get('active', 1)), int(d.get('must_change_pwd', 0)), now(), uid))
    _log(g.auth['user_id'], 'UPDATE_USER', 'users', uid)
    return ok(msg='Data pengguna diperbarui')

@app.route('/api/users/<int:uid>/reset-password', methods=['POST'])
@role_required('admin')
def reset_password(uid):
    """Admin reset password kader — kader wajib ganti saat login berikutnya"""
    d       = request.get_json() or {}
    new_pwd = (d.get('new_password') or 'kader123').strip()
    if len(new_pwd) < 6:
        return err('Password minimal 6 karakter')

    u = q("SELECT id, name FROM users WHERE id=?", (uid,), one=True)
    if not u: return err('User tidak ditemukan', 404)

    q("UPDATE users SET password=?, must_change_pwd=1, updated_at=? WHERE id=?",
      (hash_pwd(new_pwd), now(), uid))
    _log(g.auth['user_id'], 'RESET_PWD', 'users', uid, f"reset by admin {g.auth['user_id']}")
    return ok({'message': f'Password {u["name"]} direset. Kader wajib ganti saat login berikutnya.',
               'new_password': new_pwd})

@app.route('/api/users/<int:uid>', methods=['DELETE'])
@role_required('admin')
def delete_user(uid):
    if uid == g.auth['user_id']:
        return err('Tidak bisa hapus akun sendiri')
    u = q("SELECT name FROM users WHERE id=?", (uid,), one=True)
    if not u: return err('User tidak ditemukan', 404)
    # Soft delete (set inactive) to preserve data integrity
    q("UPDATE users SET active=0, updated_at=? WHERE id=?", (now(), uid))
    _log(g.auth['user_id'], 'DEACTIVATE_USER', 'users', uid)
    return ok(msg=f'Akun {u["name"]} dinonaktifkan')

# ══════════════════════════════════════════════════════
# TODDLER ENDPOINTS
# ══════════════════════════════════════════════════════
def _get_user_zone(uid):
    u = q("SELECT zone FROM users WHERE id=?", (uid,), one=True)
    return u['zone'] if u else 'all'

@app.route('/api/toddlers', methods=['GET'])
@auth_required
def get_toddlers():
    search = request.args.get('search', '')
    zone   = request.args.get('zone', 'all')
    risk   = request.args.get('risk', '')

    sql = """
        SELECT t.*,
            m.height_cm    as last_height,
            m.weight_kg    as last_weight,
            m.risk_level   as last_risk,
            m.stunting_status as last_status,
            m.measure_date as last_visit,
            m.risk_prob    as last_prob,
            u.name         as registered_by_name,
            (SELECT COUNT(*) FROM measurements WHERE toddler_id=t.id) as visit_count
        FROM toddlers t
        LEFT JOIN measurements m ON m.id = (
            SELECT id FROM measurements WHERE toddler_id=t.id
            ORDER BY measure_date DESC, id DESC LIMIT 1)
        LEFT JOIN users u ON u.id=t.registered_by
        WHERE 1=1"""
    args = []

    # Enforce zone restriction for kader
    user_zone = _get_user_zone(g.auth['user_id'])
    if g.auth['role'] == 'kader' and user_zone and user_zone != 'all':
        sql += " AND t.zone=?"; args.append(user_zone)
    elif zone and zone != 'all':
        sql += " AND t.zone=?"; args.append(zone)

    if search:
        sql += " AND (t.name LIKE ? OR t.nik_balita LIKE ? OR t.mother_name LIKE ?)"
        args += [f'%{search}%', f'%{search}%', f'%{search}%']
    if risk:
        sql += " AND m.risk_level=?"; args.append(risk)

    sql += " ORDER BY t.created_at DESC"
    return ok(rows2list(q(sql, args)))

@app.route('/api/toddlers/<int:tid>', methods=['GET'])
@auth_required
def get_toddler(tid):
    t = row2dict(q("SELECT * FROM toddlers WHERE id=?", (tid,), one=True))
    if not t: return err('Balita tidak ditemukan', 404)
    return ok(t)

@app.route('/api/toddlers', methods=['POST'])
@auth_required
def create_toddler():
    d = request.get_json() or {}
    if not d.get('name') or not d.get('birth_date') or not d.get('mother_name'):
        return err('Nama balita, tanggal lahir, dan nama ibu wajib diisi')
    if d.get('nik_balita'):
        ex = q("SELECT id FROM toddlers WHERE nik_balita=?", (d['nik_balita'],), one=True)
        if ex: return err('NIK balita sudah terdaftar')
    cur = get_db().execute("""
        INSERT INTO toddlers
        (nik_balita,name,birth_date,gender,birth_weight,birth_height,zone,village,subdistrict,
         mother_name,mother_nik,mother_age,mother_height,mother_edu,mother_illness,mother_ctps,
         father_name,father_edu,father_job,family_income,family_members,
         water_source,toilet_type,waste_mgmt,floor_type,sanitation_score,
         excl_breastfeed,imd,infection_hist,registered_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (d.get('nik_balita'), d['name'], d['birth_date'], d.get('gender','male'),
         d.get('birth_weight'), d.get('birth_height'), d.get('zone','lowlands'),
         d.get('village',''), d.get('subdistrict',''), d['mother_name'], d.get('mother_nik',''),
         d.get('mother_age'), d.get('mother_height'), d.get('mother_edu','sma'),
         int(d.get('mother_illness',0)), int(d.get('mother_ctps',1)),
         d.get('father_name',''), d.get('father_edu','sma'), d.get('father_job',''),
         d.get('family_income'), d.get('family_members'),
         d.get('water_source','well'), d.get('toilet_type','own'),
         d.get('waste_mgmt','collected'), d.get('floor_type','cement'),
         int(d.get('sanitation_score',0)),
         int(d.get('excl_breastfeed',0)), int(d.get('imd',0)), int(d.get('infection_hist',0)),
         g.auth['user_id']))
    get_db().commit()
    new_id = cur.lastrowid
    _log(g.auth['user_id'], 'CREATE', 'toddlers', new_id, d['name'])
    return ok({'id': new_id, 'message': f'{d["name"]} berhasil didaftarkan'}), 201

@app.route('/api/toddlers/<int:tid>', methods=['PUT'])
@auth_required
def update_toddler(tid):
    d = request.get_json() or {}
    if not d.get('name') or not d.get('birth_date') or not d.get('mother_name'):
        return err('Nama balita, tanggal lahir, dan nama ibu wajib diisi')
    q("""UPDATE toddlers SET
         name=?,birth_date=?,gender=?,birth_weight=?,birth_height=?,zone=?,village=?,subdistrict=?,
         mother_name=?,mother_nik=?,mother_age=?,mother_height=?,mother_edu=?,mother_illness=?,mother_ctps=?,
         father_name=?,father_edu=?,father_job=?,family_income=?,family_members=?,
         water_source=?,toilet_type=?,waste_mgmt=?,floor_type=?,sanitation_score=?,
         excl_breastfeed=?,imd=?,infection_hist=?,updated_at=? WHERE id=?""",
         (d['name'], d['birth_date'], d.get('gender','male'),
          d.get('birth_weight'), d.get('birth_height'), d.get('zone'),
          d.get('village',''), d.get('subdistrict',''), d['mother_name'], d.get('mother_nik',''),
          d.get('mother_age'), d.get('mother_height'), d.get('mother_edu','sma'),
          int(d.get('mother_illness',0)), int(d.get('mother_ctps',1)),
          d.get('father_name',''), d.get('father_edu','sma'), d.get('father_job',''),
          d.get('family_income'), d.get('family_members'),
          d.get('water_source'), d.get('toilet_type'), d.get('waste_mgmt'),
          d.get('floor_type'), int(d.get('sanitation_score',0)),
          int(d.get('excl_breastfeed',0)), int(d.get('imd',0)), int(d.get('infection_hist',0)),
          now(), tid))
    _log(g.auth['user_id'], 'UPDATE', 'toddlers', tid, d['name'])
    return ok(msg='Data balita diperbarui')

@app.route('/api/toddlers/<int:tid>', methods=['DELETE'])
@role_required('admin', 'researcher')
def delete_toddler(tid):
    t = q("SELECT name FROM toddlers WHERE id=?", (tid,), one=True)
    if not t: return err('Balita tidak ditemukan', 404)
    q("DELETE FROM toddlers WHERE id=?", (tid,))
    _log(g.auth['user_id'], 'DELETE', 'toddlers', tid, t['name'])
    return ok(msg=f'{t["name"]} berhasil dihapus')

# ══════════════════════════════════════════════════════
# MEASUREMENT ENDPOINTS
# ══════════════════════════════════════════════════════
@app.route('/api/toddlers/<int:tid>/measurements', methods=['GET'])
@auth_required
def get_measurements(tid):
    ms = rows2list(q("""
        SELECT m.*, u.name as measured_by_name
        FROM measurements m
        LEFT JOIN users u ON u.id=m.measured_by
        WHERE m.toddler_id=? ORDER BY m.measure_date ASC, m.id ASC""", (tid,)))
    return ok(ms)

@app.route('/api/toddlers/<int:tid>/measurements', methods=['POST'])
@auth_required
def create_measurement(tid):
    d = request.get_json() or {}
    if not d.get('height_cm'): return err('Tinggi badan wajib diisi')
    if d.get('age_months') is None: return err('Usia wajib diisi')
    today = datetime.date.today().isoformat()
    cur = get_db().execute("""
        INSERT INTO measurements
        (toddler_id,measured_by,measure_date,age_months,height_cm,weight_kg,
         head_circ_cm,arm_circ_cm,z_score_hfa,stunting_status,risk_level,risk_prob,notes,intervention)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (tid, g.auth['user_id'],
         d.get('measure_date', today), int(d['age_months']), float(d['height_cm']),
         float(d['weight_kg']) if d.get('weight_kg') else None,
         float(d['head_circ_cm']) if d.get('head_circ_cm') else None,
         float(d['arm_circ_cm']) if d.get('arm_circ_cm') else None,
         float(d['z_score_hfa']) if d.get('z_score_hfa') is not None else None,
         d.get('stunting_status'), d.get('risk_level'),
         float(d['risk_prob']) if d.get('risk_prob') is not None else None,
         d.get('notes',''), d.get('intervention','')))
    get_db().commit()
    new_id = cur.lastrowid
    _log(g.auth['user_id'], 'CREATE', 'measurements', new_id,
         f"toddler={tid} ht={d['height_cm']} risk={d.get('risk_level')}")
    return ok({'id': new_id, 'message': 'Pengukuran berhasil disimpan'}), 201

@app.route('/api/measurements/<int:mid>', methods=['DELETE'])
@role_required('admin', 'researcher')
def delete_measurement(mid):
    q("DELETE FROM measurements WHERE id=?", (mid,))
    return ok(msg='Pengukuran dihapus')

# ══════════════════════════════════════════════════════
# QUALITATIVE ENDPOINTS
# ══════════════════════════════════════════════════════
@app.route('/api/qualitative', methods=['GET'])
@auth_required
def get_all_qualitative():
    qs = rows2list(q("""
        SELECT qd.*, t.name as toddler_name, t.zone, u.name as interviewer_name
        FROM qualitative_data qd
        LEFT JOIN toddlers t ON t.id=qd.toddler_id
        LEFT JOIN users u ON u.id=qd.interviewed_by
        ORDER BY qd.interview_date DESC, qd.id DESC"""))
    return ok(qs)

@app.route('/api/toddlers/<int:tid>/qualitative', methods=['GET'])
@auth_required
def get_qualitative(tid):
    qs = rows2list(q(
        "SELECT * FROM qualitative_data WHERE toddler_id=? ORDER BY interview_date DESC", (tid,)))
    return ok(qs)

@app.route('/api/qualitative', methods=['POST'])
@auth_required
def create_qualitative():
    d = request.get_json() or {}
    if not d.get('respondent_code') or not d.get('interview_date'):
        return err('Kode responden dan tanggal wajib diisi')
    cur = get_db().execute("""
        INSERT INTO qualitative_data
        (toddler_id,respondent_code,interview_date,interviewed_by,interview_type,
         food_taboo,decision_maker,breastfeed_knowledge,stunting_knowledge,
         posyandu_freq,health_barriers,water_src_qual,toilet_usage,mpasi_practice,
         cultural_beliefs,community_practices,verbatim_notes,theme_codes,sentiment)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (d.get('toddler_id'), d['respondent_code'], d['interview_date'],
         g.auth['user_id'], d.get('interview_type','idi'),
         d.get('food_taboo',''), d.get('decision_maker',''),
         int(d.get('breastfeed_knowledge',0)),
         d.get('stunting_knowledge',''), d.get('posyandu_freq',''),
         d.get('health_barriers',''), d.get('water_src_qual',''),
         d.get('toilet_usage',''), d.get('mpasi_practice',''),
         d.get('cultural_beliefs',''), d.get('community_practices',''),
         d.get('verbatim_notes',''), d.get('theme_codes',''), d.get('sentiment','')))
    get_db().commit()
    _log(g.auth['user_id'], 'CREATE', 'qualitative_data', cur.lastrowid,
         d['respondent_code'])
    return ok({'id': cur.lastrowid, 'message': 'Data wawancara berhasil disimpan'}), 201

# ══════════════════════════════════════════════════════
# DASHBOARD & ANALYTICS
# ══════════════════════════════════════════════════════
@app.route('/api/dashboard', methods=['GET'])
@auth_required
def dashboard():
    total    = q("SELECT COUNT(*) as n FROM toddlers", one=True)['n']
    by_risk  = rows2list(q("""
        SELECT m.risk_level, COUNT(*) as n FROM (
            SELECT toddler_id, MAX(measure_date) as md FROM measurements GROUP BY toddler_id
        ) latest
        JOIN measurements m ON m.toddler_id=latest.toddler_id AND m.measure_date=latest.md
        GROUP BY m.risk_level"""))
    by_zone  = rows2list(q("""
        SELECT t.zone, COUNT(DISTINCT t.id) as total,
            SUM(CASE WHEN m.stunting_status IN ('Stunted','Severely Stunted') THEN 1 ELSE 0 END) as stunted,
            SUM(CASE WHEN m.stunting_status='Severely Stunted' THEN 1 ELSE 0 END) as severe
        FROM toddlers t
        LEFT JOIN (
            SELECT toddler_id, MAX(measure_date) as md FROM measurements GROUP BY toddler_id
        ) latest ON latest.toddler_id=t.id
        LEFT JOIN measurements m ON m.toddler_id=t.id AND m.measure_date=latest.md
        GROUP BY t.zone ORDER BY t.zone"""))
    recent   = rows2list(q("""
        SELECT m.*, t.name as toddler_name, t.zone, u.name as by_name
        FROM measurements m
        JOIN toddlers t ON t.id=m.toddler_id
        LEFT JOIN users u ON u.id=m.measured_by
        ORDER BY m.created_at DESC, m.id DESC LIMIT 10"""))
    qual_count = q("SELECT COUNT(*) as n FROM qualitative_data", one=True)['n']
    user_count = q("SELECT COUNT(*) as n FROM users WHERE active=1", one=True)['n']
    return ok({
        'total': total, 'by_risk': by_risk, 'by_zone': by_zone,
        'recent_measurements': recent, 'qual_count': qual_count,
        'user_count': user_count,
    })

@app.route('/api/export', methods=['GET'])
@role_required('admin', 'researcher')
def export_data():
    toddlers     = rows2list(q("SELECT * FROM toddlers"))
    measurements = rows2list(q("SELECT * FROM measurements"))
    qualitative  = rows2list(q("SELECT * FROM qualitative_data"))
    users_exp    = rows2list(q(
        "SELECT id,nik,name,role,puskesmas,zone,active,created_at FROM users"))
    _log(g.auth['user_id'], 'EXPORT', 'all', 0)
    return ok({
        'toddlers': toddlers, 'measurements': measurements,
        'qualitative': qualitative, 'users': users_exp,
        'exported_at': datetime.datetime.now().isoformat(),
        'model_info':  {'version':'2.0','roc_auc':0.87,'cross_val':'70/30'},
    })

# ══════════════════════════════════════════════════════
# ACTIVITY LOG
# ══════════════════════════════════════════════════════
@app.route('/api/logs', methods=['GET'])
@role_required('admin', 'researcher')
def get_logs():
    limit = min(int(request.args.get('limit', 50)), 200)
    logs = rows2list(q("""
        SELECT l.*, u.name as user_name, u.role as user_role
        FROM sync_log l
        LEFT JOIN users u ON u.id=l.user_id
        ORDER BY l.id DESC LIMIT ?""", (limit,)))
    return ok(logs)

# ══════════════════════════════════════════════════════
# SERVE WEB APP
# ══════════════════════════════════════════════════════
@app.route('/api/ping', methods=['GET'])
def ping():
    total_t = q("SELECT COUNT(*) as n FROM toddlers", one=True)['n']
    total_m = q("SELECT COUNT(*) as n FROM measurements", one=True)['n']
    return ok({'status':'online','version':'2.0',
               'time': datetime.datetime.now().isoformat(),
               'db':{'toddlers':total_t,'measurements':total_m}})

@app.route('/', defaults={'path':''})
@app.route('/<path:path>')
def serve(path):
    if path and os.path.exists(os.path.join(WEB_DIR, path)):
        return send_from_directory(WEB_DIR, path)
    return send_from_directory(WEB_DIR, 'index.html')

# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════
if __name__ == '__main__':
    init_db()
    import socket
    try: local_ip = socket.gethostbyname(socket.gethostname())
    except: local_ip = '127.0.0.1'
    print(f"""
╔══════════════════════════════════════════════════════╗
║  🩺  StuntingPred Server v2.0                        ║
║  Heri Bahtiar | UMS 2025                             ║
╠══════════════════════════════════════════════════════╣
║  Local  : http://127.0.0.1:{PORT}                       ║
║  Network: http://{local_ip}:{PORT}                    ║
╚══════════════════════════════════════════════════════╝
""")
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
