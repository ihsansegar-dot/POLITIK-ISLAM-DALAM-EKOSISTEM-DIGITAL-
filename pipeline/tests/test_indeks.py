import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import news_scrapling as ns

def page_html(items):
    return "<html><body>" + "".join(
        f'<article><a href="{u}" title="{t}"><img></a><a href="{u}"><h2 class="t">{t}</h2> News 8 Agustus 2024</a></article>'
        for u, t in items) + "</body></html>"

class P:
    def __init__(self, html, status=200): self.body, self.status = html.encode(), status

def test_index_links_and_crawl(tmp_path, monkeypatch):
    monkeypatch.setattr(ns, "STATE", tmp_path / "state.json")
    k = "https://nasional.kompas.com/read/2024/08/08/{}/{}"
    p1 = page_html([(k.format(1, "gerindra-sebut-cak-imin-putuskan-sikap-pkb"), "Gerindra Sebut Cak Imin Perlu Waktu Putuskan Sikap PKB"),
                    (k.format(2, "harga-cabai"), "Harga Cabai Naik &quot;Lagi&quot;")])
    p2 = page_html([(k.format(3, "pks-dan-pan"), "PKS dan PAN Bahas Koalisi"), (k.format(4, "panci"), "Panci Murah di Pasar")])
    calls = []
    def get(u):
        calls.append(u)
        if "page=1" in u: return P(p1)
        if "page=2" in u: return P(p2)
        return P(page_html([]))  # halaman 3 kosong -> berhenti
    c = ns.cfg_media(); c.update(since="2024-08-01", until="2024-08-31", index_days_per_month=1, index_sources=["kompas"], domain_delay_s=0)
    monkeypatch.setattr(ns.Polite, "allowed", lambda self, u: True)
    monkeypatch.setattr(ns, "sample_days", lambda c: [__import__("datetime").date(2024, 8, 8)])
    ns.cmd_indeks(c, get=get)
    assert len(calls) == 3 and "date=2024-08-08" in calls[0]
    s = json.loads((tmp_path / "state.json").read_text())
    arts = sorted((r["title"], r["parties_query"]) for r in s["articles"].values())
    assert arts == [("Gerindra Sebut Cak Imin Perlu Waktu Putuskan Sikap PKB", ["PKB"]), ("PKS dan PAN Bahas Koalisi", ["PAN", "PKS"])]
    assert s["index_done"]["kompas|2024-08-08"] == {"articles_total": 4, "party_hits": 2, "error": None}
    calls.clear(); ns.cmd_indeks(c, get=get); assert calls == []  # dilanjutkan, tidak diulang

def test_sample_days_nested():
    c = ns.cfg_media(); c.update(since="2024-01-01", until="2024-03-31")
    a = set(ns.sample_days(dict(c, index_days_per_month=2))); b = set(ns.sample_days(dict(c, index_days_per_month=4)))
    assert len(a) == 6 and len(b) == 12 and a <= b
