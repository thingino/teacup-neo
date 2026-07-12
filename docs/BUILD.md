# Teacup Neo — hardware build guide (headless KiCad, agent-facing)

This is the **how**. [`UNIVERSAL.md`](UNIVERSAL.md) is the **what** — the design
spec (connector, power, rails, pinout budget, peripherals). Read UNIVERSAL.md first;
this document tells an agent how to turn that spec into fabricated boards using the
headless toolchain, and it encodes the method + gotchas already proven on the T41
board (now archived in [`../old/`](../old/) — reuse those scripts as templates).

Two boards, built against **one shared pinout contract**:
- **interposer** — per-SoC module (SoC + fanout + clock + decoupling + straps
  + optional local power / NOR), gold-finger card edge.
- **carrier** — universal baseboard (DDR4 socket + power + peripherals + ESP32-S3
  BMC + full breakout).

> **Prime directive: verify every step by machine, never by eyeballing.** The T41
> board was trustworthy because each stage was checked programmatically — netlist
> export diff, per-pad net comparison, DRC. A schematic that "looks right" in a
> render is not verified. Every phase below ends in a **Verify** gate; do not
> advance past a failing gate.

---

## 1. Toolchain (exact, verified on this host)

| Tool | Version | Use |
|---|---|---|
| `kicad-cli` | **9.0.2** (`/usr/bin/kicad-cli`) | netlist/gerber/drill/pos/bom/svg/drc export |
| Python `pcbnew` | **9.0.2** | headless PCB surgery (footprint swap/add, per-pad `SetNet`, DSN/SES) |
| OpenJDK | **21.0.11** | runs FreeRouting |
| FreeRouting | **1.9.0** (download jar) | autorouter. **NOT 2.2.4** — it needs Java 25; we have 21 |
| `xvfb-run` | present (`/usr/bin/xvfb-run`) | FreeRouting throws `HeadlessException` without an X display |

Setup notes:
- **FreeRouting jar is not on disk** — fetch `freerouting-1.9.0.jar` from the v1.9.0
  GitHub release and keep the path in a variable. Confirm it starts:
  `xvfb-run java -jar freerouting-1.9.0.jar --help`.
- Stock KiCad libraries live at `/usr/share/kicad/footprints` and cover
  `Package_BGA`, `Package_QFP`, `Connector_PinHeader_*`, `MountingHole`, `Package_SO`
  (SOIC/SOT). **There is no DDR connector footprint** — the card edge is custom (§4).
- Schematic edits are done as **plain-text S-expression surgery** (regex on the
  `.kicad_sch`); PCB edits go through the **`pcbnew` Python API**. Both are
  scriptable and deterministic — that is the whole point.

Repo layout to create (mirrors `old/` but per-board):
```
hw/
  interposer/   interposer.kicad_pro|_sch|_pcb, teacup-neo.kicad_sym, *.pretty/
  carrier/      carrier.kicad_pro|_sch|_pcb,     teacup-neo.kicad_sym, *.pretty/
  common.pretty/   card-edge + shared footprints
scripts/        generators (copy + adapt from old/scripts/)
docs/pinout_288.csv   the contract (§3)
```

---

## 2. The proven method (reuse it verbatim, don't reinvent)

Everything below was validated on the T41 board. The scripts named are in
[`../old/scripts/`](../old/scripts/) — copy and adapt, don't start from scratch.

**2.1 Connectivity is by label name (flat sheet).** You do not draw wires. To
connect a pin to a net, place a **label** (signal), **power-symbol** (rail), or
**`no_connect`** (NC) at that pin's *absolute* position on the sheet. Same label
name = same net. This makes rewiring a pin a one-line placement, not a routing
problem. (`old/scripts/gen_schematic.py`, `gen_power_bucks.py`, `gen_new_circuits.py`.)

**2.2 The pin transform (calibrated).** A symbol pin at local `(sym.x, sym.y)` with
instance origin `O` lands at absolute `(O.x + sym.x, O.y − sym.y)` for rotation 0.
Parse the pin table from the symbol, compute each absolute position, place the
label there. Verify — never trust the transform blind.

**2.3 Verify the schematic by netlist diff, not by looking.**
```
kicad-cli sch export netlist -o /tmp/out.net hw/<board>/<board>.kicad_sch
```
Parse it, assert every intended `(ref,pin) -> net` is present and nothing was
orphaned. The T41 build treated "97 pins on intended nets, 0 mismatch" as the pass
condition. Do the same.

