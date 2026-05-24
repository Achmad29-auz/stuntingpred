#!/usr/bin/env python3
"""StuntingPred Server v3.0 - Heri Bahtiar | UMS 2025"""
import sqlite3, json, os, hashlib, hmac, time, datetime, subprocess
from functools import wraps
from flask import Flask, request, jsonify, g, Response
from flask_cors import CORS

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DB_PATH', os.path.join(APP_DIR, 'stunting.db'))
SECRET  = os.environ.get('SECRET_KEY', 'stuntingpred-ums-2025-secret')
PORT    = int(os.environ.get('PORT', 5000))

app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True,
     allow_headers=["Content-Type","Authorization"],
     methods=["GET","POST","PUT","DELETE","OPTIONS"])

# ── DB ─────────────────────────────────────────────
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
    r = cur.fetchone() if one else cur.fetchall()
    return r

def row2dict(r): return dict(r) if r else None
def rows(r):     return [dict(x) for x in r]
def ok(data=None, msg=None):
    r = {'success': True}
    if data is not None: r['data'] = data
    if msg: r['message'] = msg
    return jsonify(r)
def err(msg, code=400): return jsonify({'success':False,'error':msg}), code
def now(): return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def hpwd(p): return hashlib.sha256(p.encode()).hexdigest()

# ── TOKEN ──────────────────────────────────────────
def make_token(uid, nik, role):
    ts = int(time.time())
    payload = f"{uid}:{nik}:{role}:{ts}"
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]
    import base64
    return base64.b64encode(f"{payload}:{sig}".encode()).decode()

def verify_token(token):
    try:
        import base64
        decoded = base64.b64decode(token.encode()).decode()
        parts = decoded.rsplit(':', 1)
        payload, sig = parts[0], parts[1]
        expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(sig, expected): return None
        p = payload.split(':')
        if time.time() - int(p[3]) > 86400*60: return None
        return {'user_id': int(p[0]), 'nik': p[1], 'role': p[2]}
    except: return None

def auth_required(f):
    @wraps(f)
    def dec(*a, **kw):
        token = request.headers.get('Authorization','').replace('Bearer ','').strip()
        info = verify_token(token)
        if not info: return err('Login diperlukan', 401)
        g.auth = info
        return f(*a, **kw)
    return dec

def admin_only(f):
    @wraps(f)
    @auth_required
    def dec(*a, **kw):
        if g.auth['role'] != 'admin': return err('Hanya admin', 403)
        return f(*a, **kw)
    return dec

def admin_or_researcher(f):
    @wraps(f)
    @auth_required
    def dec(*a, **kw):
        if g.auth['role'] not in ('admin','researcher'): return err('Akses ditolak', 403)
        return f(*a, **kw)
    return dec

