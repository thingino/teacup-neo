# Teacup Neo

A universal development platform for **any Ingenic SoC** — T10, T20, T21, T23, T30,
T31, T32, T33, T40, T41, and the A1 NVR processor — regardless of package
(QFN88 / QFN96 / BGA232 / BGA356 / BGA381).

Two boards:
- a **carrier** — the universal baseboard: adjustable SoC power, all peripherals,
  full pin breakout, and an on-board **ESP32-S3 management controller** so an agent
  (an LLM, CI, or a human) can drive the target wired *or* wireless — flash, reset,
  boot-select, console, and voltage-margin it hands-off;
- a small per-SoC **interposer** — the SoC + its package fanout + clock + decoupling
  + straps (+ optional local power / boot NOR), presented on a **DDR4 card-edge**
  (UDIMM-288 desktop) socket.

Swap the interposer, keep the carrier — the package stops mattering.

## The design

**Full spec: [`docs/UNIVERSAL.md`](docs/UNIVERSAL.md).** It covers the connector
choice, the power architecture (adjustable VCORE/VDDR with digipot voltage control +
margining), the verified T10→A1 rail table, clock/flash/boot, the ESP32-S3 BMC and
autonomous flash loop, full sensor/camera support (MIPI + DVP across the whole
family), full **A1** support (dual SATA 3.0 + dual GbE), dedicated camera-SoC
peripherals (audio, PWM/IR-cut/IR-LED, JTAG), carrier test points, and the
pin-breakout budget.

**Status: design / specification.** No open or deferred design questions remain; the
next step is the geography-first pin assignment against a carrier floorplan.

## `old/` — the T41 precursor

[`old/`](old/) holds the original single-SoC **T41 (QFN96)** board that proved the
approach and the headless-KiCad pipeline (kicad-cli + pcbnew + FreeRouting). It's
netlist-verified and ~83% auto-routed — details in [`old/README.md`](old/README.md).

License: GPL-3.0 (inherited from the upstream [Teacup](https://github.com/CapnRon/Teacup)).
