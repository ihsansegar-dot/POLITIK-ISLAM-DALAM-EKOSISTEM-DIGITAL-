#!/usr/bin/env python3
"""
Pipeline pengumpulan data: Politik Islam dalam Ekosistem Digital (ScrapeCreators API).

Perintah:
  python sc_pipeline.py verify   -> cek profil semua akun seed, tulis output/account_verification.csv
  python sc_pipeline.py collect  -> ambil konten + komentar akun berstatus 'verified' (raw JSON + log)
  python sc_pipeline.py build    -> raw JSON -> 4 tabel penelitian + network + CSV SNA Explorer + audit

Variabel lingkungan:
  SCRAPECREATORS_API_KEY  kunci API (wajib untuk verify/collect)
  ANON_SALT               rahasia untuk pseudonimisasi (wajib untuk build; simpan terpisah dari data)

Prinsip (protokol bagian V.F): data mentah disimpan terpisah, setiap request dicatat,
kegagalan dicatat (tidak diam-diam dilewati), tidak ada bypass autentikasi/CAPTCHA.
"""
import argparse, csv, datetime as dt, hashlib, hmac, json, os, re, sys, time
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
LOG = ROOT / "data" / "collection_log.csv"
NOW = lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------------------------- client
class BudgetExceeded(Exception):
    pass


class Client:
    def __init__(self, cfg, run_id, api_key=None):
        import requests
        self.s = requests.Session()
        self.cfg, self.run_id = cfg, run_id
        self.key = api_key or os.environ.get("SCRAPECREATORS_API_KEY")
        if not self.key:
            sys.exit("SCRAPECREATORS_API_KEY belum di-set.")
        self.credits = 0
        self.max = cfg["budget"]["max_credits_per_run"]
        self.n = 0
        import threading; self.lock = threading.Lock()

    def get(self, key, params, meta):
        if self.credits >= self.max:
            raise BudgetExceeded(f"batas {self.max} kredit tercapai")
        url = self.cfg["api"]["base_url"] + self.cfg["api"]["endpoints"][key]
        err, data, status = "", None, None
        for attempt in range(3):
            try:
                r = self.s.get(url, params=params, headers={"x-api-key": self.key}, timeout=60)
                status = r.status_code
                if status >= 500:
                    err = f"HTTP {status}"; time.sleep(2 ** attempt * 3); continue
                data = r.json()
                break
            except Exception as e:  # jaringan/JSON
                err = repr(e); time.sleep(2 ** attempt * 3)
        charged = (data or {}).get("credits_charged", 0) or 0
        with self.lock:
            self.credits += charged
        ok = bool(data) and data.get("success", status == 200) and status in (200, 403, 404)
        if data is not None and not ok and not err:
            err = str(data.get("message") or data.get("error") or f"HTTP {status}")
        if data is not None and data.get("errorStatus"):
            err = f'{data.get("errorStatus")} {data.get("message")}'
        self._log(key, params, meta, status, charged, err)
        if data is not None:
            self._save(key, params, meta, data)
        return data if ok and not data.get("errorStatus") else None

    def _save(self, key, params, meta, data):
        with self.lock:
            self.n += 1; n = self.n
        d = RAW / self.run_id / meta["platform"]
        d.mkdir(parents=True, exist_ok=True)
        rec = {"endpoint": key, "params": params, "meta": meta, "collected_at": NOW(), "response": data}
        (d / f"{n:06d}_{key}.json").write_text(json.dumps(rec, ensure_ascii=False))

    def _log(self, key, params, meta, status, credits, err):
      with self.lock:
        new = not LOG.exists()
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["timestamp_utc", "run_id", "party", "platform", "endpoint", "params", "http_status", "credits", "error"])
            safe = {k: v for k, v in params.items() if k not in ("cursor", "continuationToken", "next_max_id", "max_cursor")}
            w.writerow([NOW(), self.run_id, meta.get("party"), meta.get("platform"), key, json.dumps(safe), status, credits, err])