**2.4 PCB "update from schematic" is done in Python** (there is no
`kicad-cli pcb update-from-sch`). Pattern from `old/scripts/gen_pcb_update.py`:
```python
import pcbnew
b = pcbnew.LoadBoard(BRD)
# swap/add footprints (FootprintLoad from a .pretty), set position/rotation
# for each pad: pad.SetNet(b.FindNet(net_name_from_netlist))
# rip tracks when a pinout changed:  for t in list(b.GetTracks()): b.Delete(t)
pcbnew.SaveBoard(BRD, b)
```
**Verify: every pad's net == the netlist's net for that (ref,pad). 0 mismatch.**
Report the ratsnest (unrouted) count.

**2.5 Routing round-trip.** `old/scripts/gen_pcb_import_route.py` shows the return
leg; the full loop:
```python
pcbnew.ExportSpecctraDSN(b, "board.dsn")          # export
# xvfb-run java -jar freerouting-1.9.0.jar -de board.dsn -do board.ses -mp <passes>
pcbnew.ImportSpecctraSES(b, "board.ses")          # import result
pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.BuildConnectivity(); pcbnew.SaveBoard(BRD,b)
```
FreeRouting flags: `-de` design in (DSN), `-do` design out (SES), `-mp` max passes.
Always under `xvfb-run`.

**2.6 Manufacturing** is pure `kicad-cli` — copy `old/scripts/gen_manufacturing.sh`:
DRC → gerbers + drill → pos (centroid) → BOM → top/bottom SVG renders.

---

## 3. Phase 0 — the pinout contract (do this FIRST)

Both boards build against a single artifact: **`docs/pinout_288.csv`** — a map of
each of the 288 socket positions to a net. Neither board can be laid out until this
exists, because the interposer's gold fingers and the carrier's socket pads must
agree pin-for-pin.

Assign **geography-first** (UNIVERSAL.md §8), not by GPIO bank order:
- The **superset** is ~180 signals + ~15 power; the rest of the 288 positions are
  **ground fill** (target ≥ 1 GND per 3 signals; 288 gives ~93 grounds).
- **High-speed on one contact row** so each escapes on a single layer.
- **Diff pairs** (MIPI 100 Ω, A1 SATA ~90 Ω, HDMI TMDS, RGMII) on **adjacent fingers,
  same face, a GND finger each side.**
- **Power clustered** at one end (the 5 V pour is a blob, not a snake).
- **Mutually-exclusive peripherals share positions** (UNIVERSAL.md §8 escape valve):
  A1 display-out (HDMI/VGA/RGB) reuses the T-series **camera-zone**; DVP reuses the
  MIPI/GPIO positions (no interposer is ever both). This is what keeps A1+SATA inside
  288.
- **A1-unique** positions: dual SATA (4 pairs), 2nd RGMII, extra USB (§10).

**Verify:** every signal named in §3/§8/§9/§10 has exactly one position; every diff
pair has flanking grounds; ground ratio ≥ 1/3; SoC-specific pin maps (per-SoC
column) all fit the assigned positions. Output is a reviewed CSV, committed.

---

## 4. Phase 1 — the card-edge footprint (the one genuinely new part)

Two mating halves of the **same 288 geometry** (UNIVERSAL.md §1 mechanical). Build
like `old/scripts/gen_footprint.py` built the QFN96 — parametric Python emitting a
`.kicad_mod`.

**4a. Interposer edge** = a footprint whose "pads" are the gold fingers:
- 288 edge pads, **144 per face**, **0.85 mm pitch** (~122 mm finger span → ~133 mm
  card), on `F.Cu` (top face) and `B.Cu` (bottom face).
- `Edge.Cuts` outline carrying the **DDR4 UDIMM key notch** at its JEDEC position
  (distinct from SO-DIMM) and the two **side latch cut-outs**.
- Board **thickness 1.0 mm ±0.1** — a hard seating requirement (set in board setup,
  not the footprint, but the fingers assume it).
- ENIG/hard-gold on the fingers, chamfered lead-in (fab/gerber concern, note it).

**4b. Carrier socket** = the mating connector footprint:
- Primary **Foxconn AH58893-T9B10-3F** (LCSC **C42403003**, SMD vertical, 288P, 738
  stock). Import the LCSC/EasyEDA footprint if available, else draw from the datasheet.
- Alt: Amphenol FCI **DDR4288V0213TF**.

**Verify:** finger/pad count == 288; pitch 0.85; notch + latch positions match the
JEDEC DDR4 UDIMM drawing; **finger N on the interposer maps to socket pad N maps to
`pinout_288.csv` row N** (a 1:1 cross-check script). A card edge that seats but is
mirror-flipped or off-by-one is the worst failure mode — check it explicitly.

---

## 5. Phase 2 — the interposer (build ONE reference first: T41 or T31)

