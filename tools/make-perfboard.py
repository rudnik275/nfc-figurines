"""Раскладка платы подставки на перфборде 3×7 см (24×10 отверстий) для DIY Layout Creator.

    python3 tools/make-perfboard.py   →  docs/perfboard.diy  (+ проверка цепей)

Отверстие (x, y): x — столбец 0..23 слева направо, y — ряд 0..9 сверху вниз,
шаг 0.1″. В DIY Layout Creator и на картинке это столбцы 1–24 и ряды A–J. Ряд 0 — шина +5V, ряд 9 — шина GND (голый провод снизу платы).
Микросхема лежит горизонтально: выводы 1–7 нижним рядом (y=5), 14–8 верхним (y=2),
вывод 1 слева снизу, выемка смотрит влево.

Перед записью скрипт сам проверяет цепи: каждая цепь связна, разные цепи не замкнуты.
"""
from collections import defaultdict
from pathlib import Path

COLS, ROWS, PITCH = 24, 10, 0.1
OUT = Path(__file__).resolve().parent.parent / "docs" / "perfboard.diy"


def at(x, y):
    # Плата сдвинута от края листа: над ней — подписи проводов, уходящих вверх.
    return round(0.5 + x * PITCH, 3), round(1.0 + y * PITCH, 3)


# ── Микросхема ─────────────────────────────────────────────────────────────
X0 = 8                                   # столбец выводов 1 и 14
IC = {p: (X0 + p - 1, 5) for p in range(1, 8)}        # 1..7 снизу
IC.update({p: (X0 + 14 - p, 2) for p in range(8, 15)})  # 14..8 сверху

parts = []      # (тип, имя, значение, [выводы-отверстия])
bridges = []    # голые перемычки снизу: ломаная по отверстиям
wires = []      # провода с платы: (отверстие, куда, цвет)
nets = defaultdict(set)   # ожидаемые цепи: имя → отверстия


def bridge(*holes):
    bridges.append(list(holes))


def path(x0, y0, x1, y1):
    """Отверстия по прямой (только по горизонтали или вертикали)."""
    if x0 == x1:
        step = 1 if y1 >= y0 else -1
        return [(x0, y) for y in range(y0, y1 + step, step)]
    step = 1 if x1 >= x0 else -1
    return [(x, y0) for x in range(x0, x1 + step, step)]


# Шины
V5, GND = path(1, 0, 23, 0), path(1, 9, 23, 9)
bridge(*V5)
bridge(*GND)

# Питание микросхемы и неиспользуемые каналы
bridge(*path(*IC[14], IC[14][0], 0))                 # 14 VCC → +5V
for p in (13, 12, 10, 9):                            # 4OE, 4A, 3OE, 3A → +5V (выключены)
    bridge(*path(*IC[p], IC[p][0], 0))
bridge(*path(*IC[1], IC[1][0], 9))                   # 1 1OE → GND (канал 1 включён)
bridge(*path(*IC[7], IC[7][0], 9))                   # 7 GND
bridge(IC[4], (IC[4][0], 6))                         # 2OE → GND (канал 2 включён...)
bridge(IC[5], (IC[5][0], 6))                         # ...вход 2A → GND, выход 2Y висит в LOW
bridge(*path(IC[4][0], 6, IC[7][0], 6))

# Керамика у микросхемы: (7,2) — к выводу 14, (7,3) — через (7,4),(7,5) к выводу 1
bridge((7, 2), IC[14])
bridge((7, 3), (7, 4), (7, 5), IC[1])
parts.append(("cap", "C1", "104 у микросхемы", [(7, 2), (7, 3)]))

# Сигнал: GPIO16 → вывод 2; вывод 3 → 220 Ом → Din ленты
bridge(IC[2], (IC[2][0], 6))
wires.append(((IC[2][0], 6), "ESP32 GPIO16", "c2185b"))
bridge(*path(*IC[3], IC[3][0], 7))
parts.append(("res", "R1", "220", [(IC[3][0], 7), (IC[3][0] - 4, 7)]))
bridge((IC[3][0] - 4, 7), (IC[3][0] - 5, 7))
wires.append(((IC[3][0] - 5, 7), "лента Din", "c2185b"))

