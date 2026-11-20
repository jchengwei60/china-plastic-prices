"""Generate the daily price short video （每日价格短视频）.

Reads only committed pipeline state (data/history.csv, data/latest.json,
generator/state/extras.json) and produces video/daily-<date>.mp4 plus a
narration transcript video/daily-<date>.txt:

- 1080x1920 vertical, the daily share card as the visual
- 4 narration segments, all numbers computed from the day's data and
  scoped to the 8 main varieties (the +/-2% alert line and every
  narration claim cover mains only; extras on the card are never
  described as alert/no-alert, which keeps the wording honest)
- voice: Microsoft Edge neural TTS (edge-tts), zh-CN-YunyangNeural
- subtitles are burned in per segment, timed to the voice

Guard: without --force, the video is generated only when the day's
data is finalised (a majority of latest.json items carry today's
16:00 update stamp, which only the evening run produces). The morning
run's carried-over data therefore produces no video.

Run from the repo root:
    python generator/make_daily_video.py [YYYY-MM-DD] [--force]
Env PLA365_TTS=stub replaces the voice with timed silence (local
assembly tests where the speech service is unreachable).
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.compute import percentile, temperature_label  # noqa: E402
from pipeline.dataio import NAMES, SLUGS, load_history  # noqa: E402
from pipeline.render_today_image import render_today_image  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VOICE = "zh-CN-YunyangNeural"
W, H = 1080, 1920
BG = (13, 27, 42)          # deep slate, matches the card header tone
FG = (255, 255, 255)
SUB_BG = (0, 0, 0)


def up_to(series, d):
    return [(dt, p) for dt, p in series if dt <= d]


def day_move(series, d):
    rows = up_to(series, d)
    if len(rows) < 2 or rows[-1][0] != d:
        return None
    prev, cur = rows[-2][1], rows[-1][1]
    return cur, prev, (cur - prev) / prev * 100.0, cur - prev


def chg_word(pct):
    if abs(pct) < 0.05:
        return "基本持平"
    return f"{'涨' if pct > 0 else '跌'}了{abs(pct):.2f}%"


def build_segments(series, extras, target):
    """Return (segments, is_alert_day). segments = [(voice_text, subtitle)]"""
    y, m, dd = (int(x) for x in target.split("-"))
    md = f"{m}月{dd}日"
    moves = {}
    for slug in SLUGS:
        mv = day_move(series[slug], target)
        if mv:
            moves[slug] = mv
    if len(moves) < len(SLUGS):
        raise SystemExit(f"{target}: only {len(moves)}/{len(SLUGS)} mains "
                         "have data - aborting")
    ranked = sorted(moves.items(), key=lambda kv: -abs(kv[1][2]))
    top_slug, top = ranked[0]
    top_name = NAMES[top_slug]
    ups = sum(1 for _s, v in moves.items() if v[2] > 0.05)
    downs = sum(1 for _s, v in moves.items() if v[2] < -0.05)
    is_alert = abs(top[2]) >= 2.0
    # extras board moves (for honest wording only)
    extra_big = False
    for _slug, st in extras.items():
        rows = [(dt, p) for dt, p in st["series"] if dt <= target]
        if len(rows) >= 2 and rows[-1][0] == target:
            if abs((rows[-1][1] - rows[-2][1]) / rows[-2][1] * 100) >= 2.0:
                extra_big = True

    if is_alert:
        s1 = (f"{md}塑料价格异动：{top_name}单日"
              f"{'涨' if top[2] > 0 else '跌'}了{abs(top[2]):.2f}%。")
        sub1 = f"{md} 异动日\n{top_name} {'+' if top[2] > 0 else ''}{top[2]:.2f}%"
    else:
        if downs > ups and downs >= 4:
            mood = "整体小幅回落"
        elif ups > downs and ups >= 4:
            mood = "整体小幅上涨"
        elif ups == 0 and downs == 0:
            mood = "整体平稳"
        else:
            mood = "涨跌互现"
        scope = "主品种" if extra_big else ""
        s1 = f"{md}塑料价格：{mood}，{scope}没有异动。"
        sub1 = f"{md} 塑料价格\n{mood}，没有异动"

    pp = moves["pp"]
    s2 = f"PP拉丝{pp[0]:.0f}元一吨，{chg_word(pp[2])}。"
    sub2 = f"PP拉丝 {pp[0]:.0f}元/吨 {pp[2]:+.2f}%"
    if top_slug != "pp":
        s2 += (f"{top_name}{top[0]:.0f}元一吨，"
               f"{'涨' if top[2] > 0 else '跌'}了{abs(top[2]):.2f}%，"
               f"是今天动静最大的。")
        sub2 += (f"\n{top_name} {top[0]:.0f}元/吨 {top[2]:+.2f}%")

    pctile = percentile(up_to(series[top_slug], target))
    temp = temperature_label(pctile)
    maxup = max(v[2] for v in moves.values())
    maxdown = min(v[2] for v in moves.values())
    s3 = (f"八个主品种，{ups}涨{downs}跌，最大涨幅{maxup:.2f}%，"
          f"最大跌幅{abs(maxdown):.2f}%。{top_name}现在这个价，"
          f"在近一年里算{temp}。")
    sub3 = (f"主品种 {ups}涨{downs}跌\n{top_name} 采购温度：{temp}"
            f"（{pctile:.0f}%分位）")

    s4 = "每天的价格和判断，关注塑价365。"
    sub4 = "每天的价格和判断\n关注塑价365"

    return [(s1, sub1), (s2, sub2), (s3, sub3), (s4, sub4)], is_alert


async def _synth_edge(text, out_path):
    import edge_tts
    await edge_tts.Communicate(text, VOICE).save(str(out_path))


def synth(text, out_path):
    if os.environ.get("PLA365_TTS") == "stub":
        dur = max(1.8, len(text) * 0.21)
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             "anullsrc=r=24000:cl=mono", "-t", f"{dur:.2f}",
             "-c:a", "libmp3lame", str(out_path)], check=True)
    else:
        asyncio.run(_synth_edge(text, out_path))
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(out_path)], capture_output=True, text=True)
    return float(r.stdout.strip())


def render_frames(card_img, segments, tmpdir):
    from PIL import Image, ImageDraw, ImageFont
    frames = []
    card = card_img.copy()
    # card is 1080x1790; scale to width 1000 -> height ~1657
    card.thumbnail((1000, 1660))
    x = (W - card.width) // 2
    y = 120
    try:
        f_title = ImageFont.truetype(
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 44)
        f_sub = ImageFont.truetype(
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 58)
    except OSError:
        f_title = ImageFont.load_default()
        f_sub = ImageFont.load_default()
    for i, (_voice, sub) in enumerate(segments):
        img = Image.new("RGB", (W, H), BG)
        img.paste(card, (x, y))
        dr = ImageDraw.Draw(img)
        dr.text((W // 2, 62), "塑价365 · 每日价格播报", font=f_title,
                fill=FG, anchor="mm")
        lines = sub.split("\n")
        total_h = len(lines) * 76
        sy = H - 40 - total_h
        dr.rectangle([0, sy - 26, W, H], fill=SUB_BG)
        for j, line in enumerate(lines):
            dr.text((W // 2, sy + j * 76 + 34), line, font=f_sub,
                    fill=FG, anchor="mm")
        p = Path(tmpdir) / f"frame{i}.png"
        img.save(p)
        frames.append(p)
    return frames


def assemble(frames, audios, durations, out_path):
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for f, d in zip(frames, durations):
        cmd += ["-loop", "1", "-t", f"{d + 0.3:.2f}", "-i", str(f)]
    for a in audios:
        cmd += ["-i", str(a)]
    n = len(frames)
    parts = []
    for i in range(n):
        parts.append(f"[{i}:v]fps=30,format=yuv420p[v{i}]")
        parts.append(f"[{n + i}:a]apad,atrim=0:{durations[i] + 0.3:.2f},"
                     f"aresample=44100[a{i}]")
    concat_in = "".join(f"[v{i}][a{i}]" for i in range(n))
    filt = ";".join(parts) + f";{concat_in}concat=n={n}:v=1:a=1[v][a]"
    cmd += ["-filter_complex", filt, "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", str(out_path)]
    subprocess.run(cmd, check=True)


def finalised(target):
    latest = json.loads(
        (ROOT / "data" / "latest.json").read_text(encoding="utf-8"))
    if latest.get("date") != target:
        return False
    md = target[5:]  # MM-DD
    hits = sum(1 for it in latest["items"]
               if it.get("updated", "").startswith(md))
    return hits >= 5


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    series = load_history(
        (ROOT / "data" / "history.csv").read_text(encoding="utf-8"))
    extras = json.loads(
        (ROOT / "generator" / "state" / "extras.json").read_text(
            encoding="utf-8"))
    target = args[0] if args else series[SLUGS[0]][-1][0]
    if not force and not finalised(target):
        print(f"{target}: data not finalised yet (no 16:00 stamps) - skip")
        return
    segments, is_alert = build_segments(series, extras, target)
    extras_series = {slug: [tuple(x) for x in st["series"]]
                     for slug, st in extras.items()}
    card = render_today_image(series, extras_series, target,
                              str(ROOT / "generator" / "assets"))
    with tempfile.TemporaryDirectory() as td:
        frames = render_frames(card, segments, td)
        audios, durations = [], []
        for i, (text, _sub) in enumerate(segments):
            ap = Path(td) / f"seg{i}.mp3"
            durations.append(synth(text, ap))
            audios.append(ap)
        outdir = ROOT / "video"
        outdir.mkdir(exist_ok=True)
        out = outdir / f"daily-{target}.mp4"
        assemble(frames, audios, durations, out)
    script = "\n".join(
        f"{i + 1}. {t}" for i, (t, _s) in enumerate(segments))
    (ROOT / "video" / f"daily-{target}.txt").write_text(
        f"每日价格短视频解说词 · {target}{'（异动日）' if is_alert else ''}\n"
        f"声音：{VOICE}\n\n{script}\n", encoding="utf-8")
    total = sum(durations) + 0.3 * len(durations)
    print(f"wrote video/daily-{target}.mp4 "
          f"({len(segments)} segments, ~{total:.1f}s, alert={is_alert})")


if __name__ == "__main__":
    main()
