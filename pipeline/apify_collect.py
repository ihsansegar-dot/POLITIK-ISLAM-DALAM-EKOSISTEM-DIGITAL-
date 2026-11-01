#!/usr/bin/env python3
"""
Instagram, YouTube, X (akun resmi PKS/PKB/PPP/PAN) lewat Apify, Jan 2024 - sekarang.

Perintah:
  python apify_collect.py probe     -> panggilan sangat kecil per Actor (beberapa sen), simpan contoh struktur keluaran
  python apify_collect.py collect   -> feed + sampel bulanan + komentar, berhenti di batas biaya (config.yaml: apify.max_usd)
  python apify_collect.py build     -> data/processed/sna_apify.csv (+ data/private/names_private_apify.csv)

Keputusan peneliti (2 Nov 2026):
- X: HANYA tweet dari akun partai (from:akun, termasuk retweet/quote/reply milik akun). Tanpa pencarian balasan publik.
- Batas biaya keras $30. Target sampel 5 post/akun/bulan; pekerjaan komentar diacak (berbenih) sehingga bila
  anggaran habis, hasilnya subsampel acak lintas bulan, bukan hanya bulan terbaru.
Anonimisasi: ID pseudonim HMAC-SHA256 dengan ANON_SALT yang sama dengan sc_pipeline (konsisten lintas sumber).
Token: variabel lingkungan APIFY_TOKEN (dibaca dari APIFY_TOKEN.txt oleh skrip PowerShell; jangan ditaruh di repo).
"""
import csv, datetime as dt, hashlib, hmac, json, os, random, re, sys, time
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = DATA / "raw_apify"
OUT = DATA / "processed"
PRIV = DATA / "private"
STATE = DATA / "apify_state.json"

ACTORS = {  # harga per 1.000 hasil menurut halaman Apify Store (dibaca 2 Nov 2026; perkiraan, cek ulang di konsol)
    "ig_posts": ("apify/instagram-scraper", 2.30),
    "ig_comments": ("apify/instagram-comment-scraper", 2.30),
    "yt_videos": ("streamers/youtube-scraper", 3.00),        # harga belum terverifikasi -> perkiraan konservatif
    "yt_comments": ("streamers/youtube-comments-scraper", 2.00),
    "x_tweets": ("apidojo/tweet-scraper", 0.40),
}
DEFAULT = {"max_usd": 30.0, "posts_per_month": 5, "min_comments": 1, "comments_per_post": 20, "seed": 2029,
           "ig_feed_limit": 1000, "yt_feed_limit": 400, "x_max_tweets_per_account": 600}


def cfg_all():
    c = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    a = dict(DEFAULT); a.update(c.get("apify") or {})
    return c, a


def load_state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"usd": 0.0, "runs": [], "feeds": {}, "done": []}


