# EV Two-Wheeler Battery Pack & Powertrain Sizing Tool

How big should a scooter's pack be, and which cell should it use? This tool answers that
from first principles: drive the vehicle through a speed trace, work out the energy and peak
current it needs, then size a series-parallel pack from each cell format and compare them.

## Model

- **Longitudinal dynamics**: F = m·a·k_rot + C_rr·m·g + ½·ρ·C_dA·v² (plus gradient if added),
  battery power = wheel power / drivetrain efficiency, partial regen on braking, auxiliary load.
- **Drive cycle**: an IDC-shaped 108 s cycle (repeated 6×), or any logged ride via `--trace`.
- **Pack sizing**: series count from the system voltage (72 V default); parallel count is the
  larger of what the range needs and what the peak current allows at the cell's max C-rate.
  Pack mass feeds back into consumption, so the loop iterates until mass settles.
- **Cells compared**: 21700 NMC, 4680 NMC, LFP prismatic. Specs, cost per kWh, usable SOC
  window and temperature derating are assumptions in `CELLS`; edit them from a datasheet.

## Run

```bash
pip install -r requirements.txt
python ev_sizing.py --range 120 --payload 80 --temp 25
python ev_sizing.py --trace my_ride.csv --top-speed 70
streamlit run app.py
```

Prints the pack for each cell (config, kWh, range, mass, cost, Wh/km, peak C-rate, whether
energy or current set the size) and writes `pareto.csv` / `pareto.png` (range vs cost and mass).

## Limits

No thermal model, no cell ageing, flat road unless a gradient is added. Cost numbers are
placeholders, not quotes.
