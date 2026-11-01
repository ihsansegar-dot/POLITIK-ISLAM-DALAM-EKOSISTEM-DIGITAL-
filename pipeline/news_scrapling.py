#!/usr/bin/env python3
"""
Media online tentang PKS, PKB, PPP, PAN (Jan 2024 – sekarang).

Tahap:
  python news_scrapling.py discover   -> cari artikel via GDELT DOC 2.0 (per partai per bulan, media Indonesia)
  python news_scrapling.py fetch      -> ambil teks artikel dengan Scrapling (HTTP biasa, patuh robots.txt, berjeda)
  python news_scrapling.py export     -> data/processed/media_articles.csv + sna_media.csv (+ gabung ke sna_explorer.csv)
  python news_scrapling.py all        -> ketiganya berurutan

Etika (protokol V.F): tidak memakai StealthyFetcher/DynamicFetcher, tidak melewati paywall/CAPTCHA,
User-Agent jujur, jeda per domain, robots.txt dihormati. Teks penuh hanya disimpan lokal untuk analisis;
yang diekspor ke dashboard hanya judul + kutipan pendek.
Bisa dijalankan ulang: kemajuan disimpan di data/media_state.json.
"""
import argparse, csv, datetime as dt, hashlib, json, random, re, sys, time, urllib.parse, urllib.robotparser
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = DATA / "raw_media"
OUT = DATA / "processed"
STATE = DATA / "media_state.json"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"

DEFAULT = {
    "since": "2024-01-01", "until": None,
    "queries": {
        "PKS": '("Partai Keadilan Sejahtera" OR PKS)',
        "PKB": '("Partai Kebangkitan Bangsa" OR PKB)',
        "PPP": '("Partai Persatuan Pembangunan" OR PPP)',
        "PAN": '("Partai Amanat Nasional" OR PAN)',
    },
    # penanda di teks untuk menetapkan partai yang disebut (dipakai juga untuk ko-penyebutan)
    "party_patterns": {
        "PKS": r"\bPKS\b|(?i:partai keadilan sejahtera)", "PKB": r"\bPKB\b|(?i:partai kebangkitan bangsa)",
        "PPP": r"\bPPP\b|(?i:partai persatuan pembangunan)", "PAN": r"\bPAN\b|(?i:partai amanat nasional)",
    },
    "max_records_per_query": 250,     # batas GDELT per permintaan
    "fetch_per_party_month": 15,      # teks diambil untuk sampel acak berbenih per partai per bulan
    "seed": 2029,
    "gdelt_delay_s": 6,               # GDELT meminta jeda >= 5 detik
    "domain_delay_s": 3,
    "user_agent": "PolitikIslamDigital-research/0.1 (riset akademik; kontak: ihsansegar@gmail.com)",
    "deny_domains": [],
}


def cfg_media():
    c = dict(DEFAULT)
    p = ROOT / "config.yaml"
    if p.exists():
        c.update((yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("media", {}) or {})
    c["until"] = c.get("until") or dt.date.today().isoformat()
    return c


def load_state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"windows_done": [], "articles": {}, "fetched": {}}