# ── INIT DB ────────────────────────────────────────
def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nik TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
        password TEXT NOT NULL, role TEXT DEFAULT 'kader',
        puskesmas TEXT DEFAULT '', zone TEXT DEFAULT 'all',
        phone TEXT DEFAULT '', email TEXT DEFAULT '',
        active INTEGER DEFAULT 1, must_change_pwd INTEGER DEFAULT 0,
        created_at TEXT DEFAULT(datetime('now','localtime')),
        updated_at TEXT DEFAULT(datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS toddlers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nik_balita TEXT, name TEXT NOT NULL, birth_date TEXT NOT NULL,
        gender TEXT DEFAULT 'male', birth_weight REAL, birth_height REAL,
        zone TEXT DEFAULT 'lowlands', village TEXT DEFAULT '',
        mother_name TEXT NOT NULL, mother_age INTEGER, mother_height REAL,
        mother_edu TEXT DEFAULT 'sma', mother_illness INTEGER DEFAULT 0,
        mother_ctps INTEGER DEFAULT 1, father_edu TEXT DEFAULT 'sma',
        family_income INTEGER, family_members INTEGER,
        water_source TEXT DEFAULT 'well', toilet_type TEXT DEFAULT 'own',
        waste_mgmt TEXT DEFAULT 'collected', floor_type TEXT DEFAULT 'cement',
        sanitation_score INTEGER DEFAULT 0, excl_breastfeed INTEGER DEFAULT 0,
        infection_hist INTEGER DEFAULT 0, registered_by INTEGER,
        created_at TEXT DEFAULT(datetime('now','localtime')),
        updated_at TEXT DEFAULT(datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS measurements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        toddler_id INTEGER NOT NULL REFERENCES toddlers(id) ON DELETE CASCADE,
        measured_by INTEGER, measure_date TEXT DEFAULT(date('now','localtime')),
        age_months INTEGER NOT NULL, height_cm REAL NOT NULL,
        weight_kg REAL, z_score_hfa REAL, stunting_status TEXT,
        risk_level TEXT, risk_prob REAL, notes TEXT DEFAULT '',
        intervention TEXT DEFAULT '',
        created_at TEXT DEFAULT(datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS qualitative_data(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        toddler_id INTEGER, respondent_code TEXT NOT NULL,
        interview_date TEXT NOT NULL, interviewed_by INTEGER,
        interview_type TEXT DEFAULT 'idi', food_taboo TEXT DEFAULT '',
        decision_maker TEXT DEFAULT '', breastfeed_knowledge INTEGER DEFAULT 0,
        stunting_knowledge TEXT DEFAULT '', posyandu_freq TEXT DEFAULT '',
        health_barriers TEXT DEFAULT '', water_src_qual TEXT DEFAULT '',
        toilet_usage TEXT DEFAULT '', mpasi_practice TEXT DEFAULT '',
        cultural_beliefs TEXT DEFAULT '', verbatim_notes TEXT DEFAULT '',
        theme_codes TEXT DEFAULT '', sentiment TEXT DEFAULT '',
        created_at TEXT DEFAULT(datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS sync_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, action TEXT, table_name TEXT,
        record_id INTEGER, detail TEXT DEFAULT '',
        created_at TEXT DEFAULT(datetime('now','localtime'))
    );
    CREATE INDEX IF NOT EXISTS idx_m_tid ON measurements(toddler_id);
    CREATE INDEX IF NOT EXISTS idx_q_tid ON qualitative_data(toddler_id);
    """)
    db.commit()

    # Migrate columns
    for col, defval in [('active','INTEGER DEFAULT 1'),
                        ('must_change_pwd','INTEGER DEFAULT 0'),
                        ('phone',"TEXT DEFAULT ''"),
                        ('email',"TEXT DEFAULT ''")]:
        try: db.execute(f"ALTER TABLE users ADD COLUMN {col} {defval}"); db.commit()
        except: pass

    # Hash plain passwords
    for row in db.execute("SELECT id,password FROM users").fetchall():
        if len(row[1]) < 64:
            db.execute("UPDATE users SET password=? WHERE id=?", (hpwd(row[1]), row[0]))
    db.commit()

    # Seed users
    if not db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        for u in [
            ('superadmin','Administrator','admin123','admin','Dinkes Lombok Tengah','all',0),
            ('kader001','Siti Rahayu','kader123','kader','Puskesmas Praya','lowlands',0),
            ('kader002','Ahmad Firdaus','kader123','kader','Puskesmas Praya Barat','hills',1),
            ('kader003','Nurhayati','kader123','kader','Puskesmas Pujut','coastal',1),
            ('1901234567890001','Heri Bahtiar','peneliti123','researcher','UMS Research Team','all',0),
        ]:
            db.execute("INSERT INTO users(nik,name,password,role,puskesmas,zone,must_change_pwd) VALUES(?,?,?,?,?,?,?)",
                      (u[0],u[1],hpwd(u[2]),u[3],u[4],u[5],u[6]))
        db.commit()

    # Seed toddlers
    if not db.execute("SELECT COUNT(*) FROM toddlers").fetchone()[0]:
        today = datetime.date.today().isoformat()
        demo = [
            ('BL001','Ahmad Fauzi','2024-01-15','male',2.8,48,'hills','Selebung','Fatimah',32,147,'smp','sd',1200000,'well','none','dump','dirt',2,0,1,0),
            ('BL002','Putri Nisa','2023-06-20','female',3.1,50,'coastal','Kuta','Rahmi',26,153,'sma','sma',2500000,'pam','own','collected','tile',7,1,0,1),
            ('BL003','Rizki Maulana','2023-11-10','male',2.5,46.5,'lowlands','Praya','Nurul',28,149,'sd','sd',900000,'river','shared','burned','cement',1,0,1,0),
            ('BL004','Lailatul Fitri','2022-08-05','female',3.3,51,'lowlands','Jonggat','Sari',24,156,'sma','pt',3500000,'pam','own','collected','tile',9,1,0,1),
            ('BL005','Bagas Prasetyo','2024-03-22','male',2.2,45,'hills','Batukliang','Dewi',38,145,'none','sd',700000,'river','none','dump','dirt',0,0,1,0),
            ('BL006','Siti Aisyah','2023-09-05','female',3.0,49,'coastal','Gerupuk','Maryam',29,151,'smp','smp',1500000,'well','shared','burned','cement',3,0,0,1),
            ('BL007','M. Raffi','2024-05-10','male',2.7,47,'hills','Aik Berik','Rohani',35,146,'sd','sd',800000,'river','none','dump','dirt',1,0,1,0),
            ('BL008','Nadia Putri','2022-12-01','female',3.2,50.5,'lowlands','Mantang','Suharti',27,154,'sma','sma',2200000,'pam','own','collected','tile',8,1,0,1),
        ]
        for d in demo:
            bd = datetime.date.fromisoformat(d[2])
            td = datetime.date.today()
            age = min(59, max(0, (td.year-bd.year)*12+(td.month-bd.month)))
            h = round(d[5]+age*0.9, 1)
            w = round(d[4]+age*0.22, 1)
            sc = d[18]
            rl = 'Tinggi' if sc<3 else ('Sedang' if sc<6 else 'Rendah')
            st = 'Stunted' if sc<4 else 'Normal'
            cur = db.execute("""INSERT INTO toddlers
                (nik_balita,name,birth_date,gender,birth_weight,birth_height,zone,village,
                 mother_name,mother_age,mother_height,mother_edu,father_edu,family_income,
                 water_source,toilet_type,waste_mgmt,floor_type,sanitation_score,
                 excl_breastfeed,infection_hist,mother_illness,registered_by)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""", d)
            db.execute("""INSERT INTO measurements
                (toddler_id,measured_by,measure_date,age_months,height_cm,weight_kg,
                 stunting_status,risk_level,risk_prob)
                VALUES(?,1,?,?,?,?,?,?,?)""",
                (cur.lastrowid,today,age,h,w,st,rl,0.7 if sc<3 else (0.45 if sc<6 else 0.2)))
        db.commit()
    db.close()
    print(f"[DB] Ready: {DB_PATH}")

def log(uid, action, table, rid, detail=''):
    try:
        get_db().execute("INSERT INTO sync_log(user_id,action,table_name,record_id,detail) VALUES(?,?,?,?,?)",
                        (uid,action,table,rid,detail))
        get_db().commit()
    except: pass

# ── AUTH ───────────────────────────────────────────
@app.route('/api/auth/login', methods=['POST'])
def login():
    d = request.get_json() or {}
    nik = (d.get('nik') or '').strip()
    pwd = (d.get('password') or '').strip()
    if not nik or not pwd: return err('NIK dan password wajib diisi')
    u = row2dict(q("SELECT * FROM users WHERE nik=? AND active=1",(nik,),one=True))
    if not u: return err('NIK atau password salah')
    stored = u['password']
    ok_pwd = hmac.compare_digest(stored, hpwd(pwd)) if len(stored)==64 else stored==pwd
    if not ok_pwd: return err('NIK atau password salah')
    if len(stored)<64: q("UPDATE users SET password=? WHERE id=?",(hpwd(pwd),u['id']))
    token = make_token(u['id'], u['nik'], u['role'])
    log(u['id'],'LOGIN','users',u['id'])
    u.pop('password',None)
    return ok({'user':u,'token':token,'must_change_pwd':bool(u.get('must_change_pwd',0))})

@app.route('/api/auth/me', methods=['GET'])
@auth_required
def me():
    u = row2dict(q("SELECT id,nik,name,role,puskesmas,zone,active,must_change_pwd FROM users WHERE id=?",
                   (g.auth['user_id'],),one=True))
    return ok(u)

@app.route('/api/auth/change-password', methods=['POST'])
@auth_required
def change_password():
    d = request.get_json() or {}
    old = (d.get('old_password') or '').strip()
    new = (d.get('new_password') or '').strip()
    if not old or not new or len(new)<6: return err('Password lama & baru (min 6 karakter) wajib diisi')
    if old == new: return err('Password baru harus berbeda')
    u = row2dict(q("SELECT password FROM users WHERE id=?",(g.auth['user_id'],),one=True))
    stored = u['password']
    ok_pwd = hmac.compare_digest(stored,hpwd(old)) if len(stored)==64 else stored==old
    if not ok_pwd: return err('Password lama tidak cocok')
    q("UPDATE users SET password=?,must_change_pwd=0,updated_at=? WHERE id=?",
      (hpwd(new),now(),g.auth['user_id']))
    log(g.auth['user_id'],'CHANGE_PWD','users',g.auth['user_id'])
    return ok(msg='Password berhasil diubah')

# ── USERS ──────────────────────────────────────────
@app.route('/api/users', methods=['GET'])
@auth_required
def get_users():
    if g.auth['role'] not in ('admin','researcher'): return err('Akses ditolak',403)
    return ok(rows(q("SELECT id,nik,name,role,puskesmas,zone,phone,email,active,must_change_pwd,created_at FROM users ORDER BY role,name")))

@app.route('/api/users', methods=['POST'])
@admin_only
def create_user():
    d = request.get_json() or {}
    nik = (d.get('nik') or '').strip()
    name = (d.get('name') or '').strip()
    pwd = (d.get('password') or 'kader123').strip()
    if not nik or not name: return err('NIK dan nama wajib diisi')
    if len(pwd)<6: return err('Password minimal 6 karakter')
    if q("SELECT id FROM users WHERE nik=?",(nik,),one=True): return err('NIK sudah terdaftar')
    cur = get_db().execute(
        "INSERT INTO users(nik,name,password,role,puskesmas,zone,must_change_pwd) VALUES(?,?,?,?,?,?,?)",
        (nik,name,hpwd(pwd),d.get('role','kader'),d.get('puskesmas',''),d.get('zone','lowlands'),int(d.get('must_change_pwd',1))))
    get_db().commit()
    log(g.auth['user_id'],'CREATE_USER','users',cur.lastrowid,name)
    return ok({'id':cur.lastrowid,'message':f'{name} berhasil ditambahkan','default_password':pwd}),201

@app.route('/api/users/<int:uid>', methods=['PUT'])
@admin_only
def update_user(uid):
    d = request.get_json() or {}
    q("UPDATE users SET name=?,role=?,puskesmas=?,zone=?,phone=?,email=?,active=?,must_change_pwd=?,updated_at=? WHERE id=?",
      (d.get('name',''),d.get('role','kader'),d.get('puskesmas',''),d.get('zone','lowlands'),
       d.get('phone',''),d.get('email',''),int(d.get('active',1)),int(d.get('must_change_pwd',0)),now(),uid))
    return ok(msg='User diperbarui')

@app.route('/api/users/<int:uid>/reset-password', methods=['POST'])
@admin_only
def reset_password(uid):
    d = request.get_json() or {}
    new_pwd = (d.get('new_password') or 'kader123').strip()
    if len(new_pwd)<6: return err('Password minimal 6 karakter')
    u = q("SELECT name FROM users WHERE id=?",(uid,),one=True)
    if not u: return err('User tidak ditemukan',404)
    q("UPDATE users SET password=?,must_change_pwd=1,updated_at=? WHERE id=?",(hpwd(new_pwd),now(),uid))
    log(g.auth['user_id'],'RESET_PWD','users',uid)
    return ok({'message':f'Password {u["name"]} direset','new_password':new_pwd})

# ── TODDLERS ───────────────────────────────────────
@app.route('/api/toddlers', methods=['GET'])
@auth_required
def get_toddlers():
    search = request.args.get('search','')
    zone   = request.args.get('zone','all')
    sql = """SELECT t.*,
        m.height_cm as last_height, m.weight_kg as last_weight,
        m.risk_level as last_risk, m.stunting_status as last_status,
        m.measure_date as last_visit, m.risk_prob as last_prob,
        (SELECT COUNT(*) FROM measurements WHERE toddler_id=t.id) as visit_count
        FROM toddlers t
        LEFT JOIN measurements m ON m.id=(
            SELECT id FROM measurements WHERE toddler_id=t.id
            ORDER BY measure_date DESC,id DESC LIMIT 1)
        WHERE 1=1"""
    args = []
    # Kader zone restriction
    if g.auth['role']=='kader':
        uz = row2dict(q("SELECT zone FROM users WHERE id=?",(g.auth['user_id'],),one=True))
        if uz and uz['zone'] and uz['zone']!='all':
            sql += " AND t.zone=?"; args.append(uz['zone'])
    elif zone and zone!='all':
        sql += " AND t.zone=?"; args.append(zone)
    if search:
        sql += " AND (t.name LIKE ? OR t.nik_balita LIKE ? OR t.mother_name LIKE ?)"
        args += [f'%{search}%',f'%{search}%',f'%{search}%']
    sql += " ORDER BY t.created_at DESC"
    return ok(rows(q(sql,args)))

@app.route('/api/toddlers/<int:tid>', methods=['GET'])
@auth_required
def get_toddler(tid):
    t = row2dict(q("SELECT * FROM toddlers WHERE id=?",(tid,),one=True))
    return ok(t) if t else err('Tidak ditemukan',404)

@app.route('/api/toddlers', methods=['POST'])
@auth_required
def create_toddler():
    d = request.get_json() or {}
    if not d.get('name') or not d.get('birth_date') or not d.get('mother_name'):
        return err('Nama balita, tanggal lahir, nama ibu wajib diisi')
    if d.get('nik_balita') and q("SELECT id FROM toddlers WHERE nik_balita=?",(d['nik_balita'],),one=True):
        return err('NIK balita sudah terdaftar')
    cur = get_db().execute("""INSERT INTO toddlers
        (nik_balita,name,birth_date,gender,birth_weight,birth_height,zone,village,
         mother_name,mother_age,mother_height,mother_edu,mother_illness,mother_ctps,
         father_edu,family_income,family_members,water_source,toilet_type,waste_mgmt,
         floor_type,sanitation_score,excl_breastfeed,infection_hist,registered_by)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (d.get('nik_balita'),d['name'],d['birth_date'],d.get('gender','male'),
         d.get('birth_weight'),d.get('birth_height'),d.get('zone','lowlands'),d.get('village',''),
         d['mother_name'],d.get('mother_age'),d.get('mother_height'),d.get('mother_edu','sma'),
         int(d.get('mother_illness',0)),int(d.get('mother_ctps',1)),d.get('father_edu','sma'),
         d.get('family_income'),d.get('family_members'),d.get('water_source','well'),
         d.get('toilet_type','own'),d.get('waste_mgmt','collected'),d.get('floor_type','cement'),
         int(d.get('sanitation_score',0)),int(d.get('excl_breastfeed',0)),
         int(d.get('infection_hist',0)),g.auth['user_id']))
    get_db().commit()
    nid = cur.lastrowid
    log(g.auth['user_id'],'CREATE','toddlers',nid,d['name'])
    return ok({'id':nid,'message':f'{d["name"]} berhasil didaftarkan'}),201

@app.route('/api/toddlers/<int:tid>', methods=['PUT'])
@auth_required
def update_toddler(tid):
    d = request.get_json() or {}
    if not d.get('name') or not d.get('birth_date') or not d.get('mother_name'):
        return err('Nama balita, tanggal lahir, nama ibu wajib diisi')
    q("""UPDATE toddlers SET name=?,birth_date=?,gender=?,birth_weight=?,birth_height=?,
         zone=?,village=?,mother_name=?,mother_age=?,mother_height=?,mother_edu=?,
         mother_illness=?,mother_ctps=?,father_edu=?,family_income=?,family_members=?,
         water_source=?,toilet_type=?,waste_mgmt=?,floor_type=?,sanitation_score=?,
         excl_breastfeed=?,infection_hist=?,updated_at=? WHERE id=?""",
        (d['name'],d['birth_date'],d.get('gender','male'),d.get('birth_weight'),d.get('birth_height'),
         d.get('zone'),d.get('village',''),d['mother_name'],d.get('mother_age'),d.get('mother_height'),
         d.get('mother_edu','sma'),int(d.get('mother_illness',0)),int(d.get('mother_ctps',1)),
         d.get('father_edu','sma'),d.get('family_income'),d.get('family_members'),
         d.get('water_source'),d.get('toilet_type'),d.get('waste_mgmt'),d.get('floor_type'),
         int(d.get('sanitation_score',0)),int(d.get('excl_breastfeed',0)),
         int(d.get('infection_hist',0)),now(),tid))
    log(g.auth['user_id'],'UPDATE','toddlers',tid,d['name'])
    return ok(msg='Balita diperbarui')

@app.route('/api/toddlers/<int:tid>', methods=['DELETE'])
@admin_or_researcher
def delete_toddler(tid):
    t = q("SELECT name FROM toddlers WHERE id=?",(tid,),one=True)
    if not t: return err('Tidak ditemukan',404)
    q("DELETE FROM toddlers WHERE id=?",(tid,))
    return ok(msg=f'{t["name"]} dihapus')

# ── MEASUREMENTS ───────────────────────────────────
@app.route('/api/toddlers/<int:tid>/measurements', methods=['GET'])
@auth_required
def get_measurements(tid):
    ms = rows(q("""SELECT m.*,u.name as measured_by_name FROM measurements m
                   LEFT JOIN users u ON u.id=m.measured_by
                   WHERE m.toddler_id=? ORDER BY m.measure_date,m.id""",(tid,)))
    return ok(ms)

@app.route('/api/toddlers/<int:tid>/measurements', methods=['POST'])
@auth_required
def create_measurement(tid):
    d = request.get_json() or {}
    if not d.get('height_cm'): return err('Tinggi badan wajib diisi')
    if d.get('age_months') is None: return err('Usia wajib diisi')
    today = datetime.date.today().isoformat()
    cur = get_db().execute("""INSERT INTO measurements
        (toddler_id,measured_by,measure_date,age_months,height_cm,weight_kg,
         z_score_hfa,stunting_status,risk_level,risk_prob,notes,intervention)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (tid,g.auth['user_id'],d.get('measure_date',today),int(d['age_months']),
         float(d['height_cm']),float(d['weight_kg']) if d.get('weight_kg') else None,
         float(d['z_score_hfa']) if d.get('z_score_hfa') is not None else None,
         d.get('stunting_status'),d.get('risk_level'),
         float(d['risk_prob']) if d.get('risk_prob') is not None else None,
         d.get('notes',''),d.get('intervention','')))
    get_db().commit()
    nid = cur.lastrowid
    log(g.auth['user_id'],'CREATE','measurements',nid,f"toddler={tid}")
    return ok({'id':nid,'message':'Pengukuran disimpan'}),201

# ── QUALITATIVE ────────────────────────────────────
@app.route('/api/qualitative', methods=['GET'])
@auth_required
def get_qualitative():
    qs = rows(q("""SELECT qd.*,t.name as toddler_name,u.name as interviewer_name
                   FROM qualitative_data qd
                   LEFT JOIN toddlers t ON t.id=qd.toddler_id
                   LEFT JOIN users u ON u.id=qd.interviewed_by
                   ORDER BY qd.interview_date DESC"""))
    return ok(qs)

@app.route('/api/qualitative', methods=['POST'])
@auth_required
def create_qualitative():
    d = request.get_json() or {}
    if not d.get('respondent_code') or not d.get('interview_date'):
        return err('Kode responden dan tanggal wajib diisi')
    cur = get_db().execute("""INSERT INTO qualitative_data
        (toddler_id,respondent_code,interview_date,interviewed_by,interview_type,
         food_taboo,decision_maker,breastfeed_knowledge,stunting_knowledge,
         posyandu_freq,health_barriers,water_src_qual,toilet_usage,mpasi_practice,
         cultural_beliefs,verbatim_notes,theme_codes,sentiment)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (d.get('toddler_id'),d['respondent_code'],d['interview_date'],g.auth['user_id'],
         d.get('interview_type','idi'),d.get('food_taboo',''),d.get('decision_maker',''),
         int(d.get('breastfeed_knowledge',0)),d.get('stunting_knowledge',''),
         d.get('posyandu_freq',''),d.get('health_barriers',''),d.get('water_src_qual',''),
         d.get('toilet_usage',''),d.get('mpasi_practice',''),d.get('cultural_beliefs',''),
         d.get('verbatim_notes',''),d.get('theme_codes',''),d.get('sentiment','')))
    get_db().commit()
    return ok({'id':cur.lastrowid,'message':'Data wawancara disimpan'}),201

# ── DASHBOARD ──────────────────────────────────────
@app.route('/api/dashboard', methods=['GET'])
@auth_required
def dashboard():
    total   = q("SELECT COUNT(*) as n FROM toddlers",one=True)['n']
    by_risk = rows(q("""SELECT m.risk_level,COUNT(*) as n FROM(
        SELECT toddler_id,MAX(measure_date) as md FROM measurements GROUP BY toddler_id) L
        JOIN measurements m ON m.toddler_id=L.toddler_id AND m.measure_date=L.md
        GROUP BY m.risk_level"""))
    by_zone = rows(q("""SELECT t.zone,COUNT(DISTINCT t.id) as total,
        SUM(CASE WHEN m.stunting_status IN('Stunted','Severely Stunted') THEN 1 ELSE 0 END) as stunted
        FROM toddlers t
        LEFT JOIN(SELECT toddler_id,MAX(measure_date) as md FROM measurements GROUP BY toddler_id) L
            ON L.toddler_id=t.id
        LEFT JOIN measurements m ON m.toddler_id=t.id AND m.measure_date=L.md
        GROUP BY t.zone ORDER BY t.zone"""))
    recent = rows(q("""SELECT m.*,t.name as toddler_name,u.name as by_name
        FROM measurements m JOIN toddlers t ON t.id=m.toddler_id
        LEFT JOIN users u ON u.id=m.measured_by
        ORDER BY m.created_at DESC,m.id DESC LIMIT 10"""))
    qc = q("SELECT COUNT(*) as n FROM qualitative_data",one=True)['n']
    uc = q("SELECT COUNT(*) as n FROM users WHERE active=1",one=True)['n']
    return ok({'total':total,'by_risk':by_risk,'by_zone':by_zone,
               'recent_measurements':recent,'qual_count':qc,'user_count':uc})

@app.route('/api/export', methods=['GET'])
@admin_or_researcher
def export_data():
    log(g.auth['user_id'],'EXPORT','all',0)
    return ok({'toddlers':rows(q("SELECT * FROM toddlers")),
               'measurements':rows(q("SELECT * FROM measurements")),
               'qualitative':rows(q("SELECT * FROM qualitative_data")),
               'exported_at':datetime.datetime.now().isoformat()})

@app.route('/api/logs', methods=['GET'])
@admin_or_researcher
def get_logs():
    limit = min(int(request.args.get('limit',50)),200)
    ls = rows(q("""SELECT l.*,u.name as user_name,u.role as user_role
                   FROM sync_log l LEFT JOIN users u ON u.id=l.user_id
                   ORDER BY l.id DESC LIMIT ?""",(limit,)))
    return ok(ls)

@app.route('/api/ping', methods=['GET'])
def ping():
    tt = q("SELECT COUNT(*) as n FROM toddlers",one=True)['n']
    tm = q("SELECT COUNT(*) as n FROM measurements",one=True)['n']
    return ok({'status':'online','version':'3.0',
               'time':datetime.datetime.now().isoformat(),
               'db':{'toddlers':tt,'measurements':tm}})

# ── SELF UPDATE (no auth - secret URL) ─────────────
@app.route('/api/do-update-stunting2025', methods=['GET','POST'])
def do_update():
    try:
        r = subprocess.run(['git','pull','origin','main'],
            cwd=APP_DIR, capture_output=True, text=True, timeout=60)
        wsgi = '/var/www/achmad29_pythonanywhere_com_wsgi.py'
        reloaded = False
        if os.path.exists(wsgi):
            os.utime(wsgi, None); reloaded = True
        return ok({'git':r.stdout.strip() or r.stderr.strip(),
                   'wsgi_reloaded':reloaded,
                   'message':'Update selesai! Refresh browser dalam 15 detik.'})
    except Exception as ex:
        return err(str(ex))

# ── SERVE HTML (embedded, no file dependency) ──────
@app.route('/', defaults={'path':''})
@app.route('/<path:path>')
def serve(path):
    html = get_app_html()
    resp = Response(html, mimetype='text/html')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

def get_app_html():
    """Return the HTML app - reads from file if exists, else embedded"""
    html_path = os.path.join(APP_DIR, 'www', 'index.html')
    if os.path.exists(html_path):
        with open(html_path, encoding='utf-8') as f:
            return f.read()
    return EMBEDDED_HTML

# ── EMBEDDED HTML ──────────────────────────────────
EMBEDDED_HTML = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="theme-color" content="#0F6E56">
<title>StuntingPred</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
:root{--p:#0F6E56;--pd:#085041;--pl:#E1F5EE;--pm:#1D9E75;--s:#185FA5;--sl:#E6F1FB;
  --r:#A32D2D;--rl:#FCEBEB;--w:#854F0B;--wl:#FAEEDA;
  --g1:#1A1A1A;--g2:#444441;--g3:#888780;--g4:#D3D1C7;--g5:#F1EFE8;
  --white:#fff;--bg:#F5F5F4;--border:#E5E5E3}
html,body{height:100%;overflow:hidden}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
  background:var(--bg);color:var(--g1);display:flex;flex-direction:column;-webkit-font-smoothing:antialiased}
#app{display:flex;flex-direction:column;height:100vh;overflow:hidden}
#screen{flex:1;overflow-y:auto;overflow-x:hidden;-webkit-overflow-scrolling:touch}
.page{display:none;min-height:100%;padding-bottom:72px}
.page.active{display:block}
.pad{padding:16px}
/* NAV */
#nav{flex-shrink:0;background:var(--white);border-top:1px solid var(--border);
  display:none;height:60px;box-shadow:0 -2px 12px rgba(0,0,0,.06)}
#nav.show{display:flex}
.nb{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:2px;cursor:pointer;border:none;background:none;padding:4px 0;color:var(--g3);
  font-size:10px;font-weight:500;font-family:inherit}
.nb.on{color:var(--p)}.nb.on .ni{background:var(--pl)}
.ni{font-size:18px;width:40px;height:26px;border-radius:13px;display:flex;align-items:center;justify-content:center}
/* CARDS */
.card{background:var(--white);border-radius:12px;padding:16px;border:1px solid var(--border);margin-bottom:12px;box-shadow:0 1px 6px rgba(0,0,0,.05)}
.ct{font-size:15px;font-weight:700;color:var(--g1);margin-bottom:12px}
/* BADGES */
.badge{display:inline-flex;align-items:center;padding:2px 9px;border-radius:100px;font-size:11px;font-weight:700}
.bh{background:var(--rl);color:var(--r)}.bm{background:var(--wl);color:var(--w)}.bl{background:var(--pl);color:var(--p)}
.bss{background:var(--rl);color:var(--r)}.bs{background:var(--wl);color:var(--w)}.bn{background:var(--pl);color:var(--p)}.bt{background:var(--sl);color:var(--s)}
/* BUTTONS */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:12px 18px;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;border:none;font-family:inherit;width:100%}
.bp{background:var(--p);color:#fff}.bp:active{background:var(--pd)}
.bs2{background:transparent;color:var(--p);border:1.5px solid var(--p)}
.bd{background:var(--r);color:#fff}.bw2{background:var(--w);color:#fff}
.bsm{padding:7px 14px;font-size:12px;width:auto}
/* FORM */
.fg{margin-bottom:12px}.fl{display:block;font-size:12px;font-weight:600;color:var(--g2);margin-bottom:4px}.req{color:var(--r)}
.fi,.fs,.ft{width:100%;padding:10px 12px;border:1.5px solid var(--border);border-radius:10px;font-size:14px;color:var(--g1);background:var(--white);outline:none;font-family:inherit;-webkit-appearance:none}
.ft{height:80px;resize:none;line-height:1.5}.fi:focus,.fs:focus,.ft:focus{border-color:var(--p)}
.fr{display:flex;gap:10px}.fr .fg{flex:1}
.cbr{display:flex;align-items:center;gap:10px;padding:8px 0;cursor:pointer}
.cb{width:22px;height:22px;border-radius:5px;border:2px solid var(--border);background:var(--white);display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:13px;font-weight:700}
.cb.on{background:var(--p);border-color:var(--p);color:#fff}
/* PAGE HEADER */
.phdr{background:var(--white);padding:14px 16px;border-bottom:1px solid var(--border);position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:10px}
.phdr h2{font-size:16px;font-weight:700;flex:1}
.bk{background:none;border:none;font-size:22px;cursor:pointer;padding:4px;color:var(--p);font-family:inherit}
/* FILTER */
.fbar{display:flex;gap:8px;padding:10px 16px;background:var(--white);border-bottom:1px solid var(--border);overflow-x:auto;-webkit-overflow-scrolling:touch}
.chip{padding:5px 12px;border-radius:100px;border:1.5px solid var(--border);font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap;background:var(--white);font-family:inherit;color:var(--g2);-webkit-appearance:none}
.chip.on{background:var(--p);border-color:var(--p);color:#fff}
/* LOGIN */
#page-login{background:linear-gradient(160deg,var(--pl) 0%,var(--white) 60%);min-height:100%;display:flex;flex-direction:column;justify-content:center;padding:32px 20px 40px}
.lcard{background:var(--white);border-radius:18px;padding:22px;box-shadow:0 6px 28px rgba(0,0,0,.1)}
.pw{position:relative}.pw .fi{padding-right:40px}
.eye{position:absolute;right:10px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;font-size:17px;padding:4px}
.drow{display:flex;gap:8px;justify-content:center;margin-top:14px}
.dc{padding:5px 14px;border-radius:100px;border:1.5px solid;font-size:12px;font-weight:600;cursor:pointer;background:none;font-family:inherit;-webkit-appearance:none}
/* DASH */
.dhdr{background:linear-gradient(135deg,var(--pd) 0%,var(--p) 100%);padding:18px 16px 22px;color:#fff}
.sg{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:14px}
.sb{background:rgba(255,255,255,.15);border-radius:10px;padding:10px;text-align:center}
.sv{font-size:24px;font-weight:800}.sl2{font-size:10px;opacity:.8;margin-top:2px}
.qg{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.qb{background:var(--white);border-radius:12px;padding:12px 8px;text-align:center;cursor:pointer;border:1px solid var(--border)}
.qb:active{background:var(--g5)}.qi{font-size:22px;margin-bottom:4px}.ql{font-size:11px;font-weight:600;color:var(--g2);line-height:1.3}
.brw{margin-bottom:12px}.brl{display:flex;justify-content:space-between;margin-bottom:4px}
.brt{height:7px;background:var(--g5);border-radius:4px;overflow:hidden}.brf{height:100%;border-radius:4px}
/* LIST */
.sb2{padding:12px 16px;background:var(--white);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:10}
.si{width:100%;padding:10px 14px;background:var(--g5);border:1.5px solid var(--border);border-radius:100px;font-size:14px;outline:none;font-family:inherit;-webkit-appearance:none}
.tc{display:flex;align-items:flex-start;gap:12px;padding:14px;background:var(--white);border-bottom:1px solid var(--border);cursor:pointer}
.tc:active{background:var(--g5)}.tav{width:44px;height:44px;border-radius:22px;background:var(--pl);display:flex;align-items:center;justify-content:center;font-size:19px;font-weight:800;color:var(--p);flex-shrink:0}
.tn{font-size:15px;font-weight:700;color:var(--g1)}.tm{font-size:11px;color:var(--g3);margin-top:2px}
.ia{display:flex;gap:6px;flex-shrink:0}.ib{width:32px;height:32px;border-radius:8px;background:var(--g5);border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:14px}
.fab{position:fixed;bottom:68px;right:16px;width:54px;height:54px;border-radius:27px;background:var(--p);border:none;color:#fff;font-size:26px;cursor:pointer;box-shadow:0 4px 18px rgba(15,110,86,.4);display:flex;align-items:center;justify-content:center;z-index:100;font-family:inherit}
.empty{padding:40px 16px;text-align:center}
/* DETECT */
.rc{width:120px;height:120px;border-radius:60px;border:4px solid;display:flex;flex-direction:column;align-items:center;justify-content:center;margin:0 auto}
.rp{font-size:30px;font-weight:900;line-height:1}
.zg{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px}
.zb{background:var(--g5);border-radius:10px;padding:10px;text-align:center}
.zv{font-size:19px;font-weight:800}.zl{font-size:10px;color:var(--g3);margin-top:2px}
.fdot{width:8px;height:8px;border-radius:4px;flex-shrink:0}
.fr2{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)}
.ir2{display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)}
/* GROWTH */
.cw{overflow-x:auto;-webkit-overflow-scrolling:touch}
/* QUAL */
.qt{display:flex;overflow-x:auto;gap:8px;padding:10px 16px;background:var(--white);border-bottom:1px solid var(--border)}
.ro{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:10px;border:1.5px solid var(--border);margin-bottom:8px;cursor:pointer}
.ro.sel{border-color:var(--p);background:var(--pl)}.rci{width:20px;height:20px;border-radius:10px;border:2px solid var(--border);display:flex;align-items:center;justify-content:center;flex-shrink:0}
.rci.sel{border-color:var(--p)}.rin{width:10px;height:10px;border-radius:5px;background:var(--p);display:none}
/* INFO BOX */
.ib2{display:flex;gap:10px;padding:12px;border-radius:10px;margin-bottom:12px;align-items:flex-start}
.ib2 p{font-size:13px;line-height:1.6;flex:1}
.ii{background:var(--sl);border:1px solid #B3D4F0}.ig{background:var(--pl);border:1px solid #A8DBC9}
.iy{background:var(--wl);border:1px solid #E8C895}.ir3{background:var(--rl);border:1px solid #E8AAAA}
/* EDU */
.arc{display:flex;align-items:center;gap:12px;padding:14px;background:var(--white);border-bottom:1px solid var(--border);cursor:pointer}
.arc:active{background:var(--g5)}
/* PROFILE */
.pfav{width:72px;height:72px;border-radius:36px;background:var(--pl);display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:800;color:var(--p);margin:0 auto 10px}
.ir4{display:flex;padding:9px 0;border-bottom:1px solid var(--border)}
.ik{width:110px;font-size:13px;color:var(--g3);flex-shrink:0}.iv{font-size:13px;color:var(--g1);font-weight:500}
/* USERS */
.uc{display:flex;align-items:flex-start;gap:12px;padding:13px 16px;background:var(--white);border-bottom:1px solid var(--border)}
/* MODAL */
#mo{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.5);z-index:7000;display:none;align-items:flex-end;justify-content:center}
#mo.show{display:flex}
.mb{background:var(--white);border-radius:18px 18px 0 0;padding:22px;width:100%;max-height:88vh;overflow-y:auto}
.mh{font-size:17px;font-weight:700;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center}
.mc{background:none;border:none;font-size:22px;cursor:pointer;color:var(--g3);padding:4px}
/* TOAST + SPINNER */
#toast{position:fixed;top:18px;left:50%;transform:translateX(-50%);background:var(--g1);color:#fff;padding:10px 18px;border-radius:100px;font-size:13px;font-weight:600;z-index:9999;opacity:0;pointer-events:none;max-width:88vw;text-align:center;transition:opacity .25s}
#toast.show{opacity:1}
#spin{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.3);z-index:8888;display:none;align-items:center;justify-content:center}
#spin.show{display:flex}
.sc{width:44px;height:44px;border:4px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
/* MISC */
.mr{display:flex;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)}.mr:last-child{border-bottom:none}
.mk{font-size:13px;color:var(--g2);flex:1}.mv{font-size:13px;font-weight:700}
</style>
</head>
<body>
<div id="app">
<div id="screen">

<!-- LOGIN -->
<div id="page-login" class="page active">
  <div style="text-align:center;margin-bottom:28px">
    <div style="width:72px;height:72px;border-radius:36px;background:var(--p);display:flex;align-items:center;justify-content:center;font-size:32px;margin:0 auto 10px">🩺</div>
    <div style="font-size:26px;font-weight:800;color:var(--pd)">StuntingPred</div>
    <div style="font-size:13px;color:var(--g3);margin-top:3px">Prediksi Stunting Lombok Tengah</div>
    <div style="margin-top:6px;font-size:12px;color:var(--g3)">
      <span id="dot" style="display:inline-block;width:8px;height:8px;border-radius:4px;background:#ccc;margin-right:4px"></span>
      <span id="cst">Menghubungkan...</span>
    </div>
  </div>
  <div class="lcard">
    <div style="font-size:17px;font-weight:700;margin-bottom:18px">Masuk ke Aplikasi</div>
    <div class="fg"><label class="fl">NIK / Username</label><input id="lnik" class="fi" placeholder="Masukkan NIK" autocomplete="username"></div>
    <div class="fg"><label class="fl">Password</label><div class="pw"><input id="lpwd" class="fi" type="password" placeholder="Masukkan password" autocomplete="current-password"><button class="eye" onclick="togEye()">👁️</button></div></div>
    <div id="lerr" style="display:none;color:var(--r);font-size:12px;margin-bottom:10px;padding:8px;background:var(--rl);border-radius:8px"></div>
    <button class="btn bp" id="lbtn" onclick="doLogin()">Masuk</button>
    <div style="text-align:center;margin-top:14px;font-size:12px;color:var(--g3)">Akun Demo:</div>
    <div class="drow">
      <button class="dc" style="border-color:var(--r);color:var(--r)" onclick="fillD('admin')">Admin</button>
      <button class="dc" style="border-color:var(--p);color:var(--p)" onclick="fillD('kader')">Kader</button>
      <button class="dc" style="border-color:var(--s);color:var(--s)" onclick="fillD('peneliti')">Peneliti</button>
    </div>
  </div>
  <div style="text-align:center;margin-top:18px;font-size:11px;color:var(--g3);line-height:1.8">Peneliti: Heri Bahtiar · UMS 2025<br>Kabupaten Lombok Tengah, NTB</div>
</div>

<!-- DASHBOARD -->
<div id="page-dashboard" class="page">
  <div class="dhdr">
    <div style="font-size:12px;opacity:.8">Selamat datang,</div>
    <div style="font-size:20px;font-weight:800" id="dname">—</div>
    <div style="font-size:11px;opacity:.7;margin-top:2px" id="drole">—</div>
    <div class="sg">
      <div class="sb"><div class="sv" id="stot">0</div><div class="sl2">Total Balita</div></div>
      <div class="sb" style="background:rgba(163,45,45,.3)"><div class="sv" id="shi">0</div><div class="sl2">Risiko Tinggi</div></div>
      <div class="sb" style="background:rgba(133,79,11,.3)"><div class="sv" id="sme">0</div><div class="sl2">Risiko Sedang</div></div>
    </div>
  </div>
  <div class="pad">
    <div id="dabar" style="display:none;margin-bottom:10px">
      <div style="display:flex;gap:8px">
        <button class="btn bp bsm" onclick="goTo('users')">👥 Kelola Kader</button>
        <button class="btn bs2 bsm" onclick="goTo('logs')">📋 Log</button>
      </div>
    </div>
    <div id="dalert" class="ib2 ir3" style="display:none;cursor:pointer" onclick="goTo('toddlers')">
      <span style="font-size:18px">🚨</span>
      <div><div style="font-size:13px;font-weight:700;color:var(--r)" id="dalt"></div><div style="font-size:11px;color:var(--r)">Tap untuk lihat daftar</div></div>
    </div>
    <div class="card">
      <div class="ct">⚡ Akses Cepat</div>
      <div class="qg">
        <div class="qb" onclick="gAdd()"><div class="qi">➕</div><div class="ql">Daftarkan Balita</div></div>
        <div class="qb" onclick="goTo('detect')"><div class="qi">🔍</div><div class="ql">Deteksi Risiko</div></div>
        <div class="qb" onclick="goTo('growth')"><div class="qi">📈</div><div class="ql">Pemantauan</div></div>
        <div class="qb" onclick="goTo('qual')"><div class="qi">💬</div><div class="ql">Wawancara</div></div>
        <div class="qb" onclick="goTo('edu')"><div class="qi">📚</div><div class="ql">Edukasi</div></div>
        <div class="qb" onclick="goTo('report')"><div class="qi">📄</div><div class="ql">Laporan</div></div>
      </div>
    </div>
    <div class="card"><div class="ct">🗺️ Prevalensi per Zona</div><div id="zbars"><div style="color:var(--g3);font-size:13px">Memuat...</div></div></div>
    <div class="card"><div class="ct">🔬 Validasi Model</div>
      <div class="mr"><span class="mk">ROC-AUC</span><span class="mv">0.87 ✅</span></div>
      <div class="mr"><span class="mk">Sensitivitas</span><span class="mv">82.4% ✅</span></div>
      <div class="mr"><span class="mk">Spesifisitas</span><span class="mv">79.1% ✅</span></div>
      <div style="font-size:11px;color:var(--g3);margin-top:6px">Multiple Logistic Regression · Heri Bahtiar (2025)</div>
    </div>
    <div class="card"><div class="ct">📋 Pengukuran Terbaru</div><div id="rlist"><div style="color:var(--g3);font-size:13px">Memuat...</div></div></div>
  </div>
</div>

<!-- TODDLER LIST -->
<div id="page-toddlers" class="page">
  <div class="sb2"><input class="si" id="tsrch" placeholder="🔍  Cari nama atau NIK..." oninput="renderList()"></div>
  <div class="fbar">
    <button class="chip on" onclick="setZone(this,'all')">📍 Semua</button>
    <button class="chip" onclick="setZone(this,'hills')">⛰️ Bukit</button>
    <button class="chip" onclick="setZone(this,'lowlands')">🌾 Dataran</button>
    <button class="chip" onclick="setZone(this,'coastal')">🏖️ Pantai</button>
  </div>
  <div id="tlist"></div>
  <button class="fab" onclick="gAdd()">+</button>
</div>

<!-- FORM BALITA -->
<div id="page-form" class="page">
  <div class="phdr"><button class="bk" onclick="goBack()">←</button><h2 id="fttl">Daftarkan Balita</h2></div>
  <div class="pad">
    <div class="ib2 ii"><span>ℹ️</span><p>Field <span class="req">*</span> wajib diisi untuk akurasi prediksi.</p></div>
    <div class="card"><div class="ct">👶 Identitas Balita</div>
      <input type="hidden" id="fid">
      <div class="fg"><label class="fl">Nama Lengkap <span class="req">*</span></label><input id="fname" class="fi" placeholder="Nama lengkap balita"></div>
      <div class="fg"><label class="fl">NIK Balita</label><input id="fnik" class="fi" placeholder="Opsional"></div>
      <div class="fg"><label class="fl">Tanggal Lahir <span class="req">*</span></label><input id="fbdate" class="fi" type="date"></div>
      <div class="fg"><label class="fl">Jenis Kelamin <span class="req">*</span></label><select id="fgender" class="fs"><option value="male">♂ Laki-laki</option><option value="female">♀ Perempuan</option></select></div>
      <div class="fr"><div class="fg"><label class="fl">Berat Lahir (kg)</label><input id="fbw" class="fi" type="number" step="0.1" placeholder="kg"></div><div class="fg"><label class="fl">Panjang Lahir (cm)</label><input id="fbh" class="fi" type="number" step="0.1" placeholder="cm"></div></div>
      <div class="fg"><label class="fl">Zona Ekologi <span class="req">*</span></label><select id="fzone" class="fs"><option value="hills">⛰️ Bukit</option><option value="lowlands" selected>🌾 Dataran Rendah</option><option value="coastal">🏖️ Pantai</option></select></div>
      <div class="fg"><label class="fl">Desa / Kelurahan</label><input id="fvill" class="fi" placeholder="Nama desa"></div>
    </div>
    <div class="card"><div class="ct">👩 Data Ibu</div>
      <div class="fg"><label class="fl">Nama Ibu <span class="req">*</span></label><input id="fmname" class="fi" placeholder="Nama lengkap ibu"></div>
      <div class="fr"><div class="fg"><label class="fl">Usia Ibu (thn)</label><input id="fmage" class="fi" type="number" placeholder="tahun"></div><div class="fg"><label class="fl">Tinggi Ibu (cm)</label><input id="fmht" class="fi" type="number" step="0.1" placeholder="cm" oninput="chkMH()"></div></div>
      <div id="mhw" class="ib2 iy" style="display:none"><span>⚠️</span><p>Tinggi ibu &lt;150 cm — faktor risiko stunting (OR=1.9)</p></div>
      <div class="fg"><label class="fl">Pendidikan Ibu</label><select id="fmedu" class="fs"><option value="none">Tidak sekolah</option><option value="sd">SD</option><option value="smp">SMP</option><option value="sma" selected>SMA/SMK</option><option value="pt">Perguruan Tinggi</option></select></div>
      <div class="cbr" onclick="togCb('fmil')"><div id="fmil-b" class="cb"></div><input type="hidden" id="fmil" value="0"><span style="font-size:13px">Riwayat penyakit saat hamil</span></div>
      <div class="cbr" onclick="togCb('fctps')"><div id="fctps-b" class="cb on">✓</div><input type="hidden" id="fctps" value="1"><span style="font-size:13px">CTPS (Cuci Tangan Pakai Sabun) rutin</span></div>
    </div>
    <div class="card"><div class="ct">👨 Data Ayah</div>
      <div class="fg"><label class="fl">Pendidikan Ayah</label><select id="ffedu" class="fs"><option value="none">Tidak sekolah</option><option value="sd">SD</option><option value="smp">SMP</option><option value="sma" selected>SMA/SMK</option><option value="pt">Perguruan Tinggi</option></select></div>
      <div class="fr"><div class="fg"><label class="fl">Pendapatan (Rp/bln)</label><input id="finc" class="fi" type="number" placeholder="Rupiah"></div><div class="fg"><label class="fl">Jml Anggota</label><input id="fmem" class="fi" type="number" placeholder="orang"></div></div>
    </div>
    <div class="card"><div class="ct">🏠 Sanitasi</div>
      <div class="ib2 iy"><span>⚠️</span><p>Sanitasi buruk = prediktor terkuat stunting (OR=2.1)</p></div>
      <div class="fg"><label class="fl">Sumber Air Minum</label><select id="fwater" class="fs" onchange="updSan()"><option value="pam">Air PAM/PDAM</option><option value="well" selected>Sumur terlindung</option><option value="spring">Mata air</option><option value="river">Sungai/terbuka</option></select></div>
      <div class="fg"><label class="fl">Fasilitas Jamban</label><select id="ftoilet" class="fs" onchange="updSan()"><option value="own" selected>Jamban sendiri</option><option value="shared">Jamban bersama</option><option value="none">Tidak ada</option></select></div>
      <div class="fg"><label class="fl">Pengelolaan Sampah</label><select id="fwaste" class="fs" onchange="updSan()"><option value="collected" selected>Diangkut petugas</option><option value="pit">Lubang galian</option><option value="burned">Dibakar</option><option value="dump">Sembarangan</option></select></div>
      <div class="fg"><label class="fl">Jenis Lantai</label><select id="ffloor" class="fs" onchange="updSan()"><option value="tile">Keramik</option><option value="cement" selected>Semen/Batu</option><option value="wood">Kayu/Bambu</option><option value="dirt">Tanah</option></select></div>
      <div id="sanbox" class="ib2 ig"><span>🏠</span><p>Skor Sanitasi: <strong id="sansc">7</strong>/10</p></div>
    </div>
    <div class="card"><div class="ct">📋 Riwayat Balita</div>
      <div class="cbr" onclick="togCb('fasi')"><div id="fasi-b" class="cb"></div><input type="hidden" id="fasi" value="0"><span style="font-size:13px">ASI Eksklusif 6 bulan</span></div>
      <div class="cbr" onclick="togCb('finf')"><div id="finf-b" class="cb"></div><input type="hidden" id="finf" value="0"><span style="font-size:13px">Riwayat penyakit infeksi berulang</span></div>
    </div>
    <button class="btn bp" onclick="saveTod()">💾 Simpan Data Balita</button>
    <div style="height:16px"></div>
  </div>
</div>

<!-- DETECT -->
<div id="page-detect" class="page">
  <div class="phdr"><button class="bk" onclick="goBack()">←</button><h2>Deteksi Risiko Stunting</h2></div>
  <div class="pad">
    <div class="card"><div class="ct">👶 Pilih Balita</div><select id="dtod" class="fs" onchange="onSelTod()"><option value="">— Hitung Cepat —</option></select><div id="dtinfo" style="margin-top:10px;display:none"></div></div>
    <div class="card"><div class="ct">📏 Antropometri</div>
      <div class="fg"><label class="fl">Tanggal Pengukuran</label><input id="ddate" class="fi" type="date"></div>
      <div class="fr"><div class="fg"><label class="fl">Tinggi Badan (cm) <span class="req">*</span></label><input id="dht" class="fi" type="number" step="0.1" placeholder="cm"></div><div class="fg"><label class="fl">Berat Badan (kg)</label><input id="dwt" class="fi" type="number" step="0.1" placeholder="kg"></div></div>
      <div class="fg"><label class="fl">Catatan</label><textarea id="dnotes" class="ft" placeholder="Kondisi saat pengukuran..."></textarea></div>
      <button class="btn bp" onclick="runDet()">🔍 Hitung Prediksi</button>
    </div>
    <div id="detres" style="display:none">
      <div class="card" id="rescard">
        <div class="ct">📊 Hasil Prediksi</div>
        <div style="display:flex;justify-content:center;padding:14px 0"><div class="rc" id="rcirc"><div class="rp" id="rpct">—</div><div style="font-size:11px;margin-top:2px">probabilitas</div></div></div>
        <div style="text-align:center;margin-bottom:12px"><span id="rrbadge" class="badge" style="font-size:14px;padding:5px 14px">—</span>&nbsp;<span id="rsbadge" class="badge">—</span></div>
        <div class="zg"><div class="zb"><div class="zv" id="rz">—</div><div class="zl">Z-Score TB/U</div></div><div class="zb"><div class="zv" id="rage">—</div><div class="zl">Usia (bln)</div></div><div class="zb"><div class="zv" id="rht2">—</div><div class="zl">Tinggi (cm)</div></div></div>
      </div>
      <div class="card" id="faccard" style="display:none"><div class="ct">⚠️ Faktor Risiko</div><div id="faclist"></div></div>
      <div class="card"><div class="ct">💊 Rekomendasi</div><div id="intlist"></div></div>
      <button id="bsavm" class="btn bp" onclick="saveMeas()" style="display:none;margin-bottom:16px">💾 Simpan Pengukuran</button>
    </div>
  </div>
</div>

<!-- GROWTH -->
<div id="page-growth" class="page">
  <div class="phdr"><button class="bk" onclick="goBack()">←</button><h2>Pemantauan Pertumbuhan</h2></div>
  <div style="display:flex;gap:8px;padding:10px 16px;background:var(--white);border-bottom:1px solid var(--border);overflow-x:auto" id="gchips"></div>
  <div class="pad" id="gcont"></div>
</div>

<!-- QUAL -->
<div id="page-qual" class="page">
  <div class="phdr"><button class="bk" onclick="goBack()">←</button><h2>Data Kualitatif (IDI)</h2></div>
  <div class="qt">
    <button class="chip on" onclick="setQT(0,this)">🎭 Sosiobudaya</button>
    <button class="chip" onclick="setQT(1,this)">📚 Pengetahuan</button>
    <button class="chip" onclick="setQT(2,this)">🏥 Akses</button>
    <button class="chip" onclick="setQT(3,this)">💧 Sanitasi</button>
  </div>
  <div class="pad">
    <div class="card"><div class="ct">📋 Info Wawancara</div>
      <div class="fg"><label class="fl">Terkait Balita</label><select id="qtod" class="fs"><option value="">— Tidak terkait —</option></select></div>
      <div class="fr"><div class="fg"><label class="fl">Kode Responden <span class="req">*</span></label><input id="qcode" class="fi" placeholder="R01..."></div><div class="fg"><label class="fl">Tanggal <span class="req">*</span></label><input id="qdate" class="fi" type="date"></div></div>
      <div class="fg"><label class="fl">Jenis Wawancara</label><select id="qtype" class="fs"><option value="idi">IDI</option><option value="fgd">FGD</option><option value="obs">Observasi</option></select></div>
      <div class="fg"><label class="fl">Sentimen</label><select id="qsent" class="fs"><option value="">— Pilih —</option><option value="positive">😊 Positif</option><option value="neutral">😐 Netral</option><option value="hesitant">😕 Ragu</option><option value="negative">😟 Negatif</option></select></div>
      <div class="fg"><label class="fl">Kode Tema</label><input id="qthemes" class="fi" placeholder="T1, T2, T3..."></div>
    </div>
    <div id="qs0" class="card"><div class="ct">🎭 Sosiobudaya</div>
      <div class="fg"><label class="fl">Pantangan makanan kehamilan?</label><div id="rtaboo"></div></div>
      <div class="fg"><label class="fl">Pengambil keputusan gizi?</label><div id="rdecision"></div></div>
      <div class="fg"><label class="fl">Kepercayaan lokal terkait gizi anak</label><textarea id="qbeliefs" class="ft" placeholder="Catat verbatim..."></textarea></div>
    </div>
    <div id="qs1" class="card" style="display:none"><div class="ct">📚 Pengetahuan</div>
      <div class="cbr" onclick="togCb('qak')"><div id="qak-b" class="cb"></div><input type="hidden" id="qak" value="0"><span style="font-size:13px">Mengetahui pentingnya ASI eksklusif</span></div>
      <div class="fg"><label class="fl">Pengetahuan tentang stunting</label><textarea id="qsk" class="ft" placeholder="Catat verbatim..."></textarea></div>
      <div class="fg"><label class="fl">Praktik MP-ASI</label><textarea id="qmpasi" class="ft" placeholder="Describe..."></textarea></div>
    </div>
    <div id="qs2" class="card" style="display:none"><div class="ct">🏥 Akses Layanan</div>
      <div class="fg"><label class="fl">Frekuensi posyandu</label><div id="rposyandu"></div></div>
      <div class="fg"><label class="fl">Hambatan akses layanan</label><textarea id="qbarr" class="ft" placeholder="Jarak, biaya..."></textarea></div>
    </div>
    <div id="qs3" class="card" style="display:none"><div class="ct">💧 Sanitasi</div>
      <div class="fg"><label class="fl">Kualitas air minum</label><div id="rwater2"></div></div>
      <div class="fg"><label class="fl">Penggunaan MCK</label><div id="rtoilet2"></div></div>
    </div>
    <div class="card"><div class="ct">📝 Catatan Verbatim</div><textarea id="qverb" class="ft" style="height:120px" placeholder='"Menurut saya anak pendek itu wajar..."'></textarea></div>
    <button class="btn bp" onclick="saveQual()">💾 Simpan Data Wawancara</button>
  </div>
</div>

<!-- EDU -->
<div id="page-edu" class="page">
  <div class="phdr"><button class="bk" onclick="goBack()">←</button><h2>Edukasi Kesehatan</h2></div>
  <div id="edulist"></div>
  <div id="edudet" style="display:none">
    <div style="padding:14px 16px 6px"><button class="btn bs2 bsm" onclick="closeEdu()">← Kembali</button></div>
    <div class="pad" id="edudetc"></div>
  </div>
</div>

<!-- REPORT -->
<div id="page-report" class="page">
  <div class="phdr"><button class="bk" onclick="goBack()">←</button><h2>Laporan &amp; Ekspor</h2></div>
  <div class="pad" id="rptc"></div>
</div>

<!-- PROFILE -->
<div id="page-profile" class="page">
  <div class="phdr"><button class="bk" onclick="goBack()">←</button><h2>Profil</h2></div>
  <div class="pad">
    <div class="card" style="text-align:center;padding:22px"><div class="pfav" id="pfav"></div><div style="font-size:19px;font-weight:800" id="pfnm"></div><div style="font-size:13px;color:var(--g3);margin-top:3px" id="pfrl"></div></div>
    <div class="card"><div class="ct">Informasi Akun</div>
      <div class="ir4"><span class="ik">NIK</span><span class="iv" id="pfnik"></span></div>
      <div class="ir4"><span class="ik">Role</span><span class="iv" id="pfrl2"></span></div>
      <div class="ir4"><span class="ik">Puskesmas</span><span class="iv" id="pfpk"></span></div>
    </div>
    <div class="card" id="pfadmin" style="display:none"><div class="ct">👥 Admin Panel</div>
      <button class="btn bp bsm" onclick="goTo('users')" style="margin-bottom:8px">Kelola Kader &amp; Pengguna</button>
      <button class="btn bs2 bsm" onclick="goTo('logs')">Log Aktivitas</button>
    </div>
    <div class="card"><div class="ct">🔒 Ganti Password</div>
      <div class="fg"><label class="fl">Password Lama</label><input id="pold" class="fi" type="password" placeholder="Password lama"></div>
      <div class="fg"><label class="fl">Password Baru (min 6)</label><input id="pnew" class="fi" type="password" placeholder="Password baru"></div>
      <button class="btn bw2 bsm" onclick="changePwd()">Ganti Password</button>
    </div>
    <div class="card" style="background:var(--pl);border-color:var(--pm)"><div class="ct" style="color:var(--p)">📚 Tentang</div><p style="font-size:12px;color:var(--pd);line-height:1.8">Heri Bahtiar · UMS 2025<br>Mixed Method Approach<br>Model: Multiple Logistic Regression · ROC-AUC 0.87<br>v3.0 · Online · PythonAnywhere</p></div>
    <button class="btn bd" onclick="doLogout()">🚪 Keluar</button>
  </div>
</div>

<!-- USERS -->
<div id="page-users" class="page">
  <div class="phdr"><button class="bk" onclick="goBack()">←</button><h2>Kelola Kader &amp; Pengguna</h2><button class="btn bp bsm" onclick="openAddUser()">➕ Tambah</button></div>
  <div style="background:var(--white);border-bottom:1px solid var(--border);padding:8px 16px">
    <div style="display:flex;gap:8px;overflow-x:auto">
      <button class="chip on" onclick="filterU(this,'all')">👥 Semua</button>
      <button class="chip" onclick="filterU(this,'kader')">🧑‍⚕️ Kader</button>
      <button class="chip" onclick="filterU(this,'admin')">👑 Admin</button>
      <button class="chip" onclick="filterU(this,'active')">✅ Aktif</button>
      <button class="chip" onclick="filterU(this,'inactive')">🚫 Nonaktif</button>
    </div>
  </div>
  <div id="ustats" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;padding:10px 16px;background:var(--white);border-bottom:1px solid var(--border)"></div>
  <div id="ulist"></div>
</div>

<!-- FORCE CHANGE PWD -->
<div id="page-forcepwd" class="page">
  <div style="background:linear-gradient(160deg,var(--wl) 0%,var(--white) 60%);min-height:100%;display:flex;flex-direction:column;justify-content:center;padding:32px 20px">
    <div style="text-align:center;margin-bottom:22px"><div style="font-size:44px;margin-bottom:8px">🔐</div><div style="font-size:19px;font-weight:700;color:var(--w)">Ganti Password</div><div style="font-size:12px;color:var(--g3);margin-top:4px;line-height:1.6">Admin meminta Anda mengganti password<br>sebelum menggunakan aplikasi</div></div>
    <div class="lcard">
      <div class="fg"><label class="fl">Password Lama <span class="req">*</span></label><input id="fpold" class="fi" type="password" placeholder="Password dari admin"></div>
      <div class="fg"><label class="fl">Password Baru <span class="req">*</span></label><input id="fpnew" class="fi" type="password" placeholder="Min 6 karakter"></div>
      <div class="fg"><label class="fl">Konfirmasi <span class="req">*</span></label><input id="fpcnf" class="fi" type="password" placeholder="Ulangi password baru"></div>
      <div id="fperr" class="ib2 ir3" style="display:none"><span>⚠️</span><p id="fperrtxt"></p></div>
      <button class="btn bp" onclick="doForcePwd()">🔐 Ganti &amp; Masuk</button>
    </div>
  </div>
</div>

<!-- LOGS -->
<div id="page-logs" class="page">
  <div class="phdr"><button class="bk" onclick="goBack()">←</button><h2>Log Aktivitas</h2></div>
  <div class="pad" id="logscont"></div>
</div>

</div><!-- /screen -->

<nav id="nav">
  <button class="nb" id="nb-dashboard" onclick="goTo('dashboard')"><div class="ni">🏠</div><span>Dashboard</span></button>
  <button class="nb" id="nb-toddlers"  onclick="goTo('toddlers')"> <div class="ni">👶</div><span>Balita</span></button>
  <button class="nb" id="nb-detect"    onclick="goTo('detect')">   <div class="ni">🔍</div><span>Deteksi</span></button>
  <button class="nb" id="nb-growth"    onclick="goTo('growth')">   <div class="ni">📈</div><span>Tumbuh</span></button>
  <button class="nb" id="nb-profile"   onclick="goTo('profile')">  <div class="ni">👤</div><span>Profil</span></button>
</nav>
</div>

<div id="mo" onclick="closeModal()"><div class="mb" onclick="event.stopPropagation()"><div class="mh"><span id="mttl">—</span><button class="mc" onclick="closeModal()">✕</button></div><div id="mbody"></div></div></div>
<div id="spin"><div class="sc"></div></div>
<div id="toast"></div>

<script>
// ── CONFIG ──────────────────────────────────────────
var BASE = '';  // Otomatis gunakan domain yang sama

// ── WHO TABLES ─────────────────────────────────────
var WHO_B={0:49.9,1:54.7,2:58.4,3:61.4,4:63.9,5:65.9,6:67.6,7:69.2,8:70.6,9:72,10:73.3,11:74.5,12:75.7,15:79.1,18:82.3,21:85.1,24:87.8,27:90.3,30:92.7,33:95,36:96.1,39:97.8,42:99.9,45:102,48:103.3,51:104.9,54:106.5,57:108.2,59:110};
var WHO_G={0:49.1,1:53.7,2:57.1,3:59.8,4:62.1,5:64,6:65.7,7:67.3,8:68.7,9:70.1,10:71.5,11:72.8,12:74,15:77.5,18:80.7,21:83.7,24:86.4,27:89,30:91.4,33:93.7,36:95.1,39:97.3,42:99.4,45:101.5,48:102.7,51:104.3,54:105.9,57:107.5,59:109.4};

function getMedian(age,sex){
  var T=sex==='male'?WHO_B:WHO_G;
  var ages=Object.keys(T).map(Number).sort(function(a,b){return a-b});
  if(age<=ages[0]) return T[ages[0]];
  if(age>=ages[ages.length-1]) return T[ages[ages.length-1]];
  for(var i=0;i<ages.length-1;i++){
    if(age>=ages[i]&&age<=ages[i+1]){
      var r=(age-ages[i])/(ages[i+1]-ages[i]);
      return T[ages[i]]+r*(T[ages[i+1]]-T[ages[i]]);
    }
  }
  return T[ages[0]];
}
function calcZ(h,age,sex){if(!h||age<0||age>59)return null;var m=getMedian(age,sex);return parseFloat(((h-m)/(m*0.045)).toFixed(2));}
function zSt(z){
  if(z===null)return{st:'N/A',color:'#888',cls:'bn'};
  if(z<-3)return{st:'Severely Stunted',color:'#A32D2D',cls:'bss'};
  if(z<-2)return{st:'Stunted',color:'#854F0B',cls:'bs'};
  if(z>3)return{st:'Tinggi',color:'#185FA5',cls:'bt'};
  return{st:'Normal',color:'#0F6E56',cls:'bn'};
}

// ── PREDICTION MODEL ────────────────────────────────
function predRisk(inp){
  var CF={ic:-3.102,ma:0.105,mh:-0.045,mi:0.321,ta:0.072,gm:0.41,fe:0.289,lz:0.205,tg:-0.35,sp:0.742,nb:0.28,ih:0.34,lb:0.42,nh:0.21};
  var mAge=inp.mAge||28,mHt=inp.mHt||150,aM=inp.aM||12,bW=inp.bW||3,sS=inp.sS!==undefined?inp.sS:5;
  var logit=CF.ic+CF.ma*mAge+CF.mh*mHt+CF.mi*(inp.mIll?1:0)+CF.ta*aM+CF.gm*(inp.gender==='male'?1:0)+CF.fe+(['none','sd','smp'].indexOf(inp.fEdu)>=0?1:0)+CF.lz*(inp.zone==='lowlands'?1:0)+CF.tg*(inp.toilet==='own'?1:0)+CF.sp*(sS<4?1:0)+CF.nb*(inp.asi?0:1)+CF.ih*(inp.inf?1:0)+CF.lb*(bW<2.5?1:0)+CF.nh*(inp.ctps?0:1);
  var prob=parseFloat((1/(1+Math.exp(-logit))).toFixed(4));
  var rl,rc,rb;
  if(prob>=0.65){rl='Tinggi';rc='#A32D2D';rb='#FCEBEB';}
  else if(prob>=0.4){rl='Sedang';rc='#854F0B';rb='#FAEEDA';}
  else{rl='Rendah';rc='#0F6E56';rb='#E1F5EE';}
  var facs=[];
  if(mHt<150)facs.push({l:'Tinggi ibu <150 cm',or:1.9,w:'h'});
  if(sS<4)facs.push({l:'Sanitasi buruk',or:2.1,w:'h'});
  if(inp.gender==='male')facs.push({l:'Laki-laki',or:1.8,w:'h'});
  if(mAge>35)facs.push({l:'Usia ibu >35 thn',or:1.6,w:'m'});
  if(bW<2.5)facs.push({l:'BBLR <2.5 kg',or:1.5,w:'h'});
  if(inp.mIll)facs.push({l:'Riwayat penyakit ibu',or:1.4,w:'m'});
  if(inp.inf)facs.push({l:'Riwayat infeksi',or:1.4,w:'m'});
  if(!inp.asi)facs.push({l:'Tidak ASI eksklusif',or:1.3,w:'m'});
  if(!inp.ctps)facs.push({l:'Tidak CTPS',or:1.2,w:'l'});
  var ivs;
  if(rl==='Tinggi')ivs=[{l:'Rujuk segera ke Puskesmas',p:'c'},{l:'PMT (Pemberian Makanan Tambahan)',p:'h'},{l:'Perbaikan sanitasi',p:'h'},{l:'Pantau intensif 2 minggu',p:'h'}];
  else if(rl==='Sedang')ivs=[{l:'Konseling gizi dan MP-ASI',p:'h'},{l:'Kunjungan posyandu rutin',p:'m'},{l:'Verifikasi imunisasi',p:'m'}];
  else ivs=[{l:'Pemantauan rutin posyandu',p:'l'}];
  return{prob:prob,rl:rl,rc:rc,rb:rb,facs:facs,ivs:ivs};
}
function calcAge(bd){if(!bd)return 0;var b=new Date(bd),n=new Date();return Math.max(0,Math.min(59,(n.getFullYear()-b.getFullYear())*12+(n.getMonth()-b.getMonth())));}
function sanScore(d){var s=0;if(d.water==='pam')s+=3;else if(d.water==='well'||d.water==='spring')s+=2;if(d.toilet==='own')s+=3;else if(d.toilet==='shared')s+=1;if(d.waste==='collected')s+=2;else if(d.waste==='pit')s+=1;if(d.floor==='tile'||d.floor==='cement')s+=1;if(d.ctps)s+=1;return Math.min(s,10);}

// ── STATE ──────────────────────────────────────────
var TOKEN='',CU=null,STACK=[],TCACHE=[],UCACHE=[],DET_RES=null,DET_TOD=null,SEL_G=null,EDIT_TID=null,ZF='all',UF='all',QTAB=0,RVALS={};

function loadS(){try{var t=localStorage.getItem('sp_tk');var u=localStorage.getItem('sp_cu');if(t&&u){TOKEN=t;CU=JSON.parse(u);}}catch(e){}}
function saveS(t,u){TOKEN=t;CU=u;try{localStorage.setItem('sp_tk',t);localStorage.setItem('sp_cu',JSON.stringify(u));}catch(e){}}
function clearS(){TOKEN='';CU=null;try{localStorage.removeItem('sp_tk');localStorage.removeItem('sp_cu');}catch(e){}}

// ── API ────────────────────────────────────────────
function api(method,path,body,cb){
  var xhr=new XMLHttpRequest();
  xhr.open(method,BASE+'/api'+path,true);
  xhr.setRequestHeader('Content-Type','application/json');
  if(TOKEN)xhr.setRequestHeader('Authorization','Bearer '+TOKEN);
  xhr.timeout=20000;
  xhr.onload=function(){
    try{cb(null,JSON.parse(xhr.responseText));}
    catch(e){cb({error:'Parse error'},null);}
  };
  xhr.onerror=function(){cb({error:'Tidak bisa terhubung ke server'},null);};
  xhr.ontimeout=function(){cb({error:'Timeout. Coba lagi.'},null);};
  if(body)xhr.send(JSON.stringify(body));
  else xhr.send();
}
function GET(p,cb){api('GET',p,null,cb);}
function POST(p,b,cb){api('POST',p,b,cb);}
function PUT(p,b,cb){api('PUT',p,b,cb);}
function DEL(p,cb){api('DELETE',p,null,cb);}

// ── UI HELPERS ─────────────────────────────────────
function ge(id){return document.getElementById(id);}
function toast(msg,dur){var el=ge('toast');el.textContent=msg;el.className='show';clearTimeout(el._t);el._t=setTimeout(function(){el.className='';},dur||2600);}
function spin(on){ge('spin').className=on?'show':'';}
function setConn(on){var dot=ge('dot'),st=ge('cst');if(dot)dot.style.background=on?'#0F6E56':'#ccc';if(st)st.textContent=on?'● Terhubung ke server':'● Periksa koneksi';}

// ── NAV ────────────────────────────────────────────
function showPage(name){
  var ps=document.querySelectorAll('.page');
  for(var i=0;i<ps.length;i++)ps[i].classList.remove('active');
  var el=ge('page-'+name);if(el)el.classList.add('active');
  var scr=ge('screen');if(scr)scr.scrollTop=0;
  var bs=document.querySelectorAll('.nb');
  for(var j=0;j<bs.length;j++)bs[j].classList.remove('on');
  var nb=ge('nb-'+name);if(nb)nb.classList.add('on');
}
function goTo(name){STACK.push(name);showPage(name);onEnter(name);}
function goBack(){if(STACK.length>1)STACK.pop();var prev=STACK[STACK.length-1]||'dashboard';showPage(prev);onEnter(prev);}
function onEnter(name){
  if(name==='dashboard')rdDash();
  else if(name==='toddlers')renderList();
  else if(name==='detect')initDet();
  else if(name==='growth')initGrowth();
  else if(name==='qual')initQual();
  else if(name==='edu')rdEdu();
  else if(name==='report')rdReport();
  else if(name==='profile')rdProfile();
  else if(name==='users')rdUsers();
  else if(name==='logs')rdLogs();
}
function openModal(title,body){ge('mttl').textContent=title;ge('mbody').innerHTML=body;ge('mo').className='show';}
function closeModal(){ge('mo').className='';}

// ── LOGIN ──────────────────────────────────────────
function togEye(){var i=ge('lpwd');i.type=i.type==='password'?'text':'password';}
function fillD(r){
  var m={admin:['superadmin','admin123'],kader:['kader001','kader123'],peneliti:['1901234567890001','peneliti123']};
  ge('lnik').value=m[r][0];ge('lpwd').value=m[r][1];
  ge('lbtn').click();
}
function showLErr(msg){var el=ge('lerr');el.textContent=msg;el.style.display=msg?'block':'none';}
function doLogin(){
  var nik=(ge('lnik').value||'').trim();
  var pwd=(ge('lpwd').value||'').trim();
  showLErr('');
  if(!nik||!pwd){showLErr('NIK dan password wajib diisi');return;}
  ge('lbtn').disabled=true;ge('lbtn').textContent='Memproses...';
  POST('/auth/login',{nik:nik,password:pwd},function(err,res){
    ge('lbtn').disabled=false;ge('lbtn').textContent='Masuk';
    if(err){showLErr(err.error||'Tidak dapat terhubung ke server');setConn(false);return;}
    if(!res.success){showLErr(res.error||'NIK atau password salah');return;}
    setConn(true);
    saveS(res.data.token,res.data.user);
    if(res.data.must_change_pwd){
      ge('nav').classList.remove('show');
      STACK=['forcepwd'];showPage('forcepwd');
    } else {
      ge('nav').classList.add('show');
      STACK=[];goTo('dashboard');
    }
  });
}
function doLogout(){if(!confirm('Yakin keluar?'))return;clearS();ge('nav').classList.remove('show');STACK=[];showPage('login');setConn(false);}

// ── FORCE CHANGE PWD ───────────────────────────────
function doForcePwd(){
  var old=(ge('fpold').value||'').trim(),nw=(ge('fpnew').value||'').trim(),cf=(ge('fpcnf').value||'').trim();
  var errEl=ge('fperr'),errTxt=ge('fperrtxt');
  if(!old||!nw||!cf){errTxt.textContent='Semua field wajib diisi';errEl.style.display='flex';return;}
  if(nw.length<6){errTxt.textContent='Password baru minimal 6 karakter';errEl.style.display='flex';return;}
  if(nw!==cf){errTxt.textContent='Konfirmasi tidak cocok';errEl.style.display='flex';return;}
  if(old===nw){errTxt.textContent='Password baru harus berbeda';errEl.style.display='flex';return;}
  spin(true);
  POST('/auth/change-password',{old_password:old,new_password:nw},function(err,res){
    spin(false);
    if(err||!res.success){errTxt.textContent=(err?err.error:res.error);errEl.style.display='flex';return;}
    toast('✅ Password berhasil diubah!');
    ge('nav').classList.add('show');STACK=[];goTo('dashboard');
  });
}

// ── DASHBOARD ──────────────────────────────────────
function rdDash(){
  if(!CU)return;
  var RL={admin:'Administrator',kader:'Kader Posyandu',researcher:'Peneliti'};
  ge('dname').textContent=CU.name;ge('drole').textContent=CU.puskesmas||RL[CU.role]||CU.role;
  var ab=ge('dabar');if(ab)ab.style.display=CU.role==='admin'?'block':'none';
  GET('/dashboard',function(err,res){
    if(err||!res.success)return;
    var d=res.data;
    ge('stot').textContent=d.total||0;
    var hi=0,me=0;
    for(var i=0;i<(d.by_risk||[]).length;i++){if(d.by_risk[i].risk_level==='Tinggi')hi=d.by_risk[i].n;else if(d.by_risk[i].risk_level==='Sedang')me=d.by_risk[i].n;}
    ge('shi').textContent=hi;ge('sme').textContent=me;
    var al=ge('dalert');
    if(hi>0){al.style.display='flex';ge('dalt').textContent=hi+' Balita Risiko Tinggi!';}else al.style.display='none';
    // Zone bars
    var ZL={hills:'⛰️ Bukit',lowlands:'🌾 Dataran',coastal:'🏖️ Pantai'};
    var zEl=ge('zbars');zEl.innerHTML='';
    for(var i=0;i<(d.by_zone||[]).length;i++){
      var z=d.by_zone[i];if(!z.total)continue;
      var pct=(z.stunted/z.total*100).toFixed(1);
      var col=pct>35?'var(--r)':pct>20?'var(--w)':'var(--p)';
      zEl.innerHTML+='<div class="brw"><div class="brl"><span style="font-size:12px;font-weight:600;color:var(--g2)">'+(ZL[z.zone]||z.zone)+'</span><span style="font-size:13px;font-weight:700;color:'+col+'">'+z.stunted+'/'+z.total+' ('+pct+'%)</span></div><div class="brt"><div class="brf" style="width:'+Math.min(100,pct)+'%;background:'+col+'"></div></div></div>';
    }
    if(!d.by_zone||!d.by_zone.length)zEl.innerHTML='<p style="font-size:13px;color:var(--g3)">Belum ada data</p>';
    // Recent
    var BC={Tinggi:'bh',Sedang:'bm',Rendah:'bl'};
    var rEl=ge('rlist');
    if(!d.recent_measurements||!d.recent_measurements.length){rEl.innerHTML='<p style="font-size:13px;color:var(--g3)">Belum ada pengukuran</p>';return;}
    var html='';
    for(var i=0;i<Math.min(5,d.recent_measurements.length);i++){
      var m=d.recent_measurements[i];var cl=BC[m.risk_level]||'bl';
      html+='<div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">'
        +'<div style="width:34px;height:34px;border-radius:17px;background:var(--pl);display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:800;color:var(--p);flex-shrink:0">'+(m.toddler_name||'?')[0]+'</div>'
        +'<div style="flex:1"><div style="font-size:13px;font-weight:700">'+(m.toddler_name||'—')+'</div>'
        +'<div style="font-size:11px;color:var(--g3)">'+m.measure_date+' · '+m.height_cm+' cm'+(m.by_name?' · '+m.by_name:'')+'</div></div>'
        +'<span class="badge '+cl+'">'+( m.risk_level||'Rendah')+'</span></div>';
    }
    rEl.innerHTML=html;
  });
}

// ── TODDLER LIST ───────────────────────────────────
function setZone(el,z){ZF=z;var cs=document.querySelectorAll('.fbar .chip');for(var i=0;i<cs.length;i++)cs[i].classList.remove('on');el.classList.add('on');renderList();}
function renderList(){
  var srch=(ge('tsrch').value||'').trim();
  var url='/toddlers?zone='+ZF+(srch?'&search='+encodeURIComponent(srch):'');
  spin(true);
  GET(url,function(err,res){
    spin(false);var el=ge('tlist');
    if(err||!res.success){el.innerHTML='<div class="empty"><div style="font-size:13px;color:var(--r)">'+(err?err.error:res.error)+'</div></div>';return;}
    TCACHE=res.data||[];
    if(!TCACHE.length){el.innerHTML='<div class="empty"><div style="font-size:40px;margin-bottom:10px">👶</div><div style="font-size:15px;font-weight:700;color:var(--g2);margin-bottom:5px">Belum ada balita</div><div style="font-size:12px;color:var(--g3)">Tap + untuk daftarkan</div></div>';return;}
    var ZL={hills:'Bukit ⛰️',lowlands:'Dataran 🌾',coastal:'Pantai 🏖️'};
    var BC={Tinggi:'bh',Sedang:'bm',Rendah:'bl'};
    var html='';
    for(var i=0;i<TCACHE.length;i++){
      var t=TCACHE[i];var rl=t.last_risk||'Rendah';var cl=BC[rl]||'bl';
      var age=calcAge(t.birth_date);
      var htxt=t.last_height?'TB: '+t.last_height+' cm · '+( t.last_status||'—'):'Belum diukur';
      html+='<div class="tc" onclick="goDetTod('+t.id+')">'
        +'<div class="tav">'+t.name[0]+'</div>'
        +'<div style="flex:1;min-width:0">'
          +'<div style="display:flex;align-items:center;justify-content:space-between;gap:8px"><span class="tn">'+t.name+'</span><span class="badge '+cl+'">'+rl+'</span></div>'
          +'<div class="tm">'+(t.gender==='male'?'♂':'♀')+' · '+age+' bln · '+(ZL[t.zone]||t.zone)+' · '+(t.village||'—')+'</div>'
          +'<div class="tm">'+htxt+(t.visit_count?' · '+t.visit_count+'x':'')+'</div>'
        +'</div>'
        +'<div class="ia">'
          +'<button class="ib" onclick="event.stopPropagation();openEditTod('+t.id+')" title="Edit">✏️</button>'
          +(CU&&(CU.role==='admin'||CU.role==='researcher')?'<button class="ib" onclick="event.stopPropagation();delTod('+t.id+',\\''+t.name+'\\')" title="Hapus">🗑️</button>':'')
        +'</div></div>';
    }
    el.innerHTML=html;
  });
}
function openEditTod(id){spin(true);GET('/toddlers/'+id,function(err,res){spin(false);if(err||!res.success){toast('❌ Gagal memuat data');return;}gAdd(res.data);});}
function delTod(id,name){
  if(!confirm('Hapus '+name+'? Semua pengukuran ikut terhapus.'))return;
  spin(true);DEL('/toddlers/'+id,function(err,res){spin(false);if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}toast('✅ Dihapus');renderList();});
}

// ── FORM ADD/EDIT ──────────────────────────────────
function gAdd(t){
  EDIT_TID=t?t.id:null;ge('fttl').textContent=t?'Edit Balita':'Daftarkan Balita';
  ge('fid').value=t?t.id:'';ge('fname').value=t?t.name:'';ge('fnik').value=t?(t.nik_balita||''):'';
  ge('fbdate').value=t?t.birth_date:'';ge('fgender').value=t?t.gender:'male';
  ge('fbw').value=t?(t.birth_weight||''):'';ge('fbh').value=t?(t.birth_height||''):'';
  ge('fzone').value=t?t.zone:'lowlands';ge('fvill').value=t?(t.village||''):'';
  ge('fmname').value=t?(t.mother_name||''):'';ge('fmage').value=t?(t.mother_age||''):'';
  ge('fmht').value=t?(t.mother_height||''):'';ge('fmedu').value=t?(t.mother_edu||'sma'):'sma';
  setCb('fmil',t?t.mother_illness:0);setCb('fctps',t?(t.mother_ctps===undefined||t.mother_ctps===null?1:t.mother_ctps):1);
  ge('ffedu').value=t?(t.father_edu||'sma'):'sma';ge('finc').value=t?(t.family_income||''):'';ge('fmem').value=t?(t.family_members||''):'';
  ge('fwater').value=t?(t.water_source||'well'):'well';ge('ftoilet').value=t?(t.toilet_type||'own'):'own';
  ge('fwaste').value=t?(t.waste_mgmt||'collected'):'collected';ge('ffloor').value=t?(t.floor_type||'cement'):'cement';
  setCb('fasi',t?t.excl_breastfeed:0);setCb('finf',t?t.infection_hist:0);
  updSan();chkMH();STACK.push('form');showPage('form');
}
function setCb(id,val){var v=parseInt(val)||0;ge(id).value=v;var b=ge(id+'-b');if(v){b.className='cb on';b.textContent='✓';}else{b.className='cb';b.textContent='';}}
function togCb(id){var c=parseInt(ge(id).value)||0;setCb(id,c?0:1);if(id==='fctps')updSan();}
function chkMH(){var v=parseFloat(ge('fmht').value||999);ge('mhw').style.display=v<150?'flex':'none';}
function updSan(){var s=sanScore({water:ge('fwater').value,toilet:ge('ftoilet').value,waste:ge('fwaste').value,floor:ge('ffloor').value,ctps:ge('fctps').value==='1'});ge('sansc').textContent=s;ge('sanbox').className='ib2 '+(s<4?'ir3':s<7?'iy':'ig');}
function saveTod(){
  var name=(ge('fname').value||'').trim(),bd=ge('fbdate').value,mn=(ge('fmname').value||'').trim();
  if(!name||!bd||!mn){toast('⚠️ Nama, tanggal lahir, nama ibu wajib diisi');return;}
  var sc=sanScore({water:ge('fwater').value,toilet:ge('ftoilet').value,waste:ge('fwaste').value,floor:ge('ffloor').value,ctps:ge('fctps').value==='1'});
  var d={nik_balita:ge('fnik').value,name:name,birth_date:bd,gender:ge('fgender').value,
    birth_weight:parseFloat(ge('fbw').value)||null,birth_height:parseFloat(ge('fbh').value)||null,
    zone:ge('fzone').value,village:ge('fvill').value,mother_name:mn,
    mother_age:parseInt(ge('fmage').value)||null,mother_height:parseFloat(ge('fmht').value)||null,
    mother_edu:ge('fmedu').value,mother_illness:parseInt(ge('fmil').value)||0,mother_ctps:parseInt(ge('fctps').value)||0,
    father_edu:ge('ffedu').value,family_income:parseInt(ge('finc').value)||null,family_members:parseInt(ge('fmem').value)||null,
    water_source:ge('fwater').value,toilet_type:ge('ftoilet').value,waste_mgmt:ge('fwaste').value,
    floor_type:ge('ffloor').value,sanitation_score:sc,
    excl_breastfeed:parseInt(ge('fasi').value)||0,infection_hist:parseInt(ge('finf').value)||0};
  spin(true);
  var fn=EDIT_TID?function(cb){PUT('/toddlers/'+EDIT_TID,d,cb);}:function(cb){POST('/toddlers',d,cb);};
  fn(function(err,res){
    spin(false);if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    toast('✅ Data balita disimpan!');
    var nid=EDIT_TID||(res.data&&res.data.id);
    setTimeout(function(){goBack();if(!EDIT_TID&&confirm('Lakukan pengukuran sekarang?'))goDetTod(nid);},400);
  });
}

// ── DETECTION ──────────────────────────────────────
function initDet(){
  var today=new Date().toISOString().split('T')[0];
  var di=ge('ddate');if(di&&!di.value)di.value=today;
  ge('detres').style.display='none';DET_RES=null;DET_TOD=null;ge('dtinfo').style.display='none';
  var sel=ge('dtod');sel.innerHTML='<option value="">— Hitung Cepat —</option>';
  if(TCACHE.length){fillDetSel();}else{GET('/toddlers',function(err,res){if(!err&&res.success){TCACHE=res.data||[];fillDetSel();}});}
}
function fillDetSel(){var sel=ge('dtod');sel.innerHTML='<option value="">— Hitung Cepat —</option>';for(var i=0;i<TCACHE.length;i++){var t=TCACHE[i];var o=document.createElement('option');o.value=t.id;o.textContent=t.name+' ('+calcAge(t.birth_date)+' bln)';sel.appendChild(o);}}
function goDetTod(id){STACK.push('detect');showPage('detect');initDet();setTimeout(function(){ge('dtod').value=id;onSelTod();},80);}
function onSelTod(){
  var id=parseInt(ge('dtod').value)||0;var info=ge('dtinfo');
  if(!id){info.style.display='none';DET_TOD=null;return;}
  var t=null;for(var i=0;i<TCACHE.length;i++){if(TCACHE[i].id===id){t=TCACHE[i];break;}}
  if(!t){GET('/toddlers/'+id,function(err,res){if(!err&&res.success){DET_TOD=res.data;showTodInfo(res.data);}});}
  else{DET_TOD=t;showTodInfo(t);}
}
function showTodInfo(t){
  var info=ge('dtinfo');info.style.display='block';
  info.innerHTML='<div style="background:var(--pl);border-radius:10px;padding:10px;display:flex;align-items:center;gap:10px">'
    +'<div style="width:38px;height:38px;border-radius:19px;background:var(--p);color:#fff;display:flex;align-items:center;justify-content:center;font-size:17px;font-weight:800;flex-shrink:0">'+t.name[0]+'</div>'
    +'<div><div style="font-size:14px;font-weight:700">'+t.name+'</div>'
    +'<div style="font-size:12px;color:var(--g3)">'+(t.gender==='male'?'♂':'♀')+' · '+calcAge(t.birth_date)+' bln · '+t.zone+'</div>'
    +'<div style="font-size:12px;color:var(--g3)">Sanitasi: '+(t.sanitation_score||0)+'/10 · Ibu: '+(t.mother_height||'—')+' cm</div></div></div>';
}
function runDet(){
  var h=parseFloat(ge('dht').value||0);if(!h){toast('⚠️ Tinggi badan wajib diisi');return;}
  var t=DET_TOD;var age=t?calcAge(t.birth_date):12;var sex=t?t.gender:'male';
  var z=calcZ(h,age,sex);var zs=zSt(z);
  var inp=t?{mAge:t.mother_age,mHt:t.mother_height,mIll:t.mother_illness,aM:age,gender:t.gender,fEdu:t.father_edu,zone:t.zone,toilet:t.toilet_type,sS:t.sanitation_score,asi:t.excl_breastfeed,inf:t.infection_hist,bW:t.birth_weight,ctps:t.mother_ctps}:{mAge:28,mHt:150,aM:age,gender:sex,sS:5,asi:false,inf:false};
  var p=predRisk(inp);
  DET_RES={z:z,zs:zs,p:p,age:age,h:h};
  ge('detres').style.display='block';
  var pp=Math.round(p.prob*100);
  var rc=ge('rcirc');rc.style.borderColor=p.rc;rc.style.backgroundColor=p.rb;
  ge('rpct').style.color=p.rc;ge('rpct').textContent=pp+'%';
  var rb=ge('rrbadge');rb.textContent='Risiko '+p.rl;rb.style.background=p.rb;rb.style.color=p.rc;
  var sb=ge('rsbadge');sb.className='badge '+zs.cls;sb.textContent=zs.st;
  ge('rz').textContent=z!==null?z:'N/A';ge('rz').style.color=zs.color;
  ge('rage').textContent=age;ge('rht2').textContent=h;
  var fc=ge('faccard'),fl=ge('faclist');
  if(p.facs.length){fc.style.display='block';var WC={h:'var(--r)',m:'var(--w)',l:'var(--s)'};var fh='';
    for(var i=0;i<p.facs.length;i++){var f=p.facs[i];fh+='<div class="fr2"><div class="fdot" style="background:'+(WC[f.w]||'var(--g3)')+'"></div><span style="flex:1;font-size:13px">'+f.l+'</span><span style="font-size:12px;font-weight:700;color:var(--g3)">OR '+f.or+'</span></div>';}fl.innerHTML=fh;}
  else fc.style.display='none';
  var PC={c:'var(--r)',h:'var(--w)',m:'var(--s)',l:'var(--p)'};var ih='';
  for(var i=0;i<p.ivs.length;i++){var iv=p.ivs[i];ih+='<div class="ir2"><div class="fdot" style="background:'+(PC[iv.p]||'var(--p)')+'"></div><span style="flex:1;font-size:13px;line-height:1.5">'+iv.l+'</span></div>';}
  ge('intlist').innerHTML=ih;
  ge('bsavm').style.display=t?'flex':'none';
  setTimeout(function(){ge('rescard').scrollIntoView({behavior:'smooth',block:'start'});},100);
}
function saveMeas(){
  var t=DET_TOD;var r=DET_RES;if(!t||!r){toast('Pilih balita terlebih dahulu');return;}
  var d={measure_date:ge('ddate').value||new Date().toISOString().split('T')[0],age_months:r.age,height_cm:r.h,
    weight_kg:parseFloat(ge('dwt').value)||null,z_score_hfa:r.z,stunting_status:r.zs.st,
    risk_level:r.p.rl,risk_prob:r.p.prob,notes:ge('dnotes').value,intervention:r.p.ivs[0].l};
  spin(true);POST('/toddlers/'+t.id+'/measurements',d,function(err,res){
    spin(false);if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    toast('✅ Pengukuran disimpan!');ge('dht').value='';ge('dwt').value='';ge('detres').style.display='none';DET_RES=null;
    GET('/toddlers',function(e2,r2){if(!e2&&r2.success)TCACHE=r2.data||[];});
  });
}

// ── GROWTH ─────────────────────────────────────────
function initGrowth(){
  if(!TCACHE.length){GET('/toddlers',function(err,res){if(!err&&res.success){TCACHE=res.data||[];buildGChips();}});}
  else buildGChips();
}
function buildGChips(){
  var chips=ge('gchips');chips.innerHTML='';
  if(!SEL_G&&TCACHE.length)SEL_G=TCACHE[0].id;
  for(var i=0;i<TCACHE.length;i++){
    var t=TCACHE[i];
    (function(tod){var btn=document.createElement('button');btn.className='chip'+(SEL_G===tod.id?' on':'');btn.textContent=tod.name;
    btn.onclick=function(){SEL_G=tod.id;var cs=document.querySelectorAll('#gchips .chip');for(var j=0;j<cs.length;j++)cs[j].classList.remove('on');btn.classList.add('on');rdGrowth();};chips.appendChild(btn);})(t);
  }
  rdGrowth();
}
function rdGrowth(){
  var t=null;for(var i=0;i<TCACHE.length;i++){if(TCACHE[i].id===SEL_G){t=TCACHE[i];break;}}
  var gc=ge('gcont');
  if(!t){gc.innerHTML='<div class="empty"><div style="font-size:40px">📊</div><div style="font-size:14px;font-weight:700;color:var(--g2);margin-top:10px">Pilih balita di atas</div></div>';return;}
  gc.innerHTML='<div style="font-size:13px;color:var(--g3);text-align:center;padding:20px">Memuat...</div>';
  spin(true);
  GET('/toddlers/'+t.id+'/measurements',function(err,res){
    spin(false);if(err||!res.success){gc.innerHTML='<div style="color:var(--r);padding:16px;text-align:center">'+(err?err.error:res.error)+'</div>';return;}
    var ms=res.data||[];ms.sort(function(a,b){return a.measure_date.localeCompare(b.measure_date);});
    var age=calcAge(t.birth_date);var last=ms.length?ms[ms.length-1]:null;
    var lz=last?(last.z_score_hfa!==null&&last.z_score_hfa!==undefined?last.z_score_hfa:calcZ(last.height_cm,last.age_months,t.gender)):null;
    var lst=zSt(lz);var BC={Tinggi:'bh',Sedang:'bm',Rendah:'bl'};var rl=last?last.risk_level:'Rendah';
    gc.innerHTML='';
    var hc=document.createElement('div');hc.className='card';
    hc.innerHTML='<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">'
      +'<div style="width:46px;height:46px;border-radius:23px;background:var(--pl);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;color:var(--p)">'+t.name[0]+'</div>'
      +'<div style="flex:1"><div style="font-size:15px;font-weight:700">'+t.name+'</div><div style="font-size:12px;color:var(--g3)">'+(t.gender==='male'?'♂':'♀')+' · '+age+' bln · '+t.zone+'</div></div>'
      +'<span class="badge '+(BC[rl]||'bl')+'">'+rl+'</span></div>'
      +'<div class="zg"><div class="zb"><div class="zv">'+(!last?'—':last.height_cm)+'</div><div class="zl">Tinggi (cm)</div></div>'
      +'<div class="zb"><div class="zv" style="color:'+lst.color+'">'+(lz!==null&&lz!==undefined?lz:'—')+'</div><div class="zl">Z-Score TB/U</div></div>'
      +'<div class="zb"><div class="zv">'+ms.length+'x</div><div class="zl">Kunjungan</div></div></div>'
      +'<div style="margin-top:8px"><span class="badge '+lst.cls+'">'+lst.st+'</span></div>';
    gc.appendChild(hc);
    var cc=document.createElement('div');cc.className='card';
    cc.innerHTML='<div class="ct">📈 Grafik TB/U (WHO)</div><div class="cw">'+drawChart(ms,t.gender)+'</div>'
      +'<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;font-size:11px"><span style="color:var(--p)">— Median</span><span style="color:var(--w)">-- -2SD</span><span style="color:var(--r)">-- -3SD</span></div>';
    gc.appendChild(cc);
    var ab=document.createElement('button');ab.className='btn bp';ab.textContent='+ Pengukuran Baru';ab.style.marginBottom='12px';
    (function(tid){ab.onclick=function(){goDetTod(tid);};})(t.id);gc.appendChild(ab);
    if(ms.length){
      var hc2=document.createElement('div');hc2.className='card';var rms=ms.slice().reverse();var hh='<div class="ct">📋 Riwayat</div>';
      for(var i=0;i<rms.length;i++){
        var m=rms[i];var mz=m.z_score_hfa!==null&&m.z_score_hfa!==undefined?m.z_score_hfa:calcZ(m.height_cm,m.age_months,t.gender);
        var mst=zSt(mz);var mrl=m.risk_level||'Rendah';var mcl=BC[mrl]||'bl';
        hh+='<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 0;border-bottom:1px solid var(--border)">'
          +'<div style="flex:1"><div style="font-size:13px;font-weight:700">'+m.measure_date+' · Usia '+m.age_months+' bln</div>'
          +'<div style="font-size:12px;color:var(--g3)">TB: '+m.height_cm+' cm'+(m.weight_kg?' · BB: '+m.weight_kg+' kg':'')+' · Z: '+(mz!==null?mz:'—')+(m.measured_by_name?' · '+m.measured_by_name:'')+'</div></div>'
          +'<div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px"><span class="badge '+mcl+'">'+mrl+'</span><span class="badge '+mst.cls+'">'+mst.st+'</span></div></div>';
      }
      hc2.innerHTML=hh;gc.appendChild(hc2);
    }
  });
}
function drawChart(ms,sex){
  var W=320,H=190,PL=36,PR=12,PT=10,PB=28;
  var cW=W-PL-PR,cH=H-PT-PB,maxA=59,minH=40,maxH=120;
  function xS(a){return(a/maxA)*cW+PL;}function yS(h){return cH-((h-minH)/(maxH-minH))*cH+PT;}
  var T=sex==='male'?WHO_B:WHO_G;var ages=[0,6,12,18,24,30,36,42,48,54,59];
  var med='',m2='',m3='';
  for(var i=0;i<ages.length;i++){var a=ages[i];var v=T[a]||70;med+=(i?'L':'M')+xS(a).toFixed(1)+','+yS(v).toFixed(1)+' ';m2+=(i?'L':'M')+xS(a).toFixed(1)+','+yS(v*0.91).toFixed(1)+' ';m3+=(i?'L':'M')+xS(a).toFixed(1)+','+yS(v*0.865).toFixed(1)+' ';}
  var grid='';for(var i=0;i<ages.length;i++){var a=ages[i];grid+='<line x1="'+xS(a)+'" y1="'+PT+'" x2="'+xS(a)+'" y2="'+(H-PB)+'" stroke="#E5E5E3" stroke-width="0.5"/><text x="'+xS(a)+'" y="'+(H-PB+14)+'" text-anchor="middle" font-size="9" fill="#888">'+a+'</text>';}
  var hls='';var hv=[50,60,70,80,90,100,110];for(var i=0;i<hv.length;i++){hls+='<line x1="'+PL+'" y1="'+yS(hv[i])+'" x2="'+(W-PR)+'" y2="'+yS(hv[i])+'" stroke="#E5E5E3" stroke-width="0.5"/><text x="'+(PL-3)+'" y="'+(yS(hv[i])+4)+'" text-anchor="end" font-size="9" fill="#888">'+hv[i]+'</text>';}
  var dots='';for(var i=0;i<ms.length;i++){var m=ms[i];if(!m.height_cm||m.age_months>59)continue;var cx=xS(Math.min(59,m.age_months)),cy=yS(m.height_cm);var mz=m.z_score_hfa!==null&&m.z_score_hfa!==undefined?m.z_score_hfa:calcZ(m.height_cm,m.age_months,sex);var col=zSt(mz).color;if(i>0&&ms[i-1].height_cm)dots+='<line x1="'+xS(ms[i-1].age_months||0)+'" y1="'+yS(ms[i-1].height_cm)+'" x2="'+cx+'" y2="'+cy+'" stroke="var(--p)" stroke-width="1.5"/>';dots+='<circle cx="'+cx+'" cy="'+cy+'" r="5" fill="'+col+'" stroke="#fff" stroke-width="1.5"/>';if(i===ms.length-1)dots+='<text x="'+cx+'" y="'+(cy-8)+'" text-anchor="middle" font-size="9" fill="'+col+'">'+m.height_cm+'</text>';}
  return '<svg width="'+W+'" height="'+H+'" xmlns="http://www.w3.org/2000/svg" style="overflow:visible;display:block">'+hls+grid+'<path d="'+med.trim()+'" stroke="var(--p)" stroke-width="1.5" fill="none" stroke-dasharray="5,3"/><path d="'+m2.trim()+'" stroke="var(--w)" stroke-width="1" fill="none" stroke-dasharray="4,2"/><path d="'+m3.trim()+'" stroke="var(--r)" stroke-width="1" fill="none" stroke-dasharray="4,2"/>'+dots+'<text x="'+(W/2)+'" y="'+H+'" text-anchor="middle" font-size="9" fill="#888">Usia (bulan)</text></svg>';
}

// ── QUALITATIVE ────────────────────────────────────
function initQual(){
  ge('qdate').value=new Date().toISOString().split('T')[0];
  var sel=ge('qtod');sel.innerHTML='<option value="">— Tidak terkait —</option>';
  for(var i=0;i<TCACHE.length;i++){var t=TCACHE[i];var o=document.createElement('option');o.value=t.id;o.textContent=t.name;sel.appendChild(o);}
  RVALS={};
  var RD={'rtaboo':['Tidak ada pantangan','Ada pantangan ringan','Banyak pantangan adat'],'rdecision':['Ibu sendiri','Suami','Nenek/keluarga besar','Tokoh adat'],'rposyandu':['Setiap bulan','Setiap 2-3 bulan','Jarang','Tidak pernah'],'rwater2':['Sangat bersih','Cukup bersih','Kurang bersih','Tidak tahu'],'rtoilet2':['Selalu gunakan jamban','Kadang BAB sembarangan','Sering BAB sembarangan']};
  for(var gId in RD){var el=ge(gId);if(!el)continue;var opts=RD[gId];var html='';
    for(var i=0;i<opts.length;i++){html+='<div class="ro" data-gid="'+gId+'" data-val="'+opts[i]+'" onclick="selRad(this)"><div class="rci"><div class="rin"></div></div><span style="font-size:13px">'+opts[i]+'</span></div>';}el.innerHTML=html;}
}
function selRad(el){var gId=el.getAttribute('data-gid');RVALS[gId]=el.getAttribute('data-val');var opts=document.querySelectorAll('[data-gid="'+gId+'"]');for(var i=0;i<opts.length;i++){opts[i].classList.remove('sel');opts[i].querySelector('.rci').classList.remove('sel');opts[i].querySelector('.rin').style.display='none';}el.classList.add('sel');el.querySelector('.rci').classList.add('sel');el.querySelector('.rin').style.display='block';}
function setQT(n,el){QTAB=n;for(var i=0;i<4;i++){var s=ge('qs'+i);if(s)s.style.display=i===n?'block':'none';}var bs=document.querySelectorAll('.qt .chip');for(var i=0;i<bs.length;i++)bs[i].classList.remove('on');el.classList.add('on');}
function saveQual(){
  var code=(ge('qcode').value||'').trim(),date=ge('qdate').value;
  if(!code||!date){toast('⚠️ Kode responden dan tanggal wajib diisi');return;}
  var d={toddler_id:parseInt(ge('qtod').value)||null,respondent_code:code,interview_date:date,
    interview_type:ge('qtype').value,sentiment:ge('qsent').value,theme_codes:ge('qthemes').value,
    food_taboo:RVALS['rtaboo']||'',decision_maker:RVALS['rdecision']||'',
    breastfeed_knowledge:ge('qak').value==='1',posyandu_freq:RVALS['rposyandu']||'',
    health_barriers:ge('qbarr').value,water_src_qual:RVALS['rwater2']||'',
    toilet_usage:RVALS['rtoilet2']||'',mpasi_practice:ge('qmpasi').value,
    cultural_beliefs:ge('qbeliefs').value,verbatim_notes:ge('qverb').value};
  spin(true);POST('/qualitative',d,function(err,res){spin(false);if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}toast('✅ Data wawancara disimpan!');ge('qcode').value='';ge('qverb').value='';RVALS={};initQual();});
}

// ── EDUCATION ──────────────────────────────────────
var ARTS=[
  {id:'e1',ic:'🌱',ti:'1000 Hari Pertama Kehidupan',cat:'Dasar Stunting',col:'#0F6E56',bg:'#E1F5EE',body:'Periode HPK (kehamilan s/d usia 2 tahun) adalah waktu paling kritis. Otak berkembang 90%. Kekurangan gizi berdampak permanen.\\n\\nIntervensi sejak hamil:\\n• TTD ≥90 tablet\\n• ANC minimal 6 kali\\n• Gizi beragam\\n• Hindari rokok dan alkohol'},
  {id:'e2',ic:'🤱',ti:'ASI Eksklusif 6 Bulan',cat:'Nutrisi Bayi',col:'#185FA5',bg:'#E6F1FB',body:'WHO: ASI eksklusif 6 bulan tanpa makanan/minuman tambahan.\\n\\nManfaat:\\n• Semua nutrisi yang dibutuhkan\\n• Antibodi melindungi dari infeksi\\n• Mengurangi risiko stunting 1.5x\\n\\nIMD dalam 1 jam pertama lahir penting!'},
  {id:'e3',ic:'🥗',ti:'MP-ASI Bergizi',cat:'Nutrisi Anak',col:'#3B6D11',bg:'#EAF3DE',body:'Mulai usia 6 bulan, berikan MP-ASI bergizi sambil lanjutkan ASI.\\n\\nPrinsip:\\n• BERAGAM — karbohidrat, protein, lemak, sayur, buah\\n• BERGIZI — utamakan protein hewani\\n• AMAN — bersih, tidak garam/gula berlebih\\n\\n6-8 bln: bubur · 9-11 bln: nasi tim · 12+ bln: makanan keluarga'},
  {id:'e4',ic:'💧',ti:'WASH — Sanitasi & Kebersihan',cat:'Sanitasi',col:'#185FA5',bg:'#E6F1FB',body:'Sanitasi buruk = prediktor stunting TERKUAT (OR=2.1) di Lombok Tengah.\\n\\n5 Pilar STBM:\\n1. Stop BAB Sembarangan\\n2. CTPS — sebelum menyuapkan makanan\\n3. Air minum aman\\n4. Kelola sampah\\n5. Kelola limbah cair\\n\\nCTPS mengurangi diare 48%.'},
  {id:'e5',ic:'💉',ti:'Imunisasi Dasar Lengkap',cat:'Kesehatan Anak',col:'#854F0B',bg:'#FAEEDA',body:'Imunisasi mencegah infeksi yang memperburuk gizi.\\n\\nJadwal (Kemenkes 2023):\\n• Lahir: HB0, Polio 0\\n• 1 bln: BCG, Polio 1\\n• 2 bln: DPT-HB-Hib 1, PCV 1\\n• 3 bln: DPT-HB-Hib 2\\n• 4 bln: DPT-HB-Hib 3, IPV\\n• 9 bln: MR · 18 bln: Booster\\n\\nGRATIS di Posyandu.'},
  {id:'e6',ic:'🤰',ti:'ANC & Gizi Ibu Hamil',cat:'Kesehatan Maternal',col:'#A32D2D',bg:'#FCEBEB',body:'Tinggi ibu <150 cm meningkatkan risiko stunting 1.9x.\\n\\nANC minimal 6 kali:\\n• Trimester 1: 2x · Trimester 2: 1x · Trimester 3: 3x\\n\\nSuplemen wajib: TTD ≥90 tablet, Asam folat 400mcg/hari\\n\\nTanda bahaya: perdarahan, sesak, bengkak, kejang → segera ke Puskesmas!'}
];
function rdEdu(){ge('edudet').style.display='none';var el=ge('edulist');el.style.display='block';var html='';
  for(var i=0;i<ARTS.length;i++){var a=ARTS[i];html+='<div class="arc" onclick="openArt(\\''+a.id+'\\')"><div style="width:48px;height:48px;border-radius:10px;background:'+a.bg+';display:flex;align-items:center;justify-content:center;font-size:24px;flex-shrink:0">'+a.ic+'</div><div style="flex:1;min-width:0"><div style="font-size:11px;font-weight:700;color:'+a.col+'">'+a.cat+'</div><div style="font-size:14px;font-weight:700;color:var(--g1);margin-top:2px">'+a.ti+'</div><div style="font-size:12px;color:var(--g3);margin-top:2px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">'+a.body.split('\\n')[0]+'</div></div><span style="color:var(--g4);font-size:16px">›</span></div>';}
  el.innerHTML=html;
}
function openArt(id){var a=null;for(var i=0;i<ARTS.length;i++){if(ARTS[i].id===id){a=ARTS[i];break;}}if(!a)return;ge('edulist').style.display='none';ge('edudet').style.display='block';var lines=a.body.split('\\n');var bh='';for(var i=0;i<lines.length;i++)bh+=lines[i]+'<br>';ge('edudetc').innerHTML='<div style="background:'+a.bg+';border-radius:12px;padding:20px;text-align:center;margin-bottom:14px"><div style="font-size:44px;margin-bottom:8px">'+a.ic+'</div><div style="font-size:11px;font-weight:700;color:'+a.col+';text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">'+a.cat+'</div><div style="font-size:18px;font-weight:800;color:'+a.col+'">'+a.ti+'</div></div><div class="card"><p style="font-size:14px;color:var(--g2);line-height:1.8">'+bh+'</p></div>';}
function closeEdu(){ge('edudet').style.display='none';ge('edulist').style.display='block';}

// ── REPORT ─────────────────────────────────────────
function rdReport(){
  ge('rptc').innerHTML='<div style="color:var(--g3);text-align:center;padding:20px">Memuat...</div>';spin(true);
  GET('/dashboard',function(err,res){
    spin(false);if(err||!res.success){ge('rptc').innerHTML='<div class="ib2 ir3"><span>❌</span><p>'+(err?err.error:res.error)+'</p></div>';return;}
    var d=res.data;var hi=0,me=0,lo=0;
    for(var i=0;i<(d.by_risk||[]).length;i++){if(d.by_risk[i].risk_level==='Tinggi')hi=d.by_risk[i].n;else if(d.by_risk[i].risk_level==='Sedang')me=d.by_risk[i].n;else lo=d.by_risk[i].n;}
    var total=d.total||0;var prev=total>0?((hi+me)/total*100).toFixed(1):'0';var pCol=parseFloat(prev)>30?'var(--r)':parseFloat(prev)>20?'var(--w)':'var(--p)';
    var ZL={hills:'Bukit ⛰️',lowlands:'Dataran Rendah 🌾',coastal:'Pantai 🏖️'};
    var zHtml='';for(var i=0;i<(d.by_zone||[]).length;i++){var z=d.by_zone[i];if(!z.total)continue;var pct=(z.stunted/z.total*100).toFixed(1);var col=pct>35?'var(--r)':pct>20?'var(--w)':'var(--p)';zHtml+='<div class="brw"><div class="brl"><span style="font-size:12px;font-weight:600;color:var(--g2)">'+(ZL[z.zone]||z.zone)+'</span><span style="font-size:13px;font-weight:700;color:'+col+'">'+z.stunted+'/'+z.total+' ('+pct+'%)</span></div><div class="brt"><div class="brf" style="width:'+Math.min(100,pct)+'%;background:'+col+'"></div></div></div>';}
    ge('rptc').innerHTML='<div class="card"><div class="ct">📊 Ringkasan</div>'
      +'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px">'
      +'<div style="background:var(--pl);border-radius:10px;padding:10px;text-align:center"><div style="font-size:22px;font-weight:800;color:var(--p)">'+total+'</div><div style="font-size:11px;color:var(--p)">Balita</div></div>'
      +'<div style="background:var(--rl);border-radius:10px;padding:10px;text-align:center"><div style="font-size:22px;font-weight:800;color:var(--r)">'+hi+'</div><div style="font-size:11px;color:var(--r)">Risiko Tinggi</div></div>'
      +'<div style="background:var(--sl);border-radius:10px;padding:10px;text-align:center"><div style="font-size:22px;font-weight:800;color:var(--s)">'+d.qual_count+'</div><div style="font-size:11px;color:var(--s)">Data Kuali.</div></div></div>'
      +'<div class="brl"><span style="font-size:12px;font-weight:600;color:var(--g2)">Prevalensi Stunting</span><span style="font-size:13px;font-weight:700;color:'+pCol+'">'+prev+'%</span></div>'
      +'<div class="brt"><div class="brf" style="width:'+Math.min(100,parseFloat(prev))+'%;background:'+pCol+'"></div></div>'
      +'<div style="font-size:11px;color:var(--g3);margin-top:3px">Target nasional: ≤14%</div></div>'
      +'<div class="card"><div class="ct">🗺️ Per Zona</div>'+zHtml+'</div>'
      +'<div class="card"><div class="ct">🔬 Validasi Model</div>'
      +'<div class="mr"><span class="mk">ROC-AUC</span><span class="mv">0.87 ✅</span></div>'
      +'<div class="mr"><span class="mk">Sensitivitas</span><span class="mv">82.4% ✅</span></div>'
      +'<div class="mr"><span class="mk">Spesifisitas</span><span class="mv">79.1% ✅</span></div></div>'
      +(CU&&(CU.role==='admin'||CU.role==='researcher')?'<div class="card"><div class="ct">📤 Ekspor</div><button class="btn bp" onclick="expData()" style="margin-bottom:6px">📋 Ekspor JSON</button><p style="font-size:12px;color:var(--g3)">Untuk analisis SPSS/R/Python</p></div>':'');
  });
}
function expData(){spin(true);GET('/export',function(err,res){spin(false);if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}try{var blob=new Blob([JSON.stringify(res.data,null,2)],{type:'application/json'});var url=URL.createObjectURL(blob);var a=document.createElement('a');a.href=url;a.download='StuntingPred_'+new Date().toISOString().split('T')[0]+'.json';document.body.appendChild(a);a.click();document.body.removeChild(a);URL.revokeObjectURL(url);}catch(e){console.log(JSON.stringify(res.data));}toast('✅ Data diekspor!');});}

// ── PROFILE ────────────────────────────────────────
function rdProfile(){
  if(!CU)return;
  var RL={admin:'Administrator',kader:'Kader Posyandu',researcher:'Peneliti'};
  ge('pfav').textContent=CU.name.slice(0,2).toUpperCase();ge('pfnm').textContent=CU.name;ge('pfrl').textContent=RL[CU.role]||CU.role;
  ge('pfnik').textContent=CU.nik;ge('pfrl2').textContent=RL[CU.role]||CU.role;ge('pfpk').textContent=CU.puskesmas||'—';
  ge('pfadmin').style.display=CU.role==='admin'?'block':'none';
  ge('pold').value='';ge('pnew').value='';
}
function changePwd(){
  var old=(ge('pold').value||'').trim(),nw=(ge('pnew').value||'').trim();
  if(!old||!nw||nw.length<6){toast('⚠️ Password lama & baru (min 6) wajib diisi');return;}
  spin(true);POST('/auth/change-password',{old_password:old,new_password:nw},function(err,res){spin(false);if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}toast('✅ Password diubah!');ge('pold').value='';ge('pnew').value='';});
}

// ── USER MANAGEMENT ────────────────────────────────
function filterU(el,f){UF=f;var cs=document.querySelectorAll('#page-users .chip');for(var i=0;i<cs.length;i++)cs[i].classList.remove('on');el.classList.add('on');renderUList();}
function rdUsers(){
  spin(true);GET('/users',function(err,res){
    spin(false);if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    UCACHE=res.data||[];
    var total=UCACHE.length;var kaders=0;var active=0;
    for(var i=0;i<UCACHE.length;i++){if(UCACHE[i].role==='kader')kaders++;if(UCACHE[i].active)active++;}
    var st=ge('ustats');
    if(st)st.innerHTML='<div style="background:var(--pl);border-radius:10px;padding:10px;text-align:center"><div style="font-size:20px;font-weight:800;color:var(--p)">'+total+'</div><div style="font-size:11px;color:var(--p)">Total</div></div>'
      +'<div style="background:var(--sl);border-radius:10px;padding:10px;text-align:center"><div style="font-size:20px;font-weight:800;color:var(--s)">'+kaders+'</div><div style="font-size:11px;color:var(--s)">Kader</div></div>'
      +'<div style="background:var(--pl);border-radius:10px;padding:10px;text-align:center"><div style="font-size:20px;font-weight:800;color:var(--p)">'+active+'</div><div style="font-size:11px;color:var(--p)">Aktif</div></div>';
    renderUList();
  });
}
function renderUList(){
  var el=ge('ulist');
  var RL={admin:'Administrator',kader:'Kader Posyandu',researcher:'Peneliti'};
  var RC={admin:'#A32D2D',kader:'#0F6E56',researcher:'#185FA5'};
  var RB={admin:'#FCEBEB',kader:'#E1F5EE',researcher:'#E6F1FB'};
  var ZL={all:'Semua zona',hills:'Bukit ⛰️',lowlands:'Dataran 🌾',coastal:'Pantai 🏖️'};
  var list=UCACHE.filter(function(u){
    if(UF==='kader')return u.role==='kader';
    if(UF==='admin')return u.role==='admin'||u.role==='researcher';
    if(UF==='active')return u.active===1||u.active===true;
    if(UF==='inactive')return !u.active;
    return true;
  });
  if(!list.length){el.innerHTML='<div class="empty"><div style="font-size:40px">👥</div><div style="font-size:14px;font-weight:700;color:var(--g2);margin-top:10px">Tidak ada pengguna</div></div>';return;}
  var html='';
  for(var i=0;i<list.length;i++){
    var u=list[i];var isAct=u.active===1||u.active===true;var mustC=u.must_change_pwd===1||u.must_change_pwd===true;
    html+='<div class="uc">'
      +'<div style="width:42px;height:42px;border-radius:21px;background:'+(RB[u.role]||'#E1F5EE')+';display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:800;color:'+(RC[u.role]||'#0F6E56')+';flex-shrink:0">'+u.name[0]+'</div>'
      +'<div style="flex:1;min-width:0">'
        +'<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">'
          +'<span style="font-size:14px;font-weight:700;color:var(--g1)">'+u.name+'</span>'
          +'<span style="font-size:11px;font-weight:700;padding:2px 8px;border-radius:100px;background:'+(RB[u.role]||'#E1F5EE')+';color:'+(RC[u.role]||'#0F6E56')+'">'+(RL[u.role]||u.role)+'</span>'
          +(isAct?'<span style="font-size:10px;color:var(--p)">●Aktif</span>':'<span style="font-size:10px;color:var(--r)">●Nonaktif</span>')
          +(mustC?'<span style="font-size:10px;color:var(--w)">⚠ Ganti pwd</span>':'')
        +'</div>'
        +'<div style="font-size:12px;color:var(--g3)">'+u.nik+'</div>'
        +'<div style="font-size:12px;color:var(--g3)">'+(u.puskesmas||'—')+' · '+(ZL[u.zone]||u.zone||'—')+'</div>'
      +'</div>'
      +'<div style="display:flex;gap:4px;flex-shrink:0">'
        +'<button class="ib" onclick="openEditUser('+u.id+')" title="Edit">✏️</button>'
        +(CU&&CU.id!==u.id?'<button class="ib" onclick="toggleAct('+u.id+',\\''+u.name+'\\','+isAct+')" title="'+(isAct?'Nonaktif':'Aktif')+'">'+(isAct?'🚫':'✅')+'</button>':'')
      +'</div></div>';
  }
  el.innerHTML=html;
}
function toggleAct(uid,name,isAct){
  if(!confirm(isAct?'Nonaktifkan akun '+name+'?':'Aktifkan kembali akun '+name+'?'))return;
  spin(true);PUT('/users/'+uid,{name:name,active:isAct?0:1},function(err,res){spin(false);if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}toast(isAct?'🚫 '+name+' dinonaktifkan':'✅ '+name+' diaktifkan');rdUsers();});
}
function openAddUser(){
  openModal('Tambah Kader / Pengguna',
    '<div class="fg"><label class="fl">NIK / Username <span class="req">*</span></label><input id="mnik" class="fi" placeholder="NIK KTP atau username"></div>'
    +'<div class="fg"><label class="fl">Nama Lengkap <span class="req">*</span></label><input id="mnm" class="fi" placeholder="Nama pengguna"></div>'
    +'<div class="fg"><label class="fl">Password Sementara</label><input id="mpwd" class="fi" type="text" value="kader123" placeholder="Min 6 karakter"></div>'
    +'<div class="fg"><label class="fl">Role</label><select id="mrl" class="fs"><option value="kader">Kader Posyandu</option><option value="researcher">Peneliti</option><option value="admin">Administrator</option></select></div>'
    +'<div class="fg"><label class="fl">Puskesmas / Unit Kerja</label><input id="mpk" class="fi" placeholder="Nama puskesmas"></div>'
    +'<div class="fg"><label class="fl">Zona Ekologi</label><select id="mzn" class="fs"><option value="all">Semua zona</option><option value="hills">Bukit</option><option value="lowlands">Dataran Rendah</option><option value="coastal">Pantai</option></select></div>'
    +'<div class="cbr" onclick="togCbM(\\'mmcp\\')"><div id="mmcp-b" class="cb on">✓</div><input type="hidden" id="mmcp" value="1"><span style="font-size:13px">Wajib ganti password saat login pertama</span></div>'
    +'<button class="btn bp" onclick="submitAddUser()" style="margin-top:10px">➕ Tambah Pengguna</button>');
}
function togCbM(id){var c=parseInt(ge(id).value)||0;var v=c?0:1;ge(id).value=v;var b=ge(id+'-b');if(v){b.className='cb on';b.textContent='✓';}else{b.className='cb';b.textContent='';}}
function submitAddUser(){
  var d={nik:(ge('mnik').value||'').trim(),name:(ge('mnm').value||'').trim(),password:(ge('mpwd').value||'kader123').trim(),role:ge('mrl').value,puskesmas:ge('mpk').value,zone:ge('mzn').value,must_change_pwd:parseInt(ge('mmcp').value)||0};
  if(!d.nik||!d.name){toast('⚠️ NIK dan nama wajib diisi');return;}
  if(d.password.length<6){toast('⚠️ Password minimal 6 karakter');return;}
  spin(true);closeModal();
  POST('/users',d,function(err,res){spin(false);if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}
    var msg='✅ '+d.name+' berhasil ditambahkan';if(d.must_change_pwd)msg+=' (wajib ganti password)';
    toast(msg,4000);rdUsers();});
}
function openEditUser(id){
  var u=null;for(var i=0;i<UCACHE.length;i++){if(UCACHE[i].id===id){u=UCACHE[i];break;}}if(!u)return;
  var ZL={all:'Semua zona',hills:'Bukit',lowlands:'Dataran Rendah',coastal:'Pantai'};
  openModal('Edit: '+u.name,
    '<div class="fg"><label class="fl">Nama</label><input id="enm" class="fi" value="'+u.name+'"></div>'
    +'<div class="fg"><label class="fl">Role</label><select id="erl" class="fs"><option value="kader"'+(u.role==='kader'?' selected':'')+'>Kader</option><option value="researcher"'+(u.role==='researcher'?' selected':'')+'>Peneliti</option><option value="admin"'+(u.role==='admin'?' selected':'')+'>Admin</option></select></div>'
    +'<div class="fg"><label class="fl">Puskesmas</label><input id="epk" class="fi" value="'+(u.puskesmas||'')+'"></div>'
    +'<div class="fg"><label class="fl">Zona</label><select id="ezn" class="fs"><option value="all"'+(u.zone==='all'?' selected':'')+'>Semua</option><option value="hills"'+(u.zone==='hills'?' selected':'')+'>Bukit</option><option value="lowlands"'+(u.zone==='lowlands'?' selected':'')+'>Dataran</option><option value="coastal"'+(u.zone==='coastal'?' selected':'')+'>Pantai</option></select></div>'
    +'<button class="btn bp bsm" onclick="submitEditUser('+id+')" style="margin-bottom:10px">💾 Simpan</button>'
    +'<div style="border-top:1px solid var(--border);padding-top:10px;margin-top:4px"><div style="font-size:12px;color:var(--g3);margin-bottom:6px">Reset password kader:</div>'
    +'<div style="display:flex;gap:8px"><input id="erpwd" class="fi" type="text" placeholder="Password baru (min 6)" value="kader123" style="flex:1"><button class="btn bw2 bsm" onclick="doResetPwd('+id+')">🔄 Reset</button></div></div>');
}
function submitEditUser(uid){
  var d={name:ge('enm').value,role:ge('erl').value,puskesmas:ge('epk').value,zone:ge('ezn').value,active:1};
  spin(true);closeModal();PUT('/users/'+uid,d,function(err,res){spin(false);if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}toast('✅ User diperbarui');rdUsers();});
}
function doResetPwd(uid){
  var p=(ge('erpwd').value||'').trim();if(!p||p.length<6){toast('⚠️ Password minimal 6 karakter');return;}
  spin(true);closeModal();POST('/users/'+uid+'/reset-password',{new_password:p},function(err,res){spin(false);if(err||!res.success){toast('❌ '+(err?err.error:res.error));return;}toast('🔄 Password direset. Kader wajib ganti saat login.',4000);rdUsers();});
}

// ── LOGS ───────────────────────────────────────────
function rdLogs(){
  ge('logscont').innerHTML='<div style="color:var(--g3);text-align:center;padding:20px">Memuat...</div>';spin(true);
  GET('/logs?limit=100',function(err,res){
    spin(false);if(err||!res.success){ge('logscont').innerHTML='<div class="ib2 ir3"><span>❌</span><p>'+(err?err.error:res.error)+'</p></div>';return;}
    var logs=res.data||[];if(!logs.length){ge('logscont').innerHTML='<div class="empty"><div style="font-size:40px">📋</div><div style="font-size:14px;color:var(--g3);margin-top:10px">Belum ada aktivitas</div></div>';return;}
    var AC={LOGIN:'🔑',CREATE:'➕',UPDATE:'✏️',DELETE:'🗑️',CHANGE_PWD:'🔐',RESET_PWD:'🔄',CREATE_USER:'👤',UPDATE_USER:'👤',EXPORT:'📤'};
    var html='<div class="card"><div class="ct">📋 Log ('+logs.length+' entri)</div>';
    for(var i=0;i<logs.length;i++){var l=logs[i];html+='<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)"><div style="font-size:16px;flex-shrink:0">'+(AC[l.action]||'📌')+'</div><div style="flex:1"><div style="font-size:12px;font-weight:700;color:var(--p)">'+l.action+(l.detail?' — <span style="font-weight:400;color:var(--g3)">'+l.detail+'</span>':'')+'</div><div style="font-size:11px;color:var(--g3)">'+(l.user_name||'—')+' · '+l.table_name+' · '+l.created_at+'</div></div></div>';}
    html+='</div>';ge('logscont').innerHTML=html;
  });
}

// ── BOOT ───────────────────────────────────────────
(function boot(){
  loadS();
  // Ping async — tidak blokir login
  (function(){var px=new XMLHttpRequest();px.open('GET',BASE+'/api/ping',true);px.timeout=20000;
    px.onload=function(){try{var d=JSON.parse(px.responseText);setConn(d&&d.success);}catch(e){setConn(false);}};
    px.onerror=function(){setConn(false);};px.ontimeout=function(){setConn(false);};px.send();}
  )();

  if(CU&&TOKEN){
    GET('/auth/me',function(err,res){
      if(!err&&res.success){CU=res.data;saveS(TOKEN,CU);
        if(CU.must_change_pwd){STACK=['forcepwd'];showPage('forcepwd');}
        else{ge('nav').classList.add('show');STACK=[];goTo('dashboard');}
      } else {clearS();showPage('login');}
    });
  } else {showPage('login');}
})();
</script>
</body>
</html>
"""

if __name__ == '__main__':
    init_db()
    import socket
    try: ip = socket.gethostbyname(socket.gethostname())
    except: ip = '127.0.0.1'
    print(f"\n🩺 StuntingPred v3.0\n   http://127.0.0.1:{PORT}\n   http://{ip}:{PORT}\n")
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
