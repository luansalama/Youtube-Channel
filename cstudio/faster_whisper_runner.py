"""Isolated faster-whisper runner used by the YouTube Mirror Resolver.

This module intentionally has no Cuts Studio imports so it can run under the
user's dedicated Whisper virtualenv even when the dashboard itself uses another
Python environment.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def _emit(event: str, **data) -> None:
    print("CSTUDIO_FW " + json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def _segment_dict(segment, *, offset: float = 0.0, word_timestamps: bool = False) -> dict:
    words = []
    if word_timestamps:
        for word in list(getattr(segment, "words", None) or []):
            try:
                start = float(word.start) + offset
                end = float(word.end) + offset
            except (TypeError, ValueError):
                continue
            words.append({
                "word": str(getattr(word, "word", "") or ""),
                "start": round(start, 3),
                "end": round(end, 3),
                "probability": round(float(getattr(word, "probability", 0.0) or 0.0), 5),
            })
    return {
        "start": round(float(segment.start) + offset, 3),
        "end": round(float(segment.end) + offset, 3),
        "text": str(segment.text or ""),
        "words": words,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    model_path = str(spec["model"])
    device = str(spec.get("device") or "cuda")
    compute_type = str(spec.get("compute_type") or ("float16" if device == "cuda" else "int8"))
    batch_size = max(1, int(spec.get("batch_size") or 8))
    inference_mode = str(spec.get("inference_mode") or "plain").strip().lower()
    if inference_mode not in {"plain", "batched"}:
        raise RuntimeError(f"unsupported faster-whisper inference_mode: {inference_mode}")
    language = str(spec.get("language") or "").strip() or None
    beam_size = max(1, int(spec.get("beam_size") or 5))
    word_timestamps = bool(spec.get("word_timestamps", False))

    # Import inside main so import/runtime errors are visible in the captured log.
    import ctranslate2
    import faster_whisper
    from faster_whisper import WhisperModel

    _emit(
        "runtime",
        faster_whisper=getattr(faster_whisper, "__version__", "unknown"),
        ctranslate2=getattr(ctranslate2, "__version__", "unknown"),
        cuda_devices=int(ctranslate2.get_cuda_device_count()),
        device=device,
        compute_type=compute_type,
        batch_size=(batch_size if inference_mode == "batched" else None),
        inference_mode=inference_mode,
        word_timestamps=word_timestamps,
    )

    started = time.perf_counter()
    model = WhisperModel(
        model_path,
        device=device,
        compute_type=compute_type,
        local_files_only=True,
    )
    transcriber = model
    if inference_mode == "batched":
        from faster_whisper import BatchedInferencePipeline
        transcriber = BatchedInferencePipeline(model=model)
    _emit(
        "model_ready",
        seconds=round(time.perf_counter() - started, 3),
        model=model_path,
        inference_mode=inference_mode,
    )

    all_segments: list[dict] = []
    detected_languages: list[str] = []
    processed_seconds = 0.0

    inputs = list(spec.get("inputs") or [])
    if not inputs:
        raise RuntimeError("faster-whisper runner received no inputs")

    for index, item in enumerate(inputs, 1):
        path = str(item["path"])
        offset = float(item.get("offset") or 0.0)
        ranges = list(item.get("ranges") or [])
        clip_timestamps = None
        if ranges:
            normalized_ranges = [
                (max(0.0, float(r[0])), max(float(r[0]), float(r[1])))
                for r in ranges
            ]
            # faster-whisper exposes different clip_timestamps contracts on
            # WhisperModel (flat second pairs) and BatchedInferencePipeline
            # ({start,end} dicts). Keep the adapter here so callers can use one
            # stable range representation.
            if inference_mode == "batched":
                clip_timestamps = [
                    {"start": start, "end": end}
                    for start, end in normalized_ranges
                ]
            else:
                clip_timestamps = [value for pair in normalized_ranges for value in pair]
            processed_seconds += sum(max(0.0, end - start) for start, end in normalized_ranges)
        else:
            processed_seconds += max(0.0, float(item.get("duration") or 0.0))

        _emit(
            "input_start",
            index=index,
            inputs=len(inputs),
            file=os.path.basename(path),
            ranges=len(ranges),
            offset=round(offset, 3),
        )
        t0 = time.perf_counter()
        transcribe_kwargs = {
            "language": language,
            "task": "transcribe",
            "beam_size": beam_size,
            "condition_on_previous_text": False,
            "word_timestamps": word_timestamps,
            # Segment timestamps are part of the discovery contract. Setting
            # this to True samples text tokens only and throws away the timing
            # information we need for candidate moments.
            "without_timestamps": False,
            "vad_filter": not bool(clip_timestamps),
            "clip_timestamps": clip_timestamps,
            "log_progress": True,
        }
        if inference_mode == "batched":
            transcribe_kwargs["batch_size"] = batch_size
        segments, info = transcriber.transcribe(path, **transcribe_kwargs)
        count = 0
        for segment in segments:
            all_segments.append(_segment_dict(segment, offset=offset, word_timestamps=word_timestamps))
            count += 1
        if getattr(info, "language", None):
            detected_languages.append(str(info.language))
        _emit(
            "input_done",
            index=index,
            segments=count,
            seconds=round(time.perf_counter() - t0, 3),
            language=getattr(info, "language", None),
            duration=round(float(getattr(info, "duration", 0.0) or 0.0), 3),
            duration_after_vad=round(float(getattr(info, "duration_after_vad", 0.0) or 0.0), 3),
        )

    all_segments.sort(key=lambda x: (float(x["start"]), float(x["end"])))
    text = " ".join(str(seg.get("text") or "").strip() for seg in all_segments if str(seg.get("text") or "").strip())
    raw = {
        "text": text,
        "language": detected_languages[0] if detected_languages else (language or ""),
        "segments": all_segments,
        "backend": {
            "name": "faster-whisper",
            "faster_whisper": getattr(faster_whisper, "__version__", "unknown"),
            "ctranslate2": getattr(ctranslate2, "__version__", "unknown"),
            "device": device,
            "compute_type": compute_type,
            "inference_mode": inference_mode,
            "batch_size": (batch_size if inference_mode == "batched" else None),
            "beam_size": beam_size,
            "vad_filter": True,
            "condition_on_previous_text": False,
            "word_timestamps": word_timestamps,
            "without_timestamps": False,
        },
        "processed_duration_seconds": round(processed_seconds, 3),
    }
    Path(args.output).write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    _emit("done", segments=len(all_segments), seconds=round(time.perf_counter() - started, 3))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        _emit("error", type=exc.__class__.__name__, message=str(exc)[:2000])
        raise
