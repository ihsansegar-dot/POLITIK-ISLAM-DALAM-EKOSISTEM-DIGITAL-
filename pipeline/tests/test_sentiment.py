import csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sentiment as s

class Fake:
    def __init__(self, lab): self.lab, self.seen = lab, []
    def __call__(self, texts):
        self.seen += texts
        return [{"label": self.lab(t), "score": 0.9} for t in texts]

def test_run(tmp_path):
    inp, out = tmp_path / "in.csv", tmp_path / "out.csv"
    rows = [dict(author="kompas.com", text="PKS Menang Besar — JAKARTA, KOMPAS.com - isi", platform="media", party="PKS"),
            dict(author="kompas.com", text="PKS Menang Besar — JAKARTA, KOMPAS.com - isi", platform="media", party="PKB"),
            dict(author="u_1", text="mantap @dpp_pkb https://x.y", platform="tiktok", party="PKB"),
            dict(author="u_2", text="buruk sekali", platform="tiktok", party="PKB")]
    with open(inp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    main = Fake(lambda t: "LABEL_2" if "buruk" in t else "LABEL_0")
    alt = Fake(lambda t: "negative" if "buruk" in t else ("neutral" if "PKS" in t else "positive"))
    s.run(inp, out, pipes={"main": main, "alt": alt})
    assert sorted(main.seen) == ["PKS Menang Besar", "buruk sekali", "mantap"]  # dedup + judul saja + tanpa @/URL
    o = list(csv.DictReader(open(out, encoding="utf-8-sig")))
    assert [r["sent"] for r in o] == ["positif", "positif", "positif", "negatif"]
    assert [r["sent_agree"] for r in o] == ["0", "0", "1", "1"]
