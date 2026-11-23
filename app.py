"""Streamlit dashboard: Energy Burden in Brooklyn & Queens.

Run:  streamlit run app.py   (after src/fetch_data.py and src/analysis.py)
"""

from pathlib import Path

import pandas as pd
import streamlit as st

DATA = Path(__file__).parent / "data" / "processed"

st.set_page_config(page_title="Energy Burden: Brooklyn & Queens", layout="wide")


@st.cache_data
def load():
    tracts = pd.read_csv(DATA / "tracts_burden.csv", dtype={"GEOID": str})
    pumas = pd.read_csv(DATA / "neighborhoods_burden.csv")
    return tracts, pumas


if not (DATA / "tracts_burden.csv").exists():
    st.error("No processed data yet. Run `python src/fetch_data.py` then `python src/analysis.py`.")
    st.stop()

tracts, pumas = load()

st.title("Energy Burden in Brooklyn & Queens")
st.caption(
    "Estimated share of household income spent on electricity and gas, from U.S. Census ACS 2018-2022. "
    "Estimates use bracket midpoints and median income. See README for limitations."
)

with st.sidebar:
    st.header("Filters")
    boroughs = st.multiselect("Borough", ["Brooklyn", "Queens"], default=["Brooklyn", "Queens"])
    threshold = st.slider("High-burden threshold (% of income)", 3.0, 10.0, 6.0, 0.5)

t = tracts[tracts["borough"].isin(boroughs)].dropna(subset=["burden_pct"])
p = pumas[pumas["borough"].isin(boroughs)].dropna(subset=["burden_pct"])
high = t[t["burden_pct"] >= threshold]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Census tracts", f"{len(t):,}")
c2.metric("High-burden tracts", f"{len(high):,}", f"{len(high) / max(len(t), 1):.0%} of tracts", delta_color="off")
c3.metric("Households in high-burden tracts", f"{int(high['households'].sum()):,}")
c4.metric("Median tract burden", f"{t['burden_pct'].median():.1f}%")

left, right = st.columns(2)
with left:
    st.subheader("Neighborhoods ranked by energy burden")
    top = p.sort_values("burden_pct", ascending=False).head(15)
    st.bar_chart(top.set_index("neighborhood")["burden_pct"], horizontal=True)
with right:
    st.subheader("Income vs. energy burden (each dot = a tract)")
    st.scatter_chart(t, x="median_income", y="burden_pct", color="borough")

if {"lat", "lon"}.issubset(t.columns) and high["lat"].notna().any():
    st.subheader(f"Where the high-burden tracts are (≥ {threshold:.1f}%)")
    st.map(high.dropna(subset=["lat", "lon"]), latitude="lat", longitude="lon", size=60)

st.subheader("Neighborhood table")
table = p[["neighborhood", "borough", "burden_pct", "median_income", "energy_annual", "households"]].rename(
    columns={
        "neighborhood": "Neighborhood", "borough": "Borough", "burden_pct": "Burden %",
        "median_income": "Median income", "energy_annual": "Est. annual energy cost", "households": "Households",
    }
).sort_values("Burden %", ascending=False)
st.dataframe(
    table.style.format({"Burden %": "{:.1f}%", "Median income": "${:,.0f}",
                        "Est. annual energy cost": "${:,.0f}", "Households": "{:,.0f}"}),
    use_container_width=True, hide_index=True,
)
st.download_button("Download neighborhood data (CSV)", table.to_csv(index=False), "energy_burden_neighborhoods.csv")
