#!/usr/bin/env python3
"""
StuntingPred - Test Suite Lengkap
Jalankan di PythonAnywhere Bash Console:
cd ~/stuntingpred && python3 /tmp/test_server.py
"""
import sys, os
sys.path.insert(0, '/home/achmad29/.local/lib/python3.13/site-packages')
sys.path.insert(0, '/home/achmad29/stuntingpred')
os.environ['SECRET_KEY'] = 'stuntingpred-ums-heri2025-lombok-ntb-secret-key'
os.environ['DB_PATH']    = '/home/achmad29/stuntingpred/stunting.db'

from server import app, init_db
init_db()
c = app.test_client()

results = []
def test(name, ok, detail=''):
    results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ''))

print('\n🩺 StuntingPred — Test Suite Live Server')
print('='*52)

# 1. Ping
r = c.get('/api/ping')
d = r.get_json()
test('Server ping', r.status_code==200, f"v{d['data']['version']} | DB: {d['data']['db']}")

# 2. Admin login
r = c.post('/api/auth/login', json={'nik':'superadmin','password':'admin123'})
d = r.get_json()
test('Admin login', r.status_code==200 and d['success'], f"role={d.get('data',{}).get('user',{}).get('role','?')}")
ADMIN = {'Authorization': 'Bearer ' + d['data']['token']}

# 3. Kader login
r = c.post('/api/auth/login', json={'nik':'kader001','password':'kader123'})
d = r.get_json()
test('Kader login', r.status_code==200 and d['success'])
KADER = {'Authorization': 'Bearer ' + d['data']['token']}

# 4. Peneliti login
r = c.post('/api/auth/login', json={'nik':'1901234567890001','password':'peneliti123'})
d = r.get_json()
test('Peneliti login', r.status_code==200 and d['success'])

# 5. Wrong password
r = c.post('/api/auth/login', json={'nik':'superadmin','password':'salah'})
test('Wrong password rejected', r.status_code==400)

# 6. Dashboard
r = c.get('/api/dashboard', headers=ADMIN)
d = r.get_json()
tot = d['data']['total']
test('Dashboard realtime', r.status_code==200, f"{tot} balita, {d['data']['user_count']} users")

# 7. Get toddlers list
r = c.get('/api/toddlers', headers=ADMIN)
d = r.get_json()
test('GET toddlers', r.status_code==200, f"{len(d['data'])} balita")

# 8. CREATE toddler (CRUD - Create)
r = c.post('/api/toddlers', headers=KADER, json={
    'name':'Balita Test CRUD','birth_date':'2024-03-15',
    'gender':'male','mother_name':'Ibu CRUD Test',
    'zone':'lowlands','sanitation_score':6
})
d = r.get_json()
test('CREATE balita (kader)', r.status_code==201, f"id={d.get('data',{}).get('id')}")
new_id = d.get('data',{}).get('id')

# 9. READ toddler (CRUD - Read)
r = c.get(f'/api/toddlers/{new_id}', headers=KADER)
d = r.get_json()
test('READ balita detail', r.status_code==200, d['data']['name'])

# 10. UPDATE toddler (CRUD - Update)
r = c.put(f'/api/toddlers/{new_id}', headers=KADER, json={
    'name':'Balita CRUD Updated','birth_date':'2024-03-15',
    'gender':'male','mother_name':'Ibu Updated','zone':'lowlands'
})
test('UPDATE balita', r.status_code==200)

# 11. Add measurement
r = c.post(f'/api/toddlers/{new_id}/measurements', headers=KADER, json={
    'age_months':14,'height_cm':73.5,'weight_kg':9.8,
    'z_score_hfa':-1.8,'stunting_status':'Normal',
    'risk_level':'Sedang','risk_prob':0.45
})
test('CREATE pengukuran', r.status_code==201)

# 12. Get measurements
r = c.get(f'/api/toddlers/{new_id}/measurements', headers=KADER)
d = r.get_json()
test('GET riwayat pengukuran', r.status_code==200, f"{len(d['data'])} pengukuran")

