"""EV two-wheeler battery pack and powertrain sizing.

Runs a scooter through a speed trace with a longitudinal vehicle model, gets Wh/km, peak
power and pack current, then sizes series-parallel packs from different cell formats for a
target range and compares range, pack mass, cost and peak C-rate.

Usage:
    python ev_sizing.py                      # IDC-shaped trace, 120 km target
    python ev_sizing.py --trace ride.csv     # your own trace: columns time_s, speed_kmph
"""
import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd

G, RHO = 9.81, 1.2


@dataclass
class Vehicle:
    kerb_kg: float = 95.0          # scooter without battery
    payload_kg: float = 80.0       # rider
    crr: float = 0.012             # rolling resistance
    cda: float = 0.60              # drag coefficient x frontal area, m^2
    rot_factor: float = 1.05       # rotating inertia
    eta_drive: float = 0.85        # motor x inverter x transmission
    eta_regen: float = 0.60        # share of braking energy recovered
    aux_w: float = 40.0            # lights, cluster, BMS
    system_v: float = 72.0         # target pack nominal voltage


# Cell assumptions (edit to match a datasheet). Cost is cell-level INR per kWh.
CELLS = {
    "21700_NMC":     dict(v=3.6, ah=5.0,  kg=0.070, c_max=3.0, inr_kwh=11000, soc_win=0.90),
    "4680_NMC":      dict(v=3.6, ah=23.0, kg=0.355, c_max=2.0, inr_kwh=10000, soc_win=0.90),
    "LFP_prismatic": dict(v=3.2, ah=50.0, kg=1.000, c_max=1.0, inr_kwh=8000,  soc_win=0.95),
}
PACK_MASS_FACTOR, PACK_COST_FACTOR = 1.35, 1.30   # cell-to-pack overheads
TEMP_DERATE = {"NMC": {0: 0.85, 25: 1.0, 45: 0.98}, "LFP": {0: 0.75, 25: 1.0, 45: 0.98}}


def idc_trace(repeats=6):
    """IDC-shaped 108 s cycle (idle, accelerate, cruise up to 42 km/h, decelerate).
    Built from the cycle's published summary (108 s, peak 42 km/h, mean ~22 km/h).
    Replace with the official AIS-137 table via --trace for certification-grade numbers."""
    pts = [(0, 0), (16, 0), (24, 14), (32, 14), (38, 0), (44, 0), (53, 25), (65, 25),
           (73, 0), (78, 0), (88, 42), (98, 42), (108, 0)]
    t = np.arange(0, 108)
    one = np.interp(t, *zip(*pts))
    return np.tile(one, repeats)


def drive(speed_kmph, veh, pack_kg, top_speed=None, dt=1.0):
    v = np.asarray(speed_kmph, float) / 3.6
    if top_speed:
        v = np.minimum(v, top_speed / 3.6)
    a = np.gradient(v, dt)
    m = veh.kerb_kg + veh.payload_kg + pack_kg
    f = m * veh.rot_factor * a + veh.crr * m * G + 0.5 * RHO * veh.cda * v ** 2
    p_wheel = f * v
    p_batt = np.where(p_wheel > 0, p_wheel / veh.eta_drive, p_wheel * veh.eta_regen) + veh.aux_w
    km = v.sum() * dt / 1000
    return {"wh_per_km": p_batt.sum() * dt / 3600 / km,
            "peak_kw": p_batt.max() / 1000,
            "peak_a": p_batt.max() / veh.system_v}


def size_pack(cell_name, target_km, trace, veh, temp_c=25, top_speed=None):
    c = CELLS[cell_name]
    chem = "LFP" if "LFP" in cell_name else "NMC"
    derate = np.interp(temp_c, list(TEMP_DERATE[chem]), list(TEMP_DERATE[chem].values()))
    s = round(veh.system_v / c["v"])
    pack_kg, p = 20.0, 1
    for _ in range(20):                      # pack mass changes consumption: iterate
        d = drive(trace, veh, pack_kg, top_speed)
        need_wh = d["wh_per_km"] * target_km
        cell_wh = c["v"] * c["ah"] * c["soc_win"] * derate
        p_energy = int(np.ceil(need_wh / (s * cell_wh)))
        p_current = int(np.ceil(d["peak_a"] / (c["ah"] * c["c_max"])))
        p = max(p_energy, p_current, 1)
        new_kg = s * p * c["kg"] * PACK_MASS_FACTOR
        if abs(new_kg - pack_kg) < 0.1:
            break
        pack_kg = new_kg
    kwh = s * p * c["v"] * c["ah"] / 1000
    return {"cell": cell_name, "config": f"{s}S{p}P", "kwh": round(kwh, 2),
            "range_km": round(kwh * 1000 * c["soc_win"] * derate / d["wh_per_km"], 1),
            "pack_kg": round(pack_kg, 1), "cost_inr": round(kwh * c["inr_kwh"] * PACK_COST_FACTOR),
            "wh_per_km": round(d["wh_per_km"], 1), "peak_kw": round(d["peak_kw"], 2),
            "peak_c_rate": round(d["peak_a"] / (p * c["ah"]), 2),
            "limited_by": "current" if p_current > p_energy else "energy"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", help="CSV with time_s, speed_kmph")
    ap.add_argument("--range", type=float, default=120)
    ap.add_argument("--payload", type=float, default=80)
    ap.add_argument("--temp", type=float, default=25)
    ap.add_argument("--top-speed", type=float, default=None)
    args = ap.parse_args()

    trace = pd.read_csv(args.trace)["speed_kmph"].to_numpy() if args.trace else idc_trace()
    veh = Vehicle(payload_kg=args.payload)
    rows = [size_pack(c, args.range, trace, veh, args.temp, args.top_speed) for c in CELLS]
    print(pd.DataFrame(rows).to_string(index=False))

    # Pareto sweep: range target vs pack cost and mass for each cell
    sweep = pd.DataFrame([size_pack(c, r, trace, veh, args.temp) for c in CELLS
                          for r in range(60, 221, 20)])
    sweep.to_csv("pareto.csv", index=False)
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    for c, g in sweep.groupby("cell"):
        ax[0].plot(g["range_km"], g["cost_inr"] / 1000, "o-", label=c)
        ax[1].plot(g["range_km"], g["pack_kg"], "o-", label=c)
    ax[0].set(xlabel="Range (km)", ylabel="Pack cost (INR '000)")
    ax[1].set(xlabel="Range (km)", ylabel="Pack mass (kg)")
    ax[0].legend()
    fig.tight_layout()
    fig.savefig("pareto.png", dpi=120)


if __name__ == "__main__":
    main()