# Лента: питание прямо с шин. Отдельная керамика у её входа не нужна: шины те же, что
# у керамики микросхемы в сантиметре отсюда, а у каждого пикселя ленты — свои 0.1 мкФ.
wires.append(((2, 0), "лента +5V", "d93025"))
wires.append(((2, 9), "лента GND", "202124"))

# Питание: гнездо USB-C (зарядник от 2 А; CC1/CC2 гнезда никуда не подключаются) и ESP32
wires.append(((23, 0), "USB-C V", "d93025"))
wires.append(((23, 9), "USB-C G", "202124"))
wires.append(((19, 0), "ESP32 5V", "d93025"))
wires.append(((19, 9), "ESP32 GND", "202124"))

# ── Проверка цепей ─────────────────────────────────────────────────────────
expected = {
    "+5V": [(2, 0), (23, 0), (19, 0), IC[14], IC[13], IC[12], IC[10], IC[9], (7, 2)],
    "GND": [(2, 9), (23, 9), (19, 9), IC[1], IC[7], IC[4], IC[5], (7, 3)],
    "GPIO16": [(IC[2][0], 6), IC[2]],
    "OUT": [IC[3], (IC[3][0], 7)],
    "DIN": [(IC[3][0] - 4, 7), (IC[3][0] - 5, 7)],
}


def check():
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for b in bridges:
        for a, c in zip(b, b[1:]):
            assert abs(a[0] - c[0]) + abs(a[1] - c[1]) == 1, f"перемычка не по соседним отверстиям: {a}→{c}"
            parent[find(a)] = find(c)
    ic_holes = set(IC.values())
    body = {(x, y) for x in range(X0, X0 + 7) for y in (3, 4)}  # под корпусом микросхемы
    used = defaultdict(list)
    for b in bridges:
        for h in b:
            used[h].append("bridge")
    for kind, name, _, pins in parts:
        for h in pins:
            used[h].append(name)
    for h, _, _ in wires:
        used[h].append("wire")
    errors = []
    for h in used:
        if not (0 <= h[0] < COLS and 0 <= h[1] < ROWS):
            errors.append(f"отверстие {h} за краем платы")
        if h in body:
            errors.append(f"отверстие {h} под корпусом микросхемы")
    for kind, name, _, pins in parts:
        for h in pins:
            if h in ic_holes:
                errors.append(f"{name} в отверстии вывода микросхемы {h}")
    roots = {}
    for net, holes in expected.items():
        rs = {find(h) for h in holes}
        if len(rs) != 1:
            errors.append(f"цепь {net} разорвана: {len(rs)} кусков")
        roots[net] = find(holes[0])
    by_root = defaultdict(list)
    for net, r in roots.items():
        by_root[r].append(net)
    for r, ns in by_root.items():
        if len(ns) > 1:
            errors.append(f"замкнуты цепи {ns}")
    return errors


def straight_runs():
    """Перемычки, склеенные в прямые отрезки: один голый провод на прямой участок."""
    runs = []
    for b in bridges:
        run = [b[0]]
        for c in b[1:]:
            if len(run) >= 2 and (run[-1][0] - run[-2][0], run[-1][1] - run[-2][1]) != (c[0] - run[-1][0], c[1] - run[-1][1]):
                runs.append(run)
                run = [run[-1]]
            run.append(c)
        runs.append(run)
    return runs


# ── Запись .diy ───────────────────────────────────────────────────────────
def pt(h, tag="point"):
    x, y = at(*h)
    return f'<{tag} x="{x}" y="{y}"/>'