Prove the interposer pipeline on a SoC we already have data for (T41 footprint +
symbol + pins exist in `old/`), then parametrize.

1. **Footprints** — SoC package (`old/hw/teacup.pretty/QFN96…` exists for T41; BGA
   parts use `Package_BGA` or a generated `.kicad_mod`), the **card edge** (§4a),
   plus NOR SOIC, crystal, buck, passives from stock libs.
2. **Symbol** — `old/scripts/gen_symbol.py` builds a KiCad 9 symbol from a per-SoC
   pin CSV (grouped by function onto 4 sides). One CSV per SoC.
3. **Schematic** (label method, §2.1) — place, for every SoC pin: a label routing it
   to its **card-edge finger** per `pinout_288.csv`; the **clock** (24 MHz xtal + 1 M
   + 33 R, tight); **decoupling** (mandatory local, §2 SI rules); **straps**
   (BOOT_SEL, POR); optional **local bucks** (mode A) or FB-set resistors (mode B);
   optional **8-pad NOR** on SFC0.
4. **Verify schematic** by netlist diff (§2.3).
5. **PCB** — 1.0 mm board, 4-layer; place the SoC island + the card-edge footprint;
   apply the netlist in Python (§2.4); **verify 0 pad-net mismatch.**
6. **Route** — short and local. Keep the clock off any connector. MIPI/DDR (external-
   DDR parts) get controlled-impedance care (§7). FreeRouting the rest (§2.5).
7. **DRC + outputs** (§2.6).

