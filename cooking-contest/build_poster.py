#!/usr/bin/env python3
"""生成厨艺大赛行架画面（5000mm × 2800mm）的 poster.html。

画布 1 个单位 = 1 mm。文字内容集中在下面的 TEXT 里，改完重新运行即可：

    python3 build_poster.py <fontsource 字体包目录>

字体来自 npm 上的 @fontsource/ma-shan-zheng、@fontsource/noto-serif-sc、
@fontsource/noto-sans-sc（npm pack 后解压到同一个目录）。脚本只把用到的
字形分片以 base64 内嵌进 HTML，生成的 poster.html 可以离线打开。
"""

import base64
import math
import re
import sys
from pathlib import Path

W, H = 5000, 2800
CX = W / 2

TEXT = {
    "tagline": "COOKING  COMPETITION",
    "title": "厨艺大赛",
    "seal": "争锋",
    "subtitle": "以厨会友 · 以味传情",
    "badges": ["色", "香", "味", "形"],
    "couplet_left": "巧手烹佳肴",
    "couplet_right": "匠心调百味",
    "info": ["主办单位：××××××", "活动时间：2026年××月××日", "活动地点：××××××"],
}

RED_LIGHT, RED, RED_DARK = "#D9322A", "#B71E1A", "#7C0E0E"
CREAM = "#FFF1D6"
GOLD_LINE = "#F2C766"  # 直线用纯色：渐变描边在零宽包围盒上导出 PDF 会出错

FONTS = [
    # (fontsource 包名, CSS 文件, 用到这个字体的文字)
    ("ma-shan-zheng", "index.css",
     lambda t: t["title"] + t["seal"] + "".join(t["badges"]) + t["couplet_left"] + t["couplet_right"]),
    ("noto-serif-sc", "900.css", lambda t: t["subtitle"] + t["tagline"]),
    ("noto-sans-sc", "500.css", lambda t: "".join(t["info"]) + "·"),
]


def parse_ranges(spec):
    out = []
    for part in spec.split(","):
        part = part.strip().upper().removeprefix("U+")
        lo, _, hi = part.partition("-")
        out.append((int(lo, 16), int(hi or lo, 16)))
    return out


def font_faces(font_root):
    css_out = []
    for pkg, css_name, chars_of in FONTS:
        pkg_dir = next(Path(font_root).glob(f"fontsource-{pkg}-*/package"))
        css = (pkg_dir / css_name).read_text()
        needed = {ord(c) for c in chars_of(TEXT) if not c.isspace()}
        for block in re.findall(r"@font-face\s*{[^}]*}", css):
            ranges = parse_ranges(re.search(r"unicode-range:\s*([^;]+);", block).group(1))
            if not any(lo <= c <= hi for c in needed for lo, hi in ranges):
                continue
            woff2 = re.search(r"url\(\./(files/[^)]+\.woff2)\)", block).group(1)
            data = base64.b64encode((pkg_dir / woff2).read_bytes()).decode()
            block = re.sub(r"src:[^;]+;", f"src: url(data:font/woff2;base64,{data}) format('woff2');", block)
            css_out.append(block)
    return "\n".join(css_out)


def ridge(base, peaks, wobble, seed):
    """山脊线：几座高斯山峰叠加一点正弦起伏，模拟水墨远山。"""
    pts = []
    for x in range(-40, W + 41, 20):
        y = base
        for px, h, w in peaks:
            y -= h * math.exp(-(((x - px) / w) ** 2))
        y -= wobble * (math.sin(x / 97 + seed) * 0.6 + math.sin(x / 41 + seed * 2.3) * 0.4)
        pts.append((x, y))
    return pts


def mountain_layer(pts, grad_id, gold_line=None):
    line = " ".join(f"{x:.0f},{y:.1f}" for x, y in pts)
    svg = f'<polygon points="-40,{H + 40} {line} {W + 40},{H + 40}" fill="url(#{grad_id})"/>'
    if gold_line:
        svg += (f'<polyline points="{line}" fill="none" stroke="url(#gold)" '
                f'stroke-width="{gold_line[0]}" opacity="{gold_line[1]}" stroke-linejoin="round"/>')
    return svg


def sun_rays(cx, cy, n=40, r=4200):
    paths = []
    step = 360 / n
    for i in range(n):
        a0, a1 = math.radians(i * step), math.radians(i * step + step / 2)
        paths.append(f"M{cx},{cy} L{cx + r * math.cos(a0):.0f},{cy + r * math.sin(a0):.0f} "
                     f"L{cx + r * math.cos(a1):.0f},{cy + r * math.sin(a1):.0f} Z")
    return f'<path d="{" ".join(paths)}" fill="url(#rays)"/>'


