"""Benchmark isolado Faster-Whisper — apples-to-apples + otimizado.
Uso:
  python bench_faster.py --audio sample.wav --word-timestamps True --compute-type float16 --batch-size 8 --repeats 2 --output out.json
"""
import argparse, json, time, os
def get_args():
    p = argparse.ArgumentParser()
    p.add_argument("--audio", required=True)
    p.add_argument("--word-timestamps", default="True")
    p.add_argument("--compute-type", default="float16")
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--beam-size", type=int, default=5)
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--output", required=True)
    p.add_argument("--model", default=r"K:\Applications\LLMS\Whisper\faster-whisper-large-v3-turbo")
    p.add_argument("--language", default="pt")
    p.add_argument("--device", default="cuda")
    p.add_argument("--batched", default="True", help="True=use BatchedInferencePipeline, False=plain WhisperModel")
    return p.parse_args()

def main():
    a = get_args()
    wt = str(a.word_timestamps).lower() in ("1","true","yes")
    use_batched = str(a.batched).lower() in ("1","true","yes")
    import faster_whisper, ctranslate2, torch
    print(f"faster_whisper={faster_whisper.__version__} ctranslate2={ctranslate2.__version__} cuda_devices={ctranslate2.get_cuda_device_count()}", flush=True)
    from faster_whisper import WhisperModel, BatchedInferencePipeline
    # duration via wave
    import wave
    with wave.open(a.audio, "rb") as w:
        duration_s = w.getnframes() / float(w.getframerate())
    print(f"audio {a.audio} duration={duration_s:.1f}s", flush=True)
    t0 = time.perf_counter()
    model = WhisperModel(a.model, device=a.device, compute_type=a.compute_type, local_files_only=True)
    t_load = time.perf_counter() - t0
    print(f"model loaded in {t_load:.2f}s compute_type={a.compute_type} device={a.device}", flush=True)
    pipe = BatchedInferencePipeline(model=model) if use_batched else None

    runs = []
    for i in range(a.repeats):
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        if use_batched:
            segments, info = pipe.transcribe(
                a.audio, language=a.language, task="transcribe",
                beam_size=a.beam_size, batch_size=a.batch_size,
                condition_on_previous_text=False,
                word_timestamps=wt,
            )
        else:
            segments, info = model.transcribe(
                a.audio, language=a.language, task="transcribe",
                beam_size=a.beam_size,
                condition_on_previous_text=False,
                word_timestamps=wt,
            )
        # materialize generator
        segs = list(segments)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        t_total = time.perf_counter() - t0
        vram_max = float(torch.cuda.max_memory_allocated() / (1024**3)) if torch.cuda.is_available() else 0.0
        nseg = len(segs)
        nwords = sum(len(getattr(s, "words", None) or []) for s in segs)
        rtf = t_total / duration_s if duration_s else 0
        print(f"run {i+1}/{a.repeats}: total={t_total:.2f}s segs={nseg} words={nwords} rtf={rtf:.3f} vram={vram_max:.2f}GB lang={getattr(info,'language', '?')}", flush=True)
        runs.append({"run": i+1, "total_s": round(t_total,3), "segments": nseg, "words": nwords, "rtf": round(rtf,5), "vram_max_gb": round(vram_max,3)})
        if i == 0:
            out_full = a.output.replace(".json", ".full_run0.json")
            dump = []
            for s in segs[:50]:
                words = [{"word": w.word, "start": round(float(w.start),2), "end": round(float(w.end),2), "prob": round(float(getattr(w,'probability',0)),4)} for w in (s.words or [])]
                dump.append({"start": round(float(s.start),2), "end": round(float(s.end),2), "text": s.text, "words": words})
            with open(out_full, "w", encoding="utf-8") as f:
                json.dump({"language": getattr(info,"language",""), "segments_sample": dump, "total_segments": nseg}, f, ensure_ascii=False, indent=2)
            print(f"saved {out_full}", flush=True)

    totals = sorted(r["total_s"] for r in runs)
    median = totals[len(totals)//2]
    payload = {
        "audio": os.path.abspath(a.audio), "audio_duration_s": duration_s,
        "model": a.model, "device": a.device, "compute_type": a.compute_type,
        "batch_size": a.batch_size, "beam_size": a.beam_size, "batched": use_batched,
        "language": a.language, "word_timestamps": wt, "condition_on_previous_text": False,
        "load_s": round(t_load,3), "runs": runs, "median_total_s": round(median,3),
        "median_rtf": round(median/duration_s,5) if duration_s else 0,
        "faster_whisper": faster_whisper.__version__, "ctranslate2": ctranslate2.__version__,
    }
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"WROTE {a.output} median={median:.2f}s", flush=True)

if __name__ == "__main__":
    main()
