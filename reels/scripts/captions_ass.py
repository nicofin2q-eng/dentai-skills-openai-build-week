#!/usr/bin/env python3
"""Build brand-styled ASS captions from a Whisper word-timestamp JSON.

Usage: captions_ass.py <transcript.json> <brand.json> <out.ass>

The transcript JSON is a list of segments, each with "words":
[{"start", "end", "word"}]. Words are grouped into one-line phrases, each
phrase is measured with libass (via FFmpeg's bbox filter) so the rounded
background box fits the text exactly, and an ASS file is written that FFmpeg's
`subtitles` filter can burn into the video.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_CHARS = 24       # one line at font_size 84 on a 1080px canvas
MAX_GAP_S = 0.6      # a pause longer than this starts a new phrase
HOLD_S = 0.15        # keep the last phrase on screen a bit after the word ends
STRIP_END = ".,;:"   # trailing punctuation hidden in captions (CapCut style)


def hex_to_ass(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def ts(t: float) -> str:
    t = max(t, 0.0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def group_phrases(segments):
    words = [w for seg in segments for w in seg["words"]]
    phrases, cur = [], []
    for w in words:
        text = w["word"].strip()
        if not text:
            continue
        candidate = " ".join([x["word"].strip() for x in cur] + [text])
        gap = w["start"] - cur[-1]["end"] if cur else 0
        if cur and (len(candidate) > MAX_CHARS or gap > MAX_GAP_S):
            phrases.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.?!]$", text):
            phrases.append(cur)
            cur = []
    if cur:
        phrases.append(cur)

    out = []
    for i, p in enumerate(phrases):
        text = " ".join(x["word"].strip() for x in p).rstrip(STRIP_END)
        start, end = p[0]["start"], p[-1]["end"] + HOLD_S
        if i + 1 < len(phrases):
            nxt = phrases[i + 1][0]["start"]
            end = nxt if nxt - p[-1]["end"] < MAX_GAP_S else min(end, nxt)
        out.append({"start": start, "end": end, "text": text})
    return out


def header(cap, canvas):
    c = cap
    return "\n".join([
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {canvas['width']}",
        f"PlayResY: {canvas['height']}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Caja,{c['font']},{c['font_size']},{hex_to_ass(c['box']['color'])},"
        f"{hex_to_ass(c['box']['color'])},{hex_to_ass(c['box']['color'])},&H00000000,"
        "0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        f"Style: Texto,{c['font']},{c['font_size']},{hex_to_ass(c['text_color'])},"
        f"{hex_to_ass(c['text_color'])},{hex_to_ass(c['outline_color'])},&H00000000,"
        f"0,0,0,0,100,100,0,0,1,{c['outline_px']},0,5,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ])


def measure_widths(phrases, cap, canvas):
    """Render each phrase on its own 0.1 s slot and read its width from bbox."""
    cx, cy = canvas["width"] // 2, cap["box"]["center_y_px"]
    lines = [header(cap, canvas)]
    for i, p in enumerate(phrases):
        lines.append(f"Dialogue: 0,{ts(i * 0.1)},{ts(i * 0.1 + 0.1)},Texto,,0,0,0,,"
                     f"{{\\pos({cx},{cy})\\bord0}}{p['text']}")
    with tempfile.TemporaryDirectory() as d:
        ass = Path(d) / "m.ass"
        ass.write_text("\n".join(lines) + "\n", encoding="utf-8")
        dur = len(phrases) * 0.1 + 0.05
        res = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-f", "lavfi", "-i",
             f"color=black:s={canvas['width']}x{canvas['height']}:r=10:d={dur}",
             "-vf", f"subtitles={ass},bbox", "-f", "null", "-"],
            capture_output=True, text=True, check=True)
    widths = [int(w) for w in re.findall(r" w:(\d+) ", res.stderr)]
    if len(widths) < len(phrases):
        raise RuntimeError(f"measured {len(widths)} widths for {len(phrases)} phrases")
    return widths[: len(phrases)]


def rounded_rect(x0, y0, x1, y1, r):
    return (f"m {x0 + r} {y0} l {x1 - r} {y0} b {x1} {y0} {x1} {y0} {x1} {y0 + r} "
            f"l {x1} {y1 - r} b {x1} {y1} {x1} {y1} {x1 - r} {y1} "
            f"l {x0 + r} {y1} b {x0} {y1} {x0} {y1} {x0} {y1 - r} "
            f"l {x0} {y0 + r} b {x0} {y0} {x0} {y0} {x0 + r} {y0}")


def build(segments, brand, out):
    """Write brand-styled ASS captions for Whisper segments; return the phrases."""
    cap, canvas = brand["captions"], brand["canvas"]
    box = cap["box"]
    phrases = group_phrases(segments)
    for p in phrases:
        for pattern, fixed in cap.get("replacements", {}).items():
            p["text"] = re.sub(pattern, fixed, p["text"], flags=re.IGNORECASE)
    if not phrases:
        Path(out).write_text(header(cap, canvas) + "\n", encoding="utf-8")
        return phrases
    widths = measure_widths(phrases, cap, canvas)

    cx, cy = canvas["width"] // 2, box["center_y_px"]
    half_h = box["height_px"] // 2
    lines = [header(cap, canvas)]
    for p, w in zip(phrases, widths):
        half_w = w // 2 + box["padding_x_px"]
        shape = rounded_rect(cx - half_w, cy - half_h, cx + half_w, cy + half_h,
                             box["corner_radius_px"])
        lines.append(f"Dialogue: 0,{ts(p['start'])},{ts(p['end'])},Caja,,0,0,0,,"
                     f"{{\\pos(0,0)\\p1}}{shape}{{\\p0}}")
        lines.append(f"Dialogue: 1,{ts(p['start'])},{ts(p['end'])},Texto,,0,0,0,,"
                     f"{{\\pos({cx},{cy + 3})}}{p['text']}")
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return phrases


def main():
    transcript, brand_path, out = sys.argv[1:4]
    brand = json.loads(Path(brand_path).read_text(encoding="utf-8"))
    segments = json.loads(Path(transcript).read_text(encoding="utf-8"))
    for p in build(segments, brand, out):
        print(f"[{p['start']:.2f}-{p['end']:.2f}] {p['text']}")


if __name__ == "__main__":
    main()
