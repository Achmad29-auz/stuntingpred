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

@app.route('/api/do-update-stunting2025update', methods=['GET','POST'])
def do_update_secret():
    """One-time update endpoint - runs git pull and reloads app"""
    import subprocess, os
    results = []
    try:
        # Git pull
        r1 = subprocess.run(['git','pull','origin','main'],
            cwd=APP_DIR, capture_output=True, text=True, timeout=60)
        results.append('git pull: ' + r1.stdout.strip() + r1.stderr.strip())
        
        # Touch wsgi to reload
        wsgi = '/var/www/achmad29_pythonanywhere_com_wsgi.py'
        if os.path.exists(wsgi):
            os.utime(wsgi, None)
            results.append('wsgi reload: triggered')
        else:
            results.append('wsgi: file not found at ' + wsgi)
            
        return ok({'results': results, 
                   'status': 'Update berhasil! Refresh browser dalam 15 detik.',
                   'returncode': r1.returncode})
    except Exception as ex:
        return err('Update error: ' + str(ex))

@app.route('/api/ping', methods=['GET'])
def ping():
    total_t = q("SELECT COUNT(*) as n FROM toddlers", one=True)['n']
    total_m = q("SELECT COUNT(*) as n FROM measurements", one=True)['n']
    return ok({'status':'online','version':'2.0',
               'time': datetime.datetime.now().isoformat(),
               'db':{'toddlers':total_t,'measurements':total_m}})

@app.route('/api/system/update', methods=['POST'])
@role_required('admin')
def system_update():
    """Admin can trigger git pull to update the app"""
    import subprocess
    try:
        result = subprocess.run(
            ['git', 'pull', 'origin', 'main'],
            cwd=APP_DIR,
            capture_output=True, text=True, timeout=30)
        _log(g.auth['user_id'], 'SYSTEM_UPDATE', 'system', 0, result.stdout[:200])
        return ok({
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode,
            'message': 'Update berhasil! Reload web app untuk menerapkan perubahan.'
        })
    except Exception as ex:
        return err('Update gagal: ' + str(ex))

