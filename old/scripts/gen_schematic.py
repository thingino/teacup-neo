#!/usr/bin/env python3
"""Swap IC1 T31ZX -> T41NQ in the schematic and rewire by net-name labels.

Connectivity is by label/power-symbol name (flat sheet), so we place a
label (signals), power-symbol (rails) or no_connect (NC) exactly at each
T41 pin's connection point. Old T31 stubs are removed by exact pin-position
match. Verified afterwards by netlist export diff.
Transform (calibrated vs T31): abs = (O.x + sym.x, O.y - sym.y), rot 0.
"""
import re, csv, uuid

SCH = "/home/turismo/projects/teacup-t41/hw/teacup-t41.kicad_sch"
SYMLIB = "/home/turismo/projects/teacup-t41/hw/teacup.kicad_sym"
NETS = "/home/turismo/projects/teacup-t41/docs/t41_pin_nets.csv"
PROJECT = "teacup-t41"
SHEET = "6e7ef4e6-2026-4726-8de0-60238113f775"
O = (106.68, 187.96)     # T41 instance origin (same as old T31)

def U(): return str(uuid.uuid4())

sch = open(SCH).read()

# ---- 0. normalize internal project name (files were renamed) ----
sch = sch.replace('(project "12-30-23-Teacup.kicad_pcb-revC"', f'(project "{PROJECT}"')

# ---- 1. extract + adapt T41NQ symbol def from teacup.kicad_sym ----
symlib = open(SYMLIB).read()
mt = re.search(r'\n  \(symbol "T41NQ".*?\n  \)\n', symlib, re.S)
t41 = mt.group(0)
# rename ONLY the parent for embedding under teacup: library.
# child sub-symbols keep the unprefixed "T41NQ_0_1"/"T41NQ_1_1" names.
t41 = t41.replace('(symbol "T41NQ"', '(symbol "teacup:T41NQ"', 1)
# indent from 2->4 spaces to match lib_symbols nesting
t41 = "\n".join(("  " + ln if ln.strip() else ln) for ln in t41.split("\n"))

# ---- parse T41 pin positions (at x y ang) + number ----
pindef = {}
for mm in re.finditer(r'\(pin \w+ line \(at ([-\d.]+) ([-\d.]+) (\d+)\) \(length [\d.]+\).*?\(number "(\d+)"', t41, re.S):
    x,y,a,n = mm.groups()
    pindef[int(n)] = (float(x), float(y), int(a))
assert len(pindef) == 97, f"parsed {len(pindef)} T41 pins"

def abspos(p):
    sx, sy, a = pindef[p]
    return (round(O[0]+sx, 2), round(O[1]-sy, 2), a)

# ---- 2. remove T31ZX lib def + instance ----
sch = re.sub(r'\n    \(symbol "teacup:T31ZX".*?\n    \)\n', '\n', sch, flags=re.S)
mi = re.search(r'\n  \(symbol \(lib_id "teacup:T31ZX"\).*?\n  \)\n', sch, re.S)
# compute old T31 pin abs BEFORE deleting (need its symdef; re-read from a backup copy)
orig = open(SCH).read()
t31def = re.search(r'\(symbol "teacup:T31ZX".*?\n  \)\n', orig, re.S).group(0)
t31pins = re.findall(r'\(pin \w+ \w+ \(at ([-\d.]+) ([-\d.]+) (\d+)\) \(length [\d.]+\).*?\(number "(\d+)"', t31def, re.S)
oi = re.search(r'\(symbol \(lib_id "teacup:T31ZX"\) \(at ([-\d.]+) ([-\d.]+) (\d+)\)', orig)
oox, ooy = float(oi.group(1)), float(oi.group(2))
old_abs = {(round(oox+float(x),2), round(ooy-float(y),2)) for x,y,a,n in t31pins}
sch = sch[:mi.start()] + '\n' + sch[mi.end():]

# ---- 3. remove old IC1 stubs, EXCEPT for wire-only nets that must stay
#         anchored (crystal/boot/VCM/VREF-divider/PB27-SD). For those we keep
#         the stub wire and add a reconnection label at the old pin position.
def near(pt, s, tol=0.05):
    return any(abs(pt[0]-q[0])<tol and abs(pt[1]-q[1])<tol for q in s)

# old T31 pin number -> abs pos (for the 6 keep-stub pins)
t31_abs = {int(n): (round(oox+float(x),2), round(ooy-float(y),2)) for x,y,a,n in t31pins}
# T31 pin -> clean net label to anchor (matches the T41 side)
KEEP = {5:"EXCLK_XIN", 4:"EXCLK_XOUT", 67:"BOOT_SEL0", 42:"VCM", 77:"DDR_VREF", 86:"PB27"}
keep_pos = {t31_abs[p] for p in KEEP}
remove_pos = old_abs - keep_pos     # remove stubs everywhere except the anchored pins

# wires with an endpoint at a removable old pin position; record the FAR end
far_ends = set()
def sub_wire(m):
    x1,y1,x2,y2 = [round(float(v),2) for v in m.groups()[:4]]
    n1 = near((x1,y1), remove_pos); n2 = near((x2,y2), remove_pos)
    if n1 or n2:
        sub_wire.n += 1
        far_ends.add((x2,y2) if n1 else (x1,y1))
        return ""
    return m.group(0)