def save_state(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    t = STATE.with_suffix(".tmp"); t.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8"); t.replace(STATE)


def parse_date(x):
    if x in (None, ""): return None
    if isinstance(x, (int, float)): return dt.datetime.fromtimestamp(x if x < 1e11 else x / 1000, dt.timezone.utc)
    s = str(x).strip()
    for f in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%a %b %d %H:%M:%S %z %Y"):
        try:
            d = dt.datetime.strptime(s, f); return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
        except ValueError: pass
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00")); return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError: return None


# ----------------------------------------------------------------------------- Apify
class Runner:
    def __init__(self, a, state, client=None):
        self.a, self.s = a, state
        if client is None:
            from apify_client import ApifyClient
            tok = os.environ.get("APIFY_TOKEN")
            if not tok: sys.exit("APIFY_TOKEN belum di-set.")
            client = ApifyClient(tok)
        self.client = client

    def left(self):
        return self.a["max_usd"] - self.s["usd"]

    def run(self, key, run_input, max_items, tag):
        actor, price = ACTORS[key]
        afford = int(self.left() / price * 1000)
        n = min(max_items, afford)
        if n <= 0: raise BudgetExceeded(f"anggaran ${self.a['max_usd']} habis (terpakai ${self.s['usd']:.2f})")
        run = self.client.actor(actor).call(run_input=run_input, max_items=n, timeout_secs=3600)
        items = list(self.client.dataset(run["defaultDatasetId"]).iterate_items()) if run else []
        cost = run.get("usageTotalUsd") if run else None
        est = len(items) * price / 1000
        self.s["usd"] += max(cost or 0, est)
        self.s["runs"].append({"key": key, "tag": tag, "run_id": (run or {}).get("id"), "items": len(items),
                               "usd_est": round(est, 4), "usd_reported": cost, "status": (run or {}).get("status"),
                               "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
        RAW.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w.-]+", "_", tag)[:80]
        (RAW / f"{key}__{safe}.json").write_text(json.dumps({"key": key, "tag": tag, "input": run_input, "items": items},
                                                            ensure_ascii=False), encoding="utf-8")
        save_state(self.s)
        print(f"[{key}] {tag}: {len(items)} item, ~${est:.3f} (total ${self.s['usd']:.2f} / ${self.a['max_usd']})", flush=True)
        return items


class BudgetExceeded(Exception): pass


def accounts(c):
    out = []
    for party, ps in c["seeds"].items():
        for pl in ("instagram", "youtube", "x"):
            s = ps.get(pl) or {}
            if s.get("status") == "verified" and s.get("handle"): out.append((party, pl, s["handle"]))
    return out


def profile_url(pl, h):
    return {"instagram": f"https://www.instagram.com/{h}/", "youtube": f"https://www.youtube.com/@{h}/videos",
            "x": f"https://x.com/{h}"}[pl]


# ----------------------------------------------------------------------------- normalisasi butir feed
def feed_item(pl, it):
    """-> (url, datetime, comment_count) atau None"""
    if pl == "instagram":
        return it.get("url"), parse_date(it.get("timestamp")), it.get("commentsCount") or 0
    if pl == "youtube":
        return it.get("url"), parse_date(it.get("date") or it.get("uploadDate") or it.get("publishedAt")), \
            it.get("commentsCount") or it.get("numberOfComments") or 0
    return None


def monthly_sample(items, a, since, until):
    by = defaultdict(list)
    for u, d, n in items:
        if u and d and since <= d.date() <= until and n >= a["min_comments"]: by[d.strftime("%Y-%m")].append(u)
    out = {}
    for m, us in sorted(by.items()):
        us = sorted(set(us)); rnd = random.Random(f"{a['seed']}-{m}-{len(us)}")
        out[m] = us if len(us) <= a["posts_per_month"] else sorted(rnd.sample(us, a["posts_per_month"]))
    return out


def cmd_probe(c, a, client=None):
    s = load_state(); r = Runner(a, s, client)
    acc = {pl: (p, h) for p, pl, h in accounts(c)}
    try:
        if "instagram" in acc:
            p, h = acc["instagram"]
            posts = r.run("ig_posts", {"directUrls": [profile_url("instagram", h)], "resultsType": "posts", "resultsLimit": 3,
                                       "skipPinnedPosts": True, "addParentData": False}, 3, f"probe_{h}")
            if posts:
                r.run("ig_comments", {"directUrls": [posts[0]["url"]], "resultsLimit": 5}, 5, f"probe_{h}_c")
        if "youtube" in acc:
            p, h = acc["youtube"]
            vids = r.run("yt_videos", {"startUrls": [{"url": profile_url("youtube", h)}], "maxResults": 3, "maxResultsShorts": 0,
                                       "maxResultStreams": 0, "sortVideosBy": "NEWEST"}, 3, f"probe_{h}")
            if vids:
                r.run("yt_comments", {"startUrls": [{"url": vids[0]["url"]}], "maxComments": 5, "commentsSortBy": "1"}, 5, f"probe_{h}_c")
        if "x" in acc:
            p, h = acc["x"]
            r.run("x_tweets", {"searchTerms": [f"from:{h} since:2026-09-01 include:nativeretweets"], "sort": "Latest", "maxItems": 60},
                  60, f"probe_{h}")
    except BudgetExceeded as e:
        print("[probe] DIHENTIKAN:", e)
    for f in sorted(RAW.glob("*probe*.json")):
        d = json.loads(f.read_text(encoding="utf-8")); it = (d["items"] or [{}])[0]
        print(f"\n== {f.name}: {len(d['items'])} item; kunci: {sorted(it)[:45]}")


def cmd_collect(c, a, client=None):
    s = load_state(); r = Runner(a, s, client)
    since = dt.date.fromisoformat(c["period"]["since"]); until = min(dt.date.fromisoformat(c["period"]["until"]), dt.date.today())
    acc = accounts(c)
    try:
        # 1) X: satu pencarian per akun, dipecah per semester agar tiap kueri >= 50 tweet dan tidak terpotong
        for party, pl, h in [x for x in acc if x[1] == "x"]:
            d0 = since
            while d0 <= until:
                d1 = min(dt.date(d0.year + (d0.month > 6), 1 if d0.month > 6 else 7, 1), until + dt.timedelta(days=1))
                key = f"x|{h}|{d0}"
                if key not in s["done"]:
                    q = f"from:{h} since:{d0} until:{d1} include:nativeretweets"
                    r.run("x_tweets", {"searchTerms": [q], "sort": "Latest", "maxItems": a["x_max_tweets_per_account"] // 6 + 50},
                          a["x_max_tweets_per_account"] // 6 + 50, f"{party}_x_{d0}")
                    s["done"].append(key); save_state(s)
                d0 = d1
        # 2) feed IG & YouTube
        for party, pl, h in [x for x in acc if x[1] in ("instagram", "youtube")]:
            k = f"{party}|{pl}"
            if k in s["feeds"]: continue
            if pl == "instagram":
                items = r.run("ig_posts", {"directUrls": [profile_url(pl, h)], "resultsType": "posts", "resultsLimit": a["ig_feed_limit"],
                                           "onlyPostsNewerThan": since.isoformat(), "skipPinnedPosts": True, "addParentData": False},
                              a["ig_feed_limit"], f"{party}_ig_feed")
            else:
                items = r.run("yt_videos", {"startUrls": [{"url": profile_url(pl, h)}], "maxResults": a["yt_feed_limit"],
                                            "maxResultsShorts": 0, "maxResultStreams": 0, "sortVideosBy": "NEWEST"},
                              a["yt_feed_limit"], f"{party}_yt_feed")
            fi = [feed_item(pl, it) for it in items]
            s["feeds"][k] = [(u, d.isoformat() if d else None, n) for u, d, n in fi if u]
            oldest = min((d for _, d, _ in fi if d), default=None)
            if oldest and oldest.date() > since:
                print(f"  ! {k}: feed hanya sampai {oldest.date()} (batas {a['ig_feed_limit'] if pl == 'instagram' else a['yt_feed_limit']} post); bulan lebih lama tidak tersampel", flush=True)
            save_state(s)
        # 3) sampel bulanan -> pekerjaan komentar, urutan acak berbenih
        jobs = []
        for k, items in s["feeds"].items():
            party, pl = k.split("|")
            smp = monthly_sample([(u, parse_date(d), n) for u, d, n in items], a, since, until)
            s.setdefault("sample", {})[k] = smp
            jobs += [(party, pl, u, m) for m, us in smp.items() for u in us if u not in s["done"]]
        random.Random(a["seed"]).shuffle(jobs)
        save_state(s)
        print(f"[komentar] {len(jobs)} post tersampel tersisa; sisa anggaran ${r.left():.2f}", flush=True)
        B = 20  # post per run Actor
        for pl in ("instagram", "youtube"):
            js = [j for j in jobs if j[1] == pl]
            for i in range(0, len(js), B):
                batch = js[i:i + B]; urls = [j[2] for j in batch]; n = a["comments_per_post"] * len(urls)
                if pl == "instagram":
                    r.run("ig_comments", {"directUrls": urls, "resultsLimit": a["comments_per_post"]}, n, f"ig_c_{i}")
                else:
                    r.run("yt_comments", {"startUrls": [{"url": u} for u in urls], "maxComments": a["comments_per_post"],
                                          "commentsSortBy": "1"}, n, f"yt_c_{i}")
                s["done"] += urls; save_state(s)
    except BudgetExceeded as e:
        print("[collect] DIHENTIKAN:", e, flush=True)
    except Exception as e:  # Actor gagal: simpan kemajuan, bisa dijalankan ulang
        save_state(s); print("[collect] GALAT:", repr(e)[:300], flush=True)
    done = sum(1 for k in s.get("sample", {}).values() for us in k.values() for u in us if u in s["done"])
    tot = sum(len(us) for k in s.get("sample", {}).values() for us in k.values())
    print(f"[collect] selesai: komentar {done}/{tot} post tersampel; biaya ~${s['usd']:.2f}", flush=True)


# ----------------------------------------------------------------------------- build
class Anon:
    def __init__(self, salt, keep):
        if not salt: sys.exit("ANON_SALT belum di-set.")
        self.salt, self.keep = salt.encode(), keep

    def __call__(self, pl, uid, handle):
        if handle and (pl, str(handle).lower().lstrip("@")) in self.keep: return self.keep[(pl, str(handle).lower().lstrip("@"))]
        return "u_" + hmac.new(self.salt, f"{pl}:{uid or str(handle).lower().lstrip('@')}".encode(), hashlib.sha256).hexdigest()[:12]


def cmd_build(c, a):
    keep = {(pl, s["handle"].lower()): f"{party}_{pl}_official" for party, ps in c["seeds"].items() for pl, s in ps.items() if s.get("handle")}
    anon = Anon(os.environ.get("ANON_SALT"), keep)
    owner = {}   # url konten -> (id pemilik, partai, caption)
    rows, names, seen = [], {}, set()
    with_text = c.get("sna_export_text", True)

    def acct(pl, uid, handle):
        aid = anon(pl, uid, handle)
        if handle and aid not in names: names[aid] = (pl, str(handle).lstrip("@"))
        return aid

    def add(src, tgt, pl, itype, when, text, party, url, key):
        if not src or not tgt or src == tgt or key in seen: return
        seen.add(key)
        rows.append(dict(author=src, text=(text or "") if with_text else "", type={"comment": "reply"}.get(itype, itype),
                         target_user=tgt, created_at=when.isoformat() if when else "", platform=pl, party=party,
                         interaction=itype, content_url=url))

    files = sorted(RAW.glob("*.json"))
    seedp = {(pl, s["handle"].lower()): party for party, ps in c["seeds"].items() for pl, s in ps.items() if s.get("handle")}
    for f in files:  # feed dulu agar pemilik konten diketahui
        d = json.loads(f.read_text(encoding="utf-8"))
        if d["key"] in ("ig_posts", "yt_videos"):
            pl = "instagram" if d["key"] == "ig_posts" else "youtube"
            for it in d["items"]:
                h = (it.get("ownerUsername") or it.get("channelUsername") or "").lstrip("@").lower()
                party = seedp.get((pl, h), "")
                if not party:
                    for (p2, hh), pt in seedp.items():
                        if p2 == pl and hh in json.dumps(d["input"]).lower(): party = pt; h = hh
                owner[it.get("url")] = (acct(pl, None, h), party, it.get("caption") or it.get("title") or "")
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8")); k = d["key"]
        if k == "ig_comments":
            for cm in d["items"]:
                url = cm.get("postUrl") or cm.get("inputUrl") or ""
                own, party, _ = owner.get(url, (None, "", ""))
                if not own: continue
                o = cm.get("owner") or {}
                src = acct("instagram", o.get("id") or cm.get("ownerId"), cm.get("ownerUsername") or o.get("username"))
                add(src, own, "instagram", "comment", parse_date(cm.get("timestamp")), cm.get("text"), party, url, "ig:" + str(cm.get("id")))
                for rp in cm.get("replies") or []:
                    ro = rp.get("owner") or {}
                    rsrc = acct("instagram", ro.get("id") or rp.get("ownerId"), rp.get("ownerUsername") or ro.get("username"))
                    add(rsrc, src, "instagram", "reply", parse_date(rp.get("timestamp")), rp.get("text"), party, url, "ig:" + str(rp.get("id")))
        elif k == "yt_comments":
            byc = {}
            for cm in d["items"]:
                url = cm.get("pageUrl") or cm.get("url") or ""
                vid = cm.get("videoId") or ""
                own, party, _ = owner.get(url) or next((v for u, v in owner.items() if vid and vid in (u or "")), (None, "", ""))
                if not own: continue
                src = acct("youtube", cm.get("authorChannelId"), cm.get("author"))
                byc[cm.get("cid")] = src
                parent = byc.get(cm.get("replyToCid")) if cm.get("replyToCid") else None
                # tanggal YouTube relatif ("2 tahun lalu") -> dibiarkan kosong bila tidak bisa dibaca; date_precision dicatat di audit
                when = parse_date(cm.get("publishedAt") or cm.get("date"))
                add(src, parent or own, "youtube", "reply" if parent else "comment", when, cm.get("comment") or cm.get("text"), party,
                    url, "yt:" + str(cm.get("cid")))
        elif k == "x_tweets":
            for t in d["items"]:
                au = t.get("author") or {}
                h = (au.get("userName") or "").lower()
                party = seedp.get(("x", h), "")
                src = acct("x", au.get("id"), au.get("userName"))
                when = parse_date(t.get("createdAt"))
                url = t.get("url") or t.get("twitterUrl") or ""
                rt = t.get("retweet") or t.get("retweetedTweet")
                if rt:
                    ra = rt.get("author") or {}
                    add(src, acct("x", ra.get("id"), ra.get("userName")), "x", "repost", when, rt.get("text"), party, url, "x:rt:" + str(t.get("id")))
                    continue
                q = t.get("quote") or t.get("quotedTweet")
                if q and (q.get("author") or {}).get("userName"):
                    qa = q["author"]
                    add(src, acct("x", qa.get("id"), qa.get("userName")), "x", "repost", when, t.get("text"), party, url, "x:q:" + str(t.get("id")))
                if t.get("isReply") and t.get("inReplyToUsername"):
                    add(src, acct("x", t.get("inReplyToUserId"), t["inReplyToUsername"]), "x", "reply", when, t.get("text"), party, url, "x:r:" + str(t.get("id")))
                ments = ((t.get("entities") or {}).get("user_mentions") or [])
                for m in ments:
                    add(src, acct("x", m.get("id_str"), m.get("screen_name")), "x", "mention", when, t.get("text"), party, url,
                        f"x:m:{t.get('id')}:{m.get('screen_name')}")
    OUT.mkdir(parents=True, exist_ok=True); PRIV.mkdir(parents=True, exist_ok=True)
    cols = ["author", "text", "type", "target_user", "created_at", "platform", "party", "interaction", "content_url"]
    with (OUT / "sna_apify.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
    prof = {"instagram": "https://www.instagram.com/{}", "youtube": "https://www.youtube.com/{}", "x": "https://x.com/{}"}
    with (PRIV / "names_private_apify.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh); w.writerow(["id", "handle", "nickname", "verified_reason", "profile_url"])
        for aid, (pl, h) in sorted(names.items()):
            w.writerow([aid, h, h, "institution account" if aid.endswith("_official") else "", prof[pl].format(h if pl != "youtube" or h.startswith("@") else "@" + h)])
    from collections import Counter
    cnt = Counter((r["platform"], r["interaction"]) for r in rows)
    undated = sum(1 for r in rows if not r["created_at"])
    print(f"[build] {len(rows)} baris -> {OUT / 'sna_apify.csv'}; {dict(cnt)}; tanpa tanggal: {undated}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("probe", "collect", "build"): sys.exit(__doc__)
    c, a = cfg_all()
    {"probe": cmd_probe, "collect": cmd_collect, "build": lambda c, a: cmd_build(c, a)}[sys.argv[1]](c, a)
