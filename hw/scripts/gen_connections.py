import re, sys

SHEETS = [
    ("power", "POWER"),
    ("connector", "DDR4 UDIMM-288 CONNECTOR"),
    ("bmc", "BMC - ESP32-S3"),
    ("io", "CARRIER PHYSICAL I/O"),
    ("headers", "PIN BREAKOUT HEADERS"),
]
SHEETS_DIR = "/home/administrator/projects/teacup-neo/hw/sheets"
# Regenerate before running this script:
#   kicad-cli10 sch export netlist --format kicadsexpr -o /tmp/teacup-carrier.net \
#     /home/administrator/projects/teacup-neo/hw/teacup-carrier.kicad_sch
# (needs KiCad 10's kicad-cli -- the repo's .kicad_sch files are KiCad 10
# schema; the system kicad-cli may be a KiCad 9 install that can't load them,
# check for a kicad-cli10 binary in that case)
NETLIST = "/tmp/teacup-carrier.net"
OUT = "/home/administrator/projects/teacup-neo/hw/CONNECTIONS.txt"

STD_LIBS = {
    "Device": "/usr/share/kicad/symbols/Device.kicad_sym",
    "power": "/usr/share/kicad/symbols/power.kicad_sym",
    "Connector": "/usr/share/kicad/symbols/Connector.kicad_sym",
    "Connector_Generic": "/usr/share/kicad/symbols/Connector_Generic.kicad_sym",
    "Connector_Audio": "/usr/share/kicad/symbols/Connector_Audio.kicad_sym",
    "Regulator_Linear": "/usr/share/kicad/symbols/Regulator_Linear.kicad_sym",
    "Transistor_FET": "/usr/share/kicad/symbols/Transistor_FET.kicad_sym",
}
TC = "/home/administrator/projects/teacup-neo/hw/teacup-carrier.kicad_sym"

def paren_block(t, i):
    depth = 0; instr = False; start = i
    n = len(t)
    while i < n:
        c = t[i]
        if c == '"' and t[i-1] != '\\':
            instr = not instr
        elif not instr:
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    return t[start:i+1]
        i += 1
    raise ValueError

def get_symbol_pins(lib_id):
    """lib_id like 'teacup-carrier:X' or 'Device:R'. Returns [(name, number)].
    Follows KiCad's (extends "Base") inheritance -- some library symbols
    (e.g. AO3401A extends TP0610T) carry no pins of their own."""
    libname, symname = lib_id.split(":", 1)
    path = TC if libname == "teacup-carrier" else STD_LIBS[libname]
    text = open(path).read()
    idx = text.find(f'(symbol "{symname}"')
    if idx == -1:
        raise ValueError(f"symbol {symname} not found in {path}")
    block = paren_block(text, idx)
    ext = re.search(r'\(extends "([^"]+)"\)', block)
    if ext and '(pin ' not in block:
        base_idx = text.find(f'(symbol "{ext.group(1)}"')
        block = paren_block(text, base_idx)
    pins = []
    # direct pins (single-unit symbols)
    i = 0
    while True:
        i = block.find('(pin ', i)
        if i == -1: break
        # make sure this is a DIRECT pin, not inside a nested (symbol _0_1) that
        # we'll also scan separately -- direct scan of whole block is fine since
        # we just want ALL pins across all sub-units combined (dedup by number)
        pb = paren_block(block, i)
        nm = re.search(r'\(name "([^"]*)"', pb)
        nu = re.search(r'\(number "([^"]*)"', pb)
        if nm and nu:
            pins.append((nm.group(1), nu.group(1)))
        i += len(pb)
    # dedupe keeping first occurrence per number
    seen = {}
    for nm, nu in pins:
        if nu not in seen:
            seen[nu] = nm
    return seen  # number -> name

def extract_instances(sch_text):
    """Return list of (ref, lib_id, value, footprint) for top-level placed symbols."""
    lib_start = sch_text.find("(lib_symbols")
    lib_block = paren_block(sch_text, lib_start)
    body = sch_text[lib_start + len(lib_block):]
    out = []
    i = 0
    while True:
        i = body.find('(symbol (lib_id ', i)
        if i == -1: break
        block = paren_block(body, i)
        lib_id_m = re.search(r'\(lib_id "([^"]+)"\)', block)
        ref_m = re.search(r'\(property "Reference" "([^"]+)"', block)
        val_m = re.search(r'\(property "Value" "([^"]+)"', block)
        fp_m = re.search(r'\(property "Footprint" "([^"]*)"', block)
        if lib_id_m and ref_m:
            out.append((ref_m.group(1), lib_id_m.group(1), val_m.group(1) if val_m else "", fp_m.group(1) if fp_m else ""))
        i += len(block)
    return out

def natkey(ref):
    m = re.match(r'([A-Za-z]+)(\d+)', ref)
    if m:
        return (m.group(1), int(m.group(2)))
    return (ref, 0)

def pinnatkey(num):
    try:
        return (0, int(num))
    except ValueError:
        return (1, num)

# parse full netlist -> {(ref,pin): net}
net_text = open(NETLIST).read()
pin_to_net = {}
n = len(net_text)
for m in re.finditer(r'\(net\s', net_text):
    idx = m.start()
    block = paren_block(net_text, idx)
    name_m = re.search(r'\(name "([^"]*)"\)', block)
    name = name_m.group(1) if name_m else "?"
    for pm in re.finditer(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"', block):
        pin_to_net[(pm.group(1), pm.group(2))] = name

lines = []
lines.append("TEACUP UNIVERSAL CARRIER BOARD - CONNECTION REFERENCE")
lines.append("Generated directly from the KiCad netlist export (ground truth -- if the")
lines.append("schematic's visual layout is unclear or you're rebuilding it by hand, this")
lines.append("is what every pin SHOULD end up wired to, regardless of how it currently renders.")
lines.append("=" * 80)
lines.append("")

symbol_pin_cache = {}

for fname, title in SHEETS:
    text = open(f"{SHEETS_DIR}/{fname}.kicad_sch").read()
    instances = extract_instances(text)
    # dedupe by ref (multi-unit parts like J1 place once per unit)
    by_ref = {}
    for ref, lib_id, value, fp in instances:
        if ref.startswith("#"):
            continue
        by_ref.setdefault(ref, (lib_id, value, fp))
    lines.append(f"### {title}")
    lines.append("-" * 80)
    lines.append("")
    for ref in sorted(by_ref, key=natkey):
        lib_id, value, fp = by_ref[ref]
        if lib_id not in symbol_pin_cache:
            symbol_pin_cache[lib_id] = get_symbol_pins(lib_id)
        pins = symbol_pin_cache[lib_id]
        lines.append(f"{ref}  ({value})")
        lines.append(f"      footprint: {fp}")
        for num in sorted(pins.keys(), key=pinnatkey):
            name = pins[num]
            net = pin_to_net.get((ref, num))
            if net is None:
                net = "(not connected)"
            elif net.startswith("unconnected-"):
                net = "(not connected)"
            elif net.startswith("/"):
                net = net[1:]
            namecol = "" if (name == "~" or name == num) else f"  {name}"
            lines.append(f"      pin {num:>4}{namecol:<22} -> {net}")
        lines.append("")

open(OUT, "w").write("\n".join(lines) + "\n")
print("wrote", OUT)