def corner(x, y, sx, sy):
    """回纹角花。"""
    d = "M0,260 V0 H260 M36,224 V36 H224 M72,170 V72 H170 V150 H110 V110"
    return (f'<path d="{d}" transform="translate({x},{y}) scale({sx},{sy})" fill="none" '
            f'stroke="url(#gold)" stroke-width="10" stroke-linecap="square"/>')


def vertical_text(chars, x, y0, size, gap):
    return "".join(
        f'<text x="{x}" y="{y0 + i * (size + gap)}" class="brush" font-size="{size}" '
        f'fill="{CREAM}" text-anchor="middle">{c}</text>'
        for i, c in enumerate(chars))


def couplet(chars, x):
    size, gap, y0 = 150, 28, 760
    end = y0 + (len(chars) - 1) * (size + gap)
    return (f'<circle cx="{x}" cy="{y0 - 190}" r="14" fill="url(#gold)"/>'
            f'<line x1="{x}" y1="{y0 - 150}" x2="{x}" y2="{y0 - 60}" stroke="{GOLD_LINE}" stroke-width="5"/>'
            + vertical_text(chars, x, y0 + 10, size, gap) +
            f'<line x1="{x}" y1="{end + 90}" x2="{x}" y2="{end + 180}" stroke="{GOLD_LINE}" stroke-width="5"/>'
            f'<circle cx="{x}" cy="{end + 220}" r="14" fill="url(#gold)"/>')


def chef_hat(cx, cy):
    """厨师帽：上面三团蓬起的帽顶，下面带褶的帽箍。"""
    return (f'<g transform="translate({cx},{cy})">'
            '<g fill="url(#hatgold)"><circle cx="-74" cy="-20" r="62"/><circle cx="0" cy="-62" r="80"/>'
            '<circle cx="74" cy="-20" r="62"/><rect x="-82" y="-24" width="164" height="70"/>'
            '<path d="M-74,52 H74 L68,128 Q0,140 -68,128 Z"/></g>'
            f'<path d="M-80,46 H80 M-34,64 V122 M0,64 V128 M34,64 V122" stroke="{RED}" stroke-width="8" '
            'stroke-linecap="round" fill="none"/></g>')


def badges():
    out = []
    for i, ch in enumerate(TEXT["badges"]):
        x = CX + (i - (len(TEXT["badges"]) - 1) / 2) * 330
        out.append(f'<circle cx="{x}" cy="1905" r="112" fill="{RED_DARK}" fill-opacity=".55" '
                   f'stroke="url(#gold)" stroke-width="7"/>'
                   f'<circle cx="{x}" cy="1905" r="92" fill="none" stroke="url(#gold)" stroke-width="2.5" opacity=".7"/>'
                   f'<text x="{x}" y="1958" class="brush" font-size="148" fill="{CREAM}" text-anchor="middle">{ch}</text>')
    return "".join(out)


def build(font_root):
    back = ridge(2120, [(380, 720, 420), (1150, 420, 330), (3850, 470, 360), (4650, 760, 430)], 26, 1.0)
    mid = ridge(2330, [(150, 640, 520), (900, 380, 300), (4150, 420, 330), (4900, 620, 480)], 20, 2.7)
    front = ridge(2520, [(-60, 520, 620), (700, 210, 300), (4380, 240, 300), (5080, 540, 600)], 12, 4.1)

    info = '<tspan fill="#F3C766">   ·   </tspan>'.join(TEXT["info"])

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<defs>
  <radialGradient id="bg" cx="50%" cy="38%" r="75%">
    <stop offset="0" stop-color="{RED_LIGHT}"/><stop offset=".55" stop-color="{RED}"/><stop offset="1" stop-color="#8A1210"/>
  </radialGradient>
  <linearGradient id="gold" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#FFF4C8"/><stop offset=".42" stop-color="#F6CF72"/>
    <stop offset=".72" stop-color="#E0A23A"/><stop offset="1" stop-color="#FBE3A0"/>
  </linearGradient>
  <linearGradient id="hatgold" x1="0" y1="-142" x2="0" y2="140" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="#FFF4C8"/><stop offset=".55" stop-color="#F6CF72"/><stop offset="1" stop-color="#E0A23A"/>
  </linearGradient>
  <radialGradient id="rays" cx="{CX}" cy="1000" r="3000" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="#FFD98A" stop-opacity=".16"/><stop offset="1" stop-color="#FFD98A" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="sun" cx="50%" cy="50%" r="50%">
    <stop offset="0" stop-color="#FFE1A0" stop-opacity=".30"/><stop offset=".7" stop-color="#FFD27A" stop-opacity=".14"/>
    <stop offset="1" stop-color="#FFD27A" stop-opacity=".05"/>
  </radialGradient>
  <linearGradient id="m1" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#95171A"/><stop offset=".35" stop-color="#A61C1A"/><stop offset="1" stop-color="#B7231D" stop-opacity=".2"/>
  </linearGradient>
  <linearGradient id="m2" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#7A0F12"/><stop offset=".4" stop-color="#8F1515"/><stop offset="1" stop-color="#A31B18"/>
  </linearGradient>
  <linearGradient id="m3" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#5E0A0D"/><stop offset=".5" stop-color="#6A0C0E"/><stop offset="1" stop-color="#4E080A"/>
  </linearGradient>
