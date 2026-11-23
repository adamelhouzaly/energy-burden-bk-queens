"""Estimate household energy burden for Brooklyn and Queens and write findings.

Energy burden = share of household income spent on home energy (electricity + gas).
New York's energy affordability policy uses 6% of income as the affordability
threshold, so areas at or above 6% are flagged as high-burden.

Method (estimate, see README "Limitations"):
  avg monthly cost = sum(households in bracket x bracket midpoint) / all households
  annual energy cost = 12 x (avg electricity + avg gas)
  burden % = annual energy cost / median household income x 100

Usage:
    python src/analysis.py
"""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUT_DIR = ROOT / "outputs"

HIGH_BURDEN_PCT = 6.0

# Bracket midpoints in dollars/month. Top brackets are open-ended; we use a
# conservative value 20-33% above the lower bound.
ELEC_MIDPOINTS = {
    "B25132_004E": 25.0,   # < $50
    "B25132_005E": 75.0,   # $50-99
    "B25132_006E": 125.0,  # $100-149
    "B25132_007E": 175.0,  # $150-199
    "B25132_008E": 225.0,  # $200-249
    "B25132_009E": 300.0,  # $250+
}
GAS_MIDPOINTS = {
    "B25133_004E": 12.5,   # < $25
    "B25133_005E": 37.5,   # $25-49
    "B25133_006E": 62.5,   # $50-74
    "B25133_007E": 87.5,   # $75-99
    "B25133_008E": 125.0,  # $100-149
    "B25133_009E": 180.0,  # $150+
}


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Make estimate columns numeric; Census uses large negative codes for missing."""
    df = df.copy()
    for col in [c for c in df.columns if re.fullmatch(r"B\d{5}_\d{3}E", c)]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] < 0, col] = np.nan
    return df


def avg_monthly_cost(df: pd.DataFrame, midpoints: dict[str, float], total_col: str) -> pd.Series:
    """Average monthly cost per household (households not billed count as $0)."""
    spend = sum(df[col].fillna(0) * mid for col, mid in midpoints.items())
    total = df[total_col].replace(0, np.nan)
    return spend / total


def compute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    df = clean(df)
    df["households"] = df["B25132_001E"]
    df["median_income"] = df["B19013_001E"]
    df["elec_monthly"] = avg_monthly_cost(df, ELEC_MIDPOINTS, "B25132_001E")
    df["gas_monthly"] = avg_monthly_cost(df, GAS_MIDPOINTS, "B25133_001E")
    df["energy_annual"] = 12 * (df["elec_monthly"] + df["gas_monthly"])
    df["burden_pct"] = df["energy_annual"] / df["median_income"] * 100
    df["high_burden"] = df["burden_pct"] >= HIGH_BURDEN_PCT
    return df


def short_name(puma_name: str) -> str:
    """'NYC-Brooklyn Community District 5--East New York & Starrett City PUMA; New York'
    -> 'East New York & Starrett City (BK CD 5)'"""
    m = re.search(r"NYC-(Brooklyn|Queens) Community Districts? ([\d &]+?)--(.+?) PUMA", puma_name)
    if not m:
        return puma_name.split(";")[0]
    boro = "BK" if m.group(1) == "Brooklyn" else "QN"
    return f"{m.group(3).strip()} ({boro} CD {m.group(2).strip()})"


def weighted_burden(df: pd.DataFrame) -> float:
    """Household-weighted average burden."""
    d = df.dropna(subset=["burden_pct", "households"])
    return float(np.average(d["burden_pct"], weights=d["households"])) if len(d) else float("nan")


def summarize(tracts: pd.DataFrame, pumas: pd.DataFrame) -> dict:
    valid = tracts.dropna(subset=["burden_pct"])
    top = pumas.dropna(subset=["burden_pct"]).sort_values("burden_pct", ascending=False)
    by_boro = {b: weighted_burden(g) for b, g in valid.groupby("borough")}
    corr = valid["median_income"].corr(valid["burden_pct"], method="spearman")
    hb = valid[valid["high_burden"]]
    return {
        "n_tracts": int(len(valid)),
        "n_tracts_total": int(len(tracts)),
        "n_neighborhoods": int(len(top)),
        "n_high_burden_tracts": int(len(hb)),
        "high_burden_households": int(hb["households"].sum()),
        "by_borough": by_boro,
        "income_burden_spearman": float(corr),
        "top_neighborhoods": top[["neighborhood", "borough", "burden_pct", "median_income", "energy_annual"]]
        .head(10)
        .to_dict("records"),
        "bottom_neighborhood": top.iloc[-1][["neighborhood", "burden_pct"]].to_dict() if len(top) else {},
    }


def make_charts(tracts: pd.DataFrame, pumas: pd.DataFrame, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)

    top = pumas.dropna(subset=["burden_pct"]).nlargest(10, "burden_pct").iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    colors = ["#c0392b" if v >= HIGH_BURDEN_PCT else "#2e86c1" for v in top["burden_pct"]]
    ax.barh(top["neighborhood"], top["burden_pct"], color=colors)
    ax.axvline(HIGH_BURDEN_PCT, color="#555", ls="--", lw=1)
    ax.text(HIGH_BURDEN_PCT, len(top) - 0.45, " 6% affordability line", fontsize=9, color="#555", va="bottom")
    ax.set_xlabel("Estimated energy burden (% of median household income)")
    ax.set_title("Highest energy-burden neighborhoods, Brooklyn & Queens")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "top_neighborhoods.png", dpi=200)
    plt.close(fig)

    v = tracts.dropna(subset=["burden_pct", "median_income"])
    fig, ax = plt.subplots(figsize=(8, 5.5))
    for boro, color in [("Brooklyn", "#2e86c1"), ("Queens", "#e67e22")]:
        g = v[v["borough"] == boro]
        ax.scatter(g["median_income"] / 1000, g["burden_pct"], s=10, alpha=0.5, label=boro, color=color)
    ax.axhline(HIGH_BURDEN_PCT, color="#555", ls="--", lw=1)
    ax.set_xlabel("Median household income ($ thousands)")
    ax.set_ylabel("Estimated energy burden (%)")
    ax.set_title("Lower-income tracts carry a heavier energy burden")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "income_vs_burden.png", dpi=200)
    plt.close(fig)


def write_findings(s: dict, out: Path) -> None:
    lines = [
        "# Findings: Energy Burden in Brooklyn & Queens",
        "",
        f"_Data: U.S. Census ACS 5-year estimates (2018-2022). High burden = {HIGH_BURDEN_PCT:.0f}%+ of income._",
        "",
        f"- Analyzed **{s['n_tracts']:,}** census tracts with usable data "
        f"(of {s['n_tracts_total']:,}) and **{s['n_neighborhoods']}** neighborhoods.",
        f"- **{s['n_high_burden_tracts']:,}** tracts (about **{s['high_burden_households']:,}** households) "
        f"are at or above the {HIGH_BURDEN_PCT:.0f}% affordability line.",
    ]
    for boro, val in s["by_borough"].items():
        lines.append(f"- {boro} household-weighted average burden: **{val:.1f}%**")
    lines.append(
        f"- Income vs. burden rank correlation (Spearman): **{s['income_burden_spearman']:.2f}** "
        "(negative = lower-income areas spend a larger share on energy)."
    )
    lines += ["", "## Top 10 highest-burden neighborhoods", "",
              "| # | Neighborhood | Borough | Burden | Median income | Est. annual energy cost |",
              "|---|---|---|---|---|---|"]
    for i, r in enumerate(s["top_neighborhoods"], 1):
        lines.append(
            f"| {i} | {r['neighborhood']} | {r['borough']} | {r['burden_pct']:.1f}% | "
            f"${r['median_income']:,.0f} | ${r['energy_annual']:,.0f} |"
        )
    if s["bottom_neighborhood"]:
        b = s["bottom_neighborhood"]
        lines += ["", f"Lowest-burden neighborhood: {b['neighborhood']} ({b['burden_pct']:.1f}%)."]
    lines += [
        "",
        "## Recommendations",
        "",
        "1. Prioritize bill-assistance outreach (e.g., HEAP, utility discount programs) in the top-burden "
        "neighborhoods above.",
        "2. Pair outreach with energy-efficiency and weatherization referrals where burden is high but "
        "incomes are just above program cutoffs.",
        "3. Re-run this analysis each year when new ACS data is released to track progress.",
    ]
    (out / "findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(raw_dir: Path = RAW_DIR, processed_dir: Path = PROCESSED_DIR, output_dir: Path = OUTPUT_DIR) -> dict:
    tracts = compute_metrics(pd.read_csv(raw_dir / "acs_tracts.csv", dtype={"GEOID": str, "county": str}))
    pumas = compute_metrics(pd.read_csv(raw_dir / "acs_pumas.csv"))
    pumas["neighborhood"] = pumas["NAME"].map(short_name)

    cent_path = raw_dir / "tract_centroids.csv"
    if cent_path.exists():
        tracts = tracts.merge(pd.read_csv(cent_path, dtype={"GEOID": str}), on="GEOID", how="left")

    processed_dir.mkdir(parents=True, exist_ok=True)
    tracts.to_csv(processed_dir / "tracts_burden.csv", index=False)
    pumas.to_csv(processed_dir / "neighborhoods_burden.csv", index=False)

    summary = summarize(tracts, pumas)
    make_charts(tracts, pumas, output_dir)
    write_findings(summary, output_dir)
    return summary


if __name__ == "__main__":
    s = run()
    print((OUTPUT_DIR / "findings.md").read_text(encoding="utf-8"))
    print("Charts saved to outputs/. Next: python src/make_slides.py  |  streamlit run app.py")
