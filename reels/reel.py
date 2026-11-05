#!/usr/bin/env python3
"""Batch Reels editor: silence cut, punch-in zooms, loudness, Whisper captions.

Usage:
  python reels/reel.py --brand seddamchile [--out salida/] video1.mp4 [video2.mp4 | carpeta/ ...]

For each input video it writes <out>/<name>_<brand>.mp4 (1080x1920, H.264 +
AAC, ready for Instagram Reels, TikTok and YouTube Shorts) and keeps the
transcript (.json) and captions (.ass) next to it for review.

Requires FFmpeg on PATH and the `faster-whisper` package (see reels/README.md).
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import captions_ass  # noqa: E402

ROOT = Path(__file__).resolve().parent
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv"}


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return float(out.strip())


def detect_speech(path, cfg, total):
    """Return [(start, end)] spans to keep, from FFmpeg silencedetect."""
    s = cfg["silence"]
    res = run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-vn", "-af",
               f"silencedetect=noise={s['threshold_db']}dB:d={s['min_duration_s']}",
               "-f", "null", "-"], capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", res.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", res.stderr)]
    ends += [total] * (len(starts) - len(ends))

    keep, cursor = [], 0.0
    for a, b in zip(starts, ends):
        if a > cursor:
            keep.append([cursor, a])
        cursor = b
    if cursor < total:
        keep.append([cursor, total])

    pad, min_len = s["padding_s"], s.get("min_segment_s", 0.25)
    padded = []
    for a, b in keep:
        a, b = max(0.0, a - pad), min(total, b + pad)
        if padded and a <= padded[-1][1]:
            padded[-1][1] = b
        else:
            padded.append([a, b])
    return [(a, b) for a, b in padded if b - a >= min_len]


def cut_and_zoom(src, spans, cfg, dst):
    """Concatenate kept spans, alternate punch-in zoom per cut, normalize audio."""
    W, H, fps = cfg["canvas"]["width"], cfg["canvas"]["height"], cfg["canvas"]["fps"]
    z = cfg.get("zoom", {})
    punch, focus_y = z.get("punch_in", 1.0), z.get("focus_y", 0.35)
    fade = cfg["silence"]["fade_s"]

    parts, labels = [], []
    for i, (a, b) in enumerate(spans):
        d = b - a
        zoom = punch if (z.get("alternate_cuts") and i % 2 == 1) else 1.0
        v = (f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS,"
             f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}")
        if zoom != 1.0:
            cw, ch = int(W / zoom) // 2 * 2, int(H / zoom) // 2 * 2
            v += f",crop={cw}:{ch}:(iw-{cw})/2:(ih-{ch})*{focus_y},scale={W}:{H}:flags=lanczos"
        v += f",setsar=1[v{i}]"
        au = (f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,"
              f"afade=t=in:d={fade},afade=t=out:st={max(d - fade, 0):.3f}:d={fade}[a{i}]")
        parts += [v, au]
        labels.append(f"[v{i}][a{i}]")
    graph = ";".join(parts) + ";" + "".join(labels) + \
        f"concat=n={len(spans)}:v=1:a=1[vc][ac];[vc]fps={fps},format=yuv420p[vo];" \
        "[ac]aresample=48000[ao]"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(src),
         "-filter_complex", graph, "-map", "[vo]", "-map", "[ao]",
         "-c:v", "libx264", "-preset", "fast", "-crf", "14",
         "-c:a", "pcm_s16le", str(dst)])


def transcribe(model, path, cfg):
    import numpy as np
    pcm = run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-ac", "1",
               "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
    audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
    w = cfg["whisper"]
    segs, _ = model.transcribe(audio, language=w.get("language", "es"), word_timestamps=True,
                               vad_filter=True, beam_size=5, initial_prompt=w.get("prompt"))
    return [{"start": s.start, "end": s.end, "text": s.text.strip(),
             "words": [{"start": x.start, "end": x.end, "word": x.word} for x in s.words]}
            for s in segs]


def loudnorm_filter(src, cfg):
    """Two-pass EBU R128 loudness normalization (accurate on short clips)."""
    a = cfg["audio"]
    base = f"loudnorm=I={a['loudness_lufs']}:TP={a['true_peak_db']}:LRA=11"
    res = run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(src), "-vn", "-af",
               base + ":print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    m = json.loads(res.stderr[res.stderr.rindex("{"):res.stderr.rindex("}") + 1])
    return (f"{base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
            f"offset={m['target_offset']}:linear=true,aresample=48000")


def export(src, ass, cfg, dst):
    e = cfg["export"]
    vf = f"subtitles={ass}" if ass else "null"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(src),
           "-vf", vf, "-af", loudnorm_filter(src, cfg),
           "-c:v", e["video_codec"], "-preset", "medium", "-crf", str(e["crf"]),
           "-profile:v", e["profile"], "-pix_fmt", e["pix_fmt"],
           "-c:a", e["audio_codec"], "-b:a", e["audio_bitrate"]]
    if e.get("faststart"):
        cmd += ["-movflags", "+faststart"]
    run(cmd + [str(dst)])


def collect(inputs):
    files = []
    for p in map(Path, inputs):
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in VIDEO_EXT)
        elif p.is_file():
            files.append(p)
        else:
            sys.exit(f"No existe: {p}")
    return files


def main():
    ap = argparse.ArgumentParser(description="Editor de Reels por lotes")
    ap.add_argument("inputs", nargs="+", help="videos o carpetas")
    ap.add_argument("--brand", required=True, help="nombre del archivo en reels/brands/")
    ap.add_argument("--out", default="salida", help="carpeta de salida")
    ap.add_argument("--no-captions", action="store_true", help="omitir subtítulos")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "brands" / f"{args.brand}.json").read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    files = collect(args.inputs)

    model = None
    if not args.no_captions:
        from faster_whisper import WhisperModel
        model = WhisperModel(cfg["whisper"]["model"], device="cpu", compute_type="int8")

    for f in files:
        t0 = time.time()
        stem = f"{f.stem}_{args.brand}"
        total = duration(f)
        spans = detect_speech(f, cfg, total)
        if not spans:
            print(f"✗ {f.name}: no se detectó voz, se omite")
            continue
        kept = sum(b - a for a, b in spans)
        with tempfile.TemporaryDirectory() as tmp:
            cut = Path(tmp) / "cut.mkv"
            cut_and_zoom(f, spans, cfg, cut)
            ass = None
            if model:
                words = transcribe(model, cut, cfg)
                (out / f"{stem}.json").write_text(
                    json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
                ass = out / f"{stem}.ass"
                captions_ass.build(words, cfg, ass)
            export(cut, ass, cfg, out / f"{stem}.mp4")
        print(f"✓ {f.name}: {total:.1f}s → {kept:.1f}s, {len(spans)} tramos, "
              f"{time.time() - t0:.0f}s de proceso → {out / (stem + '.mp4')}")


if __name__ == "__main__":
    main()
