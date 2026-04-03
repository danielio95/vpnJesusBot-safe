python3 - <<'PY'
import json
cfg='/etc/sing-box/config.json'
try:
    with open(cfg,'r',encoding='utf-8') as f:
        data=json.load(f)
except Exception:
    print(0)
    raise SystemExit
inbounds=data.get('inbounds',[])
users=[]
for inbound in inbounds:
    if isinstance(inbound,dict) and inbound.get('tag')=='tuic-in':
        users=inbound.get('users') or []
        break
blocked={'ADMIN','7724842241','619189872','5154320206','5159386538','5879603362'}
count=0
for u in users:
    if not isinstance(u,dict):
        continue
    name=str(u.get('name') or u.get('email') or '')
    if any(b in name for b in blocked):
        continue
    count += 1
print(count)
PY