def save_state(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8"); tmp.replace(STATE)


def months(since, until):
    d = dt.date.fromisoformat(since).replace(day=1); end = dt.date.fromisoformat(until)
    while d <= end:
        nxt = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield d, min(nxt, end + dt.timedelta(days=1))
        d = nxt


def aid(url):
    return hashlib.sha1(url.encode()).hexdigest()[:16]


# ----------------------------------------------------------------------------- discover (GDELT)
def gdelt_window(query, start, end, c, http_get):
    q = f"{query} sourcecountry:indonesia sourcelang:indonesian"
    params = {"query": q, "mode": "ArtList", "format": "json", "maxrecords": c["max_records_per_query"],
              "sort": "DateAsc", "startdatetime": start.strftime("%Y%m%d000000"), "enddatetime": end.strftime("%Y%m%d000000")}
    txt = http_get(GDELT + "?" + urllib.parse.urlencode(params))
    try:
        return (json.loads(txt) if txt.strip() else {}).get("articles", [])
    except json.JSONDecodeError:
        return None  # GDELT mengembalikan teks error (mis. kueri terlalu pendek / rate limit)


def cmd_discover(c, http_get=None):
    import requests
    s = load_state()
    sess = requests.Session(); sess.headers["User-Agent"] = c["user_agent"]
    http_get = http_get or (lambda u: sess.get(u, timeout=60).text)
    RAW.mkdir(parents=True, exist_ok=True)
    for party, q in c["queries"].items():
        for a, b in months(c["since"], c["until"]):
            key = f"{party}|{a:%Y-%m}"
            if key in s["windows_done"]: continue
            arts = gdelt_window(q, a, b, c, http_get)
            if arts is None:
                print(f"[discover] {key}: respons bukan JSON (dicoba lagi di run berikutnya)", flush=True)
                time.sleep(c["gdelt_delay_s"] * 2); continue
            (RAW / f"gdelt_{party}_{a:%Y-%m}.json").write_text(json.dumps(arts, ensure_ascii=False), encoding="utf-8")
            for x in arts:
                u = x.get("url");
                if not u: continue
                r = s["articles"].setdefault(aid(u), {"url": u, "domain": x.get("domain"), "title": x.get("title"),
                                                     "seendate": x.get("seendate"), "parties_query": [], "month": f"{a:%Y-%m}"})
                if party not in r["parties_query"]: r["parties_query"].append(party)
            s["windows_done"].append(key); save_state(s)
            print(f"[discover] {key}: {len(arts)} artikel (total unik {len(s['articles'])})", flush=True)
            if len(arts) >= c["max_records_per_query"]:
                print(f"  ! {key} menyentuh batas {c['max_records_per_query']}: liputan bulan ini terpotong", flush=True)
            time.sleep(c["gdelt_delay_s"])


# ----------------------------------------------------------------------------- fetch (Scrapling)
BODY_SEL = ["div[itemprop=articleBody] p", "div.detail__body-text p", "div.read__content p", "div.detail-text p",
            "div.post-content p", "div.entry-content p", "article p", "div.content p", "p"]


def extract(page):
    title = page.css("meta[property='og:title']::attr(content)").get() or page.css("h1::text").get() or ""
    pub = (page.css("meta[property='article:published_time']::attr(content)").get()
           or page.css("meta[name='publishdate']::attr(content)").get()
           or page.css("meta[name='content_PublishedDate']::attr(content)").get() or "")
    for sel in BODY_SEL:
        paras = [" ".join(p.get_all_text().split()) for p in page.css(sel)]
        paras = [p for p in paras if len(p) > 40 and not re.match(r"^(baca juga|simak|lihat juga|advertisement)", p, re.I)]
        if sum(len(p) for p in paras) > 300:
            return title.strip(), pub, "\n".join(paras), sel
    return title.strip(), pub, "", ""


class Polite:
    def __init__(self, c, fetch=None):
        self.c, self.last, self.robots = c, {}, {}
        self.fetch = fetch

    def allowed(self, url):
        p = urllib.parse.urlsplit(url); base = f"{p.scheme}://{p.netloc}"
        if base not in self.robots:
            rp = urllib.robotparser.RobotFileParser(); rp.set_url(base + "/robots.txt")
            try: rp.read()
            except Exception: rp = None
            self.robots[base] = rp
        rp = self.robots[base]
        return True if rp is None else rp.can_fetch(self.c["user_agent"], url)

    def get(self, url):
        dom = urllib.parse.urlsplit(url).netloc
        wait = self.c["domain_delay_s"] - (time.time() - self.last.get(dom, 0))
        if wait > 0: time.sleep(wait)
        self.last[dom] = time.time()
        if self.fetch: return self.fetch(url)
        from scrapling.fetchers import Fetcher
        return Fetcher.get(url, headers={"User-Agent": self.c["user_agent"]}, timeout=25, follow_redirects=True,
                           stealthy_headers=False, retries=1)


def sample_for_fetch(s, c):
    by = defaultdict(list)
    for k, r in s["articles"].items():
        if r["domain"] in c["deny_domains"]: continue
        for p in r["parties_query"]: by[(p, r["month"])].append(k)
    pick = []
    for (p, m), ks in sorted(by.items()):
        ks = sorted(set(ks)); rnd = random.Random(f"{c['seed']}-{p}-{m}")
        pick += ks if len(ks) <= c["fetch_per_party_month"] else rnd.sample(ks, c["fetch_per_party_month"])
    return list(dict.fromkeys(pick))


def cmd_fetch(c, fetch=None):
    s = load_state(); pol = Polite(c, fetch)
    todo = [k for k in sample_for_fetch(s, c) if k not in s["fetched"]]
    print(f"[fetch] {len(todo)} artikel akan diambil", flush=True)
    for i, k in enumerate(todo, 1):
        r = s["articles"][k]; url = r["url"]
        rec = {"ok": False, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        try:
            if not pol.allowed(url):
                rec["error"] = "dilarang robots.txt"
            else:
                page = pol.get(url)
                st = getattr(page, "status", 200)
                if st != 200:
                    rec["error"] = f"HTTP {st}"
                else:
                    title, pub, text, sel = extract(page)
                    rec.update(ok=bool(text), title=title, published=pub, selector=sel, chars=len(text))
                    if text:
                        (RAW / "teks").mkdir(parents=True, exist_ok=True)
                        (RAW / "teks" / f"{k}.txt").write_text(text, encoding="utf-8")
                    else:
                        rec["error"] = "teks tidak ditemukan (mungkin JS/paywall)"
        except Exception as e:
            rec["error"] = repr(e)[:200]
        s["fetched"][k] = rec
        if i % 20 == 0:
            save_state(s); print(f"[fetch] {i}/{len(todo)}", flush=True)
    save_state(s)
    ok = sum(1 for v in s["fetched"].values() if v.get("ok"))
    print(f"[fetch] selesai: {ok}/{len(s['fetched'])} berhasil", flush=True)


# ----------------------------------------------------------------------------- export
def cmd_export(c):
    s = load_state(); OUT.mkdir(parents=True, exist_ok=True)
    pats = {p: re.compile(rx) for p, rx in c["party_patterns"].items()}  # singkatan peka huruf besar
    rows, sna = [], []
    for k, r in s["articles"].items():
        f = s["fetched"].get(k, {})
        text = (RAW / "teks" / f"{k}.txt").read_text(encoding="utf-8") if f.get("ok") else ""
        title = f.get("title") or r.get("title") or ""
        hay = title + "\n" + text
        parties = sorted({p for p, rx in pats.items() if rx.search(hay)} | (set() if text else set(r["parties_query"])))
        pub = f.get("published") or (r.get("seendate") and dt.datetime.strptime(r["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc).isoformat()) or ""
        excerpt = (text[:300] + "…") if len(text) > 300 else text
        rows.append({"article_id": k, "url": r["url"], "domain": r["domain"], "title": title, "published": pub,
                     "parties": ";".join(parties), "parties_query": ";".join(r["parties_query"]),
                     "text_fetched": bool(text), "text_chars": len(text), "fetch_error": f.get("error", ""), "month": r["month"]})
        for p in parties:  # edge media -> partai (mention); ko-penyebutan membentuk jembatan antarpartai
            sna.append({"author": r["domain"], "text": title + (" — " + excerpt if excerpt else ""), "type": "mention",
                        "target_user": f"{p}_partai", "created_at": pub, "platform": "media", "party": p,
                        "interaction": "mention", "content_url": r["url"]})
    def w(name, data):
        if not data: return
        with (OUT / name).open("w", newline="", encoding="utf-8-sig") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(data[0])); wr.writeheader(); wr.writerows(data)
    w("media_articles.csv", rows); w("sna_media.csv", sna)
    base = OUT / "sna_explorer.csv"
    if base.exists() and sna:
        old = [x for x in csv.DictReader(base.open(encoding="utf-8-sig")) if x.get("platform") != "media"]
        cols = list(dict.fromkeys(list(old[0]) + list(sna[0]))) if old else list(sna[0])
        with base.open("w", newline="", encoding="utf-8-sig") as fh:
            wr = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); wr.writeheader(); wr.writerows(old + sna)
    n_ok = sum(1 for r in rows if r["text_fetched"])
    print(f"[export] {len(rows)} artikel ({n_ok} dengan teks), {len(sna)} edge media→partai; "
          f"{'digabung ke sna_explorer.csv' if base.exists() else 'sna_explorer.csv belum ada; pakai sna_media.csv'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["discover", "fetch", "export", "all"])
    a = ap.parse_args(); c = cfg_media()
    if a.command in ("discover", "all"): cmd_discover(c)
    if a.command in ("fetch", "all"): cmd_fetch(c)
    if a.command in ("export", "all"): cmd_export(c)


if __name__ == "__main__":
    main()