</defs>

<rect width="{W}" height="{H}" fill="url(#bg)"/>
{sun_rays(CX, 1000)}
<circle cx="{CX}" cy="1000" r="860" fill="url(#sun)"/>
<circle cx="{CX}" cy="1000" r="860" fill="none" stroke="url(#gold)" stroke-width="6" opacity=".55"/>
<circle cx="{CX}" cy="1000" r="900" fill="none" stroke="url(#gold)" stroke-width="2.5" opacity=".35" stroke-dasharray="4 26" stroke-linecap="round"/>

{mountain_layer(back, "m1")}
{mountain_layer(mid, "m2", (4, .45))}
{mountain_layer(front, "m3", (6, .8))}

<rect x="60" y="60" width="{W - 120}" height="{H - 120}" fill="none" stroke="url(#gold)" stroke-width="10"/>
<rect x="96" y="96" width="{W - 192}" height="{H - 192}" fill="none" stroke="url(#gold)" stroke-width="3" opacity=".8"/>
{corner(130, 130, 1, 1)}{corner(W - 130, 130, -1, 1)}{corner(130, H - 130, 1, -1)}{corner(W - 130, H - 130, -1, -1)}

{chef_hat(CX, 270)}
<line x1="1640" y1="488" x2="1900" y2="488" stroke="{GOLD_LINE}" stroke-width="5"/>
<line x1="3100" y1="488" x2="3360" y2="488" stroke="{GOLD_LINE}" stroke-width="5"/>
<text x="{CX}" y="514" class="serif" font-size="70" letter-spacing="26" fill="#F6D27E" text-anchor="middle">{TEXT["tagline"]}</text>

<text x="{CX + 14}" y="1322" class="brush" font-size="800" letter-spacing="24" fill="#4A0606" opacity=".55" text-anchor="middle">{TEXT["title"]}</text>
<text x="{CX}" y="1300" class="brush" font-size="800" letter-spacing="24" fill="url(#gold)" stroke="#6E0B0B" stroke-width="22" paint-order="stroke" stroke-linejoin="round" text-anchor="middle">{TEXT["title"]}</text>

<g transform="translate(4240,1190) rotate(-6)">
  <rect x="-100" y="-112" width="200" height="224" rx="20" fill="{CREAM}"/>
  <rect x="-84" y="-96" width="168" height="192" rx="10" fill="none" stroke="{RED}" stroke-width="6"/>
  {vertical_text(TEXT["seal"], 0, -8, 84, 2).replace(f'fill="{CREAM}"', f'fill="{RED}"')}
</g>

<text x="{CX}" y="1585" class="serif" font-size="172" letter-spacing="34" fill="{CREAM}" text-anchor="middle">{TEXT["subtitle"]}</text>
<line x1="1640" y1="1712" x2="2420" y2="1712" stroke="{GOLD_LINE}" stroke-width="5"/>
<line x1="2580" y1="1712" x2="3360" y2="1712" stroke="{GOLD_LINE}" stroke-width="5"/>
<rect x="2478" y="1690" width="44" height="44" transform="rotate(45 2500 1712)" fill="url(#gold)"/>

{badges()}
{couplet(TEXT["couplet_left"], 470)}
{couplet(TEXT["couplet_right"], W - 470)}

<text x="{CX}" y="2610" class="sans" font-size="88" letter-spacing="6" fill="{CREAM}" text-anchor="middle">{info}</text>
</svg>"""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>厨艺大赛行架画面 5000×2800mm</title>
<style>
{font_faces(font_root)}
html, body {{ margin: 0; background: #2a2a2a; }}
svg {{ display: block; width: 100vw; height: auto; }}
.brush {{ font-family: 'Ma Shan Zheng'; }}
.serif {{ font-family: 'Noto Serif SC'; font-weight: 900; }}
.sans {{ font-family: 'Noto Sans SC'; font-weight: 500; }}
</style>
</head>
<body>
{svg}
</body>
</html>
"""


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = Path(__file__).with_name("poster.html")
    out.write_text(build(sys.argv[1]))
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
