"""Additional descriptive findings from the paired six-day collar recordings."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from cattrack.compare import score_rest


def main():
    out = Path("analysis")
    previous = json.loads((out / "comparison.json").read_text())
    idx = pd.date_range(previous["analysis_start"], previous["analysis_end_exclusive"],
                        freq="5s", inclusive="left")
    cats = {}
    for name in ["Peach", "Toast"]:
        ep = pd.read_pickle(out / f"{name.lower()}_epochs.pkl")
        ep["rest"], _ = score_rest(ep)
        cats[name] = ep.reindex(idx)
    valid = (cats["Peach"].valid & cats["Toast"].valid).to_numpy()
    days = idx.normalize().unique()
    result = {"analysis_start": str(idx[0]), "analysis_end_exclusive": previous["analysis_end_exclusive"],
              "movement": {}, "windows": {}, "daily": {}, "activity_lag": []}
    for name, ep in cats.items():
        q = ep.loc[valid, "rms_mg"]
        result["movement"][name] = [{"threshold_mg": threshold,
            "movement_hours_per_24h": float((q >= threshold).mean()*24),
            "mean_rms_during_movement_mg": float(q[q >= threshold].mean())} for threshold in [15, 20, 30, 40]]
        result["daily"][name] = {str(k.date()): float(v) for k, v in ep.rms_mg.where(valid).resample("D").mean().items()}
    for a, b in [(0, 4), (4, 7), (7, 9), (11, 17), (18, 22), (22, 24)]:
        window = (idx.hour >= a) & (idx.hour < b)
        row = {}
        for name, ep in cats.items():
            m = window & valid
            row[name] = {"mean_rms_mg": float(ep.loc[m, "rms_mg"].mean()),
                "rest_fraction": float(ep.loc[m, "rest"].mean()),
                "mean_rms_by_day": {str(d.date()): float(ep.loc[m & (idx.normalize() == d), "rms_mg"].mean()) for d in days}}
        result["windows"][f"{a:02d}:00–{b:02d}:00"] = row

    # Positive lag = Toast's activity occurs after Peach's. Correlation measures
    # timing only; do not treat a selected maximum as evidence of causation.
    for minutes in [5, 15, 30]:
        series = {name: ep.rms_mg.where(valid).resample(f"{minutes}min").mean() for name,ep in cats.items()}
        p, t = series["Peach"], series["Toast"]
        for lag in range(-60, 61, minutes):
            result["activity_lag"].append({"bin_minutes": minutes, "toast_delay_minutes": lag,
                                            "correlation": float(p.corr(t.shift(-lag//minutes)))})

    # Different-date baseline keeps clock time fixed; same-day matching retains
    # both the shared daily routine and additional alignment particular to a day.
    daytime = (idx.hour >= 6) & (idx.hour < 22)
    rest_days = {}
    for name, ep in cats.items():
        rest_days[name] = [ep.loc[daytime & (idx.normalize() == d), "rest"].to_numpy(dtype=bool) for d in days]
    valid_days = [valid[daytime & (idx.normalize() == d)] for d in days]
    overlaps = []
    for i in range(len(days)):
        for j in range(len(days)):
            m = valid_days[i] & valid_days[j]
            both = rest_days["Peach"][i] & rest_days["Toast"][j]
            overlaps.append({"peach_date": str(days[i].date()), "toast_date": str(days[j].date()),
                             "same_day": i == j, "overlap_hours_per_16h": float(both[m].mean()*16)})
    same = float(np.mean([x["overlap_hours_per_16h"] for x in overlaps if x["same_day"]]))
    different = float(np.mean([x["overlap_hours_per_16h"] for x in overlaps if not x["same_day"]]))
    result["rest_alignment"] = {"mean_same_day_overlap_hours": same,
        "mean_different_date_overlap_hours": different, "additional_same_day_minutes": (same-different)*60,
        "date_pairs": overlaps}

    target = "2026-09-04"
    p_daily = result["daily"]["Peach"]
    other_day_mean = np.mean([v for k,v in p_daily.items() if k != target])
    evening = result["windows"]["18:00–22:00"]["Peach"]["mean_rms_by_day"]
    other_evening_mean = np.mean([v for k,v in evening.items() if k != target])
    result["peach_quieter_date"] = {"date": target,
        "daily_percent_below_other_days": float((1-p_daily[target]/other_day_mean)*100),
        "evening_percent_below_other_days": float((1-evening[target]/other_evening_mean)*100),
        "selected_after_inspecting_data": True}
    (out / "additional_insights.json").write_text(json.dumps(result, indent=2)+"\n")

    report = f"""# Additional observations: Peach and Toast

These describe the same six paired calendar days, August 31–September 5, 2026. Clock times are assumed device-local Pacific time. They are descriptive observations from one week, not established long-term traits.

**Peach is relatively busier early; Toast is busier late.** From 4–7 a.m., Peach's average movement is 50.6 mg versus Toast's 39.0 mg: about 30% higher. From 10 p.m.–midnight, Toast's is 68.1 mg versus Peach's 44.1 mg: about 55% higher. Both comparisons hold on five of the six days. At 7–9 a.m., their movement is nearly equal. These are movement tendencies, not measured wake-up or sleep-onset times.

**Toast's extra activity includes substantially more time moving.** Using the shared 20 mg cutoff, Toast averages 7.9 hours/day above the cutoff, versus Peach's 6.5 hours—about 84 additional minutes. During those intervals Toast's average movement intensity is only about 7% higher (181.9 versus 169.7 mg). Across cutoffs of 15–40 mg, the extra movement time remains approximately 76–86 minutes/day. Time is summed over five-second intervals and does not mean continuous exercise; collar/head movement and grooming can contribute.

**Their quietest overnight stretch is midnight–4 a.m.** About 90% of Peach's and 94% of Toast's time qualifies as sustained quiet rest then. Both are substantially more active before and after that window. Quiet wakefulness can also qualify; bout-length differences do not robustly identify a less-fragmented sleeper.

**September 4 was unusually quiet for Peach.** Peach's daily movement was {result['peach_quieter_date']['daily_percent_below_other_days']:.0f}% below the other five-day average, especially from 6–10 p.m., when it was {result['peach_quieter_date']['evening_percent_below_other_days']:.0f}% lower. Peach's daily average returned to the other days' range on September 5. Toast's overall activity on September 4 was close to Toast's usual level in this recording. This was identified after examining the data and does not establish a cause or health problem.

**Their rest aligns beyond merely having similar clock-time routines.** Matching the same date gives {same:.2f} hours/day of overlapping daytime rest; matching each Peach day with the five different Toast dates, while keeping clock times the same, gives {different:.2f} hours. That is about {(same-different)*60:.0f} extra shared minutes on matching dates. Shared household events could contribute, but these data cannot identify what produces the alignment or show that they are sleeping in the same location.

**There is no reliable activity leader.** Across 5-, 15-, and 30-minute summaries, movement correlation is highest with zero delay. The recordings therefore do not support a claim that one cat consistently starts moving first or causes the other to move. Device clock alignment was assumed rather than independently verified.

[Computed statistics](additional_insights.json) · [Reproducible script](../cattrack/insights.py)

Reproduce with `.venv/bin/python -m cattrack.insights` after generating the current epoch caches with `.venv/bin/python -m cattrack.compare`.
"""
    (out / "additional_insights.md").write_text(report)
    print(json.dumps({k:v for k,v in result.items() if k not in ["windows", "activity_lag", "rest_alignment"]}, indent=2))
    print("Rest alignment:",same,different,(same-different)*60)


if __name__ == "__main__":
    main()
