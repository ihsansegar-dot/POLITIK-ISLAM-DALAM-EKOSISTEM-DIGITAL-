"""Uji offline: collect + build memakai fixture (tanpa API, tanpa kredit). Jalankan: python -m pytest -q tests"""
import copy, csv, json, os, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import yaml
import sc_pipeline as sp

FX = ROOT / "tests" / "fixtures"
FILES = {"ig_user_posts": "ig_user_posts.json", "ig_post_comments": "ig_post_comments.json",
         "tt_profile_videos": "tt_profile_videos.json", "tt_video_comments": "tt_video_comments.json",
         "yt_channel_videos": "yt_channel_videos.json", "yt_video_comments": "yt_video_comments.json",
         "yt_comment_replies": "yt_comment_replies.json", "x_user_tweets": "x_user_tweets.json"}


class FakeClient(sp.Client):
    def __init__(self, cfg, run_id):
        self.cfg, self.run_id, self.credits, self.max, self.n = cfg, run_id, 0, cfg["budget"]["max_credits_per_run"], 0
        self.calls = []
        import threading; self.lock = threading.Lock()

    def get(self, key, params, meta):
        if self.credits >= self.max:
            raise sp.BudgetExceeded("x")
        self.calls.append(key)
        d = json.loads((FX / FILES[key]).read_text())
        d["next_max_id"] = None  # hentikan paginasi
        self.credits += d.get("credits_charged", 1)
        self._log(key, params, meta, 200, 1, "")
        self._save(key, params, meta, d)
        return d


def setup(tmp_path, monkeypatch, budget=500, replies=True):
    monkeypatch.setattr(sp, "RAW", tmp_path / "raw"); monkeypatch.setattr(sp, "OUT", tmp_path / "out")
    monkeypatch.setattr(sp, "LOG", tmp_path / "log.csv"); monkeypatch.setenv("ANON_SALT", "uji-garam")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    cfg["period"] = {"since": "2019-01-01", "until": "2026-12-31"}
    cfg["budget"].update(max_credits_per_run=budget, max_posts_per_account=3, max_comment_pages_per_post=1, fetch_replies=replies)
    for p in cfg["seeds"]["PKS"].values():
        p["status"] = "verified"
    return cfg


def read(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def test_end_to_end(tmp_path, monkeypatch):
    cfg = setup(tmp_path, monkeypatch)
    fc = FakeClient(cfg, "run1")
    sp.cmd_collect(cfg, client=fc)
    # akun non-verified (PKB/PPP/PAN) tidak boleh disentuh
    assert all(c in FILES for c in fc.calls)
    sp.cmd_build(cfg)
    out = tmp_path / "out"
    content, comments, net, acc = (read(out / f) for f in ["content_dataset.csv", "comment_dataset.csv", "network_dataset.csv", "account_dataset.csv"])
    assert {r["platform"] for r in content} == {"instagram", "tiktok", "youtube", "x"}
    # anonimisasi: tidak ada username warga di output
    blob = "".join(open(out / f, encoding="utf-8-sig").read() for f in os.listdir(out))
    for name in ["warga_a", "warga_b", "warga_c", "penonton1", "penonton2", "penonton_tt"]:
        assert name not in blob, name
    # akun resmi tetap bernama institusional
    assert any(r["anonymous_account_id"] == "PKS_instagram_official" for r in acc)
    # IG: komentar -> akun resmi, balasan -> penulis komentar induk
    ig = [r for r in net if r["platform"] == "instagram"]
    types = {r["interaction_type"] for r in ig}
    assert {"comment", "reply"} <= types and "mention" in types
    owners = {r["account_id"] for r in content if r["platform"] == "instagram"}
    assert all(r["target_id"] in owners for r in ig if r["interaction_type"] == "comment")
    # feed pilot nyata memuat post kolaborasi milik akun lain -> harus ditandai
    assert any(r["owned_by_seed"] == "False" for r in content if r["platform"] == "instagram")
    # YouTube: balasan menunjuk ke penulis komentar induk, tanggal ditandai perkiraan
    yt = [r for r in comments if r["platform"] == "youtube"]
    assert {r["date_precision"] for r in yt} == {"approx_relative"} and any(r["reply_to"] for r in yt)
    # SNA Explorer: kolom wajib ada
    sna = read(out / "sna_explorer.csv")
    assert set(sna[0]) >= {"author", "text", "type", "target_user", "created_at"}
    assert sum(int(r["interaction_weight"]) for r in net) == len(sna)


def test_salt_changes_ids(tmp_path, monkeypatch):
    cfg = setup(tmp_path, monkeypatch)
    sp.cmd_collect(cfg, client=FakeClient(cfg, "r"))
    sp.cmd_build(cfg); a = {r["anonymous_account_id"] for r in read(tmp_path / "out" / "account_dataset.csv")}
    monkeypatch.setenv("ANON_SALT", "garam-lain"); sp.cmd_build(cfg)
    b = {r["anonymous_account_id"] for r in read(tmp_path / "out" / "account_dataset.csv")}
    assert {x for x in a if x.endswith("_official")} == {x for x in b if x.endswith("_official")}
    assert a != b


def test_budget_stops(tmp_path, monkeypatch):
    cfg = setup(tmp_path, monkeypatch, budget=3)
    fc = FakeClient(cfg, "r"); sp.cmd_collect(cfg, client=fc)
    assert fc.credits <= 3 + 1 and len(fc.calls) <= 4


def test_no_double_count_across_runs(tmp_path, monkeypatch):
    cfg = setup(tmp_path, monkeypatch)
    sp.cmd_collect(cfg, client=FakeClient(cfg, "r1")); sp.cmd_build(cfg)
    n1 = len(read(tmp_path / "out" / "comment_dataset.csv")); e1 = len(read(tmp_path / "out" / "sna_explorer.csv"))
    sp.cmd_collect(cfg, client=FakeClient(cfg, "r2")); sp.cmd_build(cfg)   # komentar yang sama terambil lagi
    assert len(read(tmp_path / "out" / "comment_dataset.csv")) == n1
    assert len(read(tmp_path / "out" / "sna_explorer.csv")) == e1


def test_monthly_sampling(tmp_path, monkeypatch):
    cfg = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(sp, "STATE", tmp_path / "state.json")
    cfg["period"] = {"since": "2026-10-01", "until": "2026-11-30"}
    cfg["sampling"] = {"platforms": ["instagram", "tiktok", "youtube"], "posts_per_month": 2, "min_comments": 1,
                       "seed": 2029, "max_credits_per_account": 50, "max_feed_pages": 3, "workers": 2}
    fc = FakeClient(cfg, "m"); sp.cmd_collect_monthly(cfg, client=fc)
    st = json.loads((tmp_path / "state.json").read_text())
    ig = st["sample"]["PKS|instagram"]
    assert set(ig) <= {"2026-10", "2026-11"} and all(len(v) <= 2 for v in ig.values())
    # deterministik: run ulang memberi sampel sama dan tidak mengambil ulang komentar
    n_calls = len(fc.calls); fc2 = FakeClient(cfg, "m"); sp.cmd_collect_monthly(cfg, client=fc2)
    assert json.loads((tmp_path / "state.json").read_text())["sample"]["PKS|instagram"] == ig
    assert "ig_post_comments" not in fc2.calls
    assert "x_user_tweets" not in fc.calls
