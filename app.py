"""Streamlit front end: streamlit run app.py"""
import pandas as pd
import streamlit as st

from ev_sizing import CELLS, Vehicle, idc_trace, size_pack

st.title("EV Two-Wheeler Pack Sizing")
target = st.slider("Target range (km)", 60, 220, 120, 10)
payload = st.slider("Payload (kg)", 60, 160, 80, 10)
temp = st.slider("Ambient temperature (°C)", 0, 45, 25, 5)
top = st.slider("Top speed cap (km/h)", 30, 90, 90, 5)
up = st.file_uploader("Speed trace CSV (time_s, speed_kmph)", type="csv")

trace = pd.read_csv(up)["speed_kmph"].to_numpy() if up else idc_trace()
veh = Vehicle(payload_kg=payload)
res = pd.DataFrame([size_pack(c, target, trace, veh, temp, top) for c in CELLS])
st.dataframe(res, hide_index=True)
st.bar_chart(res.set_index("cell")[["cost_inr"]])
st.bar_chart(res.set_index("cell")[["pack_kg"]])