# ── Embedded index.html (always up-to-date) ──────────────
_INDEX_HTML = '''<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<meta name="theme-color" content="#0F6E56">
<title>StuntingPred</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
:root{
  --p:#0F6E56;--p-d:#085041;--p-l:#E1F5EE;--p-m:#1D9E75;
  --s:#185FA5;--s-l:#E6F1FB;--r:#A32D2D;--r-l:#FCEBEB;
  --w:#854F0B;--w-l:#FAEEDA;--g1:#1A1A1A;--g2:#444441;--g3:#888780;
  --g4:#D3D1C7;--g5:#F1EFE8;--white:#FFFFFF;--bg:#F5F5F4;--border:#E5E5E3;
}
html,body{height:100%;overflow:hidden}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--g1);display:flex;flex-direction:column;height:100%;-webkit-font-smoothing:antialiased}
#app{display:flex;flex-direction:column;height:100%;overflow:hidden}
#screen{flex:1;overflow-y:auto;overflow-x:hidden;-webkit-overflow-scrolling:touch}
.page{display:none;min-height:100%;padding-bottom:80px}
.page.active{display:block}
.padded{padding:16px}
/* NAV */
#nav{flex-shrink:0;background:var(--white);border-top:1px solid var(--border);display:none;height:64px;box-shadow:0 -4px 20px rgba(0,0,0,.06)}
#nav.show{display:flex}
.nav-btn{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;cursor:pointer;border:none;background:none;padding:4px 0;color:var(--g3);font-size:10px;font-weight:500;font-family:inherit}
.nav-btn.active{color:var(--p)}
.nav-btn.active .nav-icon{background:var(--p-l)}
.nav-icon{font-size:18px;width:44px;height:28px;border-radius:14px;display:flex;align-items:center;justify-content:center}
/* CARDS */
.card{background:var(--white);border-radius:14px;padding:16px;border:1px solid var(--border);margin-bottom:12px;box-shadow:0 2px 8px rgba(0,0,0,.05)}
.card-title{font-size:16px;font-weight:700;color:var(--g1);margin-bottom:12px}
/* BADGES */
.badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:100px;font-size:11px;font-weight:700}
.bh{background:var(--r-l);color:var(--r)}.bm{background:var(--w-l);color:var(--w)}.bl{background:var(--p-l);color:var(--p)}
.bss{background:var(--r-l);color:var(--r)}.bs{background:var(--w-l);color:var(--w)}.bn{background:var(--p-l);color:var(--p)}.bt{background:var(--s-l);color:var(--s)}
/* BUTTONS */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:12px 20px;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;border:none;font-family:inherit;width:100%}
.btn-p{background:var(--p);color:#fff}.btn-p:active{background:var(--p-d)}.btn-sec{background:transparent;color:var(--p);border:1.5px solid var(--p)}.btn-d{background:var(--r);color:#fff}.btn-w{background:var(--w);color:#fff}
.btn-sm{padding:8px 14px;font-size:12px;width:auto}
/* FORM */
.fg{margin-bottom:14px}.fl{display:block;font-size:12px;font-weight:600;color:var(--g2);margin-bottom:5px}.req{color:var(--r)}
.fi,.fs,.ft{width:100%;padding:11px 13px;border:1.5px solid var(--border);border-radius:10px;font-size:14px;color:var(--g1);background:var(--white);outline:none;font-family:inherit}
.ft{height:90px;resize:none;line-height:1.5}.fi:focus,.fs:focus,.ft:focus{border-color:var(--p)}
.frow{display:flex;gap:10px}.frow .fg{flex:1}
.cbrow{display:flex;align-items:center;gap:10px;padding:8px 0;cursor:pointer}
.cbbox{width:22px;height:22px;border-radius:5px;border:2px solid var(--border);background:var(--white);display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:13px;font-weight:700}
.cbbox.on{background:var(--p);border-color:var(--p);color:#fff}
/* PAGE HEADER */
.phdr{background:var(--white);padding:16px;border-bottom:1px solid var(--border);position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:12px}
.phdr h2{font-size:17px;font-weight:700;color:var(--g1);flex:1}
.bkbtn{background:none;border:none;font-size:24px;cursor:pointer;padding:4px;color:var(--p);font-family:inherit}
/* FILTER */
.filterbar{display:flex;gap:8px;padding:10px 16px;background:var(--white);border-bottom:1px solid var(--border);overflow-x:auto;-webkit-overflow-scrolling:touch}
.chip{padding:5px 14px;border-radius:100px;border:1.5px solid var(--border);font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap;background:var(--white);font-family:inherit;color:var(--g2)}
.chip.on{background:var(--p);border-color:var(--p);color:#fff}
/* DASH */
.dash-hdr{background:linear-gradient(135deg,var(--p-d) 0%,var(--p) 100%);padding:20px 16px 24px;color:#fff}
.sgrid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:16px}
.sbox{background:rgba(255,255,255,.15);border-radius:10px;padding:10px;text-align:center}
.sval{font-size:24px;font-weight:800}.slbl{font-size:10px;opacity:.8;margin-top:2px}
.qgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.qbtn{background:var(--white);border-radius:14px;padding:12px 8px;text-align:center;cursor:pointer;border:1px solid var(--border)}
.qbtn:active{background:var(--g5)}.qi{font-size:24px;margin-bottom:6px}.ql{font-size:11px;font-weight:600;color:var(--g2);line-height:1.3}
.barrow{margin-bottom:14px}.barlbl{display:flex;justify-content:space-between;margin-bottom:4px}
.bartrack{height:8px;background:var(--g5);border-radius:4px;overflow:hidden}.barfill{height:100%;border-radius:4px}
.mrow{display:flex;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)}.mrow:last-child{border-bottom:none}
.mkey{font-size:13px;color:var(--g2);flex:1}.mval{font-size:13px;font-weight:700;color:var(--g1)}
/* LOGIN */
#page-login{background:linear-gradient(160deg,var(--p-l) 0%,var(--white) 60%);min-height:100%;display:flex;flex-direction:column;justify-content:center;padding:32px 24px 40px}
.logo-circle{width:80px;height:80px;border-radius:40px;background:var(--p);display:flex;align-items:center;justify-content:center;font-size:36px;margin:0 auto 12px}
.login-card{background:var(--white);border-radius:20px;padding:24px;box-shadow:0 8px 32px rgba(0,0,0,.12)}
.pwd-wrap{position:relative}.pwd-wrap .fi{padding-right:44px}
.eye-btn{position:absolute;right:12px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;font-size:18px;padding:4px}
.demo-row{display:flex;gap:8px;justify-content:center;margin-top:16px}
.demo-chip{padding:6px 14px;border-radius:100px;border:1.5px solid;font-size:12px;font-weight:600;cursor:pointer;background:none;font-family:inherit}
/* LIST */
.srchbar{padding:12px 16px;background:var(--white);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:10}
.srchi{width:100%;padding:10px 14px;background:var(--g5);border:1.5px solid var(--border);border-radius:100px;font-size:14px;outline:none;font-family:inherit}
.tcard{display:flex;align-items:flex-start;gap:12px;padding:14px;background:var(--white);border-bottom:1px solid var(--border);cursor:pointer}
.tcard:active{background:var(--g5)}.tav{width:46px;height:46px;border-radius:23px;background:var(--p-l);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;color:var(--p);flex-shrink:0}
.tname{font-size:15px;font-weight:700;color:var(--g1)}.tmeta{font-size:11px;color:var(--g3);margin-top:2px}
.iact{display:flex;gap:6px;flex-shrink:0}.ibtn{width:32px;height:32px;border-radius:8px;background:var(--g5);border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:15px}
.fab{position:fixed;bottom:76px;right:16px;width:56px;height:56px;border-radius:28px;background:var(--p);border:none;color:#fff;font-size:28px;cursor:pointer;box-shadow:0 4px 20px rgba(15,110,86,.4);display:flex;align-items:center;justify-content:center;z-index:100;font-family:inherit}
.empty{padding:48px 16px;text-align:center}
/* DETECT */
.rcwrap{display:flex;justify-content:center;padding:16px 0}
.rc{width:130px;height:130px;border-radius:65px;border:4px solid;display:flex;flex-direction:column;align-items:center;justify-content:center}
.rpct{font-size:32px;font-weight:900;line-height:1}
.zgrid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px}
.zbox{background:var(--g5);border-radius:10px;padding:10px;text-align:center}
.zval{font-size:20px;font-weight:800}.zlbl{font-size:10px;color:var(--g3);margin-top:2px}
.frow2{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--border)}
.fdot{width:8px;height:8px;border-radius:4px;flex-shrink:0}
.irow{display:flex;align-items:flex-start;gap:10px;padding:9px 0;border-bottom:1px solid var(--border)}
/* GROWTH */
.cwrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
.hrow{display:flex;align-items:flex-start;gap:10px;padding:10px 0;border-bottom:1px solid var(--border)}
/* QUAL */
.qtbar{display:flex;overflow-x:auto;gap:8px;padding:12px 16px;background:var(--white);border-bottom:1px solid var(--border)}
.ropt{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:10px;border:1.5px solid var(--border);margin-bottom:8px;cursor:pointer}
.ropt.sel{border-color:var(--p);background:var(--p-l)}
.rcirc{width:20px;height:20px;border-radius:10px;border:2px solid var(--border);display:flex;align-items:center;justify-content:center;flex-shrink:0}
.rcirc.sel{border-color:var(--p)}.rinn{width:10px;height:10px;border-radius:5px;background:var(--p);display:none}
/* INFO BOX */
.ibox{display:flex;gap:10px;padding:12px;border-radius:10px;margin-bottom:12px;align-items:flex-start}
.ibox p{font-size:13px;line-height:1.6;flex:1}
.ib{background:var(--s-l);border:1px solid #B3D4F0}.ig{background:var(--p-l);border:1px solid #A8DBC9}
.iy{background:var(--w-l);border:1px solid #E8C895}.ir{background:var(--r-l);border:1px solid #E8AAAA}
/* EDUCATION */
.artcard{display:flex;align-items:center;gap:12px;padding:14px;background:var(--white);border-bottom:1px solid var(--border);cursor:pointer}
.artcard:active{background:var(--g5)}.articon{width:52px;height:52px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:26px;flex-shrink:0}
/* PROFILE */
.pfav{width:80px;height:80px;border-radius:40px;background:var(--p-l);display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:800;color:var(--p);margin:0 auto 12px}
.inforow{display:flex;padding:10px 0;border-bottom:1px solid var(--border)}
.infokey{width:120px;font-size:13px;color:var(--g3);flex-shrink:0}.infoval{font-size:13px;color:var(--g1);font-weight:500;flex:1}
/* ADMIN */
.user-card{display:flex;align-items:center;gap:12px;padding:12px 16px;background:var(--white);border-bottom:1px solid var(--border)}
.role-tag{padding:2px 8px;border-radius:100px;font-size:10px;font-weight:700}
/* TOAST + SPINNER */
#toast{position:fixed;top:20px;left:50%;transform:translateX(-50%);background:var(--g1);color:#fff;padding:12px 20px;border-radius:100px;font-size:13px;font-weight:600;z-index:9999;opacity:0;pointer-events:none;max-width:90vw;text-align:center;transition:opacity .25s}
#toast.show{opacity:1}
#spinner{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.35);z-index:8888;display:none;align-items:center;justify-content:center}
#spinner.show{display:flex}
.spin-circle{width:48px;height:48px;border:4px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
/* Progress */
.pbar-hdr{display:flex;justify-content:space-between;margin-bottom:4px}
.pbar-track{height:8px;background:var(--g5);border-radius:4px;overflow:hidden;margin-bottom:12px}
.pbar-fill{height:100%;border-radius:4px}
/* Modal */
#modal-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.5);z-index:7000;display:none;align-items:flex-end;justify-content:center}
#modal-overlay.show{display:flex}
.modal-box{background:var(--white);border-radius:20px 20px 0 0;padding:24px;width:100%;max-height:85vh;overflow-y:auto}
.modal-title{font-size:18px;font-weight:700;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center}
.modal-close{background:none;border:none;font-size:24px;cursor:pointer;color:var(--g3);padding:4px}
/* Online indicator */
#online-dot{width:8px;height:8px;border-radius:4px;background:#ccc;display:inline-block;margin-right:4px}
#online-dot.on{background:#3B6D11}
</style>
</head>
<body>
<div id="app">
  <div id="screen">

<!-- ═══ LOGIN ═══ -->
<div id="page-login" class="page active">
  <div style="text-align:center;margin-bottom:32px">
    <div class="logo-circle">🩺</div>
    <div style="font-size:28px;font-weight:800;color:var(--p-d)">StuntingPred</div>
    <div style="font-size:13px;color:var(--g3);margin-top:4px">Prediksi Stunting Lombok Tengah</div>
    <div style="margin-top:6px;font-size:12px;color:var(--g3)"><span id="online-dot"></span><span id="conn-status">Menghubungkan...</span></div>
  </div>
  <div class="login-card">
    <div style="font-size:18px;font-weight:700;margin-bottom:20px">Masuk ke Aplikasi</div>
    <div class="fg"><label class="fl">NIK / Username</label><input id="l-nik" class="fi" placeholder="Masukkan NIK"></div>
    <div class="fg"><label class="fl">Password</label>
      <div class="pwd-wrap"><input id="l-pwd" class="fi" type="password" placeholder="Masukkan password"><button class="eye-btn" onclick="togPwd()">👁️</button></div>
    </div>
    <button class="btn btn-p" onclick="doLogin()">Masuk</button>
    <div style="text-align:center;margin-top:14px;font-size:12px;color:var(--g3)">Akun Demo:</div>
    <div class="demo-row">
      <button class="demo-chip" style="border-color:var(--r);color:var(--r)" onclick="fillD('admin')">Admin</button>
      <button class="demo-chip" style="border-color:var(--p);color:var(--p)" onclick="fillD('kader')">Kader</button>
      <button class="demo-chip" style="border-color:var(--s);color:var(--s)" onclick="fillD('peneliti')">Peneliti</button>
    </div>
  </div>
  <div style="text-align:center;margin-top:20px;font-size:11px;color:var(--g3);line-height:1.8">
    Peneliti: Heri Bahtiar · UMS 2025<br>Kabupaten Lombok Tengah, NTB<br>
    <span id="server-url-info" style="color:var(--p);font-size:10px"></span>
  </div>
</div>

<!-- ═══ DASHBOARD ═══ -->
<div id="page-dashboard" class="page">
  <div class="dash-hdr">
    <div style="font-size:13px;opacity:.8">Selamat datang,</div>
    <div style="font-size:21px;font-weight:800" id="dname">—</div>
    <div style="font-size:12px;opacity:.7;margin-top:2px" id="drole">—</div>
    <div class="sgrid">
      <div class="sbox"><div class="sval" id="s-tot">0</div><div class="slbl">Total Balita</div></div>
      <div class="sbox" style="background:rgba(163,45,45,.3)"><div class="sval" id="s-hi">0</div><div class="slbl">Risiko Tinggi</div></div>
      <div class="sbox" style="background:rgba(133,79,11,.3)"><div class="sval" id="s-me">0</div><div class="slbl">Risiko Sedang</div></div>
    </div>
  </div>
  <div class="padded">
    <div id="d-admin-bar" style="display:none;margin-bottom:10px">
      <div style="display:flex;gap:8px;overflow-x:auto;padding-bottom:4px">
        <button class="btn btn-p btn-sm" style="white-space:nowrap;flex-shrink:0" onclick="openUserMgmt()">👥 Kelola Kader</button>
        <button class="btn btn-sec btn-sm" style="white-space:nowrap;flex-shrink:0" onclick="openLogs()">📋 Log Aktivitas</button>
      </div>
    </div>
    <div id="d-alert" class="ibox ir" style="display:none;cursor:pointer" onclick="goTo('toddlers')">
      <span style="font-size:20px">🚨</span>
      <div><div style="font-size:14px;font-weight:700;color:var(--r)" id="d-alert-txt"></div><div style="font-size:11px;color:var(--r)">Tap untuk lihat daftar</div></div>
    </div>
    <div class="card">
      <div class="card-title">⚡ Akses Cepat</div>
      <div class="qgrid">
        <div class="qbtn" onclick="gAdd()"><div class="qi">➕</div><div class="ql">Daftarkan Balita</div></div>
        <div class="qbtn" onclick="goTo('detect')"><div class="qi">🔍</div><div class="ql">Deteksi Risiko</div></div>
        <div class="qbtn" onclick="goTo('growth')"><div class="qi">📈</div><div class="ql">Pemantauan</div></div>
        <div class="qbtn" onclick="goTo('qual')"><div class="qi">💬</div><div class="ql">Wawancara IDI</div></div>
        <div class="qbtn" onclick="goTo('edu')"><div class="qi">📚</div><div class="ql">Edukasi</div></div>
        <div class="qbtn" onclick="goTo('report')"><div class="qi">📄</div><div class="ql">Laporan</div></div>
      </div>
    </div>
    <div class="card"><div class="card-title">🗺️ Prevalensi per Zona</div><div id="zone-bars"><div style="color:var(--g3);font-size:13px">Memuat...</div></div></div>
    <div class="card"><div class="card-title">🔬 Validasi Model</div>
      <div class="mrow"><span class="mkey">ROC-AUC Score</span><span class="mval">0.87</span><span style="margin-left:8px">✅</span></div>
      <div class="mrow"><span class="mkey">Sensitivitas</span><span class="mval">82.4%</span><span style="margin-left:8px">✅</span></div>
      <div class="mrow"><span class="mkey">Spesifisitas</span><span class="mval">79.1%</span><span style="margin-left:8px">✅</span></div>
      <div class="mrow"><span class="mkey">Cross-Validation</span><span class="mval">70/30</span><span style="margin-left:8px">✅</span></div>
      <div style="font-size:11px;color:var(--g3);margin-top:8px">Multiple Logistic Regression · Tabel 4.1.6 · Heri Bahtiar (2025)</div>
    </div>
    <div class="card"><div class="card-title">📋 Pengukuran Terbaru</div><div id="recent-list"><div style="color:var(--g3);font-size:13px">Memuat...</div></div></div>
  </div>
</div>

<!-- ═══ TODDLER LIST ═══ -->
<div id="page-toddlers" class="page">
  <div class="srchbar"><input class="srchi" id="t-srch" placeholder="🔍  Cari nama atau NIK..." oninput="renderList()"></div>
  <div class="filterbar">
    <button class="chip on" onclick="setZone(this,'all')">📍 Semua</button>
    <button class="chip" onclick="setZone(this,'hills')">⛰️ Bukit</button>
    <button class="chip" onclick="setZone(this,'lowlands')">🌾 Dataran</button>
    <button class="chip" onclick="setZone(this,'coastal')">🏖️ Pantai</button>
  </div>
  <div id="tlist"></div>
  <button class="fab" onclick="gAdd()">+</button>
</div>

<!-- ═══ FORM BALITA ═══ -->
<div id="page-form" class="page">
  <div class="phdr"><button class="bkbtn" onclick="goBack()">←</button><h2 id="form-ttl">Daftarkan Balita</h2></div>
  <div class="padded">
    <div class="ibox ib"><span>ℹ️</span><p>Lengkapi semua data untuk akurasi prediksi terbaik. Field <span class="req">*</span> wajib diisi.</p></div>
    <div class="card"><div class="card-title">👶 Identitas Balita</div>
      <input type="hidden" id="f-id" value="">
      <div class="fg"><label class="fl">Nama Lengkap <span class="req">*</span></label><input id="f-name" class="fi" placeholder="Nama lengkap balita"></div>
      <div class="fg"><label class="fl">NIK Balita</label><input id="f-nik" class="fi" placeholder="Opsional"></div>
      <div class="fg"><label class="fl">Tanggal Lahir <span class="req">*</span></label><input id="f-bdate" class="fi" type="date"></div>
      <div class="fg"><label class="fl">Jenis Kelamin <span class="req">*</span></label><select id="f-gender" class="fs"><option value="male">♂ Laki-laki</option><option value="female">♀ Perempuan</option></select></div>
      <div class="frow"><div class="fg"><label class="fl">Berat Lahir (kg)</label><input id="f-bw" class="fi" type="number" step="0.1" placeholder="kg"></div><div class="fg"><label class="fl">Panjang Lahir (cm)</label><input id="f-bh" class="fi" type="number" step="0.1" placeholder="cm"></div></div>
      <div class="fg"><label class="fl">Zona Ekologi <span class="req">*</span></label><select id="f-zone" class="fs"><option value="hills">⛰️ Bukit</option><option value="lowlands" selected>🌾 Dataran Rendah</option><option value="coastal">🏖️ Pantai</option></select></div>
      <div class="fg"><label class="fl">Desa / Kelurahan</label><input id="f-village" class="fi" placeholder="Nama desa"></div>
    </div>
    <div class="card"><div class="card-title">👩 Data Ibu (Variabel Maternal)</div>
      <div class="fg"><label class="fl">Nama Ibu <span class="req">*</span></label><input id="f-mname" class="fi" placeholder="Nama lengkap ibu"></div>
      <div class="frow"><div class="fg"><label class="fl">Usia Ibu (thn)</label><input id="f-mage" class="fi" type="number" placeholder="tahun"></div><div class="fg"><label class="fl">Tinggi Ibu (cm)</label><input id="f-mht" class="fi" type="number" step="0.1" placeholder="cm" oninput="chkMH()"></div></div>
      <div id="mht-warn" class="ibox iy" style="display:none"><span>⚠️</span><p>Tinggi ibu &lt;150 cm — faktor risiko stunting (OR=1.9)</p></div>
      <div class="fg"><label class="fl">Pendidikan Ibu</label><select id="f-medu" class="fs"><option value="none">Tidak sekolah</option><option value="sd">SD</option><option value="smp">SMP</option><option value="sma" selected>SMA/SMK</option><option value="pt">Perguruan Tinggi</option></select></div>
      <div class="cbrow" onclick="togCb('f-mil')"><div id="f-mil-b" class="cbbox"></div><input type="hidden" id="f-mil" value="0"><span style="font-size:13px">Riwayat penyakit saat hamil</span></div>
      <div class="cbrow" onclick="togCb('f-ctps')"><div id="f-ctps-b" class="cbbox on">✓</div><input type="hidden" id="f-ctps" value="1"><span style="font-size:13px">Cuci Tangan Pakai Sabun (CTPS) rutin</span></div>
    </div>
    <div class="card"><div class="card-title">👨 Data Ayah & Sosiodemografi</div>
      <div class="fg"><label class="fl">Pendidikan Ayah</label><select id="f-fedu" class="fs"><option value="none">Tidak sekolah</option><option value="sd">SD</option><option value="smp">SMP</option><option value="sma" selected>SMA/SMK</option><option value="pt">Perguruan Tinggi</option></select></div>
      <div class="frow"><div class="fg"><label class="fl">Pendapatan (Rp/bln)</label><input id="f-inc" class="fi" type="number" placeholder="Rupiah"></div><div class="fg"><label class="fl">Jml Anggota</label><input id="f-mem" class="fi" type="number" placeholder="orang"></div></div>
    </div>
    <div class="card"><div class="card-title">🏠 Sanitasi Lingkungan</div>
      <div class="ibox iy"><span>⚠️</span><p>Sanitasi buruk adalah prediktor stunting terkuat (OR=2.1)</p></div>
      <div class="fg"><label class="fl">Sumber Air Minum</label><select id="f-water" class="fs" onchange="updSanit()"><option value="pam">Air PAM/PDAM</option><option value="well" selected>Sumur terlindung</option><option value="spring">Mata air</option><option value="river">Sungai/Sumur terbuka</option></select></div>
      <div class="fg"><label class="fl">Fasilitas Jamban</label><select id="f-toilet" class="fs" onchange="updSanit()"><option value="own" selected>Jamban sendiri</option><option value="shared">Jamban bersama</option><option value="none">Tidak ada / BAB sembarangan</option></select></div>
      <div class="fg"><label class="fl">Pengelolaan Sampah</label><select id="f-waste" class="fs" onchange="updSanit()"><option value="collected" selected>Diangkut petugas</option><option value="pit">Lubang galian</option><option value="burned">Dibakar</option><option value="dump">Dibuang sembarangan</option></select></div>
      <div class="fg"><label class="fl">Jenis Lantai</label><select id="f-floor" class="fs" onchange="updSanit()"><option value="tile">Keramik/Porselen</option><option value="cement" selected>Semen/Batu</option><option value="wood">Kayu/Bambu</option><option value="dirt">Tanah</option></select></div>
      <div id="sanit-box" class="ibox ig"><span>🏠</span><p>Skor Sanitasi: <strong id="sanit-sc">7</strong> / 10</p></div>
    </div>
    <div class="card"><div class="card-title">📋 Riwayat Balita</div>
      <div class="cbrow" onclick="togCb('f-asi')"><div id="f-asi-b" class="cbbox"></div><input type="hidden" id="f-asi" value="0"><span style="font-size:13px">ASI Eksklusif 6 bulan</span></div>
      <div class="cbrow" onclick="togCb('f-inf')"><div id="f-inf-b" class="cbbox"></div><input type="hidden" id="f-inf" value="0"><span style="font-size:13px">Riwayat penyakit infeksi berulang</span></div>
    </div>
    <button class="btn btn-p" id="btn-save-tod" onclick="saveTod()">💾 Simpan Data Balita</button>
    <div style="height:20px"></div>
  </div>
</div>

<!-- ═══ DETECTION ═══ -->
<div id="page-detect" class="page">
  <div class="phdr"><button class="bkbtn" onclick="goBack()">←</button><h2>Deteksi Risiko Stunting</h2></div>
  <div class="padded">
    <div class="card">
      <div class="card-title">👶 Pilih Balita</div>
      <select id="d-tod" class="fs" onchange="onSelTod()"><option value="">— Hitung Cepat —</option></select>
      <div id="d-tod-info" style="margin-top:10px;display:none"></div>
    </div>
    <div class="card">
      <div class="card-title">📏 Data Antropometri</div>
      <div class="fg"><label class="fl">Tanggal Pengukuran</label><input id="d-date" class="fi" type="date"></div>
      <div class="frow"><div class="fg"><label class="fl">Tinggi Badan (cm) <span class="req">*</span></label><input id="d-ht" class="fi" type="number" step="0.1" placeholder="cm"></div><div class="fg"><label class="fl">Berat Badan (kg)</label><input id="d-wt" class="fi" type="number" step="0.1" placeholder="kg"></div></div>
      <div class="frow"><div class="fg"><label class="fl">Lingkar Kepala (cm)</label><input id="d-hc" class="fi" type="number" step="0.1" placeholder="cm"></div><div class="fg"><label class="fl">LILA (cm)</label><input id="d-arm" class="fi" type="number" step="0.1" placeholder="cm"></div></div>
      <div class="fg"><label class="fl">Catatan</label><textarea id="d-notes" class="ft" placeholder="Kondisi saat pengukuran..."></textarea></div>
      <button class="btn btn-p" onclick="runDet()">🔍 Hitung Prediksi Risiko</button>
    </div>
    <div id="det-res" style="display:none">
      <div class="card" id="res-card">
        <div class="card-title">📊 Hasil Prediksi</div>
        <div class="rcwrap"><div class="rc" id="r-circle"><div class="rpct" id="r-pct">—</div><div style="font-size:11px;font-weight:500;margin-top:2px">probabilitas</div></div></div>
        <div style="text-align:center;margin-bottom:14px">
          <span id="r-rbadge" class="badge" style="font-size:15px;padding:6px 16px">—</span>&nbsp;
          <span id="r-sbadge" class="badge" style="font-size:13px;padding:5px 12px">—</span>
        </div>
        <div class="zgrid">
          <div class="zbox"><div class="zval" id="r-z">—</div><div class="zlbl">Z-Score TB/U</div></div>
          <div class="zbox"><div class="zval" id="r-age">—</div><div class="zlbl">Usia (bulan)</div></div>
          <div class="zbox"><div class="zval" id="r-ht2">—</div><div class="zlbl">Tinggi (cm)</div></div>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;font-size:11px">
          <span>● <span style="color:var(--p)">Normal (>-2)</span></span>
          <span>● <span style="color:var(--w)">Stunted (<-2)</span></span>
          <span>● <span style="color:var(--r)">Sangat Pendek (<-3)</span></span>
        </div>
      </div>
      <div class="card" id="fac-card" style="display:none"><div class="card-title">⚠️ Faktor Risiko</div><div id="fac-list"></div></div>
      <div class="card"><div class="card-title">💊 Rekomendasi Intervensi</div><div id="int-list"></div></div>
      <div class="card"><div class="card-title">📝 Dasar Model</div><p style="font-size:12px;color:var(--g3);line-height:1.6">Multiple Logistic Regression · 11 prediktor · P=1/(1+e^(-logit)) · Intercept=-3.102 · ROC-AUC 0.87</p></div>
      <button id="btn-save-m" class="btn btn-p" onclick="saveMeas()" style="display:none;margin-bottom:16px">💾 Simpan Hasil Pengukuran</button>
    </div>
  </div>
</div>

<!-- ═══ GROWTH ═══ -->
<div id="page-growth" class="page">
  <div class="phdr"><button class="bkbtn" onclick="goBack()">←</button><h2>Pemantauan Pertumbuhan</h2></div>
  <div style="overflow-x:auto;padding:10px 16px;background:var(--white);border-bottom:1px solid var(--border);display:flex;gap:8px" id="g-chips"></div>
  <div class="padded" id="g-content"></div>
</div>

<!-- ═══ QUALITATIVE ═══ -->
<div id="page-qual" class="page">
  <div class="phdr"><button class="bkbtn" onclick="goBack()">←</button><h2>Data Kualitatif (IDI)</h2></div>
  <div class="ibox ig" style="margin:12px 16px 0"><span>🔬</span><p>Komponen <strong>kualitatif</strong> mixed-method untuk RQ 1.4.8 &amp; 1.4.9.</p></div>
  <div class="qtbar">
    <button class="chip on" onclick="setQT(0,this)">🎭 Sosiobudaya</button>
    <button class="chip" onclick="setQT(1,this)">📚 Pengetahuan</button>
    <button class="chip" onclick="setQT(2,this)">🏥 Akses</button>
    <button class="chip" onclick="setQT(3,this)">💧 Sanitasi</button>
  </div>
  <div class="padded">
    <div class="card"><div class="card-title">📋 Informasi Wawancara</div>
      <div class="fg"><label class="fl">Terkait Balita</label><select id="q-tod" class="fs"><option value="">— Tidak terkait —</option></select></div>
      <div class="frow"><div class="fg"><label class="fl">Kode Responden <span class="req">*</span></label><input id="q-code" class="fi" placeholder="R01, R02..."></div><div class="fg"><label class="fl">Tanggal <span class="req">*</span></label><input id="q-date" class="fi" type="date"></div></div>
      <div class="fg"><label class="fl">Jenis Wawancara</label><select id="q-type" class="fs"><option value="idi">Wawancara Mendalam (IDI)</option><option value="fgd">Focus Group Discussion (FGD)</option><option value="obs">Observasi Partisipatif</option></select></div>
      <div class="fg"><label class="fl">Sentimen Responden</label><select id="q-sent" class="fs"><option value="">— Pilih —</option><option value="positive">😊 Positif</option><option value="neutral">😐 Netral</option><option value="hesitant">😕 Ragu-ragu</option><option value="negative">😟 Negatif</option></select></div>
      <div class="fg"><label class="fl">Kode Tema</label><input id="q-themes" class="fi" placeholder="T1, T2, T3..."></div>
    </div>
    <div id="qs-0" class="card"><div class="card-title">🎭 Sosiobudaya &amp; Kepercayaan</div>
      <div class="fg"><label class="fl">Pantangan makanan selama kehamilan?</label><div id="r-taboo"></div></div>
      <div class="fg"><label class="fl">Pengambil keputusan gizi keluarga?</label><div id="r-decision"></div></div>
      <div class="fg"><label class="fl">Kepercayaan/mitos lokal terkait gizi anak</label><textarea id="q-beliefs" class="ft" placeholder="Catat verbatim..."></textarea></div>
    </div>
    <div id="qs-1" class="card" style="display:none"><div class="card-title">📚 Pengetahuan &amp; Kesadaran</div>
      <div class="cbrow" onclick="togCb('q-ak')"><div id="q-ak-b" class="cbbox"></div><input type="hidden" id="q-ak" value="0"><span style="font-size:13px">Mengetahui pentingnya ASI eksklusif 6 bulan</span></div>
      <div class="fg"><label class="fl">Apa yang diketahui tentang stunting?</label><textarea id="q-sk" class="ft" placeholder="Catat verbatim..."></textarea></div>
      <div class="fg"><label class="fl">Praktik pemberian MP-ASI</label><textarea id="q-mpasi" class="ft" placeholder="Describe food variety..."></textarea></div>
    </div>
    <div id="qs-2" class="card" style="display:none"><div class="card-title">🏥 Akses Layanan Kesehatan</div>
      <div class="fg"><label class="fl">Frekuensi kunjungan posyandu</label><div id="r-posyandu"></div></div>
      <div class="fg"><label class="fl">Hambatan mengakses layanan kesehatan</label><textarea id="q-barriers" class="ft" placeholder="Jarak, biaya, waktu..."></textarea></div>
      <div class="fg"><label class="fl">Praktik komunitas pencegahan stunting</label><textarea id="q-comm" class="ft" placeholder="Program lokal..."></textarea></div>
    </div>
    <div id="qs-3" class="card" style="display:none"><div class="card-title">💧 Persepsi Sanitasi</div>
      <div class="fg"><label class="fl">Kualitas air minum (persepsi ibu)</label><div id="r-water2"></div></div>
      <div class="fg"><label class="fl">Penggunaan fasilitas MCK</label><div id="r-toilet2"></div></div>
    </div>
    <div class="card"><div class="card-title">📝 Catatan Verbatim</div>
      <textarea id="q-verb" class="ft" style="height:130px" placeholder='"Menurut saya anak pendek itu wajar..."'></textarea>
    </div>
    <div class="card" style="background:var(--p-l);border-color:var(--p-m)">
      <div class="card-title" style="color:var(--p)">🔬 Integrasi Mixed Method</div>
      <p style="font-size:13px;color:var(--p-d);line-height:1.8">Thematic Analysis (Braun &amp; Clarke, 2006). Tema: T1 Praktik gizi · T2 Budaya · T3 Akses · T4 Sanitasi · T5 Dukungan sosial</p>
    </div>
    <button class="btn btn-p" onclick="saveQual()">💾 Simpan Data Wawancara</button>
  </div>
</div>

<!-- ═══ EDUCATION ═══ -->
<div id="page-edu" class="page">
  <div class="phdr"><button class="bkbtn" onclick="goBack()">←</button><h2>Edukasi Kesehatan</h2></div>
  <div id="edu-list"></div>
  <div id="edu-det" style="display:none">
    <div style="padding:16px 16px 8px"><button class="btn btn-sec btn-sm" onclick="closeEdu()">← Kembali</button></div>
    <div class="padded" id="edu-det-c"></div>
  </div>
</div>

<!-- ═══ REPORT ═══ -->
<div id="page-report" class="page">
  <div class="phdr"><button class="bkbtn" onclick="goBack()">←</button><h2>Laporan &amp; Ekspor</h2></div>
  <div class="padded" id="rpt-c"></div>
</div>

<!-- ═══ PROFILE ═══ -->
<div id="page-profile" class="page">
  <div class="phdr"><button class="bkbtn" onclick="goBack()">←</button><h2>Profil Pengguna</h2></div>
  <div class="padded">
    <div class="card" style="text-align:center;padding:24px">
      <div class="pfav" id="pf-av"></div>
      <div style="font-size:20px;font-weight:800" id="pf-nm"></div>
      <div style="font-size:13px;color:var(--g3);margin-top:4px" id="pf-rl"></div>
    </div>
    <div class="card"><div class="card-title">Informasi Akun</div>
      <div class="inforow"><span class="infokey">NIK/Username</span><span class="infoval" id="pf-nik"></span></div>
      <div class="inforow"><span class="infokey">Role</span><span class="infoval" id="pf-rl2"></span></div>
      <div class="inforow"><span class="infokey">Puskesmas</span><span class="infoval" id="pf-pk"></span></div>
    </div>
    <div class="card" id="pf-admin-panel" style="display:none"><div class="card-title">👥 Manajemen Pengguna</div>
      <button class="btn btn-sec btn-sm" onclick="openUserMgmt()" style="margin-bottom:8px">Kelola Pengguna →</button>
      <button class="btn btn-sec btn-sm" onclick="openLogs()" style="margin-bottom:8px">📋 Log Aktivitas →</button>
    </div>
    <div class="card">
      <div class="card-title">🔒 Ganti Password</div>
      <div class="fg"><label class="fl">Password Lama</label><input id="p-old" class="fi" type="password" placeholder="Password lama"></div>
      <div class="fg"><label class="fl">Password Baru (min 6)</label><input id="p-new" class="fi" type="password" placeholder="Password baru"></div>
      <button class="btn btn-w btn-sm" onclick="changePwd()">Ganti Password</button>
    </div>
    <div class="card" style="background:var(--p-l);border-color:var(--p-m)">
      <div class="card-title" style="color:var(--p)">📚 Tentang Penelitian</div>
      <p style="font-size:12px;color:var(--p-d);line-height:1.8">"Development of Stunting Prediction Model for Stunting Prevention and Management in Toddlers in Central Lombok Regency: A Mixed Method Approach"<br><br><strong>Peneliti:</strong> Heri Bahtiar<br><strong>Institusi:</strong> University of Malaysia Sabah (UMS)<br><strong>Versi:</strong> 1.2.0 · Database: Terpusat (SQLite)</p>
    </div>
    <button class="btn btn-d" onclick="doLogout()">🚪 Keluar dari Aplikasi</button>
  </div>
</div>

<!-- ═══ USER MANAGEMENT ═══ -->
    <div id="page-users" class="page">
      <div class="phdr">
        <button class="bkbtn" onclick="goBack()">←</button>
        <h2>Kelola Kader &amp; Pengguna</h2>
        <button class="btn btn-p btn-sm" onclick="openAddUser()" style="white-space:nowrap">➕ Tambah Kader</button>
      </div>
      <div style="background:var(--white);border-bottom:1px solid var(--border);padding:8px 16px">
        <div style="display:flex;gap:8px;overflow-x:auto">
          <button class="chip on" onclick="filterUsers(this,'all')">👥 Semua</button>
          <button class="chip" onclick="filterUsers(this,'kader')">🧑‍⚕️ Kader</button>
          <button class="chip" onclick="filterUsers(this,'admin')">👑 Admin</button>
          <button class="chip" onclick="filterUsers(this,'active')">✅ Aktif</button>
          <button class="chip" onclick="filterUsers(this,'inactive')">🚫 Nonaktif</button>
        </div>
      </div>
      <div id="user-stats" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;padding:12px 16px;background:var(--white);border-bottom:1px solid var(--border)"></div>
      <div id="user-list"></div>
    </div>

    <!-- ═══ FORCE CHANGE PASSWORD ═══ -->
    <div id="page-forcepwd" class="page">
      <div style="background:linear-gradient(160deg,var(--w-l) 0%,var(--white) 60%);min-height:100%;display:flex;flex-direction:column;justify-content:center;padding:32px 24px">
        <div style="text-align:center;margin-bottom:24px">
          <div style="font-size:48px;margin-bottom:10px">🔐</div>
          <div style="font-size:20px;font-weight:700;color:var(--w)">Ganti Password Sekarang</div>
          <div style="font-size:13px;color:var(--g3);margin-top:6px;line-height:1.6">Administrator meminta Anda mengganti password<br>sebelum menggunakan aplikasi</div>
        </div>
        <div class="login-card">
          <div class="fg"><label class="fl">Password Lama (dari admin) <span class="req">*</span></label><input id="fp-old" class="fi" type="password" placeholder="Password yang diberikan admin"></div>
          <div class="fg"><label class="fl">Password Baru <span class="req">*</span></label><input id="fp-new" class="fi" type="password" placeholder="Min 6 karakter, mudah diingat"></div>
          <div class="fg"><label class="fl">Konfirmasi Password Baru <span class="req">*</span></label><input id="fp-confirm" class="fi" type="password" placeholder="Ketik ulang password baru"></div>
          <div id="fp-err" class="ibox ir" style="display:none"><span>⚠️</span><p id="fp-errtxt"></p></div>
          <button class="btn btn-p" onclick="doForcePwdChange()">🔐 Ganti Password & Masuk</button>
        </div>
      </div>
    </div>

    <!-- ═══ ACTIVITY LOG (Admin) ═══ -->
    <div id="page-logs" class="page">
      <div class="phdr"><button class="bkbtn" onclick="goBack()">←</button><h2>Log Aktivitas</h2></div>
      <div class="padded" id="logs-content"></div>
    </div>
  </div><!-- /screen -->
  <nav id="nav">
    <button class="nav-btn" id="nb-dashboard" onclick="goTo('dashboard')"><div class="nav-icon">🏠</div><span>Dashboard</span></button>
    <button class="nav-btn" id="nb-toddlers"  onclick="goTo('toddlers')"> <div class="nav-icon">👶</div><span>Balita</span></button>
    <button class="nav-btn" id="nb-detect"    onclick="goTo('detect')">   <div class="nav-icon">🔍</div><span>Deteksi</span></button>
    <button class="nav-btn" id="nb-growth"    onclick="goTo('growth')">   <div class="nav-icon">📈</div><span>Tumbuh</span></button>
    <button class="nav-btn" id="nb-profile"   onclick="goTo('profile')">  <div class="nav-icon">👤</div><span>Profil</span></button>
  </nav>
</div>

<!-- MODAL -->
<div id="modal-overlay" onclick="closeModal()">
  <div class="modal-box" onclick="event.stopPropagation()">
    <div class="modal-title"><span id="modal-title">—</span><button class="modal-close" onclick="closeModal()">✕</button></div>
    <div id="modal-body"></div>
  </div>
</div>

<div id="spinner"><div class="spin-circle"></div></div>
<div id="toast"></div>

<script>
// ═══════════════════════════════════════════════════════
// CONFIG — API Server URL
// Ubah BASE_URL ke IP server Anda:
// Contoh: var BASE_URL = 'http://192.168.1.100:5000';
// ═══════════════════════════════════════════════════════
var BASE_URL = '';  // auto: kosong = gunakan domain yang sama (bekerja untuk semua hosting)

// Tampilkan info server di login page
function showServerInfo(){
  var el=ge('server-url-info');
  if(el){
    var host=window.location.hostname;
    el.textContent='Server: '+host+BASE_URL+'/api/ping';
  }
}

// ═══════════════════════════════════════════════════════
// WHO TABLES
// ═══════════════════════════════════════════════════════
var WHO_B={0:49.9,1:54.7,2:58.4,3:61.4,4:63.9,5:65.9,6:67.6,7:69.2,8:70.6,9:72,10:73.3,11:74.5,12:75.7,15:79.1,18:82.3,21:85.1,24:87.8,27:90.3,30:92.7,33:95,36:96.1,39:97.8,42:99.9,45:102,48:103.3,51:104.9,54:106.5,57:108.2,59:110};
var WHO_G={0:49.1,1:53.7,2:57.1,3:59.8,4:62.1,5:64,6:65.7,7:67.3,8:68.7,9:70.1,10:71.5,11:72.8,12:74,15:77.5,18:80.7,21:83.7,24:86.4,27:89,30:91.4,33:93.7,36:95.1,39:97.3,42:99.4,45:101.5,48:102.7,51:104.3,54:105.9,57:107.5,59:109.4};

function getMedian(age,sex){
  var t=sex==='male'?WHO_B:WHO_G;
  var ages=Object.keys(t).map(Number).sort(function(a,b){return a-b});
  if(age<=ages[0]) return t[ages[0]];
  if(age>=ages[ages.length-1]) return t[ages[ages.length-1]];
  for(var i=0;i<ages.length-1;i++){
    if(age>=ages[i]&&age<=ages[i+1]){var r=(age-ages[i])/(ages[i+1]-ages[i]);return t[ages[i]]+r*(t[ages[i+1]]-t[ages[i]]);}
  }
  return t[ages[0]];
}
function calcZ(h,age,sex){if(!h||age<0||age>59) return null;var med=getMedian(age,sex);return parseFloat(((h-med)/(med*0.045)).toFixed(2));}
function zSt(z){
  if(z===null) return {st:'N/A',color:'#888',cls:'bn'};
  if(z<-3) return {st:'Severely Stunted',color:'#A32D2D',cls:'bss'};
  if(z<-2) return {st:'Stunted',color:'#854F0B',cls:'bs'};
  if(z>3)  return {st:'Tinggi',color:'#185FA5',cls:'bt'};
  return {st:'Normal',color:'#0F6E56',cls:'bn'};
}
function predRisk(inp){
  var C={ic:-3.102,ma:0.105,mh:-0.045,mi:0.321,ta:0.072,gm:0.41,fe:0.289,lz:0.205,tg:-0.35,sp:0.742,nb:0.28,ih:0.34,lb:0.42,nh:0.21};
  var mAge=inp.mAge||28,mHt=inp.mHt||150,aM=inp.aM||12,bW=inp.bW||3,sSc=(inp.sSc!==undefined)?inp.sSc:5;
  var logit=C.ic+C.ma*mAge+C.mh*mHt+C.mi*(inp.mIll?1:0)+C.ta*aM+C.gm*(inp.gender==='male'?1:0)+C.fe+(['none','sd','smp'].indexOf(inp.fEdu)>=0?1:0)+C.lz*(inp.zone==='lowlands'?1:0)+C.tg*(inp.toilet==='own'?1:0)+C.sp*(sSc<4?1:0)+C.nb*(inp.asi?0:1)+C.ih*(inp.inf?1:0)+C.lb*(bW<2.5?1:0)+C.nh*(inp.ctps?0:1);
  var prob=parseFloat((1/(1+Math.exp(-logit))).toFixed(4));
  var rl,rc,rb;
  if(prob>=0.65){rl='Tinggi';rc='#A32D2D';rb='#FCEBEB';}
  else if(prob>=0.4){rl='Sedang';rc='#854F0B';rb='#FAEEDA';}
  else{rl='Rendah';rc='#0F6E56';rb='#E1F5EE';}
  var facs=[];
  if(mHt<150) facs.push({l:'Tinggi ibu <150 cm',or:1.9,w:'h'});
  if(sSc<4) facs.push({l:'Sanitasi lingkungan buruk',or:2.1,w:'h'});
  if(inp.gender==='male') facs.push({l:'Jenis kelamin laki-laki',or:1.8,w:'h'});
  if(mAge>35) facs.push({l:'Usia ibu >35 tahun',or:1.6,w:'m'});
  if(bW<2.5) facs.push({l:'Berat lahir rendah (BBLR)',or:1.5,w:'h'});
  if(inp.mIll) facs.push({l:'Riwayat penyakit ibu',or:1.4,w:'m'});
  if(inp.inf) facs.push({l:'Riwayat infeksi berulang',or:1.4,w:'m'});
  if(['none','sd','smp'].indexOf(inp.fEdu)>=0) facs.push({l:'Pendidikan ayah ≤SMP',or:1.3,w:'m'});
  if(!inp.asi) facs.push({l:'Tidak ASI eksklusif',or:1.3,w:'m'});
  if(inp.toilet==='none') facs.push({l:'Tidak ada jamban',or:1.4,w:'m'});
  if(!inp.ctps) facs.push({l:'Tidak CTPS',or:1.2,w:'l'});
  var ivs;
  if(rl==='Tinggi') ivs=[{l:'Rujuk segera ke Puskesmas/dokter gizi',p:'c'},{l:'Pemberian Makanan Tambahan (PMT) segera',p:'h'},{l:'Perbaikan sanitasi dan sumber air bersih',p:'h'},{l:'Edukasi MP-ASI bergizi untuk ibu',p:'m'},{l:'Pemantauan intensif setiap 2 minggu',p:'h'}];
  else if(rl==='Sedang') ivs=[{l:'Konseling gizi dan MP-ASI',p:'h'},{l:'Kunjungan posyandu setiap bulan',p:'m'},{l:'Verifikasi kelengkapan imunisasi',p:'m'},{l:'Edukasi CTPS',p:'m'}];
  else ivs=[{l:'Pemantauan pertumbuhan rutin posyandu',p:'l'}];
  return {prob:prob,rl:rl,rc:rc,rb:rb,facs:facs,ivs:ivs};
}
function calcAge(bd){if(!bd) return 0;var b=new Date(bd),n=new Date();return Math.max(0,Math.min(59,(n.getFullYear()-b.getFullYear())*12+(n.getMonth()-b.getMonth())));}
function sanitScore(d){var s=0;if(d.water==='pam') s+=3;else if(d.water==='well'||d.water==='spring') s+=2;if(d.toilet==='own') s+=3;else if(d.toilet==='shared') s+=1;if(d.waste==='collected') s+=2;else if(d.waste==='pit') s+=1;if(d.floor==='tile'||d.floor==='cement') s+=1;if(d.ctps) s+=1;return Math.min(s,10);}

// ═══════════════════════════════════════════════════════
// API LAYER
// ═══════════════════════════════════════════════════════
var TOKEN = '';
var CU = null;
var PAGE_STACK = [];
var ZONE_F = 'all';
var TODDLERS_CACHE = [];
var DET_RES = null;
var DET_TOD = null;
var SEL_G = null;
var EDIT_TID = null;

function loadSaved(){
  try{var t=localStorage.getItem('sp_token');var u=localStorage.getItem('sp_user');if(t&&u){TOKEN=t;CU=JSON.parse(u);}}catch(e){}
}
function saveSess(token,user){TOKEN=token;CU=user;try{localStorage.setItem('sp_token',token);localStorage.setItem('sp_user',JSON.stringify(user));}catch(e){}}
function clearSess(){TOKEN='';CU=null;try{localStorage.removeItem('sp_token');localStorage.removeItem('sp_user');}catch(e){}}

function api(method,path,body,cb){
  var url=BASE_URL+'/api'+path;
  var xhr=new XMLHttpRequest();
  xhr.open(method,url,true);
  xhr.setRequestHeader('Content-Type','application/json');
  if(TOKEN) xhr.setRequestHeader('Authorization','Bearer '+TOKEN);
  xhr.onload=function(){
    try{var d=JSON.parse(xhr.responseText);cb(null,d);}
    catch(e){cb({error:'Parse error'},null);}
  };
  xhr.onerror=function(){cb({error:'Tidak bisa terhubung. Coba refresh halaman.'},null);};
  xhr.ontimeout=function(){cb({error:'Server lambat merespons ('+Math.round(xhr.timeout/1000)+'s). Coba lagi.'},null);};
  xhr.timeout=20000;
  if(body) xhr.send(JSON.stringify(body));
  else xhr.send();
}
function GET(p,cb){api('GET',p,null,cb);}
function POST(p,b,cb){api('POST',p,b,cb);}
function PUT(p,b,cb){api('PUT',p,b,cb);}
function DEL(p,cb){api('DELETE',p,null,cb);}

// ═══════════════════════════════════════════════════════
// UI HELPERS
// ═══════════════════════════════════════════════════════
function ge(id){return document.getElementById(id);}
function toast(msg,dur){var el=ge('toast');el.textContent=msg;el.className='show';clearTimeout(el._t);el._t=setTimeout(function(){el.className='';},dur||2800);}
function spin(show){ge('spinner').className=show?'show':'';}
function setConnStatus(online){
  var dot=ge('online-dot');var st=ge('conn-status');
  if(dot) dot.className=online?'on':'';
  if(st)  st.textContent=online?'● Terhubung ke server':'● Cek koneksi...';
}

// ═══════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════
function showPage(name){
  var pages=document.querySelectorAll('.page');
  for(var i=0;i<pages.length;i++) pages[i].classList.remove('active');
  var el=ge('page-'+name);if(el) el.classList.add('active');
  var scr=ge('screen');if(scr) scr.scrollTop=0;
  var btns=document.querySelectorAll('.nav-btn');
  for(var j=0;j<btns.length;j++) btns[j].classList.remove('active');
  var nb=ge('nb-'+name);if(nb) nb.classList.add('active');
}
function goTo(name){PAGE_STACK.push(name);showPage(name);onEnter(name);}
function goBack(){if(PAGE_STACK.length>1) PAGE_STACK.pop();var prev=PAGE_STACK[PAGE_STACK.length-1]||'dashboard';showPage(prev);onEnter(prev);}
function onEnter(name){
  if(name==='dashboard') rdDash();
  else if(name==='toddlers') renderList();
  else if(name==='detect') initDet();
  else if(name==='growth') initGrowth();
  else if(name==='qual') initQual();
  else if(name==='edu') rdEdu();
  else if(name==='report') rdReport();
  else if(name==='profile') rdProfile();
  else if(name==='users') rdUsers();
}

// MODAL
function openModal(title,bodyHtml){ge('modal-title').textContent=title;ge('modal-body').innerHTML=bodyHtml;ge('modal-overlay').className='show';}
function closeModal(){ge('modal-overlay').className='';}

// ═══════════════════════════════════════════════════════
// LOGIN
// ═══════════════════════════════════════════════════════
function fillD(r){
  var m={admin:['superadmin','admin123'],kader:['kader001','kader123'],peneliti:['1901234567890001','peneliti123']};
  ge('l-nik').value=m[r][0];
  ge('l-pwd').value=m[r][1];
  // Auto-login setelah isi form
  setTimeout(function(){doLogin();},100);
}
function togPwd(){var i=ge('l-pwd');i.type=i.type==='password'?'text':'password';}
function doLogin(){
  var nik=(ge('l-nik').value||'').trim();
  var pwd=(ge('l-pwd').value||'').trim();
  if(!nik||!pwd){toast('⚠️ Isi NIK dan password');return;}
  ge('conn-status').textContent='● Menghubungkan ke server...';
  spin(true);
  POST('/auth/login',{nik:nik,password:pwd},function(err,res){
    spin(false);
    if(err){
      var msg=err.error||'Gagal terhubung - cek koneksi internet';
      toast('❌ '+msg);
      ge('conn-status').textContent='● Tidak terhubung';
      return;
    }
    if(!res||!res.success){
      toast('❌ '+(res&&res.error?res.error:'NIK atau password salah'));
      return;
    }
    saveSess(res.data.token,res.data.user);
    setConnStatus(true);
    if(res.data.must_change_pwd){
      ge('nav').classList.remove('show');
      showForcePwdChange();
    } else {
      ge('nav').classList.add('show');
      PAGE_STACK=[];
      goTo('dashboard');
    }
  });
}
function doLogout(){
  if(!confirm('Yakin ingin keluar?')) return;
  clearSess();
  ge('nav').classList.remove('show');
  PAGE_STACK=[];
  showPage('login');
  setConnStatus(false);
}

// ═══════════════════════════════════════════════════════
// DASHBOARD
// ═══════════════════════════════════════════════════════
function rdDash(){
  if(!CU) return;
  var rl={admin:'Administrator',kader:'Kader Posyandu',researcher:'Peneliti'};
  ge('dname').textContent=CU.name;
  ge('drole').textContent=CU.puskesmas||rl[CU.role]||CU.role;
  // Show admin bar for admin role
  var adminBar=ge('d-admin-bar');
  if(adminBar) adminBar.style.display=(CU.role==='admin')?'block':'none';
  GET('/dashboard',function(err,res){
    if(err||!res.success) return;
    var d=res.data;
    ge('s-tot').textContent=d.total||0;
    var hi=0,me=0;
    for(var i=0;i<(d.by_risk||[]).length;i++){if(d.by_risk[i].risk_level==='Tinggi') hi=d.by_risk[i].n;else if(d.by_risk[i].risk_level==='Sedang') me=d.by_risk[i].n;}
    ge('s-hi').textContent=hi; ge('s-me').textContent=me;
    var ab=ge('d-alert');
    if(hi>0){ab.style.display='flex';ge('d-alert-txt').textContent=hi+' Balita Risiko Tinggi — Intervensi Segera!';}
    else ab.style.display='none';
    // zone bars
    var zl={hills:'⛰️ Bukit',lowlands:'🌾 Dataran Rendah',coastal:'🏖️ Pantai'};
    var zEl=ge('zone-bars');zEl.innerHTML='';
    for(var i=0;i<(d.by_zone||[]).length;i++){
      var z=d.by_zone[i];if(!z.total) continue;
      var pct=(z.stunted/z.total*100).toFixed(1);
      var col=pct>35?'var(--r)':pct>20?'var(--w)':'var(--p)';
      zEl.innerHTML+='<div class="barrow"><div class="barlbl"><span style="font-size:12px;font-weight:600;color:var(--g2)">'+(zl[z.zone]||z.zone)+'</span><span style="font-size:13px;font-weight:700;color:'+col+'">'+z.stunted+'/'+z.total+' ('+pct+'%)</span></div><div class="bartrack"><div class="barfill" style="width:'+Math.min(100,pct)+'%;background:'+col+'"></div></div></div>';
    }
    if(!d.by_zone||!d.by_zone.length) zEl.innerHTML='<p style="font-size:13px;color:var(--g3)">Belum ada data pengukuran</p>';
    // recent
    var bc={Tinggi:'bh',Sedang:'bm',Rendah:'bl'};
    var rEl=ge('recent-list');
    if(!d.recent_measurements||!d.recent_measurements.length){rEl.innerHTML='<p style="font-size:13px;color:var(--g3)">Belum ada data pengukuran</p>';return;}
    var html='';
    for(var i=0;i<Math.min(5,d.recent_measurements.length);i++){
      var m=d.recent_measurements[i];var cl=bc[m.risk_level]||'bl';
      html+='<div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">'
        +'<div style="width:36px;height:36px;border-radius:18px;background:var(--p-l);display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:800;color:var(--p);flex-shrink:0">'+(m.toddler_name||'?')[0]+'</div>'
        +'<div style="flex:1"><div style="font-size:13px;font-weight:700">'+(m.toddler_name||'—')+'</div>'
        +'<div style="font-size:11px;color:var(--g3)">'+m.measure_date+' · '+m.height_cm+' cm · '+(m.by_name||'—')+'</div></div>'
        +'<span class="badge '+cl+'">Risiko '+(m.risk_level||'Rendah')+'</span></div>';
    }
    rEl.innerHTML=html;
  });
}

// ═══════════════════════════════════════════════════════
// TODDLER LIST
// ═══════════════════════════════════════════════════════
function setZone(el,z){ZONE_F=z;var cs=document.querySelectorAll('.filterbar .chip');for(var i=0;i<cs.length;i++) cs[i].classList.remove('on');el.classList.add('on');renderList();}
function renderList(){
  var srch=(ge('t-srch').value||'').trim();
  var url='/toddlers?zone='+ZONE_F+(srch?'&search='+encodeURIComponent(srch):'');
  spin(true);
  GET(url,function(err,res){
    spin(false);
    var el=ge('tlist');
    if(err||!res.success){el.innerHTML='<div class="empty"><div style="font-size:48px">⚠️</div><div style="font-size:14px;font-weight:700;color:var(--r);margin-top:8px">'+(err?err.error:res.error)+'</div></div>';return;}
    TODDLERS_CACHE=res.data||[];
    if(!TODDLERS_CACHE.length){el.innerHTML='<div class="empty"><div style="font-size:48px;margin-bottom:12px">👶</div><div style="font-size:16px;font-weight:700;color:var(--g2);margin-bottom:6px">Belum ada balita</div><div style="font-size:13px;color:var(--g3)">Tap + untuk mendaftarkan balita baru</div></div>';return;}
    var zl={hills:'Bukit ⛰️',lowlands:'Dataran 🌾',coastal:'Pantai 🏖️'};
    var bc={Tinggi:'bh',Sedang:'bm',Rendah:'bl'};
    var html='';
    for(var i=0;i<TODDLERS_CACHE.length;i++){
      var t=TODDLERS_CACHE[i];var rl=t.last_risk||'Rendah';var cl=bc[rl]||'bl';
      var age=calcAge(t.birth_date);
      var htxt=t.last_height?'TB: '+t.last_height+' cm · '+t.last_status:'Belum diukur';
      html+='<div class="tcard" onclick="goDetTod('+t.id+')">'
        +'<div class="tav">'+t.name[0]+'</div>'
        +'<div style="flex:1;min-width:0">'
          +'<div style="display:flex;align-items:center;justify-content:space-between;gap:8px"><span class="tname">'+t.name+'</span><span class="badge '+cl+'">Risiko '+rl+'</span></div>'
          +'<div class="tmeta">'+(t.gender==='male'?'♂':'♀')+' · '+age+' bulan · '+(zl[t.zone]||t.zone)+' · '+(t.village||'—')+'</div>'
          +'<div class="tmeta">'+htxt+(t.visit_count?' · '+t.visit_count+'x kunjungan':'')+'</div>'
        +'</div>'
        +'<div class="iact">'
          +'<button class="ibtn" onclick="event.stopPropagation();openEditTod('+t.id+')" title="Edit">✏️</button>'
          +'<button class="ibtn" onclick="event.stopPropagation();goDetTod('+t.id+')" title="Deteksi">🔍</button>'
          +(CU&&(CU.role==='admin'||CU.role==='researcher')?'<button class="ibtn" onclick="event.stopPropagation();delTod('+t.id+',\\''+t.name+'\\')" title="Hapus">🗑️</button>':'')
        +'</div></div>';
    }
    el.innerHTML=html;
  });
}

function openEditTod(id){
  var t=null;for(var i=0;i<TODDLERS_CACHE.length;i++){if(TODDLERS_CACHE[i].id===id){t=TODDLERS_CACHE[i];break;}}
  if(!t) return;
  // Fetch full toddler data
  spin(true);
  GET('/toddlers/'+id,function(err,res){
    spin(false);
    if(err||!res.success){toast('❌ Gagal memuat data');return;}
    gAdd(res.data);
  });
}

function delTod(id,name){
  if(!confirm('Hapus data '+name+'? Semua pengukuran akan ikut terhapus.')) return;
  spin(true);
  DEL('/toddlers/'+id,function(err,res){
    spin(false);
    if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    toast('✅ Data balita dihapus');renderList();
  });
}

// ═══════════════════════════════════════════════════════
// FORM ADD/EDIT
// ═══════════════════════════════════════════════════════
function gAdd(t){
  EDIT_TID=t?t.id:null;
  ge('form-ttl').textContent=t?'Edit Balita':'Daftarkan Balita';
  ge('f-id').value=t?t.id:'';
  ge('f-name').value=t?t.name:'';
  ge('f-nik').value=t?(t.nik_balita||''):'';
  ge('f-bdate').value=t?t.birth_date:'';
  ge('f-gender').value=t?t.gender:'male';
  ge('f-bw').value=t?(t.birth_weight||''):'';
  ge('f-bh').value=t?(t.birth_height||''):'';
  ge('f-zone').value=t?t.zone:'lowlands';
  ge('f-village').value=t?(t.village||''):'';
  ge('f-mname').value=t?(t.mother_name||''):'';
  ge('f-mage').value=t?(t.mother_age||''):'';
  ge('f-mht').value=t?(t.mother_height||''):'';
  ge('f-medu').value=t?(t.mother_edu||'sma'):'sma';
  setCb('f-mil',t?t.mother_illness:0);
  setCb('f-ctps',t?(t.mother_ctps===undefined||t.mother_ctps===null?1:t.mother_ctps):1);
  ge('f-fedu').value=t?(t.father_edu||'sma'):'sma';
  ge('f-inc').value=t?(t.family_income||''):'';
  ge('f-mem').value=t?(t.family_members||''):'';
  ge('f-water').value=t?(t.water_source||'well'):'well';
  ge('f-toilet').value=t?(t.toilet_type||'own'):'own';
  ge('f-waste').value=t?(t.waste_mgmt||'collected'):'collected';
  ge('f-floor').value=t?(t.floor_type||'cement'):'cement';
  setCb('f-asi',t?t.excl_breastfeed:0);
  setCb('f-inf',t?t.infection_hist:0);
  updSanit();chkMH();
  PAGE_STACK.push('form');showPage('form');
}
function setCb(id,val){var v=parseInt(val)||0;ge(id).value=v;var b=ge(id+'-b');if(v){b.className='cbbox on';b.textContent='✓';}else{b.className='cbbox';b.textContent=' ';}}
function togCb(id){var cur=parseInt(ge(id).value)||0;setCb(id,cur?0:1);if(id==='f-ctps') updSanit();}
function chkMH(){var v=parseFloat(ge('f-mht').value||'999');ge('mht-warn').style.display=v<150?'flex':'none';}
function updSanit(){
  var sc=sanitScore({water:ge('f-water').value,toilet:ge('f-toilet').value,waste:ge('f-waste').value,floor:ge('f-floor').value,ctps:ge('f-ctps').value==='1'});
  ge('sanit-sc').textContent=sc;ge('sanit-box').className='ibox '+(sc<4?'ir':sc<7?'iy':'ig');
}
function saveTod(){
  var name=(ge('f-name').value||'').trim();
  var bd=ge('f-bdate').value;
  var mn=(ge('f-mname').value||'').trim();
  if(!name||!bd||!mn){toast('⚠️ Nama balita, tanggal lahir, dan nama ibu wajib diisi');return;}
  var sc=sanitScore({water:ge('f-water').value,toilet:ge('f-toilet').value,waste:ge('f-waste').value,floor:ge('f-floor').value,ctps:ge('f-ctps').value==='1'});
  var d={nik_balita:ge('f-nik').value,name:name,birth_date:bd,gender:ge('f-gender').value,
    birth_weight:parseFloat(ge('f-bw').value)||null,birth_height:parseFloat(ge('f-bh').value)||null,
    zone:ge('f-zone').value,village:ge('f-village').value,mother_name:mn,
    mother_age:parseInt(ge('f-mage').value)||null,mother_height:parseFloat(ge('f-mht').value)||null,
    mother_edu:ge('f-medu').value,mother_illness:parseInt(ge('f-mil').value)||0,mother_ctps:parseInt(ge('f-ctps').value)||0,
    father_edu:ge('f-fedu').value,family_income:parseInt(ge('f-inc').value)||null,family_members:parseInt(ge('f-mem').value)||null,
    water_source:ge('f-water').value,toilet_type:ge('f-toilet').value,waste_mgmt:ge('f-waste').value,floor_type:ge('f-floor').value,
    sanitation_score:sc,excl_breastfeed:parseInt(ge('f-asi').value)||0,infection_hist:parseInt(ge('f-inf').value)||0};
  spin(true);
  var fn=EDIT_TID?function(cb){PUT('/toddlers/'+EDIT_TID,d,cb);}:function(cb){POST('/toddlers',d,cb);};
  fn(function(err,res){
    spin(false);
    if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    toast('✅ Data balita berhasil disimpan!');
    var newId=EDIT_TID||(res.data&&res.data.id);
    setTimeout(function(){goBack();if(!EDIT_TID&&confirm('Lakukan pengukuran sekarang?')) goDetTod(newId);},400);
  });
}

// ═══════════════════════════════════════════════════════
// DETECTION
// ═══════════════════════════════════════════════════════
function initDet(){
  var today=new Date().toISOString().split('T')[0];
  var di=ge('d-date');if(di&&!di.value) di.value=today;
  ge('det-res').style.display='none';DET_RES=null;DET_TOD=null;
  ge('d-tod-info').style.display='none';
  // Fill toddler dropdown from cache or fetch
  var sel=ge('d-tod');sel.innerHTML='<option value="">— Hitung Cepat —</option>';
  var list=TODDLERS_CACHE.length?TODDLERS_CACHE:[];
  if(!list.length){
    GET('/toddlers',function(err,res){
      if(!err&&res.success){TODDLERS_CACHE=res.data||[];fillDetSel();}
    });
  } else fillDetSel();
}
function fillDetSel(){
  var sel=ge('d-tod');sel.innerHTML='<option value="">— Hitung Cepat —</option>';
  for(var i=0;i<TODDLERS_CACHE.length;i++){
    var t=TODDLERS_CACHE[i];var o=document.createElement('option');
    o.value=t.id;o.textContent=t.name+' ('+calcAge(t.birth_date)+' bln)';sel.appendChild(o);
  }
}
function goDetTod(id){PAGE_STACK.push('detect');showPage('detect');initDet();setTimeout(function(){ge('d-tod').value=id;onSelTod();},80);}
function onSelTod(){
  var id=parseInt(ge('d-tod').value)||0;
  var info=ge('d-tod-info');
  if(!id){info.style.display='none';DET_TOD=null;return;}
  var t=null;for(var i=0;i<TODDLERS_CACHE.length;i++){if(TODDLERS_CACHE[i].id===id){t=TODDLERS_CACHE[i];break;}}
  if(!t){
    GET('/toddlers/'+id,function(err,res){if(!err&&res.success){DET_TOD=res.data;showTodInfo(res.data);}});
  } else {DET_TOD=t;showTodInfo(t);}
}
function showTodInfo(t){
  var info=ge('d-tod-info');info.style.display='block';
  info.innerHTML='<div style="background:var(--p-l);border-radius:10px;padding:10px;display:flex;align-items:center;gap:10px">'
    +'<div style="width:40px;height:40px;border-radius:20px;background:var(--p);color:#fff;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:800;flex-shrink:0">'+t.name[0]+'</div>'
    +'<div><div style="font-size:14px;font-weight:700">'+t.name+'</div>'
    +'<div style="font-size:12px;color:var(--g3)">'+(t.gender==='male'?'♂':'♀')+' · '+calcAge(t.birth_date)+' bulan · '+t.zone+'</div>'
    +'<div style="font-size:12px;color:var(--g3)">Sanitasi: '+(t.sanitation_score||0)+'/10 · Ibu: '+(t.mother_height||'—')+' cm</div></div></div>';
}
function runDet(){
  var h=parseFloat(ge('d-ht').value||0);if(!h){toast('⚠️ Tinggi badan wajib diisi');return;}
  var t=DET_TOD;var age=t?calcAge(t.birth_date):12;var sex=t?t.gender:'male';
  var z=calcZ(h,age,sex);var zs=zSt(z);
  var inp=t?{mAge:t.mother_age,mHt:t.mother_height,mIll:t.mother_illness,aM:age,gender:t.gender,fEdu:t.father_edu,zone:t.zone,toilet:t.toilet_type,sSc:t.sanitation_score,asi:t.excl_breastfeed,inf:t.infection_hist,bW:t.birth_weight,ctps:t.mother_ctps}:{mAge:28,mHt:150,aM:age,gender:sex,sSc:5,asi:false,inf:false};
  var p=predRisk(inp);
  DET_RES={z:z,zs:zs,p:p,age:age,h:h};
  ge('det-res').style.display='block';
  var pp=Math.round(p.prob*100);
  var rc=ge('r-circle');rc.style.borderColor=p.rc;rc.style.backgroundColor=p.rb;
  ge('r-pct').style.color=p.rc;ge('r-pct').textContent=pp+'%';
  var rb=ge('r-rbadge');rb.textContent='Risiko '+p.rl;rb.style.background=p.rb;rb.style.color=p.rc;
  var sb=ge('r-sbadge');sb.className='badge '+zs.cls;sb.textContent=zs.st;
  ge('r-z').textContent=z!==null?z:'N/A';ge('r-z').style.color=zs.color;
  ge('r-age').textContent=age;ge('r-ht2').textContent=h;
  var fc=ge('fac-card'),fl=ge('fac-list');
  if(p.facs.length){
    fc.style.display='block';var wc={h:'var(--r)',m:'var(--w)',l:'var(--s)'};var fh='';
    for(var i=0;i<p.facs.length;i++){var f=p.facs[i];fh+='<div class="frow2"><div class="fdot" style="background:'+(wc[f.w]||'var(--g3)')+'"></div><span style="flex:1;font-size:13px">'+f.l+'</span><span style="font-size:12px;font-weight:700;color:var(--g3)">OR '+f.or+'</span></div>';}
    fl.innerHTML=fh;
  } else fc.style.display='none';
  var pc={c:'var(--r)',h:'var(--w)',m:'var(--s)',l:'var(--p)'};var ih='';
  for(var i=0;i<p.ivs.length;i++){var iv=p.ivs[i];ih+='<div class="irow"><div class="fdot" style="background:'+(pc[iv.p]||'var(--p)')+'"></div><span style="flex:1;font-size:13px;line-height:1.5">'+iv.l+'</span></div>';}
  ge('int-list').innerHTML=ih;
  ge('btn-save-m').style.display=t?'flex':'none';
  setTimeout(function(){ge('res-card').scrollIntoView({behavior:'smooth',block:'start'});},100);
}
function saveMeas(){
  var t=DET_TOD;var r=DET_RES;if(!t||!r){toast('Pilih balita terlebih dahulu');return;}
  var d={measure_date:ge('d-date').value||new Date().toISOString().split('T')[0],age_months:r.age,height_cm:r.h,
    weight_kg:parseFloat(ge('d-wt').value)||null,head_circ_cm:parseFloat(ge('d-hc').value)||null,arm_circ_cm:parseFloat(ge('d-arm').value)||null,
    z_score_hfa:r.z,stunting_status:r.zs.st,risk_level:r.p.rl,risk_prob:r.p.prob,
    notes:ge('d-notes').value,intervention:r.p.ivs[0].l};
  spin(true);
  POST('/toddlers/'+t.id+'/measurements',d,function(err,res){
    spin(false);
    if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    toast('✅ Hasil pengukuran disimpan ke server!');
    ge('d-ht').value='';ge('d-wt').value='';ge('det-res').style.display='none';DET_RES=null;
    // refresh toddlers cache
    GET('/toddlers',function(e2,r2){if(!e2&&r2.success) TODDLERS_CACHE=r2.data||[];});
  });
}

// ═══════════════════════════════════════════════════════
// GROWTH
// ═══════════════════════════════════════════════════════
var G_MEAS_CACHE=[];
function initGrowth(){
  var chips=ge('g-chips');chips.innerHTML='';
  var list=TODDLERS_CACHE.length?TODDLERS_CACHE:[];
  if(!list.length){
    GET('/toddlers',function(err,res){if(!err&&res.success){TODDLERS_CACHE=res.data||[];buildGrowthChips();}});
  } else buildGrowthChips();
}
function buildGrowthChips(){
  var chips=ge('g-chips');chips.innerHTML='';
  var list=TODDLERS_CACHE;
  if(!SEL_G&&list.length) SEL_G=list[0].id;
  for(var i=0;i<list.length;i++){
    var t=list[i];
    (function(tod){
      var btn=document.createElement('button');
      btn.className='chip'+(SEL_G===tod.id?' on':'');
      btn.textContent=tod.name;
      btn.onclick=function(){SEL_G=tod.id;var cs=document.querySelectorAll('#g-chips .chip');for(var j=0;j<cs.length;j++) cs[j].classList.remove('on');btn.classList.add('on');rdGrowth();};
      chips.appendChild(btn);
    })(t);
  }
  rdGrowth();
}
function rdGrowth(){
  var t=null;for(var i=0;i<TODDLERS_CACHE.length;i++){if(TODDLERS_CACHE[i].id===SEL_G){t=TODDLERS_CACHE[i];break;}}
  var gc=ge('g-content');
  if(!t){gc.innerHTML='<div class="empty"><div style="font-size:48px">📊</div><div style="font-size:16px;font-weight:700;color:var(--g2);margin-top:12px">Pilih balita di atas</div></div>';return;}
  gc.innerHTML='<div style="font-size:13px;color:var(--g3);text-align:center;padding:20px">Memuat data...</div>';
  spin(true);
  GET('/toddlers/'+t.id+'/measurements',function(err,res){
    spin(false);
    if(err||!res.success){gc.innerHTML='<div style="color:var(--r);padding:20px;text-align:center">'+(err?err.error:res.error)+'</div>';return;}
    var ms=res.data||[];
    ms.sort(function(a,b){return a.measure_date.localeCompare(b.measure_date)});
    G_MEAS_CACHE=ms;
    var age=calcAge(t.birth_date);
    var last=ms.length?ms[ms.length-1]:null;
    var lz=last?(last.z_score_hfa!==null&&last.z_score_hfa!==undefined?last.z_score_hfa:calcZ(last.height_cm,last.age_months,t.gender)):null;
    var lst=zSt(lz);var bc={Tinggi:'bh',Sedang:'bm',Rendah:'bl'};var rl=last?last.risk_level:'Rendah';
    gc.innerHTML='';
    // header
    var hc=document.createElement('div');hc.className='card';
    hc.innerHTML='<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">'
      +'<div style="width:50px;height:50px;border-radius:25px;background:var(--p-l);display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:800;color:var(--p)">'+t.name[0]+'</div>'
      +'<div style="flex:1"><div style="font-size:16px;font-weight:700">'+t.name+'</div><div style="font-size:12px;color:var(--g3)">'+(t.gender==='male'?'♂':'♀')+' · '+age+' bulan · '+t.zone+'</div></div>'
      +'<span class="badge '+(bc[rl]||'bl')+'">Risiko '+rl+'</span></div>'
      +'<div class="zgrid">'
      +'<div class="zbox"><div class="zval">'+(!last?'—':last.height_cm)+'</div><div class="zlbl">Tinggi (cm)</div></div>'
      +'<div class="zbox"><div class="zval" style="color:'+lst.color+'">'+(lz!==null&&lz!==undefined?lz:'—')+'</div><div class="zlbl">Z-Score TB/U</div></div>'
      +'<div class="zbox"><div class="zval">'+ms.length+'x</div><div class="zlbl">Kunjungan</div></div>'
      +'</div><div style="margin-top:10px"><span class="badge '+lst.cls+'">'+lst.st+'</span></div>';
    gc.appendChild(hc);
    // chart
    var cc=document.createElement('div');cc.className='card';
    cc.innerHTML='<div class="card-title">📈 Grafik Pertumbuhan TB/U (WHO)</div>'
      +'<div class="cwrap">'+drawChart(ms,t.gender)+'</div>'
      +'<div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:10px;font-size:11px">'
      +'<span style="color:var(--p)">— Median WHO</span><span style="color:var(--w)">-- -2 SD</span><span style="color:var(--r)">-- -3 SD</span></div>';
    gc.appendChild(cc);
    var ab=document.createElement('button');ab.className='btn btn-p';ab.textContent='+ Pengukuran Baru';ab.style.marginBottom='12px';
    (function(tid){ab.onclick=function(){goDetTod(tid);};})(t.id);gc.appendChild(ab);
    if(ms.length){
      var hc2=document.createElement('div');hc2.className='card';
      var rms=ms.slice().reverse();var hh='<div class="card-title">📋 Riwayat Pengukuran</div>';
      for(var i=0;i<rms.length;i++){
        var m=rms[i];var mz=m.z_score_hfa!==null&&m.z_score_hfa!==undefined?m.z_score_hfa:calcZ(m.height_cm,m.age_months,t.gender);
        var mst=zSt(mz);var mrl=m.risk_level||'Rendah';var mcl=bc[mrl]||'bl';
        hh+='<div class="hrow"><div style="flex:1">'
          +'<div style="font-size:13px;font-weight:700">'+m.measure_date+' — Usia '+m.age_months+' bulan</div>'
          +'<div style="font-size:12px;color:var(--g3)">TB: '+m.height_cm+' cm'+(m.weight_kg?' · BB: '+m.weight_kg+' kg':'')+' · Z: '+(mz!==null&&mz!==undefined?mz:'—')+(m.measured_by_name?' · '+m.measured_by_name:'')+'</div>'
          +(m.notes?'<div style="font-size:11px;color:var(--g3);margin-top:2px">'+m.notes+'</div>':'')
          +'</div><div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">'
          +'<span class="badge '+mcl+'">Risiko '+mrl+'</span><span class="badge '+mst.cls+'">'+mst.st+'</span></div></div>';
      }
      hc2.innerHTML=hh;gc.appendChild(hc2);
    }
  });
}
function drawChart(ms,sex){
  var W=340,H=200,PL=38,PR=16,PT=12,PB=32;
  var cW=W-PL-PR,cH=H-PT-PB,maxA=59,minH=40,maxH=120;
  function xS(a){return(a/maxA)*cW+PL;}function yS(h){return cH-((h-minH)/(maxH-minH))*cH+PT;}
  var t=sex==='male'?WHO_B:WHO_G;var ages=[0,6,12,18,24,30,36,42,48,54,59];
  var med='',m2='',m3='';
  for(var i=0;i<ages.length;i++){var a=ages[i];var v=t[a]||70;
    med+=(i?'L':'M')+xS(a).toFixed(1)+','+yS(v).toFixed(1)+' ';
    m2+=(i?'L':'M')+xS(a).toFixed(1)+','+yS(v*0.91).toFixed(1)+' ';
    m3+=(i?'L':'M')+xS(a).toFixed(1)+','+yS(v*0.865).toFixed(1)+' ';
  }
  var grid='';for(var i=0;i<ages.length;i++){var a=ages[i];grid+='<line x1="'+xS(a)+'" y1="'+PT+'" x2="'+xS(a)+'" y2="'+(H-PB)+'" stroke="#E5E5E3" stroke-width="0.5"/><text x="'+xS(a)+'" y="'+(H-PB+14)+'" text-anchor="middle" font-size="9" fill="#888">'+a+'</text>';}
  var hls='';var hv=[50,60,70,80,90,100,110];for(var i=0;i<hv.length;i++){hls+='<line x1="'+PL+'" y1="'+yS(hv[i])+'" x2="'+(W-PR)+'" y2="'+yS(hv[i])+'" stroke="#E5E5E3" stroke-width="0.5"/><text x="'+(PL-4)+'" y="'+(yS(hv[i])+4)+'" text-anchor="end" font-size="9" fill="#888">'+hv[i]+'</text>';}
  var dots='';
  for(var i=0;i<ms.length;i++){
    var m=ms[i];if(!m.height_cm||m.age_months>59) continue;
    var cx=xS(Math.min(59,m.age_months)),cy=yS(m.height_cm);
    var mz=m.z_score_hfa!==null&&m.z_score_hfa!==undefined?m.z_score_hfa:calcZ(m.height_cm,m.age_months,sex);
    var col=zSt(mz).color;
    if(i>0&&ms[i-1].height_cm) dots+='<line x1="'+xS(ms[i-1].age_months||0)+'" y1="'+yS(ms[i-1].height_cm)+'" x2="'+cx+'" y2="'+cy+'" stroke="var(--p)" stroke-width="1.5"/>';
    dots+='<circle cx="'+cx+'" cy="'+cy+'" r="5" fill="'+col+'" stroke="#fff" stroke-width="1.5"/>';
    if(i===ms.length-1) dots+='<text x="'+cx+'" y="'+(cy-9)+'" text-anchor="middle" font-size="9" fill="'+col+'">'+m.height_cm+'</text>';
  }
  return '<svg width="'+W+'" height="'+H+'" xmlns="http://www.w3.org/2000/svg" style="overflow:visible;display:block">'+hls+grid+'<path d="'+med.trim()+'" stroke="var(--p)" stroke-width="1.5" fill="none" stroke-dasharray="5,3"/><path d="'+m2.trim()+'" stroke="var(--w)" stroke-width="1" fill="none" stroke-dasharray="4,2"/><path d="'+m3.trim()+'" stroke="var(--r)" stroke-width="1" fill="none" stroke-dasharray="4,2"/>'+dots+'<text x="'+(W/2)+'" y="'+H+'" text-anchor="middle" font-size="9" fill="#888">Usia (bulan)</text></svg>';
}

// ═══════════════════════════════════════════════════════
// QUALITATIVE
// ═══════════════════════════════════════════════════════
var QTAB=0;
var RADIO_VALS={};
function initQual(){
  ge('q-date').value=new Date().toISOString().split('T')[0];
  var sel=ge('q-tod');sel.innerHTML='<option value="">— Tidak terkait —</option>';
  var list=TODDLERS_CACHE.length?TODDLERS_CACHE:[];
  for(var i=0;i<list.length;i++){var t=list[i];var o=document.createElement('option');o.value=t.id;o.textContent=t.name;sel.appendChild(o);}
  RADIO_VALS={};
  var rData={'r-taboo':['Tidak ada pantangan','Ada pantangan ringan','Banyak pantangan adat'],'r-decision':['Ibu sendiri','Suami','Nenek/keluarga besar','Tokoh adat/agama'],'r-posyandu':['Setiap bulan (rutin)','Setiap 2-3 bulan','Jarang / hanya jika sakit','Tidak pernah'],'r-water2':['Sangat bersih dan aman','Cukup bersih','Kurang bersih','Tidak tahu'],'r-toilet2':['Selalu menggunakan jamban','Kadang BAB sembarangan','Sering BAB sembarangan']};
  for(var gId in rData){
    var el=ge(gId);if(!el) continue;var opts=rData[gId];var html='';
    for(var i=0;i<opts.length;i++){html+='<div class="ropt" id="ropt-'+gId+'-'+i+'" data-gid="'+gId+'" data-val="'+opts[i]+'" onclick="selRad(this)">'+'<div class="rcirc"><div class="rinn"></div></div><span style="font-size:13px;color:var(--g1)">'+opts[i]+'</span></div>';}
    el.innerHTML=html;
  }
}
function selRad(el){
  var gId=el.getAttribute('data-gid');var val=el.getAttribute('data-val');RADIO_VALS[gId]=val;
  var opts=document.querySelectorAll('[data-gid="'+gId+'"]');
  for(var i=0;i<opts.length;i++){opts[i].classList.remove('sel');opts[i].querySelector('.rcirc').classList.remove('sel');opts[i].querySelector('.rinn').style.display='none';}
  el.classList.add('sel');el.querySelector('.rcirc').classList.add('sel');el.querySelector('.rinn').style.display='block';
}
function setQT(n,el){QTAB=n;for(var i=0;i<4;i++){var s=ge('qs-'+i);if(s) s.style.display=i===n?'block':'none';}var bs=document.querySelectorAll('.qtbar .chip');for(var i=0;i<bs.length;i++) bs[i].classList.remove('on');el.classList.add('on');}
function saveQual(){
  var code=(ge('q-code').value||'').trim();var date=ge('q-date').value;
  if(!code||!date){toast('⚠️ Kode responden dan tanggal wajib diisi');return;}
  var d={toddler_id:parseInt(ge('q-tod').value)||null,respondent_code:code,interview_date:date,
    interview_type:ge('q-type').value,sentiment:ge('q-sent').value,theme_codes:ge('q-themes').value,
    food_taboo:RADIO_VALS['r-taboo']||'',decision_maker:RADIO_VALS['r-decision']||'',
    breastfeed_knowledge:ge('q-ak').value==='1',stunting_knowledge:ge('q-sk').value,
    posyandu_freq:RADIO_VALS['r-posyandu']||'',health_barriers:ge('q-barriers').value,
    community_practices:ge('q-comm').value,cultural_beliefs:ge('q-beliefs').value,
    water_src_qual:RADIO_VALS['r-water2']||'',toilet_usage:RADIO_VALS['r-toilet2']||'',
    mpasi_practice:ge('q-mpasi').value,verbatim_notes:ge('q-verb').value};
  spin(true);
  POST('/qualitative',d,function(err,res){
    spin(false);
    if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    toast('✅ Data wawancara disimpan ke server!');
    ge('q-code').value='';ge('q-verb').value='';ge('q-sk').value='';RADIO_VALS={};
    initQual();
  });
}

// ═══════════════════════════════════════════════════════
// EDUCATION
// ═══════════════════════════════════════════════════════
var ARTS=[
  {id:'e1',ic:'🌱',ti:'1000 Hari Pertama Kehidupan (HPK)',cat:'Dasar Stunting',col:'var(--p)',bg:'var(--p-l)',body:'Periode 1000 HPK (kehamilan hingga usia 2 tahun) adalah waktu paling kritis tumbuh kembang anak. Otak berkembang 90% dari ukuran dewasa. Kekurangan gizi berdampak permanen.\\n\\nIntervensi sejak ibu hamil:\\n• Konsumsi TTD ≥90 tablet\\n• ANC minimal 6 kali\\n• Makan makanan bergizi beragam\\n• Hindari rokok dan alkohol'},
  {id:'e2',ic:'🤱',ti:'ASI Eksklusif 6 Bulan',cat:'Nutrisi Bayi',col:'var(--s)',bg:'var(--s-l)',body:'WHO merekomendasikan ASI eksklusif 6 bulan pertama.\\n\\nManfaat:\\n• Semua nutrisi yang dibutuhkan bayi\\n• Antibodi alami melindungi infeksi\\n• Mengurangi risiko stunting 1.5x lebih rendah\\n\\nIMD: Susui bayi dalam 1 jam pertama kelahiran. Kolostrum sangat kaya antibodi.'},
  {id:'e3',ic:'🥗',ti:'MP-ASI Bergizi Seimbang',cat:'Nutrisi Anak',col:'#3B6D11',bg:'#EAF3DE',body:'Mulai usia 6 bulan berikan MP-ASI bergizi sambil lanjutkan ASI.\\n\\nPrinsip:\\n• BERAGAM — karbohidrat, protein, lemak, sayur, buah\\n• BERGIZI — utamakan protein hewani (ikan, telur, daging)\\n• AMAN — dimasak bersih\\n\\n6-8 bln: bubur saring · 9-11 bln: nasi tim · 12+ bln: makanan keluarga'},
  {id:'e4',ic:'💧',ti:'WASH — Air, Sanitasi & Kebersihan',cat:'Sanitasi Lingkungan',col:'var(--s)',bg:'var(--s-l)',body:'Sanitasi buruk adalah prediktor stunting TERKUAT (OR=2.1) di Lombok Tengah.\\n\\n5 Pilar STBM:\\n1. Stop BAB Sembarangan\\n2. Cuci Tangan Pakai Sabun (CTPS)\\n3. Pengelolaan air minum aman\\n4. Pengelolaan sampah\\n5. Pengelolaan limbah cair\\n\\nCTPS mengurangi diare 48% dan pneumonia 23%.'},
  {id:'e5',ic:'💉',ti:'Imunisasi Dasar Lengkap',cat:'Kesehatan Anak',col:'var(--w)',bg:'var(--w-l)',body:'Imunisasi mencegah infeksi yang memperburuk gizi dan menyebabkan stunting.\\n\\nJadwal (Kemenkes 2023):\\n• Lahir: HB0, Polio 0\\n• 1 bln: BCG, Polio 1\\n• 2 bln: DPT-HB-Hib 1, PCV 1\\n• 3 bln: DPT-HB-Hib 2\\n• 4 bln: DPT-HB-Hib 3, IPV\\n• 9 bln: MR\\n• 18 bln: Booster\\n\\nGRATIS di Posyandu dan Puskesmas.'},
  {id:'e6',ic:'🤰',ti:'ANC & Gizi Ibu Hamil',cat:'Kesehatan Maternal',col:'var(--r)',bg:'var(--r-l)',body:'Tinggi ibu <150 cm meningkatkan risiko stunting 1.9x.\\n\\nANC minimal 6 kali:\\n• Trimester 1: 2 kunjungan\\n• Trimester 2: 1 kunjungan\\n• Trimester 3: 3 kunjungan\\n\\nSuplemen wajib: TTD ≥90 tablet · Asam folat 400mcg/hari\\n\\nTanda bahaya: perdarahan, sesak napas, bengkak wajah/tangan, kejang, gerakan janin berkurang → segera ke Puskesmas'}
];
function rdEdu(){
  ge('edu-det').style.display='none';var el=ge('edu-list');el.style.display='block';var html='';
  for(var i=0;i<ARTS.length;i++){var a=ARTS[i];
    html+='<div class="artcard" onclick="openArt(\\''+a.id+'\\')"><div class="articon" style="background:'+a.bg+'">'+a.ic+'</div><div style="flex:1;min-width:0"><div style="font-size:11px;font-weight:700;color:'+a.col+'">'+a.cat+'</div><div style="font-size:14px;font-weight:700;color:var(--g1);margin-top:2px">'+a.ti+'</div><div style="font-size:12px;color:var(--g3);margin-top:3px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">'+a.body.split('\\n')[0]+'</div></div><span style="color:var(--g4);font-size:18px">›</span></div>';
  }
  el.innerHTML=html;
}
function openArt(id){
  var a=null;for(var i=0;i<ARTS.length;i++){if(ARTS[i].id===id){a=ARTS[i];break;}}if(!a) return;
  ge('edu-list').style.display='none';ge('edu-det').style.display='block';
  var lines=a.body.split('\\n');var bh='';for(var i=0;i<lines.length;i++) bh+=lines[i]+'<br>';
  ge('edu-det-c').innerHTML='<div style="background:'+a.bg+';border-radius:14px;padding:24px;text-align:center;margin-bottom:16px"><div style="font-size:48px;margin-bottom:10px">'+a.ic+'</div><div style="font-size:11px;font-weight:700;color:'+a.col+';text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">'+a.cat+'</div><div style="font-size:20px;font-weight:800;color:'+a.col+'">'+a.ti+'</div></div><div class="card"><p style="font-size:14px;color:var(--g2);line-height:1.8">'+bh+'</p></div>';
}
function closeEdu(){ge('edu-det').style.display='none';ge('edu-list').style.display='block';}

// ═══════════════════════════════════════════════════════
// REPORT
// ═══════════════════════════════════════════════════════
function rdReport(){
  ge('rpt-c').innerHTML='<div style="color:var(--g3);font-size:13px;text-align:center;padding:20px">Memuat laporan...</div>';
  spin(true);
  GET('/dashboard',function(err,res){
    spin(false);
    if(err||!res.success){ge('rpt-c').innerHTML='<div class="ibox ir"><span>❌</span><p>'+(err?err.error:res.error)+'</p></div>';return;}
    var d=res.data;
    var hi=0,me=0,lo=0;
    for(var i=0;i<(d.by_risk||[]).length;i++){if(d.by_risk[i].risk_level==='Tinggi') hi=d.by_risk[i].n;else if(d.by_risk[i].risk_level==='Sedang') me=d.by_risk[i].n;else lo=d.by_risk[i].n;}
    var total=d.total||0;var prev=total>0?((hi+me)/total*100).toFixed(1):'0';var pCol=parseFloat(prev)>30?'var(--r)':parseFloat(prev)>20?'var(--w)':'var(--p)';
    var zones=[{k:'hills',l:'Bukit ⛰️'},{k:'lowlands',l:'Dataran Rendah 🌾'},{k:'coastal',l:'Pantai 🏖️'}];
    var zHtml='';
    for(var i=0;i<(d.by_zone||[]).length;i++){
      var z=d.by_zone[i];if(!z.total) continue;var pct=(z.stunted/z.total*100).toFixed(1);var col=pct>35?'var(--r)':pct>20?'var(--w)':'var(--p)';
      var zLabel={hills:'Bukit ⛰️',lowlands:'Dataran Rendah 🌾',coastal:'Pantai 🏖️'};
      zHtml+='<div class="pbar-hdr"><span style="font-size:12px;font-weight:600;color:var(--g2)">'+(zLabel[z.zone]||z.zone)+'</span><span style="font-size:13px;font-weight:700;color:'+col+'">'+z.stunted+'/'+z.total+' ('+pct+'%)</span></div><div class="pbar-track"><div class="pbar-fill" style="width:'+Math.min(100,pct)+'%;background:'+col+'"></div></div>';
    }
    ge('rpt-c').innerHTML=
      '<div class="ibox ib"><span>📋</span><p>Database terpusat · '+total+' balita · '+d.qual_count+' wawancara kualitatif</p></div>'
      +'<div class="card"><div class="card-title">📊 Ringkasan Data</div>'
      +'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:14px">'
      +'<div class="sbox" style="background:var(--p-l)"><div class="sval" style="color:var(--p)">'+total+'</div><div class="slbl" style="color:var(--p)">Balita</div></div>'
      +'<div class="sbox" style="background:var(--r-l)"><div class="sval" style="color:var(--r)">'+hi+'</div><div class="slbl" style="color:var(--r)">Risiko Tinggi</div></div>'
      +'<div class="sbox" style="background:var(--s-l)"><div class="sval" style="color:var(--s)">'+d.qual_count+'</div><div class="slbl" style="color:var(--s)">Data Kuali.</div></div></div>'
      +'<div class="pbar-hdr"><span style="font-size:12px;font-weight:600;color:var(--g2)">Prevalensi Stunting</span><span style="font-size:13px;font-weight:700;color:'+pCol+'">'+prev+'%</span></div>'
      +'<div class="pbar-track"><div class="pbar-fill" style="width:'+Math.min(100,parseFloat(prev))+'%;background:'+pCol+'"></div></div>'
      +'<div style="font-size:11px;color:var(--g3);margin-top:4px">Target nasional: ≤14% (RPJMN 2024)</div></div>'
      +'<div class="card"><div class="card-title">🗺️ Prevalensi per Zona</div>'+zHtml+'</div>'
      +'<div class="card"><div class="card-title">🔬 Validasi Model</div>'
      +'<div class="mrow"><span class="mkey">ROC-AUC</span><span class="mval">0.87</span><span style="margin-left:8px">✅</span></div>'
      +'<div class="mrow"><span class="mkey">Sensitivitas</span><span class="mval">82.4%</span><span style="margin-left:8px">✅</span></div>'
      +'<div class="mrow"><span class="mkey">Spesifisitas</span><span class="mval">79.1%</span><span style="margin-left:8px">✅</span></div>'
      +'<div class="mrow"><span class="mkey">PPV</span><span class="mval">74.3%</span></div></div>'
      +(CU&&(CU.role==='admin'||CU.role==='researcher')?
        '<div class="card"><div class="card-title">📤 Ekspor Data</div><button class="btn btn-p" onclick="expData()" style="margin-bottom:8px">📋 Ekspor Semua Data (JSON)</button><p style="font-size:12px;color:var(--g3)">Export dari server ke JSON untuk analisis SPSS/R/Python.</p></div>':'')+
      '<div class="card" style="background:var(--p-l);border-color:var(--p-m)"><div class="card-title" style="color:var(--p)">📚 Referensi</div><p style="font-size:12px;color:var(--p-d);line-height:1.8">Heri Bahtiar (2025). Development of Stunting Prediction Model for Stunting Prevention and Management in Toddlers in Central Lombok Regency. University of Malaysia Sabah.<br><br>Multiple Logistic Regression · Thematic Analysis · WHO Growth Standards 2006</p></div>';
  });
}
function expData(){
  spin(true);
  GET('/export',function(err,res){
    spin(false);
    if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    var json=JSON.stringify(res.data,null,2);
    try{
      var blob=new Blob([json],{type:'application/json'});
      var url=URL.createObjectURL(blob);
      var a=document.createElement('a');a.href=url;a.download='StuntingPred_'+new Date().toISOString().split('T')[0]+'.json';
      document.body.appendChild(a);a.click();document.body.removeChild(a);URL.revokeObjectURL(url);
    }catch(e){console.log(json);}
    toast('✅ Data berhasil diekspor!');
  });
}

// ═══════════════════════════════════════════════════════
// PROFILE + CHANGE PASSWORD
// ═══════════════════════════════════════════════════════
function rdProfile(){
  if(!CU) return;
  var rl={admin:'Administrator',kader:'Kader Posyandu',researcher:'Peneliti'};
  ge('pf-av').textContent=CU.name.slice(0,2).toUpperCase();
  ge('pf-nm').textContent=CU.name;ge('pf-rl').textContent=rl[CU.role]||CU.role;
  ge('pf-nik').textContent=CU.nik;ge('pf-rl2').textContent=rl[CU.role]||CU.role;ge('pf-pk').textContent=CU.puskesmas||'—';
  ge('p-old').value='';ge('p-new').value='';
  ge('pf-admin-panel').style.display=(CU.role==='admin')?'block':'none';
}
function changePwd(){
  var old=(ge('p-old').value||'').trim();var nw=(ge('p-new').value||'').trim();
  if(!old||!nw||nw.length<6){toast('⚠️ Password lama dan baru (min 6 karakter) wajib diisi');return;}
  spin(true);
  POST('/auth/change-password',{old_password:old,new_password:nw},function(err,res){
    spin(false);
    if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    toast('✅ Password berhasil diubah!');ge('p-old').value='';ge('p-new').value='';
  });
}

// ═══════════════════════════════════════════════════════
// USER MANAGEMENT (Admin only)
// ═══════════════════════════════════════════════════════
var USERS_CACHE=[];
var USER_FILTER='all';
function openUserMgmt(){PAGE_STACK.push('users');showPage('users');rdUsers();}
function filterUsers(el,f){
  USER_FILTER=f;
  var chips=document.querySelectorAll('#page-users .chip');
  for(var i=0;i<chips.length;i++) chips[i].classList.remove('on');
  el.classList.add('on');
  renderUserList();
}
function rdUsers(){
  spin(true);
  GET('/users',function(err,res){
    spin(false);
    if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    USERS_CACHE=res.data||[];
    // Stats
    var total=USERS_CACHE.length;
    var kaders=USERS_CACHE.filter(function(u){return u.role==='kader';}).length;
    var active=USERS_CACHE.filter(function(u){return u.active;}).length;
    var stats=ge('user-stats');
    if(stats) stats.innerHTML=
      '<div style="background:var(--p-l);border-radius:10px;padding:10px;text-align:center"><div style="font-size:22px;font-weight:800;color:var(--p)">'+total+'</div><div style="font-size:11px;color:var(--p)">Total User</div></div>'
      +'<div style="background:var(--s-l);border-radius:10px;padding:10px;text-align:center"><div style="font-size:22px;font-weight:800;color:var(--s)">'+kaders+'</div><div style="font-size:11px;color:var(--s)">Kader</div></div>'
      +'<div style="background:var(--p-l);border-radius:10px;padding:10px;text-align:center"><div style="font-size:22px;font-weight:800;color:var(--p)">'+active+'</div><div style="font-size:11px;color:var(--p)">Aktif</div></div>';
    renderUserList();
  });
}
function renderUserList(){
  var el=ge('user-list');
  var rl={admin:'Administrator',kader:'Kader Posyandu',researcher:'Peneliti'};
  var rlc={admin:'#A32D2D',kader:'#0F6E56',researcher:'#185FA5'};
  var rlbg={admin:'var(--r-l)',kader:'var(--p-l)',researcher:'var(--s-l)'};
  var zl={all:'Semua zona',hills:'Bukit ⛰️',lowlands:'Dataran 🌾',coastal:'Pantai 🏖️'};
  
  var list=USERS_CACHE.filter(function(u){
    if(USER_FILTER==='kader') return u.role==='kader';
    if(USER_FILTER==='admin') return u.role==='admin'||u.role==='researcher';
    if(USER_FILTER==='active') return u.active===1||u.active===true;
    if(USER_FILTER==='inactive') return !u.active;
    return true;
  });
  
  if(!list.length){
    el.innerHTML='<div class="empty"><div style="font-size:48px">👥</div><div style="font-size:15px;font-weight:700;color:var(--g2);margin-top:12px">Tidak ada pengguna</div></div>';
    return;
  }
  
  var html='';
  for(var i=0;i<list.length;i++){
    var u=list[i];
    var rLabel=rl[u.role]||u.role;
    var rColor=rlc[u.role]||'var(--p)';
    var rBg=rlbg[u.role]||'var(--p-l)';
    var isActive=u.active===1||u.active===true;
    var mustChg=u.must_change_pwd===1||u.must_change_pwd===true;
    
    html+='<div style="background:var(--white);border-bottom:1px solid var(--border);padding:14px 16px">'
      +'<div style="display:flex;align-items:flex-start;gap:12px">'
        // Avatar
        +'<div style="width:46px;height:46px;border-radius:23px;background:'+rBg+';display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;color:'+rColor+';flex-shrink:0">'+u.name[0]+'</div>'
        // Info
        +'<div style="flex:1;min-width:0">'
          +'<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">'
            +'<span style="font-size:15px;font-weight:700;color:var(--g1)">'+u.name+'</span>'
            +'<span style="font-size:11px;font-weight:700;padding:2px 8px;border-radius:100px;background:'+rBg+';color:'+rColor+'">'+rLabel+'</span>'
            +(isActive
              ?'<span style="font-size:10px;color:var(--p)">● Aktif</span>'
              :'<span style="font-size:10px;color:var(--r)">● Nonaktif</span>')
            +(mustChg?'<span style="font-size:10px;color:var(--w)">⚠ Wajib ganti pwd</span>':'')
          +'</div>'
          +'<div style="font-size:12px;color:var(--g3);margin-top:3px">'+u.nik+'</div>'
          +'<div style="font-size:12px;color:var(--g3)">'+(u.puskesmas||'—')+' · '+(zl[u.zone]||u.zone||'—')+'</div>'
        +'</div>'
        // Actions
        +'<div style="display:flex;gap:6px;flex-shrink:0">'
          +'<button class="ibtn" onclick="openEditUser('+u.id+')" title="Edit">✏️</button>'
          +(CU&&CU.id!==u.id?'<button class="ibtn" onclick="confirmDeactivate('+u.id+',''+u.name+'','+isActive+')" title="'+(isActive?'Nonaktifkan':'Aktifkan')+'">'+(isActive?'🚫':'✅')+'</button>':'')
        +'</div>'
      +'</div>'
    +'</div>';
  }
  el.innerHTML=html;
}
function confirmDeactivate(uid,name,isActive){
  var msg=isActive?('Nonaktifkan akun '+name+'? Kader tidak bisa login.'):('Aktifkan kembali akun '+name+'?');
  if(!confirm(msg)) return;
  spin(true);
  PUT('/users/'+uid,{active:isActive?0:1,name:name},function(err,res){
    spin(false);
    if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    toast(isActive?('🚫 '+name+' dinonaktifkan'):('✅ '+name+' diaktifkan kembali'));
    rdUsers();
  });
}
function openAddUser(){
  openModal('Tambah Pengguna Baru',
    '<div class="fg"><label class="fl">NIK / Username <span class="req">*</span></label><input id="mu-nik" class="fi" placeholder="NIK KTP atau username unik"></div>'
    +'<div class="fg"><label class="fl">Nama Lengkap <span class="req">*</span></label><input id="mu-name" class="fi" placeholder="Nama pengguna"></div>'
    +'<div class="fg"><label class="fl">Password Sementara <span class="req">*</span></label><input id="mu-pwd" class="fi" type="text" value="kader123" placeholder="Min 6 karakter"></div>'
    +'<div class="fg"><label class="fl">Role</label><select id="mu-role" class="fs"><option value="kader">Kader Posyandu</option><option value="researcher">Peneliti</option><option value="admin">Administrator</option></select></div>'
    +'<div class="fg"><label class="fl">Puskesmas / Unit Kerja</label><input id="mu-pusk" class="fi" placeholder="Nama puskesmas"></div>'
    +'<div class="fg"><label class="fl">Zona Ekologi</label><select id="mu-zone" class="fs"><option value="all">Semua zona</option><option value="hills">Bukit</option><option value="lowlands">Dataran Rendah</option><option value="coastal">Pantai</option></select></div>'
    +'<div class="cbrow" onclick="togCbM('mu-mcp')"><div id="mu-mcp-b" class="cbbox on">✓</div><input type="hidden" id="mu-mcp" value="1"><span style="font-size:13px">Wajib ganti password saat login pertama</span></div>'
    +'<button class="btn btn-p" onclick="submitAddUser()" style="margin-top:8px">➕ Tambah Pengguna</button>');
}
function submitAddUser(){
  var d={nik:(ge('mu-nik').value||'').trim(),name:(ge('mu-name').value||'').trim(),password:ge('mu-pwd').value,
    role:ge('mu-role').value,puskesmas:ge('mu-pusk').value,zone:ge('mu-zone').value,
    must_change_pwd:parseInt(ge('mu-mcp').value)||0};
  if(!d.nik||!d.name||!d.password||d.password.length<6){toast('⚠️ Semua field wajib. Password min 6 karakter');return;}
  spin(true);closeModal();
  POST('/users',d,function(err,res){
    spin(false);
    if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    var msg='✅ '+d.name+' berhasil ditambahkan!';
    if(d.must_change_pwd) msg+=' (wajib ganti password saat login pertama)';
    toast(msg,4000);rdUsers();
  });
}
function openEditUser(id){
  var u=null;for(var i=0;i<USERS_CACHE.length;i++){if(USERS_CACHE[i].id===id){u=USERS_CACHE[i];break;}}if(!u) return;
  openModal('Edit Pengguna: '+u.name,
    '<div class="fg"><label class="fl">Nama Lengkap</label><input id="eu-name" class="fi" value="'+u.name+'"></div>'
    +'<div class="fg"><label class="fl">Role</label><select id="eu-role" class="fs"><option value="kader"'+(u.role==='kader'?' selected':'')+'>Kader Posyandu</option><option value="researcher"'+(u.role==='researcher'?' selected':'')+'>Peneliti</option><option value="admin"'+(u.role==='admin'?' selected':'')+'>Administrator</option></select></div>'
    +'<div class="fg"><label class="fl">Puskesmas / Unit Kerja</label><input id="eu-pusk" class="fi" value="'+(u.puskesmas||'')+'"></div>'
    +'<div class="fg"><label class="fl">Zona</label><select id="eu-zone" class="fs"><option value="all"'+(u.zone==='all'?' selected':'')+'>Semua zona</option><option value="hills"'+(u.zone==='hills'?' selected':'')+'>Bukit</option><option value="lowlands"'+(u.zone==='lowlands'?' selected':'')+'>Dataran</option><option value="coastal"'+(u.zone==='coastal'?' selected':'')+'>Pantai</option></select></div>'
    +'<div class="cbrow" onclick="togCbM(\\'eu-act\\')"><div id="eu-act-b" class="cbbox'+(u.active?' on":">✓':'">')+' </div><input type="hidden" id="eu-act" value="'+(u.active?1:0)+'"><span style="font-size:13px">Akun Aktif</span></div>'
    +'<button class="btn btn-p" onclick="submitEditUser('+id+')" style="margin-top:8px">💾 Simpan Perubahan</button>'
    +'<div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border)">'
    +'<div style="font-size:12px;color:var(--g3);margin-bottom:6px">Reset password (kader wajib ganti saat login):</div>'
    +'<div style="display:flex;gap:8px"><input id="eu-newpwd" class="fi" style="flex:1" type="text" placeholder="Password baru (min 6)" value="kader123"><button class="btn btn-w btn-sm" onclick="doResetPwd('+id+')">🔄 Reset</button></div>'
    +'</div>');
}
function togCbM(id){var cur=parseInt(ge(id).value)||0;var v=cur?0:1;ge(id).value=v;var b=ge(id+'-b');if(v){b.className='cbbox on';b.textContent='✓';}else{b.className='cbbox';b.textContent=' ';}}
function doResetPwd(uid){
  var newpwd=(ge('eu-newpwd').value||'').trim();
  if(!newpwd||newpwd.length<6){toast('⚠️ Password minimal 6 karakter');return;}
  spin(true);closeModal();
  POST('/users/'+uid+'/reset-password',{new_password:newpwd},function(err,res){
    spin(false);
    if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    toast('🔄 Password direset. Kader wajib ganti saat login berikutnya.',4000);
    rdUsers();
  });
}
function submitEditUser(id){
  var d={name:ge('eu-name').value,role:ge('eu-role').value,puskesmas:ge('eu-pusk').value,zone:ge('eu-zone').value,active:parseInt(ge('eu-act').value)||0};
  spin(true);closeModal();
  PUT('/users/'+id,d,function(err,res){
    spin(false);
    if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    toast('✅ Pengguna diperbarui!');rdUsers();
  });
}

// ═══════════════════════════════════════════════════════
// BOOT
// ═══════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════
// FORCE PASSWORD CHANGE
// ═══════════════════════════════════════════════════════
function showForcePwdChange(){
  PAGE_STACK=['forcepwd'];showPage('forcepwd');
  ge('fp-old').value='';ge('fp-new').value='';ge('fp-confirm').value='';
  ge('fp-err').style.display='none';
}
function doForcePwdChange(){
  var old=(ge('fp-old').value||'').trim();
  var nw=(ge('fp-new').value||'').trim();
  var cf=(ge('fp-confirm').value||'').trim();
  var errEl=ge('fp-err');var errTxt=ge('fp-errtxt');
  if(!old||!nw||!cf){errTxt.textContent='Semua field wajib diisi';errEl.style.display='flex';return;}
  if(nw.length<6){errTxt.textContent='Password baru minimal 6 karakter';errEl.style.display='flex';return;}
  if(nw!==cf){errTxt.textContent='Konfirmasi password tidak cocok';errEl.style.display='flex';return;}
  if(old===nw){errTxt.textContent='Password baru harus berbeda dari password lama';errEl.style.display='flex';return;}
  spin(true);
  POST('/auth/change-password',{old_password:old,new_password:nw},function(err,res){
    spin(false);
    if(err||!res.success){errTxt.textContent=(err?err.error:res.error);errEl.style.display='flex';return;}
    toast('✅ Password berhasil diubah! Selamat datang.');
    ge('nav').classList.add('show');
    PAGE_STACK=[];
    goTo('dashboard');
  });
}

// ═══════════════════════════════════════════════════════
// ACTIVITY LOG
// ═══════════════════════════════════════════════════════
function openLogs(){PAGE_STACK.push('logs');showPage('logs');rdLogs();}
function rdLogs(){
  var el=ge('logs-content');
  el.innerHTML='<div style="color:var(--g3);text-align:center;padding:20px">Memuat log...</div>';
  spin(true);
  GET('/logs?limit=100',function(err,res){
    spin(false);
    if(err||!res.success){el.innerHTML='<div class="ibox ir"><span>❌</span><p>'+(err?err.error:res.error)+'</p></div>';return;}
    var logs=res.data||[];
    if(!logs.length){el.innerHTML='<div class="empty"><div style="font-size:48px">📋</div><div style="font-size:14px;color:var(--g3);margin-top:12px">Belum ada aktivitas</div></div>';return;}
    var ac={LOGIN:'🔑',CREATE:'➕',UPDATE:'✏️',DELETE:'🗑️',CHANGE_PWD:'🔐',RESET_PWD:'🔄',CREATE_USER:'👤',UPDATE_USER:'👤',DEACTIVATE_USER:'🚫',EXPORT:'📤'};
    var cl={LOGIN:'var(--p)',CREATE:'var(--s)',UPDATE:'var(--w)',DELETE:'var(--r)',CHANGE_PWD:'var(--p)',RESET_PWD:'var(--w)',CREATE_USER:'var(--s)',EXPORT:'var(--p)'};
    var html='<div class="card"><div class="card-title">📋 Log Aktivitas Sistem ('+logs.length+' entri)</div>';
    for(var i=0;i<logs.length;i++){
      var l=logs[i];
      var icon=ac[l.action]||'📌';var color=cl[l.action]||'var(--g2)';
      html+='<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">'
        +'<div style="font-size:16px;flex-shrink:0">'+icon+'</div>'
        +'<div style="flex:1">'
          +'<div style="font-size:12px;font-weight:700;color:'+color+'">'+l.action+(l.detail?' — <span style="font-weight:400;color:var(--g3)">'+l.detail+'</span>':'')+'</div>'
          +'<div style="font-size:11px;color:var(--g3)">'+(l.user_name||'—')+' ('+( l.user_role||'—')+') · '+l.table_name+' #'+l.record_id+' · '+l.created_at+'</div>'
        +'</div></div>';
    }
    html+='</div>';
    el.innerHTML=html;
  });
}

(function boot(){
  loadSaved();
  // Check server connection
  // Ping async - tidak blokir login
  (function(){
    var px=new XMLHttpRequest();
    px.open('GET',BASE_URL+'/api/ping',true);
    px.timeout=20000;
    px.onload=function(){
      try{var d=JSON.parse(px.responseText);setConnStatus(d&&d.success);}
      catch(e){setConnStatus(false);}
    };
    px.onerror=function(){setConnStatus(false);};
    px.ontimeout=function(){setConnStatus(false);};
    px.send();
  })();

  if(CU&&TOKEN){
    // Verify token still valid
    GET('/auth/me',function(err,res){
      if(!err&&res.success){
        CU=res.data;saveSess(TOKEN,CU);
        if(res.data.must_change_pwd){
          showForcePwdChange();
        } else {
          ge('nav').classList.add('show');
          PAGE_STACK=['dashboard'];showPage('dashboard');rdDash();
        }
      } else {
        clearSess();showPage('login');
      }
    });
  } else {
    showPage('login');
  }
})();
</script>
</body>
</html>
'''

@app.route('/', defaults={'path':''})
@app.route('/<path:path>')
def serve(path):
    # Serve other static files from disk
    if path and path != 'index.html' and os.path.exists(os.path.join(WEB_DIR, path)):
        return send_from_directory(WEB_DIR, path)
    # Serve embedded index.html with no-cache
    from flask import Response
    resp = Response(_INDEX_HTML, mimetype='text/html')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

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
