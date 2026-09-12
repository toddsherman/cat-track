"""Build the public Cat Track data from the existing paired analysis.

Run from the project root with ``.venv/bin/python -m cattrack.build_site_data``.
Only aggregated movement and rest labels are exported; raw accelerometer files,
device identifiers, recording headers, and local paths stay out of site/data.json.
"""

from pathlib import Path
import json

import numpy as np
import pandas as pd

from cattrack.compare import REST_THRESHOLD, STEP, period_stats, score_rest


CATS = ("Peach", "Toast")
ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text())


def rounded(value):
    """Six decimals preserve proportions and sub-minute run boundaries."""
    if isinstance(value, dict):
        return {key: rounded(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [rounded(item) for item in value]
    if isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            return None
        return round(float(value), 6)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def label(date):
    return f"{date.strftime('%b')} {date.day}"


def state_runs(states):
    """Lossless RLE of one full day's five-second labels, with clock-minute bounds."""
    assert len(states) == 24 * 3600 // STEP
    edges = np.r_[0, np.flatnonzero(states[1:] != states[:-1]) + 1, len(states)]
    segments = [[int(a) * STEP / 60,
                 int(b) * STEP / 60, int(states[a])]
                for a, b in zip(edges[:-1], edges[1:])]
    assert segments[0][0] == 0 and segments[-1][1] == 1440
    # Verify every exported interval reconstructs the original five-second labels.
    restored = np.concatenate([
        np.full(round((end - start) * 60 / STEP), state, dtype=int)
        for start, end, state in segments
    ])
    np.testing.assert_array_equal(restored, states)
    return segments


def build():
    analysis = ROOT / "analysis"
    comparison = read_json(analysis / "comparison.json")
    overlap = read_json(analysis / "daytime_overlap.json")
    insights = read_json(analysis / "additional_insights.json")
    assert REST_THRESHOLD == 20
    assert comparison["rest_rule"]["rms_threshold_mg"] == REST_THRESHOLD
    assert comparison["calendar_days"] == 6
    for source in (overlap, insights):
        assert source["analysis_start"] == comparison["analysis_start"]
        assert source["analysis_end_exclusive"] == comparison["analysis_end_exclusive"]

    idx = pd.date_range(comparison["analysis_start"],
                        comparison["analysis_end_exclusive"], freq="5s", inclusive="left")
    aligned = {}
    for name in CATS:
        recording = pd.read_pickle(analysis / f"{name.lower()}_epochs.pkl")
        # Score on each complete recording before cropping so bouts at midnight
        # retain their original context. Missing time is never scored as rest.
        recording["sleep_like_rest"], _ = score_rest(recording)
        aligned[name] = recording.reindex(idx)

    paired = np.logical_and.reduce([
        aligned[name].valid.fillna(False).to_numpy(dtype=bool) for name in CATS
    ])
    rest = {name: aligned[name].sleep_like_rest.fillna(False).to_numpy(dtype=bool)
            for name in CATS}
    both = rest["Peach"] & rest["Toast"]
    night = (idx.hour >= 22) | (idx.hour < 6)
    day = ~night
    dates = idx.normalize().unique()

    # The public summary is independently recalculated, then checked against the
    # prior report at full precision before the export is rounded.
    summary = {}
    for name in CATS:
        summary[name] = {}
        for period, mask, duration in [("all", paired, 24),
                                       ("night", paired & night, 8),
                                       ("day", paired & day, 16)]:
            stats = period_stats(aligned[name], mask)
            stats["rest_hours_per_period"] = stats["rest_fraction"] * duration
            stats["movement_hours_per_period"] = stats["movement_fraction"] * duration
            for key, expected in comparison["cats"][name][period].items():
                np.testing.assert_allclose(stats[key], expected, rtol=1e-10, atol=1e-10,
                                           err_msg=f"{name}/{period}/{key}")
            summary[name][period] = stats
    paired_hours = int(paired.sum()) * STEP / 3600
    excluded_seconds = int((~paired).sum()) * STEP
    np.testing.assert_allclose(paired_hours, comparison["paired_observed_hours"])
    assert excluded_seconds == comparison["paired_excluded_seconds"] == 80

    def mean(array, mask):
        return float(np.asarray(array)[mask].mean()) if mask.any() else None

    def row(mask):
        """Average movement in mg and rest proportions on the paired mask."""
        valid = mask & paired
        return {
            "peach": mean(aligned["Peach"].rms_mg, valid),
            "toast": mean(aligned["Toast"].rms_mg, valid),
            "peachRest": mean(rest["Peach"], valid),
            "toastRest": mean(rest["Toast"], valid),
            "bothRest": mean(both, valid),
            "coverage": float(paired[mask].mean()),
            "observedHours": int(valid.sum()) * STEP / 3600,
        }

    hourly = [{"hour": hour, **row(idx.hour == hour)} for hour in range(24)]
    for source in comparison["hourly"]:
        name, hour = source["cat"], source["hour"]
        np.testing.assert_allclose(hourly[hour][name.lower()], source["mean_rms_mg"])
        np.testing.assert_allclose(hourly[hour][name.lower() + "Rest"], source["rest_fraction"])

    days, daily, runs = [], [], []
    clock_minute = idx.hour * 60 + idx.minute
    for date in dates:
        date_mask = idx.normalize() == date
        daytime_mask = date_mask & day & paired
        date_text, date_label = str(date.date()), label(date)
        daily_stats = row(date_mask)
        # Daily rest values represent hours per 24h. Hourly/timeline rest values
        # remain proportions. Preserve the daytime overlap field for the existing
        # narrative and explicitly name the new overlap hours per full 24h.
        daily_stats["peachRest"] *= 24
        daily_stats["toastRest"] *= 24
        daily_stats["bothRestHours"] = mean(both, daytime_mask) * 16
        daily_stats["bothRestHours24h"] = daily_stats["bothRest"] * 24
        daily.append({"date": date_text, "label": date_label, **daily_stats})
        days.append({
            "date": date_text,
            "label": date_label,
            "hourly": [{"hour": hour, **row(date_mask & (idx.hour == hour))}
                       for hour in range(24)],
            "timeline": [{"minute": minute,
                          **row(date_mask & (clock_minute >= minute)
                                & (clock_minute < minute + 5))}
                         for minute in range(0, 1440, 5)],
        })
        mask = date_mask
        states = np.where(paired[mask],
                          rest["Peach"][mask].astype(int) + 2 * rest["Toast"][mask].astype(int),
                          4)
        valid_epochs = int(np.count_nonzero(states != 4))
        np.testing.assert_allclose(np.count_nonzero(states == 3) / valid_epochs * 24,
                                   daily_stats["bothRestHours24h"])
        assert np.count_nonzero(states == 4) == np.count_nonzero(~paired[mask])
        runs.append({"date": date_text, "label": date_label,
                     "segments": state_runs(states)})

    for source in comparison["daily"]:
        if source["period"] == "all":
            export = next(item for item in daily if item["date"] == source["date"])
            key = source["cat"].lower()
            np.testing.assert_allclose(export[key], source["mean_rms_mg"])
            np.testing.assert_allclose(export[key + "Rest"], source["rest_fraction"] * 24)
    for source in overlap["daily"]:
        export = next(item for item in daily if item["date"] == source["date"])
        np.testing.assert_allclose(export["bothRestHours"], source["both_rest_hours_per_16h"])
    np.testing.assert_allclose(mean(both, paired & day) * 16,
                               overlap["state_hours_per_16h"]["Both resting"])

    metadata = comparison["metadata"]
    samples = {name: metadata[name]["samples"] for name in CATS}
    paired_samples = {name: int(aligned[name].loc[paired, "n"].sum()) for name in CATS}
    result = {
        "schemaVersion": 2,
        "summary": summary,
        "coverage": {
            "start": str(dates[0].date()),
            "end": str(dates[-1].date()),
            "endExclusive": str((dates[-1] + pd.Timedelta(days=1)).date()),
            "days": len(dates),
            "pairedHours": paired_hours,
            "expectedHours": len(dates) * 24,
            "excludedSeconds": excluded_seconds,
            "samples": sum(samples.values()),
            "samplesByCat": samples,
            "pairedSamples": sum(paired_samples.values()),
            "pairedSamplesByCat": paired_samples,
            "sampleScope": "samples counts both complete raw recordings; pairedSamples counts only retained paired five-second intervals in the six-day analysis.",
            "timeBasis": comparison["time_basis"],
            "night": comparison["night"],
            "day": comparison["day"],
            "epochSeconds": STEP,
            "timelineMinutes": 5,
            "continuousWearConfirmed": True,
        },
        "hourly": hourly,
        "daily": daily,
        "days": days,
        "overlap": {
            "summary": {key: overlap[key] for key in [
                "paired_daytime_hours", "state_hours_per_16h",
                "fraction_peach_rest_overlapping", "fraction_toast_rest_overlapping",
                "interpretation"]},
            "runs": runs,
            "runWindow": {"startMinute": 0, "endMinute": 1440,
                          "description": "Full local calendar day; human sleep hours are 22:00–06:00."},
            "hourly": overlap["hourly"],
            "sensitivity": overlap["sensitivity"],
            "alignment": insights["rest_alignment"],
            "states": {"0": "Neither resting", "1": "Peach only", "2": "Toast only",
                       "3": "Both resting", "4": "Missing paired data"},
        },
        "sensitivity": comparison["sensitivity"],
        "insights": insights,
        "method": {
            "restRule": comparison["rest_rule"],
            "movementUnit": "mg = thousandths of gravitational acceleration; movement is the root-sum of within-epoch acceleration variances across three axes.",
            "movementMeaning": "Higher values mean more variable collar movement. These are not steps, calories, distance, or a validated exercise measure. Grooming and head movements contribute.",
            "restMeaning": "Sleep-like rest is sustained low movement with stable posture. Quiet wakefulness can qualify; this does not measure physiological sleep.",
            "restRuleText": "Five-second intervals below 20 mg with less than 5 degrees of posture change, in bouts of at least five minutes that are at least 90% quiet. Internal breaks of at most 30 seconds may join a bout; the breaks themselves do not count as rest.",
            "pairing": "Both cats use exactly the same valid five-second intervals. Each interval needs at least 4.9 seconds of sample coverage. Missing time earns no movement or rest credit.",
            "normalization": "Rest hours per period are the observed rest proportion times 24, 16, or 8 hours. Daytime overlap is proportion times 16 hours; full-day overlap is proportion times 24 hours. This scales for 80 excluded daytime seconds rather than treating them as stillness.",
            "schemaUnits": "summary preserves the analysis field names and units. hourly, days.hourly, and days.timeline use mg for peach/toast and 0–1 proportions for rest and coverage. daily peachRest/toastRest and bothRestHours24h use hours per 24h; daily bothRestHours uses hours per 16h daytime. daily bothRest remains a 0–1 full-day proportion. overlap.runs cover 0–1440 clock minutes with five-second precision; state 4 explicitly preserves missing paired data. overlap.summary and overlap.hourly remain daytime statistics.",
            "restAlignment": "The different-date baseline matches each Peach date to every other Toast date at the same clock times. It is a descriptive comparison, not a randomized experiment or evidence of causation.",
            "limitations": [
                "Six shared days describe this recording, not stable lifelong traits.",
                "Device wall clocks are assumed to be aligned Pacific local time; that alignment was not independently verified.",
                "Changing the stillness threshold can reverse which cat appears to rest longer.",
                "Simultaneous rest does not establish co-location, interaction, or one cat influencing the other.",
                "The unusually quiet September 4 was identified after examining the data; it does not establish a cause or health problem.",
            ],
        },
        "population": {
            "conclusion": "These recordings cannot reliably rank Peach or Toast against most cats.",
            "reason": "A fair population comparison needs the same sensor, processing, activity definition, and cats of comparable ages and lifestyles. Collar movement, including grooming, is not interchangeable with walking or exercise time.",
            "rhythm": "Morning and evening activity peaks and substantial quiet time resemble patterns reported in other housed cats; familiar timing does not establish an average total activity level.",
            "interpretation": "Use this week as a personal baseline for each cat, not a population percentile or a medical assessment.",
        },
    }
    return rounded(result)


def main():
    result = build()
    dest = ROOT / "site" / "data.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(result, separators=(",", ":"), allow_nan=False) + "\n")
    print(f"Wrote {dest.relative_to(ROOT)} ({dest.stat().st_size:,} bytes)")
    print(f"Verified {result['coverage']['days']} paired days, "
          f"{result['coverage']['pairedHours']:.6f} hours, "
          f"{result['coverage']['excludedSeconds']} excluded seconds; "
          "summaries match comparison.json and daytime_overlap.json.")


if __name__ == "__main__":
    main()
