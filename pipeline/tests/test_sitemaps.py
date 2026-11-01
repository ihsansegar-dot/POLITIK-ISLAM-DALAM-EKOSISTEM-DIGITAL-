import gzip, importlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import news_scrapling as ns

IDX = """<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://www.contoh.id/sitemap.xml?yyyy=2023&amp;mm=12&amp;dd=31</loc></sitemap>
<sitemap><loc>https://www.contoh.id/sitemap.xml?yyyy=2024&amp;mm=08&amp;dd=08</loc></sitemap>
<sitemap><loc>https://www.contoh.id/news-2025-03.xml.gz</loc><lastmod>2025-03-31</lastmod></sitemap>
<sitemap><loc>https://www.contoh.id/lama.xml</loc><lastmod>2019-01-01</lastmod></sitemap>
</sitemapindex>"""
DAY = """<urlset xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
<url><loc>https://www.contoh.id/read/2024/08/08/anies-terancam-pkb-pks-lirik-kim-plus</loc></url>
<url><loc>https://www.contoh.id/read/2024/08/08/harga-cabai-naik</loc></url>
<url><loc>https://www.contoh.id/berita/123/zulhas</loc><news:news><news:publication_date>2024-08-08T10:00:00+07:00</news:publication_date>
<news:title><![CDATA[Zulhas: PAN Siap Dukung Pemerintah]]></news:title></news:news></url>
<url><loc>https://www.contoh.id/berita/124/panci-murah</loc><news:news><news:publication_date>2024-08-08</news:publication_date>
<news:title>Panci murah di pasar</news:title></news:news></url>
</urlset>"""
GZ = gzip.compress(b"""<urlset><url><loc>https://www.contoh.id/read/2025/03/02/ppp-gelar-muktamar</loc></url></urlset>""")


def test_parse_and_crawl(tmp_path, monkeypatch):
    monkeypatch.setattr(ns, "STATE", tmp_path / "state.json")
    pages = {"https://www.contoh.id/sitemap.xml": IDX,
             "https://www.contoh.id/sitemap.xml?yyyy=2024&mm=08&dd=08": DAY,
             "https://www.contoh.id/news-2025-03.xml.gz": GZ}
    got = []
    def http_get(u):
        got.append(u)
        if u not in pages: raise IOError("404")
        return pages[u]
    c = ns.cfg_media(); c.update(since="2024-01-01", until="2026-11-01", sitemap_domains=["contoh.id"], domain_delay_s=0)
    monkeypatch.setattr(ns.Polite, "allowed", lambda self, u: True)
    ns.cmd_sitemaps(c, http_get=http_get)
    # sitemap 2023 dan 2019 tidak pernah diminta
    assert not any("2023" in u or "lama" in u for u in got)
    s = json.loads((tmp_path / "state.json").read_text())
    arts = {r["url"].rsplit("/", 1)[-1]: r for r in s["articles"].values()}
    assert sorted(arts) == ["anies-terancam-pkb-pks-lirik-kim-plus", "ppp-gelar-muktamar", "zulhas"]
    assert arts["anies-terancam-pkb-pks-lirik-kim-plus"]["parties_query"] == ["PKB", "PKS"]
    assert arts["zulhas"]["parties_query"] == ["PAN"] and arts["zulhas"]["month"] == "2024-08"
    assert arts["ppp-gelar-muktamar"]["month"] == "2025-03"
    # dijalankan ulang: tidak membaca sitemap yang sama lagi
    got.clear(); ns.cmd_sitemaps(c, http_get=http_get)
    assert not (set(got) & set(pages))   # yang sudah terbaca tidak diminta lagi; yang gagal (404) dicoba ulang


def test_date_of():
    assert str(ns.date_of("https://x.id/read/20240808/77/1789")) == "2024-08-08"
    assert ns.date_of("https://x.id/berita/4123456/abc") is None