# 13. Qualitative data
r = c.post('/api/qualitative', headers=KADER, json={
    'respondent_code':'R-TEST-01','interview_date':'2025-06-01',
    'interview_type':'idi','verbatim_notes':'Test verbatim dari kader',
    'toddler_id': new_id
})
test('CREATE data kualitatif', r.status_code==201)

# 14. Admin: add new kader
r = c.post('/api/users', headers=ADMIN, json={
    'nik':'kader_test_live','name':'Kader Test Live',
    'password':'test123','role':'kader',
    'puskesmas':'Puskesmas Test','zone':'hills','must_change_pwd':1
})
d = r.get_json()
test('Admin CREATE kader baru', r.status_code==201, f"id={d.get('data',{}).get('id')}")
new_kader_id = d.get('data',{}).get('id')

# 15. Kader login with temp password + must_change
r = c.post('/api/auth/login', json={'nik':'kader_test_live','password':'test123'})
d = r.get_json()
test('Kader baru login (must_change=1)', r.status_code==200,
     f"must_change={d['data']['must_change_pwd']}")
NEW_KADER = {'Authorization': 'Bearer ' + d['data']['token']}

# 16. Kader change own password
r = c.post('/api/auth/change-password', headers=NEW_KADER, json={
    'old_password':'test123','new_password':'passwordbaru99'
})
test('Kader ganti password sendiri', r.status_code==200)

# 17. Login with new password, must_change=0
r = c.post('/api/auth/login', json={'nik':'kader_test_live','password':'passwordbaru99'})
d = r.get_json()
test('Login password baru (must_change=0)',
     r.status_code==200 and d['data']['must_change_pwd']==0)

# 18. Admin reset kader password
r = c.post(f'/api/users/{new_kader_id}/reset-password', headers=ADMIN,
    json={'new_password':'resetpwd99'})
test('Admin reset password kader', r.status_code==200)

# 19. After reset, must_change=1
r = c.post('/api/auth/login', json={'nik':'kader_test_live','password':'resetpwd99'})
d = r.get_json()
test('Setelah reset, must_change=1',
     r.status_code==200 and d['data']['must_change_pwd']==1)

# 20. Kader zone restriction (kader001 = lowlands only)
r2 = c.post('/api/auth/login', json={'nik':'kader001','password':'kader123'})
KDR_ZONE = {'Authorization': 'Bearer ' + r2.get_json()['data']['token']}
r = c.get('/api/toddlers', headers=KDR_ZONE)
d = r.get_json()
zones = list(set(t['zone'] for t in d['data']))
test('Kader zone restriction', all(z=='lowlands' for z in zones), f"zones={zones}")

# 21. Export data (researcher only)
r3 = c.post('/api/auth/login', json={'nik':'1901234567890001','password':'peneliti123'})
RSR = {'Authorization': 'Bearer ' + r3.get_json()['data']['token']}
r = c.get('/api/export', headers=RSR)
d = r.get_json()
test('Export data (peneliti)', r.status_code==200,
     f"{len(d['data']['toddlers'])} balita, {len(d['data']['measurements'])} pengukuran")

# 22. Kader cannot export
r = c.get('/api/export', headers=KADER)
test('Kader diblokir export', r.status_code==403)

# 23. Activity log
r = c.get('/api/logs', headers=ADMIN)
d = r.get_json()
test('Activity log', r.status_code==200, f"{len(d['data'])} entri")

# 24. DELETE toddler (cleanup)
r = c.delete(f'/api/toddlers/{new_id}', headers=ADMIN)
test('DELETE balita (cleanup)', r.status_code==200)

# 25. GET all users
r = c.get('/api/users', headers=ADMIN)
d = r.get_json()
test('GET semua users', r.status_code==200, f"{len(d['data'])} users")

# Report
print()
print('='*52)
passed = sum(1 for _,ok,_ in results if ok)
failed = [(n,d) for n,ok,d in results if not ok]
print(f'  HASIL: {passed}/{len(results)} tests passed')
if failed:
    print(f'  GAGAL:')
    for n,d in failed: print(f'    ❌ {n}', f'— {d}' if d else '')
else:
    print('  SEMUA TEST BERHASIL ✅')
    print('  Server online & database realtime berfungsi sempurna!')
print('='*52)
