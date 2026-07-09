# Teacup T31ZX -> T41NQ/XQ pin mapping notes

Full table: `pinmap_t31_to_t41.csv`. T41 pin data: `t41nq_pins.csv` (verified
identical across T41NQ/XQ/LQ datasheets - one layout serves all three).

## What maps 1:1 (same GPIO name, new pin number)

- MIPI CSI 2-lane + clock (DATAN0/CLKN/DATAN1 even keep the same pin numbers 24/26/28)
- USB0PN/PP/AVD33: same pins 35/36/37
- SFC NOR: CE/DR/DT/CLK -> SFC0 on PA23-28
- MSC0 4-bit SD: PB00-05
- GMAC RMII header: all 10 signals, PB06-16
- UART1 console: PB23/24
- Sensor I2C (SMB0/PA12,13), MCLK (PA15), sensor GPIO (PA18) - 1.8V domain preserved
- PWM0/1 (PB17/18), PB25-31 misc bank
- BOOT_SEL0 (PC00), crystal, VCM, HPOUTL, SADC input

## Remaps (T31 GPIO absent on T41 QFN96)

J4 GPIO header (was T31 PA06-11/14/16/17 @ 1.8V) -> PC bank **@ 3.3V (VDDIO2)**:

| J4 pin | was | becomes | function preserved |
|--------|-----|---------|--------------------|
| J4.5   | PA06 | PC15 (pin 3)  | PWM0, EXCLK out |
| J4.6   | PA07 | PC16 (pin 4)  | PWM1, RTC32K |
| J4.7   | PA09 | PC17 (pin 5)  | PWM2, I2S_SDTO |
| J4.8   | PA08 | PC18 (pin 1)  | PWM3, I2S_SDTI |
| J4.9   | PA11 | PC14 (pin 91) | UART2_RXD |
| J4.10  | PA10 | PC13 (pin 92) | UART2_TXD |
| J4.11  | PA16 | PC19 (pin 89) | SMB1_SDA |
| J4.12  | PA14 | PC02 (pin 11) | (gains SSI0_CLK/MSC1_CLK) |
| J4.13  | PA17 | PC20 (pin 90) | SMB1_SCK |

UART0 4-wire (was PB19-22) -> PC08/09/11/12 (pins 95/94/2/96). Net-level
unchanged (USB-C SBU A8/B8 + J6). Domain: VDDIO2 must be 3.3V.

## Dropped vs T31

- **PPRST_ / reset button S2 / J9**: T41 QFN96 is POR-only. POR_CTL (pin 60,
  3.3V level) strap per vendor reference. S2/J9 deleted (or S2 repurposed to
  power-path EN for hard reset - TBD).
- External rails gone (internal on T41): PLL_VDDHV, MIPI_AVD08 (0.8V),
  USB_AVD18, DDRPLL_VCCD. Simplifies 1.8V/0.8V distribution.
- ADC_VREF + ADC_AVDD combine into single SADC_VREFP_AVDD.
- No UART boot, RTC, JTAG on QFN96.

## New on T41 (needs schematic work)

| Pin | Signal | Plan |
|-----|--------|------|
| 60  | POR_CTL | strap per vendor ref (3.3V domain) |
| 83  | DDR_ZQ  | 240R 1% to GND |
| 84  | RZQ     | 240R 1% to GND |
| 30  | MICNL   | diff mic negative: bias/AC-couple per vendor ref |
| 42  | SFC0_WP_IO2 | wire to NOR WP# -> quad-SPI boot option |
| 45  | SFC0_HOLD_IO3 | wire to NOR HOLD# -> quad-SPI boot option |
| 6,7,10,12,13 | MSC1/SSI0 (PC03-07) | spare; test pads or new header - TBD |

## Rails delta

| Rail | T31 board | T41 board |
|------|-----------|-----------|
| Core | 0.8V (already!) | 0.8V, more pins (8), size buck >= 1.5A |
| DDRVDD | 1.8V | **1.35V DDR3L** (1.8V stuffing option -> T41LQ) |
| DDR_VREF | 100k/100k off 1.8V | same divider off 1.35V (verify vendor) |
| VDDIO18 (1.8V) | VDDIO0 | pins 17,50 + osc domain |
| VDDIO1/2 (3.3V) | 3x pins | pins 40,65 + 9 (VDDIO2 selectable, keep 3.3V) |
| EFUSE | tied GND | tied GND (programming off) |
