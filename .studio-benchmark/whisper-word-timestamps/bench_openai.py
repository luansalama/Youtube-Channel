"""Benchmark isolado OpenAI Whisper Turbo — mede load vs transcribe.
Uso:
  python bench_openai.py --audio sample.wav --word-timestamps False --repeats 2 --output out.json
Nao toca no harness; apenas le o wav e escreve JSON no output.
"""
import argparse, json, time, os, sys
import torch

def get_args():
    p = argparse.ArgumentParser()
    p.add_argument("--audio", required=True)
    p.add_argument("--word-timestamps", required=True, help="True/False")
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--output", required=True)
    p.add_argument("--model", default="turbo")
    p.add_argument("--model-dir", default=r"K:\Applications\LLMS\Whisper")
    p.add_argument("--language", default="pt")
    p.add_argument("--device", default="cuda")
    return p.parse_args()

def main():
    a = get_args()
    wt = str(a.word_timestamps).lower() in ("1","true","yes")
    import whisper
    print(f"whisper={getattr(whisper,'__version__','?')} torch={torch.__version__} cuda={torch.cuda.is_available()}", flush=True)
    # load
    t0 = time.perf_counter()
    model = whisper.load_model(a.model, device=a.device, download_root=a.model_dir)
    t_load = time.perf_counter() - t0
    print(f"model loaded in {t_load:.2f}s device={model.device}", flush=True)
    # warm-up: 30s slice via whisper audio load + tiny transcribe? Use first 30s to warm CUDA without full cost.
    # whisper.load_audio loads full file; for warmup we transcribe with word_timestamps=False on same file but discard? That would be full cost.
    # Instead do a single forward pass warmup: encode a dummy mel.
    try:
        torch.cuda.reset_peak_memory_stats()
        dummy_mel = torch.zeros((80, 3000), device=model.device)
        with torch.no_grad():
            _ = model.encoder(dummy_mel.unsqueeze(0))
        torch.cuda.synchronize()
        print("cuda warmup forward OK", flush=True)
    except Exception as e:
        print(f"warmup forward skipped: {e}", flush=True)

    audio_path = a.audio
    # duration via whisper audio
    audio = whisper.load_audio(audio_path)
    duration_s = len(audio) / 16000.0
    print(f"audio {audio_path} samples={len(audio)} duration={duration_s:.1f}s", flush=True)

    runs = []
    for i in range(a.repeats):
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        result = model.transcribe(
            audio_path,
            language=a.language,
            task="transcribe",
            word_timestamps=wt,
            condition_on_previous_text=False,
            verbose=False,
        )
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        t_total = time.perf_counter() - t0
        vram_max = float(torch.cuda.max_memory_allocated() / (1024**3)) if torch.cuda.is_available() else 0.0
        segs = result.get("segments", [])
        nseg = len(segs)
        nwords = sum(len(s.get("words", []) or []) for s in segs)
        rtf = t_total / duration_s if duration_s else 0
        print(f"run {i+1}/{a.repeats}: total={t_total:.2f}s segs={nseg} words={nwords} rtf={rtf:.3f} vram={vram_max:.2f}GB", flush=True)
        runs.append({
            "run": i+1,
            "total_s": round(t_total, 3),
            "segments": nseg,
            "words": nwords,
            "rtf": round(rtf, 5),
            "vram_max_gb": round(vram_max, 3),
        })
        # save first run full result for quality comparison (trimmed)
        if i == 0:
            # save segments+words compact
            out_full = a.output.replace(".json", ".full_run0.json")
            with open(out_full, "w", encoding="utf-8") as f:
                json.dump({"text": result.get("text","")[:2000], "language": result.get("language",""), "segments": segs}, f, ensure_ascii=False)
            print(f"saved full run0 to {out_full}", flush=True)

    totals = sorted(r["total_s"] for r in runs)
    median = totals[len(totals)//2] if totals else 0
    payload = {
        "audio": os.path.abspath(audio_path),
        "audio_duration_s": duration_s,
        "model": a.model,
        "model_dir": a.model_dir,
        "device": a.device,
        "language": a.language,
        "word_timestamps": wt,
        "condition_on_previous_text": False,
        "load_s": round(t_load, 3),
        "runs": runs,
        "median_total_s": round(median, 3),
        "median_rtf": round(median/duration_s, 5) if duration_s else 0,
        "torch": torch.__version__,
        "whisper": getattr(whisper, "__version__", "unknown"),
    }
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"WROTE {a.output} median={median:.2f}s", flush=True)

if __name__ == "__main__":
    main()
