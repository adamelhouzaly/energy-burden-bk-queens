import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import analysis  # noqa: E402


def make_row(income, elec_bins, gas_bins, elec_uncharged=0, gas_uncharged=0, **extra):
    """Build one raw ACS-style row. elec_bins/gas_bins are household counts per bracket (6 each)."""
    row = {"NAME": extra.pop("NAME", "Tract 1"), "B19013_001E": income}
    total_e = sum(elec_bins) + elec_uncharged
    row.update({"B25132_001E": total_e, "B25132_002E": elec_uncharged, "B25132_003E": sum(elec_bins)})
    row.update({f"B25132_{i:03d}E": n for i, n in zip(range(4, 10), elec_bins)})
    total_g = sum(gas_bins) + gas_uncharged
    row.update({"B25133_001E": total_g, "B25133_002E": gas_uncharged, "B25133_003E": sum(gas_bins)})
    row.update({f"B25133_{i:03d}E": n for i, n in zip(range(4, 10), gas_bins)})
    row.update(extra)
    return row


def test_average_cost_uses_midpoints():
    # 100 households all in $100-149 electricity -> $125; all in $50-74 gas -> $62.50
    df = pd.DataFrame([make_row(45000, [0, 0, 100, 0, 0, 0], [0, 0, 100, 0, 0, 0])])
    out = analysis.compute_metrics(df)
    assert out.loc[0, "elec_monthly"] == pytest.approx(125.0)
    assert out.loc[0, "gas_monthly"] == pytest.approx(62.5)
    assert out.loc[0, "energy_annual"] == pytest.approx(12 * 187.5)
    assert out.loc[0, "burden_pct"] == pytest.approx(2250 / 45000 * 100)  # 5.0%
    assert not out.loc[0, "high_burden"]


def test_uncharged_households_count_as_zero():
    # Half the households have utilities included in rent -> average halves
    df = pd.DataFrame([make_row(30000, [0, 0, 50, 0, 0, 0], [0, 0, 0, 0, 0, 0], elec_uncharged=50,
                                gas_uncharged=100)])
    out = analysis.compute_metrics(df)
    assert out.loc[0, "elec_monthly"] == pytest.approx(62.5)
    assert out.loc[0, "gas_monthly"] == pytest.approx(0.0)


def test_high_burden_flag_at_threshold():
    # $300/mo elec + $180/mo gas = $5,760/yr; income $96,000 -> exactly 6%
    df = pd.DataFrame([make_row(96000, [0, 0, 0, 0, 0, 10], [0, 0, 0, 0, 0, 10])])
    out = analysis.compute_metrics(df)
    assert out.loc[0, "burden_pct"] == pytest.approx(6.0)
    assert out.loc[0, "high_burden"]


def test_missing_income_code_becomes_nan():
    df = pd.DataFrame([make_row(-666666666, [10, 0, 0, 0, 0, 0], [10, 0, 0, 0, 0, 0])])
    out = analysis.compute_metrics(df)
    assert np.isnan(out.loc[0, "median_income"])
    assert np.isnan(out.loc[0, "burden_pct"])


def test_zero_households_does_not_divide_by_zero():
    df = pd.DataFrame([make_row(50000, [0] * 6, [0] * 6)])
    out = analysis.compute_metrics(df)
    assert np.isnan(out.loc[0, "elec_monthly"])


@pytest.mark.parametrize("name,expected", [
    ("NYC-Brooklyn Community District 5--East New York & Starrett City PUMA; New York",
     "East New York & Starrett City (BK CD 5)"),
    ("NYC-Queens Community District 12--Jamaica, Hollis & St. Albans PUMA; New York",
     "Jamaica, Hollis & St. Albans (QN CD 12)"),
    ("NYC-Brooklyn Community Districts 1 & 4--Some Area PUMA; New York", "Some Area (BK CD 1 & 4)"),
    ("Something Unexpected; New York", "Something Unexpected"),
])
def test_short_name(name, expected):
    assert analysis.short_name(name) == expected


def test_weighted_burden_weights_by_households():
    df = pd.DataFrame({"burden_pct": [2.0, 8.0], "households": [300, 100]})
    assert analysis.weighted_burden(df) == pytest.approx(3.5)