def xml_board():
    # DIYLC рисует отверстия строго внутри прямоугольника — углы на шаг за крайними отверстиями.
    x0, y0 = at(-1, -1)
    x1, y1 = at(COLS, ROWS)
    return f"""    <diylc.boards.PerfBoard>
      <name>Плата 3x7</name>
      <alpha>127</alpha>
      <value></value>
      <controlPoints>
        <point x="{x0}" y="{y0}"/>
        <point x="{x1}" y="{y1}"/>
      </controlPoints>
      <firstPoint x="{x0}" y="{y0}"/>
      <secondPoint x="{x1}" y="{y1}"/>
      <boardColor hex="1f6b3a"/>
      <borderColor hex="ada47d"/>
      <coordinateColor hex="b6b6b6"/>
      <xType>Numbers</xType>
      <coordinateOrigin>Top_Left</coordinateOrigin>
      <coordinateDisplay>Both_Sides</coordinateDisplay>
      <yType>Letters</yType>
      <mode>TwoPoints</mode>
      <spacing value="0.1" unit="in"/>
      <padColor hex="da8a67"/>
    </diylc.boards.PerfBoard>
"""


def xml_ic():
    # Формат DIYLC: точки по порядку выводов в ориентации DEFAULT (вертикально,
    # вывод 1 сверху слева). Горизонтально — поворот _270: вывод 1 снизу слева.
    # DIYLC хранит выводы 1..7, затем противоположный ряд: напротив 1 — 14, ..., напротив 7 — 8.
    order = list(range(1, 8)) + list(range(14, 7, -1))
    pts = "\n".join("        " + pt(IC[p]) for p in order)
    return f"""    <diylc.semiconductors.DIL__IC>
      <name>IC1</name>
      <alpha>127</alpha>
      <value>74AHCT125</value>
      <orientation>_270</orientation>
      <pinCount>_14</pinCount>
      <pinSpacing value="0.1" unit="in"/>
      <rowSpacing value="0.3" unit="in"/>
      <controlPoints>
{pts}
      </controlPoints>
      <display>BOTH</display>
      <bodyColor hex="3c4043"/>
      <borderColor hex="202124"/>
      <labelColor hex="ffffff"/>
      <indentColor hex="202124"/>
      <displayNumbers>DIP</displayNumbers>
    </diylc.semiconductors.DIL__IC>
"""


