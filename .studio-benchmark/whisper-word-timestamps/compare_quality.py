"""Compara qualidade word timestamps: OpenAI fallback vs Triton vs Faster-Whisper plain."""
import json
base = r"K:\Applications\Youtube-Channel\.studio-benchmark\whisper-word-timestamps"
b = json.load(open(base+r"\bench_B_WT_fallback.full_run0.json", encoding="utf-8"))
c = json.load(open(base+r"\bench_C_WT_triton.full_run0.json", encoding="utf-8"))
d = json.load(open(base+r"\bench_D_plain_float16.full_run0.json", encoding="utf-8"))

def words_from_openai(payload):
    out=[]
    for s in payload["segments"]:
        for w in s.get("words",[]):
            out.append((w["word"], float(w["start"]), float(w["end"]), float(w.get("probability",0))))
    return out

def words_from_fw(payload):
    # bench_D plain full_run0 has segments_sample? Actually bench_faster saves segments_sample with 50 segs, not full. Need full? We saved only 50 sample.
    # For full comparison, reload? Our bench_faster only saved 50 segs sample. Let's use that for first 60s, plus note limitation.
    out=[]
    segs = payload.get("segments_sample") or payload.get("segments") or []
    for s in segs:
        for w in s.get("words",[]):
            out.append((w["word"], float(w["start"]), float(w["end"]), float(w.get("prob",0))))
    return out

wb = words_from_openai(b)
wc = words_from_openai(c)
wd = words_from_fw(d)

print(f"OPENAI fallback words={len(wb)} (full 10min)")
print(f"OPENAI triton   words={len(wc)} (full 10min)")
print(f"FW plain words(sample 50 segs)={len(wd)}")

# Check B vs C identical? (should be deterministic? Triton vs fallback should give same alignment? Or tiny diffs?)
diffs = []
for i,(a1,a2) in enumerate(zip(wb,wc)):
    if a1[0]!=a2[0]:
        print(f"word mismatch at {i}: {a1[0]!r} vs {a2[0]!r}")
        break
    ds = abs(a1[1]-a2[1]); de = abs(a1[2]-a2[2])
    diffs.append((ds,de))
else:
    import numpy as np
    dss = [x[0] for x in diffs]; des=[x[1] for x in diffs]
    print(f"B vs C: max start diff={max(dss):.4f}s max end diff={max(des):.4f}s mean start diff={sum(dss)/len(dss):.5f}s")
    print(f"B vs C identical timestamps? {max(dss)==0 and max(des)==0}")

def check(name, words):
    bad_order=0; repeated=0; gaps=[]; neg_dur=0; overlaps=0
    prev_end=None
    for i,(w,s,e,p) in enumerate(words):
        if e < s:
            neg_dur+=1
        if prev_end is not None:
            if s < prev_end - 1e-6:
                # allow tiny overlap due to rounding? count if >0.05
                if prev_end - s > 0.05:
                    overlaps+=1
            gap = s - prev_end
            gaps.append(gap)
            if i>0 and s < words[i-1][1] - 1e-9:
                bad_order+=1
        prev_end=e
    import numpy as np
    gaps_arr = np.array(gaps) if gaps else np.array([0])
    print(f"\n{name}: n={len(words)} neg_dur={neg_dur} overlaps>50ms={overlaps} bad_order={bad_order}")
    print(f"  gap mean={gaps_arr.mean():.3f}s median={np.median(gaps_arr):.3f}s max={gaps_arr.max():.3f}s min={gaps_arr.min():.3f}s gaps>2s={(gaps_arr>2).sum()}")
    # repeated timestamps
    starts = [w[1] for w in words]
    print(f"  unique starts={len(set(starts))}/{len(starts)}")
    # first 15 words
    print(f"  first 15:")
    for w,s,e,p in words[:15]:
        print(f"    {s:7.2f}-{e:7.2f} p={p:.2f} {w!r}")

check("OPENAI fallback", wb)
check("OPENAI triton", wc)
check("FW plain (50 segs sample)", wd)

# Compare same region 60-120s: find words in window
def window(words, a,b_):
    return [(w,s,e,p) for w,s,e,p in words if s>=a and s<b_]
print("\n=== WINDOW 60-90s ===")
for name, words in [("fallback",wb),("triton",wc),("fw",wd)]:
    wwin = window(words,60,90)
    print(f"\n{name} ({len(wwin)} words):")
    for w,s,e,p in wwin[:20]:
        print(f"  {s:7.2f}-{e:7.2f} {w!r}")
