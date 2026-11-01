import csv, hmac, hashlib, json, re, sys, collections
sys.path.insert(0, '.')
from comments_inline import ROWS, P
SALT = open('/home/claude/realdata/ANON_SALT_RAHASIA.txt').read().strip().encode()
OFF = {('x','pksejahtera'):'PKS',('x','dpp_pkb'):'PKB',('x','dpp_ppp'):'PPP',('x','official_pan'):'PAN'}
def anon(pl, uid, handle):
    h = str(handle or '').lstrip('@').lower()
    if (pl, h) in OFF: return f"{OFF[(pl,h)]}_{pl}_official"
    return "u_" + hmac.new(SALT, f"{pl}:{uid or h}".encode(), hashlib.sha256).hexdigest()[:12]
rows, names = [], {}
def add(**r): rows.append(r)
# IG/YT komentar
for pl, party, pk, cid, ts, uid, handle, text in ROWS:
    a = anon(pl, uid, handle); names[a] = (pl, handle.lstrip('@'))
    add(author=a, text=text, type='reply', target_user=f"{party}_{pl}_official", created_at=ts, platform=pl, party=party,
        interaction='comment', content_url=P[pk])
# X
seen = set()
for party, h in [('PKS','PKSejahtera'),('PKB','DPP_PKB'),('PPP','DPP_PPP'),('PAN','Official_PAN')]:
    d = json.load(open(f'raw/x__{party}__{h}.json'))
    src = f"{party}_x_official"
    for t in d['tweets']:
        l = t.get('legacy', t); tid = t.get('rest_id') or l.get('id_str')
        if tid in seen: continue
        seen.add(tid)
        from datetime import datetime
        ts = datetime.strptime(l['created_at'], '%a %b %d %H:%M:%S %z %Y').isoformat()
        txt = l.get('full_text') or ''; url = f"https://x.com/{h}/status/{tid}"
        ments = (l.get('entities') or {}).get('user_mentions') or []
        if txt.startswith('RT @') and ments:
            m = ments[0]; tgt = anon('x', m.get('id_str'), m.get('screen_name')); names[tgt] = ('x', m.get('screen_name'))
            add(author=src, text=txt, type='retweet', target_user=tgt, created_at=ts, platform='x', party=party, interaction='repost', content_url=url)
            ments = ments[1:]
        if l.get('in_reply_to_screen_name'):
            tgt = anon('x', l.get('in_reply_to_user_id_str'), l['in_reply_to_screen_name']); names[tgt] = ('x', l['in_reply_to_screen_name'])
            add(author=src, text=txt, type='reply', target_user=tgt, created_at=ts, platform='x', party=party, interaction='reply', content_url=url)
        for m in ments:
            tgt = anon('x', m.get('id_str'), m.get('screen_name')); names[tgt] = ('x', m.get('screen_name'))
            if tgt == src: continue
            add(author=src, text=txt, type='mention', target_user=tgt, created_at=ts, platform='x', party=party, interaction='mention', content_url=url)
cols = ['author','text','type','target_user','created_at','platform','party','interaction','content_url']
with open('interim_sosmed.csv','w',newline='',encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
with open('names_interim_private.csv','w',newline='',encoding='utf-8-sig') as fh:
    w = csv.writer(fh); w.writerow(['id','handle','nickname','verified_reason','profile_url'])
    prof = {'instagram':'https://www.instagram.com/{}','youtube':'https://www.youtube.com/@{}','x':'https://x.com/{}'}
    for a,(pl,h) in sorted(names.items()):
        if a.endswith('_official'): continue
        w.writerow([a, h, h, '', prof[pl].format(h)])
c = collections.Counter((r['platform'], r['interaction'], r['party']) for r in rows)
for k in sorted(c): print(k, c[k])
print('total', len(rows), '| akun unik', len({r['author'] for r in rows} | {r['target_user'] for r in rows}))
x = [r for r in rows if r['platform']=='x']; print('X rentang', min(r['created_at'] for r in x)[:10], max(r['created_at'] for r in x)[:10])
print('top X targets', collections.Counter(names.get(r['target_user'],('',''))[1] for r in x if r['interaction']=='mention').most_common(10))