def xml_res(name, value, pins):
    num, unit = (value[:-1], "K") if value.endswith("K") else (value, "R")
    a, b = pins
    lx, ly = at((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 0.6)
    return f"""    <diylc.passive.Resistor>
      <name>{name}</name>
      <alpha>127</alpha>
      <length value="6.3" unit="mm"/>
      <width value="2.3" unit="mm"/>
      <points>
        {pt(a)}
        {pt(b)}
        <point x="{lx}" y="{ly}"/>
      </points>
      <bodyColor hex="82cffd"/>
      <borderColor hex="5b90b1"/>
      <labelColor hex="000000"/>
      <leadColor hex="cccccc"/>
      <display>BOTH</display>
      <flipStanding>false</flipStanding>
      <labelOriantation>Horizontal</labelOriantation>
      <moveLabel>false</moveLabel>
      <value value="{float(num)}" unit="{unit}"/>
      <power>QUARTER</power>
      <powerNew value="0.25" unit="W"/>
      <colorCode>_4_BAND</colorCode>
      <shape>Tubular</shape>
    </diylc.passive.Resistor>
"""


def xml_cap(name, pins):
    a, b = pins
    lx, ly = at((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return f"""    <diylc.passive.RadialCeramicDiskCapacitor>
      <name>{name}</name>
      <alpha>127</alpha>
      <length value="0.2" unit="in"/>
      <width value="0.1" unit="in"/>
      <points>
        {pt(a)}
        {pt(b)}
        <point x="{lx}" y="{ly}"/>
      </points>
      <bodyColor hex="f28c28"/>
      <borderColor hex="a85f1a"/>
      <labelColor hex="000000"/>
      <leadColor hex="cccccc"/>
      <display>NAME</display>
      <flipStanding>false</flipStanding>
      <labelOriantation>Directional</labelOriantation>
      <moveLabel>false</moveLabel>
      <pinSpacing value="0.1" unit="in"/>
      <voltage>_63V</voltage>
    </diylc.passive.RadialCeramicDiskCapacitor>
"""


def xml_jumper(i, a, b):
    lx, ly = at((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return f"""    <diylc.connectivity.Jumper>
      <name>J{i}</name>
      <alpha>127</alpha>
      <points>
        {pt(a)}
        {pt(b)}
        <point x="{lx}" y="{ly}"/>
      </points>
      <bodyColor hex="ffffff"/>
      <borderColor hex="000000"/>
      <labelColor hex="000000"/>
      <leadColor hex="9aa0a6"/>
      <display>NONE</display>
      <flipStanding>false</flipStanding>
      <labelOriantation>Directional</labelOriantation>
      <moveLabel>false</moveLabel>
      <hideShortLeads>false</hideShortLeads>
      <style>SOLID</style>
    </diylc.connectivity.Jumper>
"""


def wire_levels():
    """Подписи проводов — в три яруса по порядку слева направо, отдельно сверху и снизу."""
    levels = {}
    for up in (True, False):
        side = sorted((w for w in wires if (w[0][1] <= 4) == up), key=lambda w: w[0][0])
        for k, w in enumerate(side):
            levels[w[0]] = k % 3
    return levels


def xml_wire(i, h, label, color, k):
    # Провод к модулю уходит с платы вверх или вниз к подписи — пунктиром: по плате он
    # не идёт, в отверстие его вставляют сверху.
    x, y = at(*h)
    up = h[1] <= 4
    ey = round(at(0, 0)[1] - 0.25 - 0.2 * k, 3) if up else round(at(0, ROWS - 1)[1] + 0.25 + 0.2 * k, 3)
    return f"""    <diylc.connectivity.HookupWire>
      <name>W{i}</name>
      <alpha>127</alpha>
      <controlPoints2>
        <point x="{x}" y="{y}"/>
        <point x="{x}" y="{ey}"/>
      </controlPoints2>
      <color hex="{color}"/>
      <pointCount>TWO</pointCount>
      <style>DASHED</style>
      <smooth>true</smooth>
      <lastUpdatePointIndex>-1</lastUpdatePointIndex>
      <gauge>_26</gauge>
      <striped>false</striped>
      <stripeColor hex="ffff00"/>
    </diylc.connectivity.HookupWire>
    <diylc.misc.Label>
      <name>L{i}</name>
      <point x="{x}" y="{round(ey + (-0.08 if up else 0.08), 3)}"/>
      <text>{label}</text>
      <font name="Dialog.plain" size="9" style="0"/>
      <color hex="000000"/>
      <center>true</center>
      <horizontalAlignment>CENTER</horizontalAlignment>
      <verticalAlignment>CENTER</verticalAlignment>
      <orientation>DEFAULT</orientation>
    </diylc.misc.Label>
"""


def main():
    errors = check()
    if errors:
        raise SystemExit("ОШИБКИ раскладки:\n  " + "\n  ".join(errors))
    comps = [xml_board()]
    j = 0
    for run in straight_runs():
        j += 1
        comps.append(xml_jumper(j, run[0], run[-1]))
    comps.append(xml_ic())
    for kind, name, value, pins in parts:
        comps.append(xml_res(name, value, pins) if kind == "res" else xml_cap(name, pins))
    levels = wire_levels()
    for i, (h, label, color) in enumerate(wires, 1):
        comps.append(xml_wire(i, h, label, color, levels[h]))
    doc = f"""<?xml version="1.0" encoding="UTF-8" ?>
<project>
  <fileVersion>
    <major>4</major>
    <minor>17</minor>
    <build>0</build>
  </fileVersion>
  <title>Подставка для статуэток — плата 3x7</title>
  <author>nfc-figurines</author>
  <width value="29.0" unit="cm"/>
  <height value="21.0" unit="cm"/>
  <gridSpacing value="0.1" unit="in"/>
  <dotSpacing>1</dotSpacing>
  <components>
{"".join(comps)}  </components>
  <groups>
    <set/>
  </groups>
  <lockedLayers/>
  <lockedComponents/>
  <hiddenLayers/>
  <font name="Dialog.plain" size="14" style="0"/>
</project>
"""
    OUT.write_text(doc, encoding="utf-8")
    print(f"цепи в порядке, перемычек {j}, проводов с платы {len(wires)} → {OUT}")


if __name__ == "__main__":
    main()