sub_wire.n = 0
sch = re.sub(r'  \(wire \(pts \(xy ([-\d.]+) ([-\d.]+)\) \(xy ([-\d.]+) ([-\d.]+)\)\).*?\n  \)\n', sub_wire, sch, flags=re.S)

# remove now-inert IC1-side labels that sat at those far ends (redundant with
# the peripheral-side label / new T41 label). Keeps ERC clean.
def sub_farlbl(m):
    x,y = round(float(m.group(2)),2), round(float(m.group(3)),2)
    if near((x,y), far_ends): sub_farlbl.n += 1; return ""
    return m.group(0)
sub_farlbl.n = 0
sch = re.sub(r'  \(label "([^"]+)" \(at ([-\d.]+) ([-\d.]+) \d+\)(?: \(fields_autoplaced\))?\n(?:    \([^\n]*\)\n)*  \)\n', sub_farlbl, sch)
print(f"removed {sub_wire.n} stub wires + {sub_farlbl.n} inert far-labels; re-anchored {len(KEEP)} wire-only nets")

# ---- 4. insert T41NQ lib def into lib_symbols (before first existing symbol) ----
sch = sch.replace("\n  (lib_symbols\n", "\n  (lib_symbols\n" + t41 + "\n", 1)

# ---- 4b. add teacup:+1V35 power lib def (clone teacup:+0V8) ----
p0v8 = re.search(r'    \(symbol "teacup:\+0V8".*?\n    \)\n', sch, re.S).group(0)
p1v35 = (p0v8.replace('teacup:+0V8', 'teacup:+1V35')
              .replace('"+0V8"', '"+1V35"').replace('+0V8', '+1V35'))
sch = sch.replace(p0v8, p0v8 + p1v35, 1)

# ---- 5. T41NQ instance ----
inst = f'''  (symbol (lib_id "teacup:T41NQ") (at {O[0]} {O[1]} 0) (unit 1)
    (in_bom yes) (on_board yes) (dnp no)
    (uuid {U()})
    (property "Reference" "IC1" (at {O[0]} {O[1]-2.54} 0)
      (effects (font (size 1.27 1.27))))
    (property "Value" "T41NQ" (at {O[0]} {O[1]+2.54} 0)
      (effects (font (size 1.27 1.27))))
    (property "Footprint" "teacup:QFN96_10x10_P0.35_EP7.6x7.2_T41" (at {O[0]} {O[1]} 0)
      (effects (font (size 1.27 1.27)) hide))
    (property "Datasheet" "T41NQ_ds_v1.6" (at {O[0]} {O[1]} 0)
      (effects (font (size 1.27 1.27)) hide))
    {"".join(f'(pin "{p}" (uuid {U()})) ' for p in range(1,98))}
    (instances
      (project "{PROJECT}"
        (path "/{SHEET}" (reference "IC1") (unit 1))))
  )
'''

# ---- 6. per-pin labels / power-syms / no_connect ----
nets = {int(r["t41_pin"]): r["net_or_rail"] for r in csv.DictReader(open(NETS))}
# next free #PWR ref
pwrnums = [int(x) for x in re.findall(r'"#PWR0*(\d+)"', sch)]
pwr_n = max(pwrnums)+1 if pwrnums else 1

RAILSYM = {"+0V8":"teacup:+0V8", "+1V35":"teacup:+1V35",
           "+1V8":"power:+1V8", "+3V3":"power:+3V3", "GND":"power:GND"}
# label rotation by side so text points away from body
def lbl_rot(ang):   # pin angle 0=left side pts right,180=right,270=top,90=bottom
    return {0:180, 180:0, 90:90, 270:270}.get(ang,0)

adds = [inst]
# reconnection labels for the 6 anchored wire-only nets (at old T31 pin pos)
for t31p, name in KEEP.items():
    ax, ay = t31_abs[t31p]
    adds.append(f'''  (label "{name}" (at {ax} {ay} 0)
    (effects (font (size 1.27 1.27)) (justify left bottom)) (uuid {U()}))
''')
for p in range(1,98):
    ax, ay, ang = abspos(p)
    net = nets[p]
    if net in RAILSYM:
        ref = f"#PWR{pwr_n:03d}"; pwr_n += 1
        adds.append(f'''  (symbol (lib_id "{RAILSYM[net]}") (at {ax} {ay} {ang}) (unit 1)
    (in_bom yes) (on_board yes) (dnp no)
    (uuid {U()})
    (property "Reference" "{ref}" (at {ax} {ay-2.54} 0)
      (effects (font (size 1.27 1.27)) hide))
    (property "Value" "{net}" (at {ax} {ay+2.54} 0)
      (effects (font (size 1.27 1.27))))
    (pin "1" (uuid {U()}))
    (instances
      (project "{PROJECT}"
        (path "/{SHEET}" (reference "{ref}") (unit 1))))
  )
''')
    elif net == "NC":
        adds.append(f'  (no_connect (at {ax} {ay}) (uuid {U()}))\n')
    else:
        name = net.lstrip("/")
        adds.append(f'''  (label "{name}" (at {ax} {ay} {lbl_rot(ang)})
    (effects (font (size 1.27 1.27)) (justify left bottom)) (uuid {U()}))
''')

# insert all before (sheet_instances
sch = sch.replace("\n  (sheet_instances", "\n" + "".join(adds) + "\n  (sheet_instances", 1)

open(SCH, "w").write(sch)
print(f"placed T41NQ instance + {len(adds)-1} pin connections at origin {O}")
