#!/usr/bin/env python3
"""
Analisis sentimen (positif / netral / negatif) untuk setiap baris teks dataset dashboard.

Model utama : mdhugol/indonesia-bert-sentiment-classification
              (IndoBERT base p1, fine-tune SmSA/Prosa; LABEL_0=positive, LABEL_1=neutral, LABEL_2=negative)
Model banding: w11wo/indonesian-roberta-base-sentiment-classifier
              (RoBERTa base Indonesia, fine-tune SmSA; uji: akurasi 93,2%, F1-macro 91,02% menurut kartu model)

Dua model dipakai agar ada indikator keandalan sederhana: tingkat kesepakatan antarmodel.
Keduanya dilatih pada ulasan/komentar (SmSA), BUKAN berita politik -> label untuk judul berita
perlu divalidasi manual pada sampel sebelum dipakai sebagai temuan.

Pemakaian:
  python sentiment.py MASUKAN.csv KELUARAN.csv
Masukan: CSV berkolom author,text,type,target_user,created_at,platform,party,interaction,content_url.
Keluaran: kolom yang sama + sent, sent_score, sent_alt, sent_alt_score, sent_agree, sent_text.
Teks yang sama hanya diklasifikasi sekali (media: per judul artikel).
"""
import csv, re, sys, time

MAIN = "mdhugol/indonesia-bert-sentiment-classification"
ALT = "w11wo/indonesian-roberta-base-sentiment-classifier"
LBL = {"label_0": "positif", "label_1": "netral", "label_2": "negatif",
       "positive": "positif", "neutral": "netral", "negative": "negatif"}


def prep(row):
    """Teks yang dinilai. Media: judul saja (bagian sebelum ' — '). Sosial: buang URL & @mention."""
    t = row.get("text") or ""
    if (row.get("platform") or "").lower() == "media":
        t = t.split(" — ", 1)[0]
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"@[\w.]+", " ", t)
    return " ".join(t.split())[:1000]


def load_pipe(name):
    from transformers import pipeline
    return pipeline("text-classification", model=name, tokenizer=name, truncation=True, max_length=256, device=-1)


def classify(pipe, texts, batch=16, tag=""):
    out, t0 = [], time.time()
    for i in range(0, len(texts), batch):
        for r in pipe(texts[i:i + batch]):
            out.append((LBL.get(str(r["label"]).lower(), str(r["label"]).lower()), round(float(r["score"]), 4)))
        if (i // batch) % 10 == 0:
            print(f"  {tag} {min(i + batch, len(texts))}/{len(texts)} ({time.time() - t0:.0f} dtk)", flush=True)
    return out


def run(inp, outp, pipes=None):
    rows = list(csv.DictReader(open(inp, encoding="utf-8-sig")))
    for r in rows: r["sent_text"] = prep(r)
    uniq = sorted({r["sent_text"] for r in rows if r["sent_text"]})
    print(f"[sentimen] {len(rows)} baris, {len(uniq)} teks unik", flush=True)
    pipes = pipes or {"main": load_pipe(MAIN), "alt": load_pipe(ALT)}
    res = {k: dict(zip(uniq, classify(p, uniq, tag=k))) for k, p in pipes.items()}
    for r in rows:
        t = r["sent_text"]
        m, a = res["main"].get(t, ("", "")), res["alt"].get(t, ("", ""))
        r.update(sent=m[0], sent_score=m[1], sent_alt=a[0], sent_alt_score=a[1],
                 sent_agree=("" if not t else int(m[0] == a[0])))
    cols = list(rows[0].keys())
    with open(outp, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
    from collections import Counter
    lab = [r for r in rows if r["sent"]]
    agree = sum(int(r["sent_agree"]) for r in lab) / max(len(lab), 1)
    print(f"[sentimen] selesai: {dict(Counter(r['sent'] for r in lab))}; kesepakatan IndoBERT-RoBERTa {agree:.1%}", flush=True)
    for plat in sorted({r["platform"] for r in lab}):
        sub = [r for r in lab if r["platform"] == plat]
        print(f"  {plat}: {dict(Counter(r['sent'] for r in sub))} kesepakatan "
              f"{sum(int(r['sent_agree']) for r in sub) / len(sub):.1%}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 3: sys.exit(__doc__)
    run(sys.argv[1], sys.argv[2])
