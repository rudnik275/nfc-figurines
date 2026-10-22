"""Картинка раскладки перфборда (docs/perfboard.png) из tools/make-perfboard.py:

    uv run --with pillow python tools/render-perfboard.py docs/perfboard.png
"""
import importlib.util, sys
from PIL import Image, ImageDraw, ImageFont
spec = importlib.util.spec_from_file_location("pb", "tools/make-perfboard.py"); pb = importlib.util.module_from_spec(spec); spec.loader.exec_module(pb)
S, M, MT = 34, 70, 120
W, H = pb.COLS * S + 2 * M, pb.ROWS * S + M + MT + 110
img = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(img)
f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 13)
fb = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 13)
c = lambda h: (M + h[0] * S, MT + h[1] * S)
d.rectangle([M - S // 2, MT - S // 2, M + (pb.COLS - 1) * S + S // 2, MT + (pb.ROWS - 1) * S + S // 2], fill="#1f6b3a")
for x in range(pb.COLS):
    for y in range(pb.ROWS):
        X, Y = c((x, y)); d.ellipse([X - 6, Y - 6, X + 6, Y + 6], fill="#da8a67"); d.ellipse([X - 2, Y - 2, X + 2, Y + 2], fill="#1f6b3a")
for x in range(pb.COLS): d.text((c((x, 0))[0] - 4, MT - S), str(x), fill="black", font=f)
for y in range(pb.ROWS): d.text((M - S - 4, c((0, y))[1] - 7), str(y), fill="black", font=f)
def col(run):
    hs = set(run)
    if any(h[1] == 0 for h in hs) and all(h[1] <= 3 for h in hs) and not any(h in ((7,3),) for h in hs): return "#d93025"
    return "#c0c0c0"
for run in pb.straight_runs():
    d.line([c(run[0]), c(run[-1])], fill="#c0c0c0", width=5)
x1, y1 = c((pb.X0, 2)); x2, y2 = c((pb.X0 + 6, 5))
d.rectangle([x1 - 12, y1 + 8, x2 + 12, y2 - 8], fill="#3c4043"); d.ellipse([x1 - 18, (y1 + y2) // 2 - 7, x1 - 4, (y1 + y2) // 2 + 7], fill="#1f6b3a")
for p, h in pb.IC.items():
    X, Y = c(h); d.ellipse([X - 8, Y - 8, X + 8, Y + 8], fill="#9aa0a6"); d.text((X - 6, Y + (10 if h[1] == 5 else -24)), str(p), fill="white", font=fb)
d.text(((x1 + x2) // 2 - 40, (y1 + y2) // 2 - 7), "74AHCT125", fill="white", font=fb)
for kind, name, value, pins in pb.parts:
    a, b = c(pins[0]), c(pins[1])
    if kind == "res":
        d.line([a, b], fill="#888", width=3); mx = (a[0] + b[0]) // 2; d.rectangle([mx - 30, a[1] - 9, mx + 30, a[1] + 9], fill="#82cffd", outline="#5b90b1"); d.text((mx - 18, a[1] - 7), value, fill="black", font=fb)
    else:
        d.line([a, b], fill="#888", width=3); mx, my = (a[0] + b[0]) // 2, (a[1] + b[1]) // 2; d.ellipse([mx - 11, my - 11, mx + 11, my + 11], fill="#f28c28", outline="#a85f1a"); d.text((mx - 9, my - 7), "104", fill="black", font=f)
levels = pb.wire_levels()
def dashed(p0, p1, color, w=3, dash=7):
    import math
    L = math.dist(p0, p1); n = max(1, int(L // dash))
    for k in range(0, n, 2):
        a = (p0[0] + (p1[0] - p0[0]) * k / n, p0[1] + (p1[1] - p0[1]) * k / n)
        b = (p0[0] + (p1[0] - p0[0]) * min(k + 1, n) / n, p0[1] + (p1[1] - p0[1]) * min(k + 1, n) / n)
        d.line([a, b], fill=color, width=w)
for h, label, color in pb.wires:
    X, Y = c(h); up = h[1] <= 4; k = levels[h]
    ey = MT - S // 2 - 18 - 26 * k if up else MT + (pb.ROWS - 1) * S + S // 2 + 18 + 26 * k
    dashed((X, Y), (X, ey), "#" + color); d.ellipse([X - 8, Y - 8, X + 8, Y + 8], outline="#" + color, width=3)
    tw = d.textlength(label, font=fb); d.text((X - tw / 2, ey - (17 if up else -2)), label, fill="#" + color, font=fb)
d.text((M - S // 2, H - 30), "Пунктир — провод к модулю: вставляется в отверстие сверху. Серые линии — голые перемычки снизу платы.", fill="black", font=f)
img.save(sys.argv[1]); print("ok", img.size)
