import csv, datetime as dt, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import apify_collect as ac

class DS:
    def __init__(self, items): self.items = items
    def iterate_items(self): return iter(self.items)

class Fake:
    def __init__(self): self.calls, self.store = [], {}
    def actor(self, name):
        fk = self
        class A:
            def call(self, run_input, max_items, timeout_secs):
                fk.calls.append((name, run_input, max_items)); items = fk.make(name, run_input)[:max_items]
                did = f"d{len(fk.calls)}"; fk.store[did] = items
                return {"id": f"r{len(fk.calls)}", "status": "SUCCEEDED", "defaultDatasetId": did}
        return A()
    def dataset(self, did): return DS(self.store[did])
    def make(self, name, inp):
        if name == "apify/instagram-scraper":
            h = inp["directUrls"][0].rstrip("/").split("/")[-1]
            return [{"url": f"https://www.instagram.com/p/{h}{i}/", "timestamp": (dt.datetime(2024, 1, 15) + dt.timedelta(days=12 * i)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                     "commentsCount": 3, "ownerUsername": h, "caption": "cap"} for i in range(80)]
        if name == "streamers/youtube-scraper":
            h = inp["startUrls"][0]["url"].split("@")[1].split("/")[0]
            return [{"url": f"https://www.youtube.com/watch?v={h}{i}", "date": f"2025-0{1 + i % 9}-10T00:00:00Z", "commentsCount": 2,
                     "channelUsername": h, "title": "t"} for i in range(20)]
        if name == "apify/instagram-comment-scraper":
            return [{"id": f"{u}-{k}", "postUrl": u, "text": "mantap PKB", "ownerUsername": f"warga{k}", "owner": {"id": f"9{k}"},
                     "timestamp": "2024-02-01T00:00:00.000Z", "replies": [{"id": f"{u}-{k}-r", "text": "setuju", "ownerUsername": "warga99", "owner": {"id": "999"}, "timestamp": "2024-02-02T00:00:00.000Z"}]}
                    for u in inp["directUrls"] for k in range(2)]
        if name == "streamers/youtube-comments-scraper":
            return [{"cid": f"{x['url']}-{k}", "pageUrl": x["url"], "comment": "bagus", "author": f"@pen{k}", "replyToCid": None} for x in inp["startUrls"] for k in range(2)]
        if name == "apidojo/tweet-scraper":
            h = inp["searchTerms"][0].split()[0][5:]
            return [{"id": "t1" + h, "url": "u", "text": "rapat @DPP_PKB", "createdAt": "Thu Feb 15 00:29:16 +0000 2024", "author": {"userName": h, "id": "1"},
                     "entities": {"user_mentions": [{"screen_name": "DPP_PKB", "id_str": "2"}]}},
                    {"id": "t2" + h, "url": "u2", "text": "RT", "createdAt": "Thu Feb 15 00:29:16 +0000 2024", "author": {"userName": h, "id": "1"},
                     "retweet": {"text": "asli", "author": {"userName": "kompascom", "id": "3"}}}]
        return []

def setup(tmp_path, monkeypatch, usd):
    for k, v in {"RAW": "raw", "OUT": "out", "PRIV": "priv", "STATE": "st.json"}.items(): monkeypatch.setattr(ac, k, tmp_path / v)
    monkeypatch.setenv("ANON_SALT", "uji-garam")
    c, a = ac.cfg_all(); c["period"] = {"since": "2024-01-01", "until": "2026-11-30"}
    a.update(max_usd=usd, posts_per_month=2, comments_per_post=5)
    return c, a

def test_collect_budget_build(tmp_path, monkeypatch):
    c, a = setup(tmp_path, monkeypatch, usd=2.0)
    f = Fake(); ac.cmd_collect(c, a, client=f)
    st = json.loads((tmp_path / "st.json").read_text())
    assert st["usd"] <= 2.0 + 1e-9                      # batas biaya keras
    assert all("from:" in x[1]["searchTerms"][0] for x in f.calls if x[0] == "apidojo/tweet-scraper")  # X hanya akun partai
    assert not any("to:" in json.dumps(x[1]) for x in f.calls)
    smp = st["sample"]["PKS|instagram"]; assert all(len(v) <= 2 for v in smp.values())
    n1 = len(f.calls); ac.cmd_collect(c, a, client=f)  # dilanjutkan: tidak mengulang yang selesai
    ac.cmd_build(c, a)
    rows = list(csv.DictReader(open(tmp_path / "out" / "sna_apify.csv", encoding="utf-8-sig")))
    kinds = {(r["platform"], r["interaction"]) for r in rows}
    assert ("x", "mention") in kinds and ("x", "repost") in kinds
    assert all(r["author"].startswith(("u_", "PKS_", "PKB_", "PPP_", "PAN_")) for r in rows)
    assert not any("warga" in r["author"] for r in rows)
    names = list(csv.DictReader(open(tmp_path / "priv" / "names_private_apify.csv", encoding="utf-8-sig")))
    assert any(n["handle"] == "kompascom" for n in names)

def test_full_budget_comments(tmp_path, monkeypatch):
    c, a = setup(tmp_path, monkeypatch, usd=100.0)
    f = Fake(); ac.cmd_collect(c, a, client=f); ac.cmd_build(c, a)
    rows = list(csv.DictReader(open(tmp_path / "out" / "sna_apify.csv", encoding="utf-8-sig")))
    kinds = {(r["platform"], r["interaction"]) for r in rows}
    assert {("instagram", "comment"), ("instagram", "reply"), ("youtube", "comment")} <= kinds
    ig = [r for r in rows if r["platform"] == "instagram" and r["interaction"] == "comment"]
    assert {r["target_user"] for r in ig} <= {"PKS_instagram_official", "PKB_instagram_official", "PPP_instagram_official", "PAN_instagram_official"}

def test_v3_client_style():
    """apify-client v3: call(run_timeout=timedelta) mengembalikan model (snake_case), bukan dict."""
    from types import SimpleNamespace as NS
    from enum import Enum
    class St(Enum): OK = "SUCCEEDED"
    seen = {}
    class A3:
        def call(self, *, run_input=None, max_items=None, run_timeout=None, timeout="no_timeout"):
            seen["rt"] = run_timeout
            return NS(id="r1", status=St.OK, default_dataset_id="d1", usage_total_usd=0.01)
    run = ac._call(A3(), {"x": 1}, 5)
    assert seen["rt"] == dt.timedelta(seconds=3600)
    assert ac._rget(run, "defaultDatasetId", "default_dataset_id") == "d1"
    assert ac._rget(run, "usageTotalUsd", "usage_total_usd") == 0.01
    assert ac._status(run) == "SUCCEEDED"
    assert ac._rget({"defaultDatasetId": "d2"}, "defaultDatasetId", "default_dataset_id") == "d2"

def test_rel_date():
    ref = dt.datetime(2026, 11, 2, tzinfo=dt.timezone.utc)
    assert ac.rel_date("2 months ago", ref).date() == dt.date(2026, 9, 2)
    assert ac.rel_date("1 year ago (edited)", ref).year == 2025
    assert ac.rel_date("3 minggu yang lalu", ref).date() == dt.date(2026, 10, 12)
    assert ac.rel_date("", ref) is None and ac.rel_date("baru saja", ref) is None
