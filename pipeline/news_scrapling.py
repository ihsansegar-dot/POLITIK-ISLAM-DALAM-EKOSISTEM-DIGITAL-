#!/usr/bin/env python3
"""
Media online tentang PKS, PKB, PPP, PAN (Jan 2024 – sekarang).

Tahap:
  python news_scrapling.py discover   -> cari artikel via GDELT DOC 2.0 (hanya ~3 bulan terakhir; indeks lama GDELT tidak andal)
  python news_scrapling.py sitemaps   -> artikel terbaru dari sitemap resmi media (sitemap hanya memuat ~2 minggu terakhir)
  python news_scrapling.py indeks     -> arsip 2024–kini dari halaman indeks per tanggal (liputan6, detik, cnnindonesia, kompas);
                                         sampel hari berbenih per bulan, semua halaman di hari itu, judul disaring nama partai
  python news_scrapling.py fetch      -> ambil teks artikel dengan Scrapling (HTTP biasa, patuh robots.txt, berjeda)
  python news_scrapling.py export     -> data/processed/media_articles.csv + sna_media.csv (+ gabung ke sna_explorer.csv)
  python news_scrapling.py all        -> semuanya berurutan

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
    "gdelt_recent_months": 3,         # GDELT ArtList hanya andal ~3 bulan terakhir
    # media yang ditelusuri lewat sitemap resminya (bisa diubah di config.yaml)
    # Diuji 2 Nov 2026: tempo.co dikeluarkan (sitemap dijaga tantangan Cloudflare = proteksi teknis, tidak dilewati);
    # antaranews.com dikeluarkan (tidak menyediakan sitemap, /sitemap.xml 404).
    "sitemap_domains": ["kompas.com", "detik.com", "cnnindonesia.com", "republika.co.id", "liputan6.com", "kumparan.com"],
    "max_sitemaps_per_domain": 1100,  # batas jumlah file sitemap yang dibaca per media
    "index_days_per_month": 4,        # hari sampel per bulan per media (berbenih; dinaikkan = menambah hari, bukan mengganti)
    "index_max_pages": 40,
    "index_sources": ["liputan6", "detik", "cnnindonesia", "kompas"],
}

# Halaman indeks per tanggal (diuji 2 Nov 2026: HTTP 200, tanpa tantangan anti-bot, diizinkan robots.txt).
INDEX_SOURCES = {
    "liputan6": {"url": "https://www.liputan6.com/news/indeks/{d:%Y}/{d:%m}/{d:%d}?page={p}",
                 "link": r"https?://www\.liputan6\.com/news/read/\d+/[\w-]+"},
    "detik": {"url": "https://news.detik.com/indeks?page={p}&date={d:%m}/{d:%d}/{d:%Y}",
              "link": r"https?://[\w.]*detik\.com/[\w-]+/d-\d+/[\w-]+"},
    "cnnindonesia": {"url": "https://www.cnnindonesia.com/nasional/indeks/3?date={d:%Y}/{d:%m}/{d:%d}&page={p}",
                     "link": r"https?://www\.cnnindonesia\.com/nasional/\d{14}-\d+-\d+/[\w-]+"},
    "kompas": {"url": "https://indeks.kompas.com/?site=nasional&date={d:%Y}-{d:%m}-{d:%d}&page={p}",
               "link": r"https?://[\w.]*kompas\.com/read/\d{4}/\d\d/\d\d/\d+/[\w-]+"},
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
    until = dt.date.fromisoformat(c["until"])
    start = (until.replace(day=1) - dt.timedelta(days=31 * (c["gdelt_recent_months"] - 1))).replace(day=1)
    start = max(start, dt.date.fromisoformat(c["since"]))
    for party, q in c["queries"].items():
        for a, b in months(start.isoformat(), c["until"]):
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


# ----------------------------------------------------------------------------- discover (sitemap resmi media)
SLUG_PATS = {
    "PKS": r"(?:^|[-_/ ])pks(?:[-_/. ]|$)|partai[-_ ]keadilan[-_ ]sejahtera",
    "PKB": r"(?:^|[-_/ ])pkb(?:[-_/. ]|$)|partai[-_ ]kebangkitan[-_ ]bangsa",
    "PPP": r"(?:^|[-_/ ])ppp(?:[-_/. ]|$)|partai[-_ ]persatuan[-_ ]pembangunan",
    "PAN": r"(?:^|[-_/ ])pan(?:[-_/. ]|$)|partai[-_ ]amanat[-_ ]nasional",
}
_TAG = lambda t: re.compile(rf"<(?:\w+:)?{t}>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</(?:\w+:)?{t}>", re.S | re.I)
_LOC, _LASTMOD, _PUB, _TITLE = _TAG("loc"), _TAG("lastmod"), _TAG("publication_date"), _TAG("title")
_DATE_RX = [re.compile(r"(?<!\d)(20[12]\d)[-/_]?(0[1-9]|1[0-2])[-/_]?(0[1-9]|[12]\d|3[01])(?!\d)"),
            re.compile(r"yyyy=(20[12]\d)&(?:amp;)?mm=(\d{1,2})(?:&(?:amp;)?dd=(\d{1,2}))?"),
            re.compile(r"(?<!\d)(20[12]\d)[-/_](0[1-9]|1[0-2])(?![\d])()")]


def parse_sitemap(xml):
    """-> (anak_sitemap[(loc, lastmod)], url[(loc, tanggal_str, judul)])"""
    unesc = lambda x: (x or "").replace("&amp;", "&").strip()
    kids = [(unesc(_LOC.search(b).group(1)), unesc((_LASTMOD.search(b) or [None, ""])[1]))
            for b in re.findall(r"<sitemap\b.*?</sitemap>", xml, re.S | re.I) if _LOC.search(b)]
    urls = []
    for b in re.findall(r"<url\b.*?</url>", xml, re.S | re.I):
        m = _LOC.search(b)
        if not m: continue
        pub = _PUB.search(b) or _LASTMOD.search(b)
        t = _TITLE.search(b)
        urls.append((unesc(m.group(1)), unesc(pub.group(1)) if pub else "", unesc(t.group(1)) if t else ""))
    return kids, urls


def date_of(*cands):
    """tanggal (date) pertama yang bisa dibaca dari string ISO atau pola tanggal di URL."""
    for x in cands:
        if not x: continue
        m = re.match(r"(20\d\d)-(\d\d)-(\d\d)", x)
        if m:
            try: return dt.date(*map(int, m.groups()))
            except ValueError: pass
        for rx in _DATE_RX:
            m = rx.search(x)
            if m:
                y, mo, d = m.group(1), m.group(2), m.group(3) or "1"
                try: return dt.date(int(y), int(mo), int(d))
                except ValueError: pass
    return None


def parties_in(title, url):
    pats = {p: re.compile(rx) for p, rx in DEFAULT["party_patterns"].items()}
    found = {p for p, rx in pats.items() if title and rx.search(title)}
    slug = urllib.parse.urlsplit(url).path.lower()
    found |= {p for p, rx in SLUG_PATS.items() if re.search(rx, slug)}
    return sorted(found)


def _decode(raw):
    import gzip
    if isinstance(raw, str): return raw
    if raw[:2] == b"\x1f\x8b":
        try: raw = gzip.decompress(raw)
        except OSError: pass
    return raw.decode("utf-8", "replace")


def crawl_domain(domain, c, pol, http_get, seen):
    """Telusuri sitemap satu media. seen = set URL sitemap yang sudah dibaca (untuk melanjutkan)."""
    since, until = dt.date.fromisoformat(c["since"]), dt.date.fromisoformat(c["until"])
    floor = since.replace(day=1)
    base = f"https://www.{domain}"
    pol.allowed(base + "/")  # muat robots.txt
    rp = pol.robots.get(base)
    sms = (list(rp.sitemaps) if hasattr(rp, "sitemaps") else (rp.site_maps() or [])) if rp else []
    queue = sms or [base + "/sitemap.xml", base + "/sitemap_index.xml"]
    found, n_read, errors = [], 0, 0
    while queue and n_read < c["max_sitemaps_per_domain"]:
        sm = queue.pop(0)
        if sm in seen: continue
        if not pol.allowed(sm): continue
        try:
            xml = _decode(http_get(sm)); n_read += 1
        except Exception:
            errors += 1; continue
        seen.add(sm)  # hanya yang benar-benar terbaca; yang gagal dicoba lagi di run berikutnya
        if n_read % 100 == 0:
            print(f"[sitemaps] {domain}: {n_read} sitemap dibaca, {len(found)} artikel cocok, antrean {len(queue)}", flush=True)
        kids, urls = parse_sitemap(xml)
        for loc, lastmod in kids:
            d = date_of(loc) or date_of(lastmod)
            if d and (d < floor or d > until): continue  # di luar periode
            queue.append(loc)
        for loc, pub, title in urls:
            d = date_of(pub, loc)
            if not d or d < since or d > until: continue
            ps = parties_in(title, loc)
            if ps: found.append({"url": loc, "domain": urllib.parse.urlsplit(loc).netloc, "title": title,
                                 "pub_hint": d.isoformat(), "parties_query": ps, "month": f"{d:%Y-%m}", "source": "sitemap"})
    return found, n_read, errors


def cmd_sitemaps(c, http_get=None):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    s = load_state(); s.setdefault("sitemap_seen", {}); lock = threading.Lock()
    pol = Polite(c)
    if http_get is None:
        import requests
        sess = requests.Session(); sess.headers["User-Agent"] = c["user_agent"]
        def http_get(u):
            r = sess.get(u, timeout=40); r.raise_for_status()
            if b"<title>Just a moment" in r.content[:2000]:
                raise IOError("tantangan anti-bot: tidak dilewati")
            return r.content
    def polite_get(u):
        dom = urllib.parse.urlsplit(u).netloc
        with lock:
            wait = c["domain_delay_s"] - (time.time() - pol.last.get(dom, 0)); pol.last[dom] = time.time() + max(wait, 0)
        if wait > 0: time.sleep(wait)
        return http_get(u)
    def job(domain):
        seen = set(s["sitemap_seen"].get(domain, []))
        found, n, err = crawl_domain(domain, c, pol, polite_get, seen)
        with lock:
            new = 0
            for x in found:
                k = aid(x["url"])
                if k not in s["articles"]: s["articles"][k] = dict(x, parties_query=[]); new += 1
                r = s["articles"][k]
                r["parties_query"] = sorted(set(r["parties_query"]) | set(x["parties_query"]))
            s["sitemap_seen"][domain] = sorted(seen); save_state(s)
        print(f"[sitemaps] {domain}: {n} sitemap dibaca, {err} gagal, {len(found)} artikel cocok ({new} baru)", flush=True)
        if n >= c["max_sitemaps_per_domain"]:
            print(f"  ! {domain} menyentuh batas {c['max_sitemaps_per_domain']} sitemap; jalankan ulang untuk melanjutkan", flush=True)
    with ThreadPoolExecutor(max_workers=len(c["sitemap_domains"]) or 1) as ex:
        list(ex.map(job, c["sitemap_domains"]))
    by = defaultdict(int)
    for r in s["articles"].values():
        for p in r["parties_query"]: by[p] += 1
    print(f"[sitemaps] total artikel unik {len(s['articles'])}; per partai: {dict(sorted(by.items()))}", flush=True)


# ----------------------------------------------------------------------------- arsip: halaman indeks per tanggal
def sample_days(c):
    """Hari sampel per bulan, berbenih. Urutan diacak sekali per bulan lalu diambil k pertama,
    sehingga menaikkan k hanya menambah hari (sampel bersarang)."""
    since, until = dt.date.fromisoformat(c["since"]), dt.date.fromisoformat(c["until"])
    out = []
    for a, b in months(c["since"], c["until"]):
        days = [a + dt.timedelta(n) for n in range((b - a).days)]
        days = [d for d in days if since <= d <= until]
        random.Random(f"{c['seed']}-indeks-{a:%Y-%m}").shuffle(days)
        out += sorted(days[:c["index_days_per_month"]])
    return out


def _clean(h):
    h = re.sub(r"<[^>]+>", " ", h)
    for a, b in (("&quot;", '"'), ("&amp;", "&"), ("&#039;", "'"), ("&#39;", "'"), ("&nbsp;", " ")): h = h.replace(a, b)
    return " ".join(h.split())


def index_links(html, link_rx):
    """-> {url: judul} dari halaman indeks."""
    out = {}
    for m in re.finditer(r'<a\b([^>]*)>(.*?)</a>', html, re.S | re.I):
        hm = re.search(r'href="([^"]+)"', m.group(1))
        if not hm: continue
        u = hm.group(1).split("?")[0]
        if not re.fullmatch(link_rx, u): continue
        inner = m.group(2)
        hd = re.search(r"<h\d[^>]*>(.*?)</h\d>", inner, re.S | re.I)
        ta = re.search(r'title="([^"]+)"', m.group(1))
        t = _clean(hd.group(1)) if hd else (_clean(ta.group(1)) if ta else _clean(inner))
        if len(t) > len(out.get(u, "")): out[u] = t
    return out


def _html(page):
    b = getattr(page, "body", None)
    if isinstance(b, (bytes, bytearray)): return b.decode("utf-8", "replace")
    return str(getattr(page, "html_content", "") or b or "")


def crawl_index(name, c, pol, days, done, get=None):
    """Satu media: untuk tiap hari sampel, baca halaman 1..n sampai tidak ada artikel baru."""
    src = INDEX_SOURCES[name]; pats = {p: re.compile(rx) for p, rx in c["party_patterns"].items()}
    get = get or pol.get
    for d in days:
        key = f"{name}|{d.isoformat()}"
        if key in done: continue
        seen, hits, err = {}, [], None
        for p in range(1, c["index_max_pages"] + 1):
            u = src["url"].format(d=d, p=p)
            if not pol.allowed(u): err = "dilarang robots.txt"; break
            try:
                page = get(u); st = getattr(page, "status", 200)
            except Exception as e:
                err = repr(e)[:120]; break
            if st == 404: break
            if st != 200: err = f"HTTP {st}"; break
            html = _html(page)
            if "Just a moment" in html[:3000]: err = "tantangan anti-bot: tidak dilewati"; break
            links = {k: v for k, v in index_links(html, src["link"]).items() if k not in seen}
            if not links: break
            seen.update(links)
        for u, t in seen.items():
            ps = sorted(p for p, rx in pats.items() if rx.search(t))
            if ps: hits.append({"url": u, "domain": urllib.parse.urlsplit(u).netloc, "title": t, "pub_hint": d.isoformat(),
                                "parties_query": ps, "month": f"{d:%Y-%m}", "source": f"indeks:{name}"})
        yield key, len(seen), hits, err


def cmd_indeks(c, get=None):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    s = load_state(); s.setdefault("index_done", {}); lock = threading.Lock()
    pol = Polite(c); days = sample_days(c)
    print(f"[indeks] {len(days)} hari sampel x {len(c['index_sources'])} media", flush=True)
    def job(name):
        n_days = n_hit = 0
        for key, total, hits, err in crawl_index(name, c, pol, days, s["index_done"], get):
            with lock:
                for x in hits:
                    k = aid(x["url"])
                    r = s["articles"].setdefault(k, dict(x, parties_query=[]))
                    r["parties_query"] = sorted(set(r["parties_query"]) | set(x["parties_query"]))
                if err is None or total:  # hari yang gagal total dicoba lagi di run berikutnya
                    s["index_done"][key] = {"articles_total": total, "party_hits": len(hits), "error": err}
                save_state(s)
            n_days += 1; n_hit += len(hits)
            if err: print(f"[indeks] {key}: {err} (artikel terbaca {total})", flush=True)
            if n_days % 10 == 0:
                print(f"[indeks] {name}: {n_days} hari, {n_hit} judul menyebut partai", flush=True)
        print(f"[indeks] {name} selesai: {n_days} hari baru, {n_hit} judul menyebut partai", flush=True)
    with ThreadPoolExecutor(max_workers=len(c["index_sources"]) or 1) as ex:
        list(ex.map(job, c["index_sources"]))
    by = defaultdict(int)
    for r in s["articles"].values():
        for p in r["parties_query"]: by[p] += 1
    print(f"[indeks] total artikel unik {len(s['articles'])}; per partai: {dict(sorted(by.items()))}", flush=True)


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


import threading
_LOCK = threading.Lock()


class Polite:
    def __init__(self, c, fetch=None):
        self.c, self.last, self.robots = c, {}, {}
        self.fetch = fetch

    def allowed(self, url):
        p = urllib.parse.urlsplit(url); base = f"{p.scheme}://{p.netloc}"
        if base not in self.robots:
            # robots.txt dibaca dengan User-Agent riset kita (urllib bawaan memakai 'Python-urllib' yang sering
            # dijawab 403, lalu RobotFileParser menganggap seluruh situs terlarang).
            import requests
            rp = urllib.robotparser.RobotFileParser(); rp.set_url(base + "/robots.txt")
            try:
                r = requests.get(base + "/robots.txt", headers={"User-Agent": self.c["user_agent"]}, timeout=30)
                if r.status_code in (401, 403): rp.disallow_all = True      # standar: akses ditolak = jangan ambil
                elif r.status_code >= 400: rp.allow_all = True              # tidak ada robots.txt = boleh
                else:
                    try:  # Protego = pengurai sesuai RFC 9309 (wildcard *, $, aturan terpanjang menang)
                        from protego import Protego
                        rp = Protego.parse(r.text)
                    except ImportError:
                        rp.parse(r.text.splitlines())
            except Exception:
                rp = None
            self.robots[base] = rp
        rp = self.robots[base]
        if rp is None: return True
        if hasattr(rp, "can_fetch") and type(rp).__name__ == "Protego":
            return rp.can_fetch(url, self.c["user_agent"])
        return rp.can_fetch(self.c["user_agent"], url)

    def get(self, url):
        dom = urllib.parse.urlsplit(url).netloc
        with _LOCK:
            now = time.time(); slot = max(now, self.last.get(dom, 0) + self.c["domain_delay_s"])
            self.last[dom] = slot
        if slot > now: time.sleep(slot - now)
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
        pub = f.get("published") or r.get("pub_hint") or (r.get("seendate") and dt.datetime.strptime(r["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc).isoformat()) or ""
        excerpt = (text[:300] + "…") if len(text) > 300 else text
        rows.append({"article_id": k, "url": r["url"], "domain": r["domain"], "title": title, "published": pub,
                     "parties": ";".join(parties), "parties_query": ";".join(r["parties_query"]),
                     "text_fetched": bool(text), "text_chars": len(text), "fetch_error": f.get("error", ""), "month": r["month"],
                     "source": r.get("source", "gdelt")})
        for p in parties:  # edge media -> partai (mention); ko-penyebutan membentuk jembatan antarpartai
            sna.append({"author": r["domain"], "text": title + (" — " + excerpt if excerpt else ""), "type": "mention",
                        "target_user": f"{p}_partai", "created_at": pub, "platform": "media", "party": p,
                        "interaction": "mention", "content_url": r["url"]})
    def w(name, data):
        if not data: return
        with (OUT / name).open("w", newline="", encoding="utf-8-sig") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(data[0])); wr.writeheader(); wr.writerows(data)
    w("media_articles.csv", rows); w("sna_media.csv", sna)
    cov = [{"media": k.split("|")[0], "tanggal": k.split("|")[1], **v} for k, v in sorted(s.get("index_done", {}).items())]
    w("media_cakupan.csv", cov)  # penyebut: total artikel per media per hari sampel (untuk proporsi liputan)
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
    ap.add_argument("command", choices=["discover", "sitemaps", "indeks", "fetch", "export", "all"])
    a = ap.parse_args(); c = cfg_media()
    if a.command in ("discover", "all"): cmd_discover(c)
    if a.command in ("sitemaps", "all"): cmd_sitemaps(c)
    if a.command in ("indeks", "all"): cmd_indeks(c)
    if a.command in ("fetch", "all"): cmd_fetch(c)
    if a.command in ("export", "all"): cmd_export(c)


if __name__ == "__main__":
    main()
