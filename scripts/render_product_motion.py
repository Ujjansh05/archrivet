"""Render two restrained README motion demos from checked ArchRivet examples.

Requires Pillow for authoring, not for the distributed MCP runtime. The queue
walkthrough captures current rules-only CLI results. The cache walkthrough
illustrates the recorded run in docs/demo-comparison.md. Neither is a screen
recording, model benchmark, or production verification.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"
W, H = 1200, 675
FPS = 10
INK = "#0B151B"
PANEL = "#14232A"
PANEL_2 = "#1B3038"
LINE = "#35515A"
WHITE = "#F5F6F1"
MUTED = "#AFC2C4"
MINT = "#67E1BD"
AMBER = "#F3BB72"
CORAL = "#F38F82"
BLUE = "#8EAFFF"


@lru_cache(maxsize=None)
def face(size: int, weight: str = "regular"):
    windows = {
        "regular": "C:/Windows/Fonts/segoeui.ttf",
        "semibold": "C:/Windows/Fonts/seguisb.ttf",
        "bold": "C:/Windows/Fonts/segoeuib.ttf",
        "mono": "C:/Windows/Fonts/CascadiaCode.ttf",
    }
    linux = {
        "regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "semibold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    }
    for name in (windows[weight], linux[weight]):
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default(size=size)


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def ramp(t: float, start: float, duration: float = 0.4) -> float:
    return ease((t - start) / duration)


def rgba(hex_color: str, alpha: float = 1.0):
    rgb = tuple(bytes.fromhex(hex_color.lstrip("#")))
    return (*rgb, round(255 * max(0.0, min(1.0, alpha))))


def mix(base: str, accent: str, part: float) -> str:
    a, b = bytes.fromhex(base.lstrip("#")), bytes.fromhex(accent.lstrip("#"))
    return "#" + "".join(f"{round(x * (1 - part) + y * part):02x}" for x, y in zip(a, b))


def txt(draw, xy, value, size=20, color=WHITE, weight="regular", opacity=1.0):
    draw.text(xy, value, font=face(size, weight), fill=rgba(color, opacity))


def rr(draw, box, radius=14, fill=PANEL, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def layer(base: Image.Image, painter, opacity: float = 1.0):
    if opacity <= 0:
        return
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    painter(ImageDraw.Draw(overlay))
    if opacity < 1:
        overlay.putalpha(overlay.getchannel("A").point(lambda v: round(v * opacity)))
    base.alpha_composite(overlay)


def shell(title: str, section: str, progress: float) -> Image.Image:
    im = Image.new("RGBA", (W, H), rgba(INK))
    d = ImageDraw.Draw(im)
    # Editorial header: quiet brand mark, a single clear headline, no fake UI chrome.
    logo = Image.open(OUT / "archrivet-icon-128.png").convert("RGBA")
    logo.thumbnail((40, 40))
    im.alpha_composite(logo, (42, 29))
    txt(d, (94, 32), "ArchRivet", 23, WHITE, "semibold")
    txt(d, (960, 37), "SYSTEM DESIGN  /  MCP", 14, MUTED, "semibold")
    d.line((42, 88, 1158, 88), fill=LINE, width=1)
    txt(d, (42, 111), section, 16, MINT, "mono")
    txt(d, (42, 142), title, 38, WHITE, "bold")
    d.line((42, 632, 1158, 632), fill=LINE, width=1)
    d.rounded_rectangle((42, 631, 42 + int(1116 * progress), 634), radius=2, fill=MINT)
    txt(d, (42, 644), "ILLUSTRATED FROM RECORDED RULES-ONLY RESULTS", 14, MUTED, "semibold")
    txt(d, (946, 644), "CAPACITY  UNKNOWN", 14, AMBER, "semibold")
    return im


def node(draw, x, y, name, detail, emphasis=False, opacity=1.0):
    fill = rgba(PANEL_2 if emphasis else PANEL, opacity)
    border = rgba(MINT if emphasis else LINE, opacity)
    rr(draw, (x, y, x + 176, y + 104), 14, fill, border, 2 if emphasis else 1)
    draw.ellipse((x + 15, y + 17, x + 25, y + 27), fill=rgba(MINT, opacity))
    txt(draw, (x + 16, y + 39), name, 23, WHITE, "semibold", opacity)
    txt(draw, (x + 16, y + 73), detail, 16, MUTED, "regular", opacity)


def flow(draw, y=291, emphasis=None, progress=1.0, dot_phase=0.0, opacity=1.0):
    names = ["Client", "API", "Queue", "Worker", "Store"]
    details = ["request", "accept", "buffer", "process", "commit"]
    positions = [57, 281, 505, 729, 953]
    for i in range(4):
        start = positions[i] + 176
        end = positions[i + 1]
        visibility = ramp(progress, i / 5, 0.22)
        draw.line((start + 8, y + 52, end - 10, y + 52), fill=rgba(MINT, opacity * visibility), width=3)
        draw.polygon([(end - 10, y + 47), (end - 2, y + 52), (end - 10, y + 57)],
                     fill=rgba(MINT, opacity * visibility))
    for i, x in enumerate(positions):
        visibility = ramp(progress, i / 5, 0.28)
        node(draw, x, y, names[i], details[i], emphasis == i, opacity * visibility)
    # A single moving packet conveys the workflow without a distracting particle field.
    segment = min(3, int((dot_phase % 1.0) * 4))
    fraction = ((dot_phase % 1.0) * 4) - segment
    px = positions[segment] + 185 + fraction * 39
    draw.ellipse((px - 5, y + 47, px + 5, y + 57), fill=rgba(WHITE, opacity))


def tag(draw, x, y, value, color, width):
    rr(draw, (x, y, x + width, y + 36), 9, mix(PANEL_2, color, 0.15), color, 1)
    txt(draw, (x + 13, y + 8), value, 16, color, "semibold")


def finding(draw, y, index, title, description, verdict, color, visible=1.0):
    x = 640 + int((1 - visible) * 80)
    rr(draw, (x, y, 1125, y + 82), 11, rgba(PANEL_2, visible), rgba(LINE, visible), 1)
    txt(draw, (x + 18, y + 15), f"0{index}  {title}", 20, WHITE, "semibold", visible)
    txt(draw, (x + 18, y + 46), description, 17, MUTED, "regular", visible)
    vw = 142 if verdict == "SUPPORTED" else 160
    rr(draw, (1125 - vw - 12, y + 13, 1113, y + 43), 8, rgba(color, 0.12 * visible),
       rgba(color, visible), 1)
    txt(draw, (1125 - vw - 2, y + 18), verdict, 14, color, "semibold", visible)


def workflow_stage(stage: int, t: float) -> Image.Image:
    titles = [
        "Start with the architecture.",
        "See what the design contradicts.",
        "Change the design facts.",
        "Re-check. Keep limits visible.",
    ]
    im = shell(titles[stage], f"0{stage + 1} / 04  QUEUE-BACKED WORKFLOW", (stage + min(t / 2.7, 1)) / 4)
    d = ImageDraw.Draw(im)
    rr(d, (42, 220, 1158, 608), 20, PANEL, LINE, 1)
    if stage == 0:
        txt(d, (67, 244), "THE PROMISE", 16, MINT, "mono")
        txt(d, (67, 275), "Safe retries. Durable acceptance. Bounded work.", 25, WHITE, "semibold")
        flow(d, y=350, progress=1.0, dot_phase=t * 0.12)
        txt(d, (67, 495), "The assistant proposes the flow. ArchRivet checks the stated guarantees.", 22, MUTED)
        tag(d, 67, 543, "3 REQUIREMENTS", BLUE, 180)
        tag(d, 260, 543, "1 REVIEW", MINT, 144)
    elif stage == 1:
        txt(d, (67, 244), "DESIGN FACTS", 16, MINT, "mono")
        for j, (name, detail, color) in enumerate([
            ("Retry", "No atomic dedup", CORAL),
            ("Accept", "Before durable commit", CORAL),
            ("Queue", "No fixed bound", CORAL),
        ]):
            y = 293 + j * 93
            rr(d, (67, y, 596, y + 75), 11, PANEL_2, LINE)
            txt(d, (86, y + 12), name, 20, WHITE, "semibold")
            txt(d, (86, y + 40), detail, 17, color)
        txt(d, (640, 244), "ARCHRIVET REVIEW", 16, MINT, "mono")
        items = [
            ("Retry safety", "Duplicate effect can happen."),
            ("Ack durability", "Success precedes commit."),
            ("Queue overload", "Queue growth is unbounded."),
        ]
        for j, (title, detail) in enumerate(items):
            layer(im, lambda draw, j=j, title=title, detail=detail: finding(
                draw, 287 + j * 97, j + 1, title, detail, "CONTRADICTED", CORAL),
                ramp(t, 0.1 + j * 0.28, 0.4))
    elif stage == 2:
        txt(d, (67, 244), "THE REVISION", 16, MINT, "mono")
        flow(d, y=292, progress=1.0, dot_phase=t * 0.12, opacity=0.85)
        fixes = [
            ("01", "Atomic dedup", "One effect per ID"),
            ("02", "Commit, then ack", "Accepted work survives"),
            ("03", "Reject at the cap", "No unbounded growth"),
        ]
        for j, (num, title, detail) in enumerate(fixes):
            x = 67 + j * 363
            alpha = ramp(t, 0.12 + j * 0.34, 0.45)
            def paint(draw, x=x, num=num, title=title, detail=detail):
                rr(draw, (x, 446, x + 339, 558), 12, PANEL_2, MINT, 1)
                txt(draw, (x + 18, 462), num, 16, MINT, "mono")
                txt(draw, (x + 18, 486), title, 22, WHITE, "semibold")
                txt(draw, (x + 18, 521), detail, 17, MUTED)
            layer(im, paint, alpha)
        txt(d, (67, 578), "Proposed facts are assumptions until implemented and tested.", 17, AMBER)
    else:
        txt(d, (67, 244), "BEFORE  →  AFTER", 16, MINT, "mono")
        for j, name in enumerate(["Retry safety", "Ack durability", "Queue overload"]):
            y = 289 + j * 88
            rr(d, (67, y, 1125, y + 72), 11, PANEL_2, LINE)
            txt(d, (86, y + 20), name, 21, WHITE, "semibold")
            tag(d, 555, y + 18, "CONTRADICTED", CORAL, 176)
            txt(d, (760, y + 22), "→", 22, MUTED, "semibold")
            if ramp(t, j * 0.25, 0.5) > 0:
                def paint(draw, y=y):
                    tag(draw, 810, y + 18, "SUPPORTED", MINT, 157)
                layer(im, paint, ramp(t, j * 0.25, 0.5))
        rr(d, (67, 566, 1125, 594), 7, mix(PANEL, AMBER, 0.12))
        txt(d, (79, 570), "500 peak messages/s is demand. Supported capacity still needs a benchmark.",
            17, AMBER, "semibold")
    return im


def cache_stage(stage: int, t: float) -> Image.Image:
    titles = [
        "A price cache has a five-second limit.",
        "One failure-path detail is missing.",
        "One answer changes the finding.",
    ]
    im = shell(titles[stage], f"0{stage + 1} / 03  PRICE-CACHE REVIEW", (stage + min(t / 2.5, 1)) / 3)
    d = ImageDraw.Draw(im)
    rr(d, (42, 220, 1158, 608), 20, PANEL, LINE, 1)
    txt(d, (68, 244), "REQUIREMENT", 16, MINT, "mono")
    txt(d, (68, 278), "Prices must be < 5s old", 29, WHITE, "bold")
    # The age ruler makes the disagreement understandable without reading JSON.
    x0, x1, yy = 79, 578, 385
    x5 = x0 + round((x1 - x0) * 5 / 60)
    d.line((x0, yy, x1, yy), fill=LINE, width=7)
    d.line((x0, yy, x5, yy), fill=MINT, width=7)
    for x in (x0, x5, x1):
        d.ellipse((x - 5, yy - 5, x + 5, yy + 5), fill=WHITE)
    txt(d, (x0 - 4, yy + 20), "0s", 16, MUTED, "semibold")
    txt(d, (x5 - 27, yy - 38), "5s LIMIT", 16, MINT, "semibold")
    txt(d, (x1 - 17, yy + 20), "60s", 16, MUTED, "semibold")
    rr(d, (624, 253, 1124, 559), 16, PANEL_2, LINE)
    txt(d, (649, 276), "ARCHRIVET REVIEW", 16, MINT, "mono")
    if stage == 0:
        txt(d, (68, 486), "Normal operation: 3s old", 21, WHITE, "semibold")
        txt(d, (68, 523), "Database outage: unspecified", 19, AMBER)
        txt(d, (649, 328), "Cache freshness", 25, WHITE, "semibold")
        tag(d, 649, 379, "INSUFFICIENT INFO", AMBER, 204)
        txt(d, (649, 453), "An outage changes the age bound.", 19, MUTED)
        txt(d, (649, 485), "The design does not say by how much.", 19, MUTED)
    elif stage == 1:
        txt(d, (68, 486), "Normal operation: 3s old", 21, WHITE, "semibold")
        txt(d, (68, 523), "Outage behavior needs an answer.", 19, AMBER)
        txt(d, (649, 328), "Missing detail", 25, WHITE, "semibold")
        txt(d, (649, 384), "How old may a price become", 22, WHITE)
        txt(d, (649, 419), "while the database is down?", 22, WHITE)
        tag(d, 649, 484, "ASK THE OWNER", AMBER, 165)
    else:
        d.line((x5, yy, x1, yy), fill=CORAL, width=7)
        txt(d, (68, 486), "Answer: serve prices up to 60s old", 21, WHITE, "semibold")
        txt(d, (68, 523), "60 seconds exceeds the five-second limit.", 19, CORAL)
        txt(d, (649, 328), "Cache freshness", 25, WHITE, "semibold")
        tag(d, 649, 379, "CONTRADICTED", CORAL, 177)
        txt(d, (649, 453), "One clarified fact changed the verdict.", 19, MUTED)
        txt(d, (649, 485), "Capacity remains unknown.", 19, AMBER)
    return im


def capture_queue_results():
    records = []
    for name, expected in (("flawed", "contradicted"), ("complete", "supported")):
        path = ROOT / "examples" / f"{name}.json"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        env["ARCH_REVIEW_HOME"] = str(ROOT / ".runtime")
        env["PYTHONUTF8"] = "1"
        result = subprocess.run([sys.executable, "-m", "arch_review", "review", str(path), "--rules-only"],
                                cwd=ROOT, env=env, check=True, capture_output=True, text=True,
                                encoding="utf-8", timeout=60)
        review = json.loads(result.stdout)
        expected_ids = {"retry_safety", "ack_durability", "queue_overload"}
        if (review["review_mode"] != "rules_only" or
                {c["check_id"] for c in review["checks"]} != expected_ids or
                any(c["verdict"] != expected for c in review["checks"])):
            raise ValueError(f"{name} verdicts changed; revise the storyboard before rendering")
        if review["capacity"]["evidence_status"] != "unknown":
            raise ValueError("Capacity evidence changed; revise the storyboard")
        if name == "complete" and review["workload_estimates"]["estimates"]["peak_messages"]["value"] != 500:
            raise ValueError("Peak workload changed; revise the storyboard")
        records.append({"input": f"examples/{name}.json", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "checks": {c["check_id"]: c["verdict"] for c in review["checks"]},
                        "capacity": review["capacity"]["evidence_status"]})
    return records


def check_cache_recording():
    path = ROOT / "docs" / "demo-comparison.md"
    content = path.read_text(encoding="utf-8")
    for fact in ("stale_on_error_bound_ms", "insufficient_information", "60,000", "contradicted"):
        if fact not in content:
            raise ValueError("The recorded cache walkthrough changed; revise its storyboard")
    return {"source": "docs/demo-comparison.md", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "change": "stale_on_error_bound_ms: unknown -> 60000",
            "verdict": "insufficient_information -> contradicted"}


def render_frames(stage_count: int, seconds: float, renderer):
    count = round(seconds * FPS)
    per_stage = seconds / stage_count
    frames = []
    for index in range(count):
        timeline = index / FPS
        stage = min(stage_count - 1, int(timeline / per_stage))
        within = timeline - stage * per_stage
        current = renderer(stage, within)
        # Short dissolves preserve the spatial map and avoid slide-deck cuts.
        if stage < stage_count - 1 and within > per_stage - 0.32:
            transition = ease((within - (per_stage - 0.32)) / 0.32)
            next_frame = renderer(stage + 1, 0.0)
            current = Image.blend(current, next_frame, transition)
        frames.append(current.convert("RGB"))
    return frames


def export(name: str, frames: list[Image.Image]):
    # One shared palette avoids the color jumps common in auto-generated GIFs.
    mosaic = Image.new("RGB", (W, H))
    thumbs = [frames[i].resize((W // 2, H // 2)) for i in
              (0, len(frames) // 4, len(frames) // 2, len(frames) - 1)]
    for thumb, xy in zip(thumbs, ((0, 0), (W // 2, 0), (0, H // 2), (W // 2, H // 2))):
        mosaic.paste(thumb, xy)
    palette = mosaic.quantize(colors=96, method=Image.Quantize.MEDIANCUT)
    indexed = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    path = OUT / f"{name}.gif"
    indexed[0].save(path, save_all=True, append_images=indexed[1:], duration=round(1000 / FPS),
                    loop=0, optimize=True, disposal=2)
    poster = OUT / f"{name}.png"
    frames[len(frames) - 2].save(poster, optimize=True)
    with Image.open(path) as actual:
        if actual.n_frames < len(frames) // 2 or actual.size != (W, H):
            raise ValueError(f"{path.name} did not preserve the animation")
    return {p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in (path, poster)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    queue = capture_queue_results()
    cache = check_cache_recording()
    queue_frames = render_frames(4, 11.2, workflow_stage)
    cache_frames = render_frames(3, 7.5, cache_stage)
    files = export("archrivet-product-walkthrough", queue_frames)
    files.update(export("archrivet-missing-detail", cache_frames))
    manifest = {"kind": "designed_motion_from_checked_results", "screen_recording": False,
                "model_inference_used": False, "timing_is_benchmark": False, "fps": FPS,
                "queue_source": queue, "cache_source": cache, "files": files}
    path = OUT / "product-motion.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"files": {k: v["bytes"] for k, v in files.items()},
                      "queue_frames": len(queue_frames), "cache_frames": len(cache_frames)}))


if __name__ == "__main__":
    main()
