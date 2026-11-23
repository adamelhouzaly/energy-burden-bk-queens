"""Build a short PowerPoint summary of the findings (outputs/energy_burden_summary.pptx).

Usage:
    python src/make_slides.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis import HIGH_BURDEN_PCT, OUTPUT_DIR, PROCESSED_DIR, summarize  # noqa: E402

NAVY = RGBColor(0x1B, 0x2A, 0x49)
GRAY = RGBColor(0x55, 0x55, 0x55)


def _title(slide, text, sub=None):
    tb = slide.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(12), Inches(1))
    p = tb.text_frame.paragraphs[0]
    p.text, p.font.size, p.font.bold, p.font.color.rgb = text, Pt(30), True, NAVY
    if sub:
        p2 = tb.text_frame.add_paragraph()
        p2.text, p2.font.size, p2.font.color.rgb = sub, Pt(14), GRAY


def _bullets(slide, items, left=0.6, top=1.6, width=12, size=20):
    tf = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(5)).text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text, p.font.size = f"• {item}", Pt(size)
        p.space_after = Pt(12)


def build(processed_dir: Path = PROCESSED_DIR, output_dir: Path = OUTPUT_DIR) -> Path:
    tracts = pd.read_csv(processed_dir / "tracts_burden.csv")
    pumas = pd.read_csv(processed_dir / "neighborhoods_burden.csv")
    s = summarize(tracts, pumas)

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]

    sl = prs.slides.add_slide(blank)
    _title(sl, "Energy Burden in Brooklyn & Queens",
           "Where are households spending the largest share of income on energy?")
    _bullets(sl, [
        "Data: U.S. Census American Community Survey, 2018-2022 (electricity & gas costs, income)",
        f"Energy burden = annual home energy cost / median household income; {HIGH_BURDEN_PCT:.0f}%+ = high burden",
        f"Scope: {s['n_tracts']:,} census tracts and {s['n_neighborhoods']} neighborhoods",
    ], top=2.2)

    sl = prs.slides.add_slide(blank)
    _title(sl, "Key findings")
    items = [
        f"{s['n_high_burden_tracts']:,} tracts (~{s['high_burden_households']:,} households) are at or above "
        f"the {HIGH_BURDEN_PCT:.0f}% affordability line",
    ]
    items += [f"{b}: {v:.1f}% average burden (household-weighted)" for b, v in s["by_borough"].items()]
    items.append(f"Income vs. burden correlation: {s['income_burden_spearman']:.2f} "
                 "(lower-income areas spend a larger share of income on energy)")
    _bullets(sl, items)

    sl = prs.slides.add_slide(blank)
    _title(sl, "Highest-burden neighborhoods")
    sl.shapes.add_picture(str(output_dir / "top_neighborhoods.png"), Inches(1.5), Inches(1.4), height=Inches(5.8))

    sl = prs.slides.add_slide(blank)
    _title(sl, "Income and energy burden")
    sl.shapes.add_picture(str(output_dir / "income_vs_burden.png"), Inches(2), Inches(1.4), height=Inches(5.8))

    sl = prs.slides.add_slide(blank)
    _title(sl, "Recommendations")
    top3 = ", ".join(r["neighborhood"].split(" (")[0] for r in s["top_neighborhoods"][:3])
    _bullets(sl, [
        f"Focus bill-assistance outreach first in: {top3}",
        "Pair outreach with weatherization / efficiency referrals for households just above program cutoffs",
        "Partner with local community organizations in high-burden areas to reach households directly",
        "Refresh the analysis yearly with new Census data to measure progress",
    ])

    path = output_dir / "energy_burden_summary.pptx"
    prs.save(path)
    return path


if __name__ == "__main__":
    print(f"Saved {build()}")
