"""Generate /today/today.jpg — the daily share card (1080x1790).

A PIL re-creation of the site's card: header with logo and date,
a 9-row price table (8 main varieties + EPS from the board extras),
red-up / green-down changes, and the dark footer with the WeChat QR.
Layout and colors follow the published 2026-11-10 card; it is a
visual equivalent, not a pixel-identical copy. The logo and QR are
static brand assets under assets/ (extracted from the site's own
icon and the published card). Fonts: Noto Sans CJK SC (install
fonts-noto-cjk in the runner).
"""
from __future__ import annotations

import glob

from PIL import Image, ImageDraw, ImageFont

from .dataio import NAMES

RED = (217, 44, 20)
GREEN = (23, 163, 74)
GRAY = (138, 143, 152)
DARK = (26, 26, 26)
FOOTER_BG = (32, 36, 46)
ORANGE = (245, 158, 11)

_font_cache = {}


def _font(bold, size):
    key = (bold, size)
    if key not in _font_cache:
        pats = ["/usr/share/fonts/**/NotoSansCJK-%s.ttc" % ("Bold" if bold else "Regular"),
                "/usr/share/fonts/**/NotoSansSC-%s.otf" % ("Bold" if bold else "Regular")]
        path = None
        for p in pats:
            hits = glob.glob(p, recursive=True)
            if hits:
                path = hits[0]
                break
        _font_cache[key] = ImageFont.truetype(path, size, index=2) if path.endswith(".ttc") \
            else ImageFont.truetype(path, size)
    return _font_cache[key]


def _chg_color(v):
    return RED if v > 0 else (GREEN if v < 0 else GRAY)


def today_rows(series, extras, today):
    """[(name, price, day_chg%, month_chg%)] for the 8 mains + EPS."""
    rows = []
    for s in ("pp", "lldpe", "hdpe", "ldpe", "pvc", "abs", "ps", "pet"):
        ent = series[s]
        i = [d for d, _ in ent].index(today)
        price = ent[i][1]
        rows.append((NAMES[s], price,
                     (price / ent[i - 1][1] - 1) * 100,
                     (price / ent[i - 30][1] - 1) * 100))
    ent = extras["eps"]
    price = ent[-1][1]
    # the board series is not daily: "近一月" is 30 calendar days back
    import datetime as _dt
    ref = (_dt.date.fromisoformat(ent[-1][0]) - _dt.timedelta(days=30)).isoformat()
    month_ref = [p for d, p in ent if d <= ref][-1]
    rows.append(("EPS", price,
                 (price / ent[-2][1] - 1) * 100,
                 (price / month_ref - 1) * 100))
    return rows


def render_today_image(series, extras, today, assets_dir):
    rows = today_rows(series, extras, today)
    W, H = 1080, 1790
    im = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, W, 10], fill=(234, 67, 23))
    logo = Image.open(f"{assets_dir}/logo_mark.png").convert("RGB")
    logo = logo.resize((92, int(92 * logo.height / logo.width)))
    im.paste(logo, (58, 52))
    y, m, d = today.split("-")
    dr.text((185, 58), "今日塑料价格", font=_font(True, 64), fill=DARK)
    dr.text((188, 148), f"{y}年{int(m)}月{int(d)}日 · 生意社基准价 · 元/吨",
            font=_font(False, 29), fill=(102, 102, 102))
    dr.text((58, 208), "塑价", font=_font(True, 31), fill=DARK)
    w365 = dr.textlength("塑价", font=_font(True, 31))
    dr.text((58 + w365, 208), "365", font=_font(True, 31), fill=(225, 37, 26))
    dr.text((58 + w365 + dr.textlength("365", font=_font(True, 31)), 208),
            " · pla365.com 每天更新 · 免费查历史走势", font=_font(False, 31),
            fill=(51, 51, 51))
    dr.line([0, 268, W, 268], fill=(232, 232, 232), width=2)
    # table
    tx0, tx1 = 40, 1040
    hy = 288
    dr.rounded_rectangle([tx0, hy, tx1, hy + 88], 12, fill=(242, 243, 245))
    cols = [58, 355, 592, 832]
    for x, t in zip(cols, ("品种", "价格", "日涨跌", "近一月")):
        dr.text((x, hy + 24), t, font=_font(True, 33), fill=(51, 51, 51))
    ry = hy + 88
    rh = 113
    for i, (name, price, dchg, mchg) in enumerate(rows):
        if i % 2 == 1:
            dr.rectangle([tx0, ry, tx1, ry + rh], fill=(248, 248, 250))
        dr.text((cols[0], ry + 34), name, font=_font(True, 37), fill=(17, 17, 17))
        dr.text((cols[1], ry + 32), f"{price:,.0f}", font=_font(True, 40), fill=DARK)
        dr.text((cols[2], ry + 36), f"{dchg:+.2f}%", font=_font(True, 35),
                fill=_chg_color(dchg))
        dr.text((cols[3], ry + 36), f"{mchg:+.1f}%", font=_font(True, 35),
                fill=_chg_color(mchg))
        ry += rh
    dr.text((58, ry + 26), "红涨绿跌 · 数据来源：生意社 100ppi.com，仅供参考",
            font=_font(False, 26), fill=GRAY)
    fy = 1465
    dr.rectangle([0, fy - 4, W, fy], fill=(225, 37, 26))
    dr.rectangle([0, fy, W, H], fill=FOOTER_BG)
    dr.text((58, fy + 55), "微信搜「塑价365」", font=_font(True, 46),
            fill=(255, 255, 255))
    dr.text((58, fy + 128), "每天一份价格表 · 每周一行行情周报",
            font=_font(False, 29), fill=(185, 190, 201))
    dr.text((58, fy + 185), "历史走势、成本计算器：pla365.com",
            font=_font(True, 31), fill=ORANGE)
    qr = Image.open(f"{assets_dir}/qr_wechat.png").convert("RGB")
    im.paste(qr, (W - 58 - qr.width, fy + 28))
    return im
