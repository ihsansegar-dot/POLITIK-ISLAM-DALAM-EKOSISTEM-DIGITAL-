"""Uji offline modul media online (tanpa jaringan)."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import news_scrapling as ns

HTML = """<html><head><meta property='og:title' content='PKS dan PKB bahas koalisi'>
<meta property='article:published_time' content='2024-02-03T10:00:00+07:00'></head><body>
<div class='detail__body-text'><p>Jakarta - Partai Keadilan Sejahtera bertemu Partai Kebangkitan Bangsa membahas peta koalisi menjelang pilkada serentak.</p>
<p>Baca juga: berita lain</p><p>Pertemuan berlangsung tertutup di kantor DPP PKB dan dihadiri sejumlah elite kedua partai yang sedang menjajaki kerja sama politik.</p>
<p>Sementara itu, pengamat menilai panjang jalan koalisi masih perlu dilihat karena dinamika internal masing-masing partai cukup kuat.</p></div></body></html>"""

def test_flow(tmp_path, monkeypatch):
    for k, v in {"DATA": tmp_path, "RAW": tmp_path / "raw", "OUT": tmp_path / "out", "STATE": tmp_path / "st.json"}.items():
        monkeypatch.setattr(ns, k, v)
    c = dict(ns.DEFAULT); c.update(since="2024-01-01", until="2024-02-29", gdelt_delay_s=0, domain_delay_s=0, fetch_per_party_month=5)
    def fake_gdelt(u):
        if "Keadilan" in u and "20240201" in u:
            return json.dumps({"articles": [{"url": "https://news.example.id/a1", "domain": "news.example.id", "title": "PKS dan PKB bahas koalisi", "seendate": "20240203T030000Z"},
                                            {"url": "https://news.example.id/a2", "domain": "news.example.id", "title": "lain", "seendate": "20240204T030000Z"}]})
        return "" if "Amanat" not in u else "Your search contained a phrase that is too short."
    ns.cmd_discover(c, http_get=fake_gdelt)
    st = ns.load_state()
    assert len(st["articles"]) == 2 and "PAN|2024-01" not in st["windows_done"]  # error GDELT -> diulang
    from scrapling.parser import Selector
    monkeypatch.setattr(ns.Polite, "allowed", lambda self, u: u.endswith("a1"))
    ns.cmd_fetch(c, fetch=lambda u: Selector(HTML))
    f = ns.load_state()["fetched"]
    assert any(v.get("ok") for v in f.values()) and any(v.get("error") == "dilarang robots.txt" for v in f.values())
    ns.cmd_export(c)
    import csv
    sna = list(csv.DictReader(open(tmp_path / "out" / "sna_media.csv", encoding="utf-8-sig")))
    assert {r["target_user"] for r in sna if r["content_url"].endswith("a1")} == {"PKS_partai", "PKB_partai"}
    assert all(r["platform"] == "media" for r in sna)
    assert "Baca juga" not in open(tmp_path / "raw" / "teks" / (ns.aid("https://news.example.id/a1") + ".txt"), encoding="utf-8").read()
