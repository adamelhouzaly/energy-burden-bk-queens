"""Download real energy-cost and income data for Brooklyn and Queens.

Source: U.S. Census Bureau, American Community Survey (ACS) 5-year estimates.
  - B19013: Median household income
  - B25132: Monthly electricity costs (households by cost bracket)
  - B25133: Monthly gas costs (households by cost bracket)

Two geographies are downloaded:
  - Census tracts in Kings County (Brooklyn) and Queens County  -> fine-grained map
  - PUMAs (Census "neighborhood" areas that line up with NYC community districts)

Usage:
    python src/fetch_data.py
    # optional, if the API asks for a key (free: https://api.census.gov/data/key_signup.html)
    CENSUS_API_KEY=your_key python src/fetch_data.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import requests

YEAR = 2022
BASE_URL = f"https://api.census.gov/data/{YEAR}/acs/acs5"
STATE_NY = "36"
COUNTIES = {"047": "Brooklyn", "081": "Queens"}

VARIABLES = (
    ["NAME", "B19013_001E"]
    + [f"B25132_{i:03d}E" for i in range(1, 10)]
    + [f"B25133_{i:03d}E" for i in range(1, 10)]
)

GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    f"{YEAR}_Gazetteer/{YEAR}_gaz_tracts_{STATE_NY}.txt"
)

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def _get(params: dict) -> pd.DataFrame:
    params = {"get": ",".join(VARIABLES), **params}
    key = os.environ.get("CENSUS_API_KEY")
    if key:
        params["key"] = key
    resp = requests.get(BASE_URL, params=params, timeout=60)
    if resp.status_code != 200 or not resp.text.strip().startswith("["):
        sys.exit(
            f"Census API request failed ({resp.status_code}). If it mentions a key, get a free one at "
            "https://api.census.gov/data/key_signup.html and rerun with CENSUS_API_KEY=... \n"
            f"Response start: {resp.text[:300]}"
        )
    rows = resp.json()
    return pd.DataFrame(rows[1:], columns=rows[0])


def fetch_tracts() -> pd.DataFrame:
    df = _get({"for": "tract:*", "in": f"state:{STATE_NY} county:{','.join(COUNTIES)}"})
    df["borough"] = df["county"].map(COUNTIES)
    df["GEOID"] = df["state"] + df["county"] + df["tract"]
    return df


def fetch_pumas() -> pd.DataFrame:
    df = _get({"for": "public use microdata area:*", "in": f"state:{STATE_NY}"})
    df["borough"] = df["NAME"].str.extract(r"NYC-(Brooklyn|Queens)", expand=False)
    return df[df["borough"].notna()].reset_index(drop=True)


def fetch_tract_centroids() -> pd.DataFrame | None:
    """Tract latitude/longitude for the dashboard map (optional)."""
    try:
        resp = requests.get(GAZETTEER_URL, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  (skipping map coordinates: {exc})")
        return None
    from io import StringIO

    gaz = pd.read_csv(StringIO(resp.text), sep="\t", dtype={"GEOID": str})
    gaz.columns = [c.strip() for c in gaz.columns]
    return gaz[["GEOID", "INTPTLAT", "INTPTLONG"]].rename(
        columns={"INTPTLAT": "lat", "INTPTLONG": "lon"}
    )


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading tract data for Brooklyn and Queens...")
    tracts = fetch_tracts()
    tracts.to_csv(RAW_DIR / "acs_tracts.csv", index=False)
    print(f"  saved {len(tracts)} tracts")

    print("Downloading neighborhood (PUMA) data...")
    pumas = fetch_pumas()
    pumas.to_csv(RAW_DIR / "acs_pumas.csv", index=False)
    print(f"  saved {len(pumas)} neighborhoods")

    print("Downloading tract coordinates for the map...")
    cents = fetch_tract_centroids()
    if cents is not None:
        cents.to_csv(RAW_DIR / "tract_centroids.csv", index=False)
        print(f"  saved {len(cents)} coordinates")

    print("Done. Next: python src/analysis.py")


if __name__ == "__main__":
    main()