**Parametrize:** other SoCs = new pin CSV → `gen_symbol.py` → new package footprint →
re-run the schematic generator against `pinout_288.csv`. The card edge, clock, decap,
and straps are the same template; only the SoC fanout changes. Note per-SoC deltas
(DDR voltage, SIP vs external DDR, DVP vs MIPI, A1's SATA/analog rails).

---

## 6. Phase 3 — the carrier (universal baseboard)

Bigger, but the same method. Build in **functional blocks**, each label-connected and
netlist-verified independently before integration.

1. **Footprints** — the **socket** (§4b); ESP32-S3-WROOM-1-N16R2 module; the
   adjustable bucks (VCORE ≥3 A / VDDR ≥1.5 A) + LDOs; MCP4661 digipot; USB-C ×2,
   RJ45 ×2, SATA ×2, HDMI, VGA, microSD, audio jack + codec passives, camera FFC,
   DIP8/SOP8 flash, JTAG 2×5, IR-cut/IR-LED drivers, test-point pads; GPIO headers.
2. **Symbols** for each IC.
3. **Schematic — one block at a time**, each label-connected + netlist-verified:
   - **Power** (UNIVERSAL.md §2/§4): switched SoC-5V domain (one load switch feeds
     VCORE/VDDR bucks + carrier 3.3/1.8 + connector 5V) vs **always-on** BMC 3.3;
     digipot on the FB dividers; VCORE_SNS to the BMC ADC.
   - **BMC** (§9): ESP32-S3, USB, BOOTSEL/reset/flash-select GPIO, UART fan-in, I²C.
   - **Peripherals** (§8): USB, dual GbE, dual SATA, HDMI/VGA, SD, audio (mic→codec,
     HPOUT→jack, I²S/DMIC headers), camera FFC + DVP header, PWM/IR-cut/IR-LED, JTAG.
   - **Breakout** (§8): every remaining socket position → labeled 0.1" header.
4. **Verify** the full schematic by netlist diff.
5. **PCB** — 4–6 layer (§7); **floorplan by geography** (§8): place the socket, then
   each block so its nets exit the socket already pointed at it (USB by the USB
   jacks, MIPI by the FFC, SATA by the SATA connectors, power clustered). Apply
   netlist in Python; **verify 0 pad-net mismatch.**
6. **Route** — FreeRouting the bulk single-ended nets; **hand-route the diff pairs**
   (§7). DRC + outputs.

---

## 7. Controlled impedance & the manual-routing gap (READ before any routing)

**FreeRouting does not do controlled impedance.** It gets you ~80–85% (single-ended,
low-speed) fast, but the high-speed pairs need a defined stackup and hand routing.
This was the T41 board's explicit "not fab-ready" gap — do not let an autorouter
"finish" and call it done.

1. **Define the stackup first** so impedance is calculable: interposer 4-layer at
   1.0 mm (fixed by the card-edge spec); carrier 4-layer, or **6-layer** if the A1
   SATA/HDMI + dual-MIPI density gets tight. Set dielectric heights in board setup.
2. **Targets:** MIPI D-PHY ~100 Ω diff; SATA ~90 Ω (100 Ω also common per PHY); HDMI
   TMDS ~100 Ω diff; RGMII single-ended ~50 Ω, length-matched to its clock.
3. **Route diff pairs by hand** (pcbnew or the GUI), length-matched, GND-flanked,
   minimum vias. Lock them, then let FreeRouting fill in around them.
4. A **human review in the KiCad GUI** before fab is mandatory (placement de-overlap,
   impedance, return paths) — the same caveat as the T41 board.

---

## 8. Verification gates (must pass before advancing)

| Phase | Gate |
|---|---|
| Pinout (§3) | every §8 signal has 1 position; diff pairs GND-flanked; GND ratio ≥ 1/3 |
| Card edge (§4) | 288 pads; 0.85 mm pitch; notch/latch per JEDEC; finger↔socket↔CSV 1:1, not mirrored/off-by-one |
| Footprint | pad count + pitch == datasheet; courtyard sane |
| Symbol | pin count == datasheet; no duplicate pin numbers |
| Schematic | `kicad-cli sch export netlist` clean; every intended net present; ERC power/NC resolved |
| PCB apply | every pad net == netlist (**0 mismatch**); ratsnest reported |
| Routing | 0 unrouted; **0 DRC errors**; diff pairs impedance + length checked |
| Manufacturing | gerbers/drill/pos/BOM emitted; JLCPCB DFM rule pass |

---

## 9. Gotchas (hard-won on the T41 build — you will hit these)

- **Schematic S-expr symbol prefixing.** When embedding a symbol into a sheet's
  `lib_symbols`, the **parent** gets the library prefix (`teacup-neo:T41NQ`) but the
  **child sub-symbols keep the unprefixed name** (`T41NQ_0_1`, `T41NQ_1_1`). Prefix
  the children and KiCad reports **"Failed to load schematic."**
- **Removing old stubs orphans wire-only nets.** Deleting a pin's old connection can
  strand nets that were only held by a wire (crystal, boot-sel, VREF, VCM…). Keep the
  stub or add a reconnection label at the old pin position, then re-verify the netlist.
- **FreeRouting version/headless.** Use **1.9.0 with Java 21** (2.2.4 needs Java 25).
  A bare run throws `HeadlessException` → always `xvfb-run`.
- **No DDR connector in stock KiCad** → the card edge is a custom footprint (§4).
- **1.0 mm board thickness is a hard requirement** for the edge to seat — set it in
  board setup; too thick spreads the contacts, too thin is intermittent.
- **Part stock data goes stale.** Verify parts on live vendor pages, not cached
  search. (The socket **C42403003** and ESP32 **C2913205** were live-verified; re-check
  at BOM time.)
- **New generated file / net → verify, don't assume.** Confirm by netlist export or
  pad-net readback, the same way you'd `nm` a new object file.
- **Retail SoC secure-boot / eFuse state is unknown** — a locked part can't be
  reflashed. Note it in the BOM (the lab once hit a locked T32NQ).

---

## 10. Definition of done (per board)

1. Schematic netlist-verified (every intended net; 0 mismatch).
2. PCB netlist applied with 0 pad-net mismatch.
3. 0 unrouted ratsnest; 0 DRC errors; diff pairs impedance + length verified.
4. Stackup defined; card-edge geometry matches the JEDEC UDIMM drawing.
5. Manufacturing set emitted (gerbers, drill, centroid, BOM, renders) and passed a
   JLCPCB DFM check.
6. **Human GUI review** signed off (placement, impedance, return paths).
7. BOM parts live-verified for stock + secure-boot state.

---

## Appendix — reusable scripts (`old/scripts/`, T41 templates)

| Script | What it does | Adapt for |
|---|---|---|
| `gen_footprint.py` | parametric `.kicad_mod` (built the QFN96) | the card edge (§4) + BGA/QFN packages |
| `gen_symbol.py` | KiCad 9 symbol from a per-SoC pin CSV | every SoC symbol |
| `gen_schematic.py` | swap SoC + rewire by net-name labels; pin transform; netlist-verify | interposer schematic per SoC |
| `gen_power_bucks.py` | add regulators, label-connected | carrier power block |
| `gen_new_circuits.py` | add passives/straps by label | decoupling, straps, NOR |
| `gen_pcb_update.py` | headless "update from schematic": footprint swap/add, per-pad `SetNet`, rip tracks; verifies pad nets | both PCBs |
| `gen_pcb_import_route.py` | DSN/SES round-trip + zone fill | both PCBs |
| `gen_manufacturing.sh` | DRC + gerbers/drill/pos/BOM/SVG via `kicad-cli` | both boards |

Start each new board by copying the relevant script, repointing its paths, and
running its **Verify** step before trusting the output.