# ----------------------------------------------------------------------------- helpers
def parse_date(v):
    """ISO string, epoch detik, atau format Twitter -> datetime UTC (None bila gagal)."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(v, dt.timezone.utc)
    s = str(v)
    for f in ("%a %b %d %H:%M:%S %z %Y",):
        try:
            return dt.datetime.strptime(s, f).astimezone(dt.timezone.utc)
        except ValueError:
            pass
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except ValueError:
        return None


def in_period(d, cfg):
    if d is None:
        return True
    since = dt.datetime.fromisoformat(cfg["period"]["since"]).replace(tzinfo=dt.timezone.utc)
    until = dt.datetime.fromisoformat(cfg["period"]["until"]).replace(tzinfo=dt.timezone.utc) + dt.timedelta(days=1)
    return since <= d < until


def older_than_period(d, cfg):
    since = dt.datetime.fromisoformat(cfg["period"]["since"]).replace(tzinfo=dt.timezone.utc)
    return d is not None and d < since


MENTION = re.compile(r"(?<![\w.])@([A-Za-z0-9_.]{2,30})")


# ----------------------------------------------------------------------------- collect
def collect_account(c, cfg, party, platform, handle):
    b = cfg["budget"]
    meta = {"party": party, "platform": platform, "seed": handle}
    posts = []
    if platform == "instagram":
        cursor = None
        while len(posts) < b["max_posts_per_account"]:
            p = {"handle": handle, "trim": "true"}
            if cursor: p["next_max_id"] = cursor
            d = c.get("ig_user_posts", p, meta)
            if not d: break
            items = d.get("items", [])
            posts += [(i.get("url"), parse_date(i.get("created_at"))) for i in items]
            cursor = d.get("next_max_id")
            if not cursor or not d.get("more_available", True) or (items and older_than_period(parse_date(items[-1].get("created_at")), cfg)):
                break
        for url, d0 in posts[: b["max_posts_per_account"]]:
            if not in_period(d0, cfg): continue
            cur = None
            for _ in range(b["max_comment_pages_per_post"]):
                p = {"url": url}
                if b["fetch_replies"]: p["include_replies"] = "true"
                if cur: p["cursor"] = cur
                d = c.get("ig_post_comments", p, {**meta, "content_url": url})
                if not d or not d.get("comments"): break
                cur = d.get("cursor")
                if not cur: break
    elif platform == "tiktok":
        cursor = None
        while len(posts) < b["max_posts_per_account"]:
            p = {"handle": handle, "sort_by": "latest", "region": "ID", "trim": "true"}
            if cursor: p["max_cursor"] = cursor
            d = c.get("tt_profile_videos", p, meta)
            if not d: break
            items = d.get("aweme_list", [])
            posts += [(f"https://www.tiktok.com/@{handle}/video/{i.get('aweme_id')}", parse_date(i.get("create_time"))) for i in items]
            cursor = d.get("max_cursor")
            if not d.get("has_more") or not cursor or (items and older_than_period(parse_date(items[-1].get("create_time")), cfg)):
                break
        for url, d0 in posts[: b["max_posts_per_account"]]:
            if not in_period(d0, cfg): continue
            cur = None
            for _ in range(b["max_comment_pages_per_post"]):
                p = {"url": url, "trim": "true"}
                if cur is not None: p["cursor"] = cur
                d = c.get("tt_video_comments", p, {**meta, "content_url": url})
                if not d or not d.get("comments"): break
                cur = d.get("cursor")
                if d.get("end_of_pagination") or cur is None: break
    elif platform == "youtube":
        token = None
        while len(posts) < b["max_posts_per_account"]:
            p = {"handle": handle, "sort": "latest"}
            if token: p["continuationToken"] = token
            d = c.get("yt_channel_videos", p, meta)
            if not d: break
            vids = d.get("videos", [])
            posts += [(v.get("url"), parse_date(v.get("publishDate") or v.get("publishedTime"))) for v in vids]
            token = d.get("continuationToken")
            if not token or (vids and older_than_period(parse_date(vids[-1].get("publishDate")), cfg)):
                break
        for url, d0 in posts[: b["max_posts_per_account"]]:
            if not in_period(d0, cfg): continue
            tok = None
            for _ in range(b["max_comment_pages_per_post"]):
                p = {"url": url, "order": "newest"}
                if tok: p["continuationToken"] = tok
                d = c.get("yt_video_comments", p, {**meta, "content_url": url})
                if not d or not d.get("comments"): break
                if b["fetch_replies"]:
                    for cm in d["comments"]:
                        rt = cm.get("repliesContinuationToken")
                        if rt:
                            c.get("yt_comment_replies", {"continuationToken": rt},
                                  {**meta, "content_url": url, "parent_comment_id": cm.get("id"),
                                   "parent_author": (cm.get("author") or {}).get("channelId") or (cm.get("author") or {}).get("name")})
                tok = d.get("continuationToken")
                if not tok: break
    elif platform == "x":
        # Catatan audit: endpoint ini hanya memberi ~100 tweet POPULER (bukan kronologis) dan tanpa balasan.
        c.get("x_user_tweets", {"handle": handle, "trim": "true"}, meta)


# ----------------------------------------------------------------------------- sampel bulanan
LIST_EP = {"instagram": "ig_user_posts", "tiktok": "tt_profile_videos", "youtube": "yt_channel_videos"}


def _list_items(platform, d, handle):
    """-> list of (url, datetime, comment_count) dari satu halaman feed."""
    out = []
    if platform == "instagram":
        for i in d.get("items", []):
            out.append((i.get("url"), parse_date(i.get("created_at")), i.get("comment_count") or 0))
    elif platform == "tiktok":
        for v in d.get("aweme_list", []):
            out.append((f"https://www.tiktok.com/@{handle}/video/{v.get('aweme_id')}", parse_date(v.get("create_time")),
                        (v.get("statistics") or {}).get("comment_count") or 0))
    elif platform == "youtube":
        for v in d.get("videos", []):
            out.append((v.get("url"), parse_date(v.get("publishDate") or v.get("publishedTime")), v.get("commentCountInt") or 0))
    return out


def list_feed(c, cfg, party, platform, handle, state):
    """Telusuri feed sampai melewati period.since. Hasil disimpan di state (bisa dilanjutkan)."""
    key = f"{party}|{platform}"
    st = state.setdefault("feeds", {}).setdefault(key, {"cursor": None, "done": False, "items": []})
    meta = {"party": party, "platform": platform, "seed": handle}
    max_pages = cfg["sampling"].get("max_feed_pages", 400)
    pages = 0
    while not st["done"] and pages < max_pages:
        if platform == "instagram":
            p = {"handle": handle, "trim": "true"}
            if st["cursor"]: p["next_max_id"] = st["cursor"]
        elif platform == "tiktok":
            p = {"handle": handle, "sort_by": "latest", "region": "ID", "trim": "true", "include_pinned": "false"}
            if st["cursor"]: p["max_cursor"] = st["cursor"]
        else:
            p = {"handle": handle, "sort": "latest"}
            if st["cursor"]: p["continuationToken"] = st["cursor"]
        d = c.get(LIST_EP[platform], p, meta)
        pages += 1
        if not d:
            st["done"] = True; st["stop_reason"] = "gagal/empty"; break
        items = _list_items(platform, d, handle)
        st["items"] += [(u, t.isoformat() if t else None, n) for u, t, n in items]
        nxt = d.get("next_max_id") if platform == "instagram" else (d.get("max_cursor") if platform == "tiktok" else d.get("continuationToken"))
        more = (d.get("more_available", True) if platform == "instagram" else (d.get("has_more", True) if platform == "tiktok" else True))
        dated = [t for _, t, _ in items if t]
        if not nxt or not more or (dated and min(dated) < dt.datetime.fromisoformat(cfg["period"]["since"]).replace(tzinfo=dt.timezone.utc)):
            st["done"] = True; st["stop_reason"] = "melewati periode" if dated else "akhir feed"
        st["cursor"] = nxt
        save_state(state)
    return st


def monthly_sample(items, cfg):
    """Sampel acak berbenih per bulan kalender, hanya post dengan >=1 komentar (perlu untuk jaringan)."""
    import random
    n = cfg["sampling"]["posts_per_month"]
    seed = cfg["sampling"].get("seed", 2029)
    by = defaultdict(list)
    seen = set()
    for u, t, cc in items:
        if not u or u in seen or not t: continue
        seen.add(u)
        d = parse_date(t)
        if not in_period(d, cfg) or (cc or 0) < cfg["sampling"].get("min_comments", 1): continue
        by[d.strftime("%Y-%m")].append(u)
    out = {}
    for m, us in sorted(by.items()):
        rnd = random.Random(f"{seed}-{m}")
        us = sorted(us)
        out[m] = us if len(us) <= n else rnd.sample(us, n)
    return out


STATE = ROOT / "data" / "collect_state.json"
def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}
def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(state)); tmp.replace(STATE)


def cmd_collect_monthly(cfg, client=None):
    """Tahap 1: telusuri feed tiap akun (verified, platform terpilih). Tahap 2: sampel per bulan. Tahap 3: komentar.
    Bisa dijalankan ulang: feed & komentar yang sudah diambil dilewati."""
    from concurrent.futures import ThreadPoolExecutor
    state = load_state()
    run_id = state.setdefault("run_id", "monthly_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    c = client or Client(cfg, run_id)
    plats = cfg["sampling"]["platforms"]
    per_acc = cfg["sampling"]["max_credits_per_account"]
    accounts = [(party, pl, s["handle"]) for party, ps in cfg["seeds"].items() for pl, s in ps.items()
                if pl in plats and s.get("status") == "verified" and s.get("handle")]
    spent = state.setdefault("spent", {})
    x_done = set(state.setdefault("x_done", []))
    try:
        # X: endpoint hanya memberi ~100 tweet populer per akun (bukan kronologis, tanpa balasan publik);
        # cukup satu panggilan per akun, tidak ikut sampel bulanan.
        for party, pl, h in [a for a in accounts if a[1] == "x"]:
            key = f"{party}|x"
            if key in x_done: continue
            before = c.credits
            d = c.get("x_user_tweets", {"handle": h, "trim": "true"}, {"party": party, "platform": "x", "seed": h})
            spent[key] = spent.get(key, 0) + (c.credits - before)
            if d is not None:
                x_done.add(key); state["x_done"] = sorted(x_done)
            save_state(state)
            print(f"[x] {key} @{h}: {len((d or {}).get('tweets') or [])} tweet", flush=True)
        accounts = [a for a in accounts if a[1] != "x"]
        for party, pl, h in accounts:
            key = f"{party}|{pl}"
            before = c.credits
            st = list_feed(c, cfg, party, pl, h, state)
            spent[key] = spent.get(key, 0) + (c.credits - before); save_state(state)
            print(f"[feed] {key} @{h}: {len(st['items'])} post, {st.get('stop_reason')}", flush=True)
        done = set(state.setdefault("comments_done", []))
        jobs = []
        for party, pl, h in accounts:
            key = f"{party}|{pl}"
            sample = monthly_sample(state["feeds"][key]["items"], cfg)
            state.setdefault("sample", {})[key] = sample
            for m, us in sample.items():
                for u in us:
                    if u not in done: jobs.append((party, pl, h, u, m))
        save_state(state)
        # urutkan bulan-demi-bulan lintas akun supaya batas kredit memotong secara merata
        jobs.sort(key=lambda j: (j[4], j[0], j[1]))
        print(f"[komentar] {len(jobs)} post tersisa", flush=True)
        ep = {"instagram": "ig_post_comments", "tiktok": "tt_video_comments", "youtube": "yt_video_comments"}
        def fetch(j):
            party, pl, h, u, m = j
            key = f"{party}|{pl}"
            if spent.get(key, 0) >= per_acc: return j, "skip_budget"
            p = {"url": u}
            if pl == "youtube": p["order"] = "top"
            d = c.get(ep[pl], p, {"party": party, "platform": pl, "seed": h, "content_url": u, "month": m})
            spent[key] = spent.get(key, 0) + ((d or {}).get("credits_charged", 1) or 0)
            return j, "ok" if d is not None else "gagal"
        n = 0
        with ThreadPoolExecutor(max_workers=cfg["sampling"].get("workers", 6)) as ex:
            for j, res in ex.map(fetch, jobs):
                if res != "skip_budget": done.add(j[3])
                n += 1
                if n % 25 == 0:
                    state["comments_done"] = sorted(done); save_state(state)
                    print(f"[komentar] {n}/{len(jobs)} kredit run={c.credits}", flush=True)
        state["comments_done"] = sorted(done); save_state(state)
    except BudgetExceeded as e:
        save_state(state); print("[collect] DIHENTIKAN:", e)
    print(f"[collect] selesai. kredit run ini: {c.credits}. per akun: {json.dumps(spent)}", flush=True)


def cmd_collect(cfg, client=None):
    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    c = client or Client(cfg, run_id)
    skipped = []
    try:
        for party, plats in cfg["seeds"].items():
            for platform, s in plats.items():
                if s.get("status") != "verified" or not s.get("handle"):
                    skipped.append((party, platform, s.get("status"), s.get("handle")))
                    continue
                print(f"[collect] {party} / {platform} / @{s['handle']}")
                collect_account(c, cfg, party, platform, s["handle"])
    except BudgetExceeded as e:
        print("[collect] DIHENTIKAN:", e)
    print(f"[collect] selesai. kredit terpakai run ini: {c.credits}. raw: {RAW / c.run_id}")
    for x in skipped:
        print("  dilewati (belum verified):", x)
    return c.run_id


def cmd_verify(cfg, client=None):
    run_id = "verify_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    c = client or Client(cfg, run_id)
    rows = []
    for party, plats in cfg["seeds"].items():
        for platform, s in plats.items():
            h = s.get("handle")
            if not h:
                rows.append([party, platform, "", s.get("status"), "", "", "", "", "handle kosong"]); continue
            meta = {"party": party, "platform": platform, "seed": h}
            name = bio = foll = ver = ""
            if platform == "x":
                d = c.get("x_profile", {"handle": h}, meta) or {}
                leg = d.get("legacy", {})
                name, bio, foll, ver = leg.get("name"), leg.get("description"), leg.get("followers_count"), d.get("is_blue_verified")
            elif platform == "tiktok":
                d = c.get("tt_profile", {"handle": h}, meta) or {}
                u, st = d.get("user", {}), d.get("stats", {})
                name, bio, foll, ver = u.get("nickname"), u.get("signature"), st.get("followerCount"), u.get("verified")
            elif platform == "youtube":
                d = c.get("yt_channel", {"handle": h}, meta) or {}
                name, bio, foll, ver = d.get("name"), d.get("description"), d.get("subscriberCount") or d.get("subscribers"), ""
            elif platform == "instagram":
                d = c.get("ig_user_posts", {"handle": h, "trim": "true"}, meta) or {}
                u = d.get("user") or {}
                name, bio, foll, ver = u.get("full_name"), u.get("biography"), u.get("follower_count"), u.get("is_verified")
            rows.append([party, platform, h, s.get("status"), name, (bio or "")[:200], foll, ver, "isi kolom keputusan secara manual"])
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "account_verification.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["party", "platform", "handle", "status_config", "display_name", "bio", "followers", "platform_verified_flag", "catatan"])
        w.writerows(rows)
    print(f"[verify] {len(rows)} baris -> {OUT / 'account_verification.csv'} | kredit: {c.credits}")


# ----------------------------------------------------------------------------- build
class Anon:
    def __init__(self, salt, keep_public):
        if not salt:
            sys.exit("ANON_SALT belum di-set. Gunakan string acak panjang dan simpan terpisah dari data.")
        self.salt = salt.encode()
        self.keep = keep_public  # {(platform, handle_lower): "PKS-official"}

    def __call__(self, platform, uid, handle=None):
        if handle and (platform, str(handle).lower()) in self.keep:
            return self.keep[(platform, str(handle).lower())]
        key = f"{platform}:{uid or handle}".encode()
        return "u_" + hmac.new(self.salt, key, hashlib.sha256).hexdigest()[:12]


def iter_raw(run_ids=None):
    for f in sorted(RAW.glob("*/*/*.json")):
        if run_ids and f.parent.parent.name not in run_ids:
            continue
        if f.parent.parent.name.startswith("verify_"):
            continue
        yield json.loads(f.read_text())


def cmd_build(cfg, run_ids=None):
    keep = {}
    for party, plats in cfg["seeds"].items():
        for platform, s in plats.items():
            if s.get("handle"):
                keep[(platform, s["handle"].lower())] = f"{party}_{platform}_official"
    for pf in cfg.get("public_figures", []) or []:
        keep[(pf["platform"], pf["handle"].lower())] = f'{pf["platform"]}:{pf["handle"]}'.lower()
    anon = Anon(os.environ.get("ANON_SALT"), keep)
    content, comments, edges, accounts = {}, {}, [], {}
    sna_rows, state = [], {"party": ""}
    with_text = cfg.get("sna_export_text", True)
    audit = Counter()
    unknown_struct = Counter()

    names = {}  # PRIVAT: id pseudonim -> handle asli, hanya untuk dashboard pribadi peneliti

    def acct(platform, uid, handle, party=None, category="public_user"):
        aid = anon(platform, uid, handle)
        if handle and aid not in names:
            names[aid] = (platform, str(handle).lstrip("@"))
        if aid not in accounts:
            official = aid.endswith("_official")
            public = ":" in aid
            accounts[aid] = {"anonymous_account_id": aid, "account_category": "party_official" if official else ("public_figure_listed" if public else category),
                             "institutional_or_individual": "institutional" if official else ("individual_public" if public else "unknown"),
                             "party_affiliation_if_publicly_verified": party if official else "",
                             "public_account_description": "", "platform": platform}
        return aid

    def add_edge(src, tgt, platform, itype, when, text=""):
        if src and tgt and src != tgt:
            edges.append((src, tgt, platform, itype, when.date().isoformat() if when else ""))
            sna_rows.append(dict(author=src, text=(text or "") if with_text else "",
                                 type="reply" if itype in ("comment", "reply") else itype, target_user=tgt,
                                 created_at=when.isoformat() if when else "", platform=platform,
                                 party=state["party"], interaction=itype, content_url=state.get("url", "")))

    def mentions(src, text, platform, when):
        for m in MENTION.findall(text or ""):
            add_edge(src, acct(platform, None, m.lower()), platform, "mention", when, text)

    for rec in iter_raw(run_ids):
        ep, meta, d, col = rec["endpoint"], rec["meta"], rec["response"], rec["collected_at"]
        party, platform = meta.get("party"), meta.get("platform")
        state["party"] = party or ""
        state["url"] = meta.get("content_url", "")
        audit[f"responses:{ep}"] += 1
        if ep == "ig_user_posts":
            for i in d.get("items", []):
                if i.get("url") in content: continue  # post sama dari run lain
                own = i.get("owner") or i.get("user") or {}
                aid = acct(platform, own.get("id") or own.get("pk"), own.get("username") or meta["seed"], party)
                when = parse_date(i.get("created_at"))
                content[i.get("url")] = dict(content_id=i.get("code") or i.get("id"), platform=platform, account_id=aid, party_category=party,
                                             publication_date=when.isoformat() if when else "", caption=i.get("caption") if isinstance(i.get("caption"), str) else (i.get("caption") or {}).get("text", ""),
                                             content_text="", content_url=i.get("url"), likes=i.get("like_count"), views=i.get("play_count"),
                                             comments_count=i.get("comment_count"), data_collection_date=col,
                                             seed_account=meta["seed"], owned_by_seed=(own.get("username") or "").lower() == meta["seed"].lower())
                state["url"] = i.get("url")
                mentions(aid, content[i.get("url")]["caption"], platform, when)
        elif ep == "tt_profile_videos":
            for v in d.get("aweme_list", []):
                au = v.get("author") or {}
                aid = acct(platform, au.get("uid"), au.get("unique_id") or meta["seed"], party)
                when = parse_date(v.get("create_time"))
                url = f"https://www.tiktok.com/@{meta['seed']}/video/{v.get('aweme_id')}"
                if url in content: continue
                st = v.get("statistics") or {}
                content[url] = dict(content_id=v.get("aweme_id"), platform=platform, account_id=aid, party_category=party,
                                    publication_date=when.isoformat() if when else "", caption=v.get("desc"), content_text="",
                                    content_url=url, likes=st.get("digg_count"), views=st.get("play_count"),
                                    comments_count=st.get("comment_count"), data_collection_date=col)
                state["url"] = url
                mentions(aid, v.get("desc"), platform, when)
        elif ep == "yt_channel_videos":
            for v in d.get("videos", []):
                if v.get("url") in content: continue
                ch = v.get("channel") or {}
                aid = acct(platform, ch.get("id"), ch.get("handle") or meta["seed"], party)
                when = parse_date(v.get("publishDate")) or parse_date(v.get("publishedTime"))
                content[v.get("url")] = dict(content_id=v.get("id"), platform=platform, account_id=aid, party_category=party,
                                             publication_date=when.isoformat() if when else "", caption=v.get("title"),
                                             content_text=v.get("description", ""), content_url=v.get("url"), likes=v.get("likeCountInt"),
                                             views=v.get("viewCountInt"), comments_count=v.get("commentCountInt"), data_collection_date=col)
        elif ep == "x_user_tweets":
            for t in d.get("tweets", []):
                leg = t.get("legacy", t)
                aid = acct(platform, leg.get("user_id_str"), meta["seed"], party)
                when = parse_date(leg.get("created_at"))
                url = t.get("url") or f"https://x.com/{meta['seed']}/status/{t.get('rest_id')}"
                if url in content: continue
                content[url] = dict(content_id=t.get("rest_id"), platform=platform, account_id=aid, party_category=party,
                                    publication_date=when.isoformat() if when else "", caption="", content_text=leg.get("full_text"),
                                    content_url=url, likes=leg.get("favorite_count"), views=(t.get("views") or {}).get("count"),
                                    comments_count=leg.get("reply_count"), data_collection_date=col)
                for m in (leg.get("entities") or {}).get("user_mentions", []):
                    add_edge(aid, acct(platform, m.get("id_str"), m.get("screen_name")), platform, "mention", when, leg.get("full_text"))
                if leg.get("in_reply_to_screen_name"):
                    add_edge(aid, acct(platform, leg.get("in_reply_to_user_id_str"), leg["in_reply_to_screen_name"]), platform, "reply", when)
        elif ep in ("ig_post_comments", "tt_video_comments", "yt_video_comments", "yt_comment_replies"):
            url = meta.get("content_url")
            owner = content.get(url, {}).get("account_id") or acct(platform, None, meta["seed"], party)
            items = d.get("comments") or d.get("replies") or []
            if not items:
                unknown_struct[ep] += 1
            for cm in items:
                rows = [(cm, None)] + [(r, cm) for r in (cm.get("replies") or cm.get("reply_comment") or [])]
                for c_, parent in rows:
                    u = c_.get("user") or c_.get("author") or {}
                    uid = u.get("id") or u.get("pk") or u.get("uid") or u.get("channelId")
                    uh = u.get("username") or u.get("unique_id") or u.get("name")
                    if not (uid or uh):
                        unknown_struct[ep + ":no_author"] += 1; continue
                    cid = c_.get("id") or c_.get("cid") or f'{c_.get("aweme_id")}-{c_.get("create_time")}-{u.get("uid") or uh}'
                    if cid and (platform, cid) in comments:
                        audit["duplikat_komentar_dilewati"] += 1; continue
                    aid = acct(platform, uid, (uh or "").lstrip("@"))
                    when = parse_date(c_.get("created_at") or c_.get("create_time") or c_.get("publishedTime"))
                    text = c_.get("text") or c_.get("content") or ""
                    if ep == "yt_comment_replies":
                        reply_to = meta.get("parent_comment_id")
                        tgt = acct(platform, meta.get("parent_author"), None) if meta.get("parent_author") else owner
                        itype = "reply"
                    elif parent is not None:
                        reply_to = parent.get("id") or parent.get("cid")
                        pu = parent.get("user") or parent.get("author") or {}
                        tgt = acct(platform, pu.get("id") or pu.get("uid") or pu.get("channelId"), (pu.get("username") or pu.get("unique_id") or pu.get("name") or "").lstrip("@"))
                        itype = "reply"
                    else:
                        reply_to, tgt, itype = "", owner, "comment"
                    eng = c_.get("engagement") or {}
                    comments[(platform, cid)] = dict(comment_id=cid, content_id=content.get(url, {}).get("content_id", url), anonymous_user_id=aid,
                                                     comment_text=text, comment_date=when.isoformat() if when else "", reply_to=reply_to,
                                                     likes_count=c_.get("comment_like_count", c_.get("digg_count", eng.get("likes"))),
                                                     sentiment_label="", sentiment_score="", aspect_category="", topic_category="",
                                                     platform=platform, date_precision="approx_relative" if platform == "youtube" else "exact")
                    add_edge(aid, tgt, platform, itype, when, text)
                    mentions(aid, text, platform, when)
        audit[f"party:{party}:{platform}"] += 0

    # agregasi edge (protokol V.F.8: hindari penghitungan ganda -> bobot = jumlah interaksi unik per hari)
    w = Counter(edges)
    agg = defaultdict(lambda: {"weight": 0, "first": "", "last": ""})
    for (s, t, p, it, day), n in w.items():
        a = agg[(s, t, p, it)]
        a["weight"] += n
        a["first"] = min(filter(None, [a["first"], day]), default="")
        a["last"] = max(filter(None, [a["last"], day]), default="")

    OUT.mkdir(parents=True, exist_ok=True)
    def write(name, rows, cols):
        with (OUT / name).open("w", newline="", encoding="utf-8-sig") as f:
            wr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); wr.writeheader(); wr.writerows(rows)
        return len(rows)

    n1 = write("content_dataset.csv", content.values(), ["content_id", "platform", "account_id", "party_category", "publication_date", "caption", "content_text", "content_url", "likes", "views", "comments_count", "data_collection_date", "seed_account", "owned_by_seed"])
    n2 = write("comment_dataset.csv", comments.values(), ["comment_id", "content_id", "anonymous_user_id", "comment_text", "comment_date", "reply_to", "likes_count", "sentiment_label", "sentiment_score", "aspect_category", "topic_category", "platform", "date_precision"])
    net_rows = [dict(source_id=s, target_id=t, platform=p, interaction_type=it, interaction_date=a["first"], interaction_date_last=a["last"], interaction_weight=a["weight"]) for (s, t, p, it), a in agg.items()]
    n3 = write("network_dataset.csv", net_rows, ["source_id", "target_id", "platform", "interaction_type", "interaction_date", "interaction_date_last", "interaction_weight"])
    PROFILE = {"x": "https://x.com/{}", "instagram": "https://www.instagram.com/{}", "tiktok": "https://www.tiktok.com/@{}",
               "youtube": "https://www.youtube.com/{}"}
    priv = OUT.parent / "private"; priv.mkdir(parents=True, exist_ok=True)
    with (priv / "names_private.csv").open("w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f); wr.writerow(["id", "handle", "nickname", "verified_reason", "profile_url"])
        for aid, (pl, h) in sorted(names.items()):
            yt = h if (h.startswith("UC") and len(h) == 24) else None
            url = (f"https://www.youtube.com/channel/{h}" if yt else PROFILE.get(pl, "{}").format(("@" + h) if pl == "youtube" else h))
            wr.writerow([aid, h, h, "institution account" if aid.endswith("_official") else "", url])
    n4 = write("account_dataset.csv", accounts.values(), ["anonymous_account_id", "account_category", "institutional_or_individual", "party_affiliation_if_publicly_verified", "public_account_description", "platform"])
    # Ekspor untuk SNA Explorer: satu baris per interaksi (comment/reply -> 'reply'; mention dibiarkan sebagai 'mention')
    # satu baris per interaksi; teks komentar ikut bila sna_export_text: true (pengguna dipseudonimkan, teks tidak)
    n5 = write("sna_explorer.csv", sna_rows, ["author", "text", "type", "target_user", "created_at", "platform", "party", "interaction", "content_url"])

    by_plat = Counter(r["platform"] for r in content.values())
    cm_plat = Counter(r["platform"] for r in comments.values())
    lines = [f"# Audit build {NOW()}", "", f"- konten: {n1} ({dict(by_plat)})", f"- komentar/balasan: {n2} ({dict(cm_plat)})",
             f"- edge teragregasi: {n3}; baris SNA Explorer: {n5}", f"- akun unik: {n4}",
             f"- konten di feed akun seed tetapi dimiliki akun lain (kolaborasi): {sum(1 for r in content.values() if r.get('owned_by_seed') is False)} -> putuskan inklusi secara eksplisit",
             "", "## Respons per endpoint"]
    lines += [f"- {k}: {v}" for k, v in sorted(audit.items()) if k.startswith("responses:")]
    lines += [f"- komentar duplikat (terambil >1 kali) dilewati: {audit['duplikat_komentar_dilewati']}"]
    lines += ["", "## Struktur tak dikenal / data tanpa penulis (cek manual)"] + ([f"- {k}: {v}" for k, v in unknown_struct.items()] or ["- tidak ada"])
    if LOG.exists():
        errs = [r for r in csv.DictReader(LOG.open(encoding="utf-8")) if r["error"]]
        lines += ["", f"## Request gagal (dari collection_log.csv): {len(errs)}"] + [f"- {r['timestamp_utc']} {r['platform']} {r['endpoint']}: {r['error']}" for r in errs[:50]]
    (OUT / "audit_build.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:6]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["verify", "collect", "collect-monthly", "build"])
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--runs", nargs="*", help="build: batasi ke run_id tertentu")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
    {"verify": cmd_verify, "collect": cmd_collect, "collect-monthly": cmd_collect_monthly}.get(a.command, lambda c: cmd_build(c, a.runs))(cfg)


if __name__ == "__main__":
    main()
