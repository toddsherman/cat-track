"""Reproducible paired analysis of Peach and Toast's collar accelerometers.

Run from the project folder: .venv/bin/python -m cattrack.compare
All timestamps are device wall-clock times; no timezone conversion is applied.
This describes movement and sustained quiet rest, not validated feline sleep.
"""
from pathlib import Path
import argparse
import gc
import json
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cattrack import cwa

STEP = 5
REST_THRESHOLD = 20  # above the shared quiet-movement mode near 8–12 mg
COLORS = {"Peach": "#dc8054", "Toast": "#527993"}


def runs(mask):
    """Half-open intervals of a Boolean array, including both kinds of run."""
    mask = np.asarray(mask, dtype=bool)
    if not len(mask):
        return []
    edges = np.r_[0, np.flatnonzero(mask[1:] != mask[:-1]) + 1, len(mask)]
    return [(int(a), int(b), bool(mask[a])) for a, b in zip(edges[:-1], edges[1:])]


def make_epochs(path):
    header, blocks, samples = cwa.read(path)
    t = samples["t"]
    if not np.all(np.diff(t) > 0):
        raise ValueError(f"{path}: sample timestamps are not strictly increasing")
    origin = int(np.floor(t[0] / STEP)) * STEP
    group = np.floor((t - origin) / STEP).astype(np.int64)
    n = np.bincount(group)
    nn = np.where(n, n, 1)
    size = len(n)
    index = pd.to_datetime(origin + np.arange(size) * STEP, unit="s")
    means, variances = [], []
    norm2 = np.zeros(len(t))
    for axis in "xyz":
        a = samples[axis]
        means.append(np.bincount(group, weights=a, minlength=size) / nn)
        second = np.bincount(group, weights=a * a, minlength=size) / nn
        variances.append(np.maximum(second - means[-1] ** 2, 0))
        norm2 += a * a
    norm = np.sqrt(norm2)
    norm_mean = np.bincount(group, weights=norm, minlength=size) / nn
    norm_var = np.maximum(np.bincount(group, weights=norm2, minlength=size) / nn - norm_mean ** 2, 0)
    enmo = np.bincount(group, weights=np.maximum(norm - 1, 0), minlength=size) / nn * 1000
    rms = np.sqrt(np.sum(variances, axis=0)) * 1000

    # Sample support, capped at the normal interval so missing time is never filled.
    # Nominal-frequency deviations are measured from the recording, not assumed.
    nominal_dt = float(np.median(np.diff(t)))
    support_end = t + nominal_dt
    support_end[:-1] = np.minimum(support_end[:-1], t[1:])
    epoch_end = origin + (group + 1) * STEP
    first = np.maximum(0, np.minimum(support_end, epoch_end) - t)
    covered = np.bincount(group, weights=first, minlength=size)
    remainder = np.maximum(support_end - epoch_end, 0)
    covered += np.bincount(group + 1, weights=remainder, minlength=size + 1)[:size]
    valid = covered >= 4.9  # require at least 98% of this 5-second epoch

    vec = np.array(means).T
    lengths = np.linalg.norm(vec, axis=1)
    dot = np.sum(vec[1:] * vec[:-1], axis=1)
    denom = lengths[1:] * lengths[:-1]
    cosine = np.divide(dot, denom, out=np.ones_like(dot), where=denom > 0)
    angle = np.r_[np.nan, np.degrees(np.arccos(np.clip(cosine, -1, 1)))]
    angle[~valid | ~np.r_[False, valid[:-1]]] = np.nan
    ep = pd.DataFrame({"n": n, "covered_s": covered, "valid": valid,
                       "rms_mg": rms, "norm_sd_mg": np.sqrt(norm_var) * 1000,
                       "raw_enmo_mg": enmo, "mean_norm_g": norm_mean,
                       "posture_change_deg": angle}, index=index)
    for key in ["temperature", "light"]:
        s = pd.Series(blocks[key], index=pd.to_datetime(blocks["timestamp"] + blocks["fraction"], unit="s"))
        ep[key] = s.resample("5s").mean().reindex(index)

    seq = blocks["sequence"].astype(np.int64)
    breaks = np.flatnonzero(np.diff(seq) != 1)
    counts = blocks["count"].astype(int)
    ends = np.cumsum(counts)
    gaps = []
    for i in breaks:
        before = ends[i] - 1
        gaps.append({"start": str(pd.to_datetime(t[before] + nominal_dt, unit="s")),
                     "end": str(pd.to_datetime(t[before + 1], unit="s")),
                     "seconds": float(t[before + 1] - t[before] - nominal_dt)})
    quiet = ep.loc[ep.valid & (ep.rms_mg < ep.loc[ep.valid, "rms_mg"].quantile(.05))]
    metadata = {"file": str(path), "header": header, "first_sample": str(pd.to_datetime(t[0], unit="s")),
                "last_sample": str(pd.to_datetime(t[-1], unit="s")), "samples": len(t),
                "median_sample_rate_hz": 1 / nominal_dt, "sequence_breaks": len(breaks),
                "gaps": gaps, "epoch_count": len(ep), "valid_epoch_count": int(valid.sum()),
                "rms_percentiles_mg": {str(q): float(ep.loc[ep.valid, "rms_mg"].quantile(q)) for q in [.01, .05, .25, .5, .75, .9, .95, .99]},
                "stillest_5pct_median_norm_g": float(quiet.mean_norm_g.median())}
    return ep, metadata


def score_rest(ep, threshold=REST_THRESHOLD, minimum_min=5, bridge_seconds=30):
    """Operational sleep-like rest; interruptions and missing time earn no rest."""
    valid = ep.valid.to_numpy()
    quiet = valid & (ep.rms_mg.to_numpy() < threshold) & (ep.posture_change_deg.to_numpy() < 5)
    connected = quiet.copy()
    for a, b, value in runs(quiet):
        if (not value and a > 0 and b < len(quiet) and (b - a) * STEP <= bridge_seconds
                and valid[a:b].all()):
            connected[a:b] = True
    accepted = np.zeros(len(ep), dtype=bool)
    bouts = []
    for a, b, value in runs(connected):
        if value and (b - a) * STEP >= minimum_min * 60 and quiet[a:b].mean() >= .90:
            accepted[a:b] = quiet[a:b]
            bouts.append({"start": str(ep.index[a]), "end": str(ep.index[b-1] + pd.Timedelta(seconds=STEP)),
                          "span_minutes": (b-a)*STEP/60, "quiet_minutes": quiet[a:b].sum()*STEP/60})
    return accepted, bouts


def period_stats(ep, mask):
    z = ep.loc[mask]
    hours = len(z) * STEP / 3600
    return {"observed_hours": hours, "mean_rms_mg": float(z.rms_mg.mean()),
            "median_rms_mg": float(z.rms_mg.median()), "mean_norm_sd_mg": float(z.norm_sd_mg.mean()),
            "raw_enmo_mg": float(z.raw_enmo_mg.mean()),
            "movement_fraction": float((z.rms_mg >= REST_THRESHOLD).mean()),
            "rest_fraction": float(z.sleep_like_rest.mean()),
            "rest_hours_observed": float(z.sleep_like_rest.sum() * STEP / 3600)}


def analyze(data, metadata):
    first = max(ep.index[0] for ep in data.values()).ceil("D")
    end = min(ep.index[-1] + pd.Timedelta(seconds=STEP) for ep in data.values()).floor("D")
    grid = pd.date_range(first, end, freq="5s", inclusive="left")
    paired = np.ones(len(grid), dtype=bool)
    for name, ep in data.items():
        ep["sleep_like_rest"], bouts = score_rest(ep)
        metadata[name]["rest_bouts_full_recording"] = bouts
        paired &= ep.valid.reindex(grid, fill_value=False).to_numpy()
    night = (grid.hour >= 22) | (grid.hour < 6)
    ndays = (end - first).days
    result = {"analysis_start": str(first), "analysis_end_exclusive": str(end), "calendar_days": ndays,
              "night": "22:00–06:00", "day": "06:00–22:00", "time_basis": "device local clock, assumed Pacific",
              "paired_observed_hours": float(paired.sum() * STEP / 3600),
              "paired_excluded_seconds": int((~paired).sum()*STEP), "cats": {}, "sensitivity": [],
              "rest_rule": {"rms_threshold_mg": REST_THRESHOLD, "posture_change_deg": 5,
                            "minimum_bout_minutes": 5, "max_internal_break_seconds": 30,
                            "minimum_quiet_fraction_per_bout": .90, "bridges_count_as_rest": False},
              "daily": [], "hourly": [], "metadata": metadata}
    for name, ep in data.items():
        z = ep.reindex(grid)
        stats = {}
        for period, mask, length in [("all", paired, 24), ("night", paired & night, 8), ("day", paired & ~night, 16)]:
            stats[period] = period_stats(z, mask)
            stats[period]["rest_hours_per_period"] = stats[period]["rest_fraction"] * length
            stats[period]["movement_hours_per_period"] = stats[period]["movement_fraction"] * length
        result["cats"][name] = stats
        for date in pd.date_range(first, end, freq="D", inclusive="left"):
            date_mask = (grid >= date) & (grid < date + pd.Timedelta(days=1))
            for period, pm in [("all", np.ones(len(grid), dtype=bool)), ("night", night), ("day", ~night)]:
                result["daily"].append({"cat": name, "date": str(date.date()), "period": period,
                                        **period_stats(z, paired & date_mask & pm)})
        for hour in range(24):
            result["hourly"].append({"cat": name, "hour": hour, **period_stats(z, paired & (grid.hour == hour))})
        for threshold in [15, 20, 30, 40]:
            for min_bout in [5, 10]:
                rest, _ = score_rest(ep, threshold, min_bout)
                r = pd.Series(rest, index=ep.index).reindex(grid).to_numpy()
                result["sensitivity"].append({"cat": name, "threshold_mg": threshold, "min_bout_minutes": min_bout,
                    "rest_hours_per_day": float(r[paired].mean() * 24),
                    "night_rest_fraction": float(r[paired & night].mean()),
                    "day_rest_fraction": float(r[paired & ~night].mean()),
                    "movement_fraction": float((z.rms_mg[paired] >= threshold).mean())})
    a, b = [data[n].reindex(grid).rms_mg.where(paired).resample("15min").mean() for n in data]
    result["activity_15min_pearson_correlation"] = float(a.corr(b))
    return result, grid, paired


def plot(result, dest):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlepad": 12})
    fig = plt.figure(figsize=(13, 10), facecolor="#fcfbf8")
    gs = fig.add_gridspec(2, 2, hspace=.46, wspace=.30, left=.08, right=.97, top=.86, bottom=.10)
    ax = fig.add_subplot(gs[0, 0]); ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, 0]); ax4 = fig.add_subplot(gs[1, 1])
    hourly = pd.DataFrame(result["hourly"])
    daily = pd.DataFrame(result["daily"])
    fig.suptitle("Peach & Toast · a week of collar movement", x=.08, y=.97, ha="left", fontsize=21, weight="bold")
    fig.text(.08, .923, "Paired comparison: Aug 31–Sep 5, 2026 · six complete days · nighttime 10 p.m.–6 a.m.", color="#50545a", fontsize=11)
    for name, color in COLORS.items():
        z = hourly[hourly.cat == name]
        ax.plot(z.hour + .5, z.mean_rms_mg, color=color, lw=2.4, label=name)
        d = daily[(daily.cat == name) & (daily.period == "all")]
        ax4.plot(np.arange(len(d)), d.mean_rms_mg, marker="o", color=color, lw=2, label=name)
    ax.set(title="When are they moving?", xlabel="Hour of day (local device clock)", ylabel="Average movement variability (mg)")
    ax.set_xlim(0, 24); ax.set_xticks([0, 6, 12, 18, 24], ["12 a.m.", "6 a.m.", "12 p.m.", "6 p.m.", "12 a.m."])
    for a, b in [(0, 6), (22, 24)]: ax.axvspan(a, b, color="#c4c9dc", alpha=.35, lw=0)
    ax.legend(frameon=False); ax.set_ylim(bottom=0)
    x = np.arange(2); width = .32
    for i, (name, color) in enumerate(COLORS.items()):
        stats = result["cats"][name]
        vals = [stats[p]["rest_fraction"] * 100 for p in ["night", "day"]]
        bars = ax2.bar(x + (i-.5)*width, vals, width, color=color, label=name)
        for bar, p, val in zip(bars, ["night", "day"], vals):
            ax2.text(bar.get_x() + width/2, val + 2, f"{val:.0f}%\n{stats[p]['rest_hours_per_period']:.1f} h", ha="center", va="bottom", fontsize=10)
        y = 1 - i
        nh = stats["night"]["rest_hours_per_period"]
        dh = stats["day"]["rest_hours_per_period"]
        ax3.barh(y, nh, color=color, height=.5)
        ax3.barh(y, dh, left=nh, color=color, alpha=.45, height=.5)
        ax3.text(nh/2, y, f"{nh:.1f} h\nnight", ha="center", va="center", color="white", weight="bold")
        ax3.text(nh+dh/2, y, f"{dh:.1f} h\nday", ha="center", va="center", color="#27313a", weight="bold")
        ax3.text(nh+dh+.25, y, f"{nh+dh:.1f} h", va="center", weight="bold")
    ax2.set(title="How much of each period is quiet rest?", ylabel="Sleep-like rest (% of observed time)", ylim=(0, 100))
    ax2.set_xticks(x, ["Night · 8 hours", "Day · 16 hours"])
    ax3.set(title="Estimated sleep-like rest per 24 hours", xlabel="Hours of sustained quiet rest", xlim=(0, 24))
    ax3.set_yticks([1, 0], list(COLORS)); ax3.set_xticks([0, 6, 12, 18, 24])
    dates = daily[(daily.cat == "Peach") & (daily.period == "all")].date
    ax4.set_xticks(np.arange(len(dates)), [pd.Timestamp(d).strftime("%b %d") for d in dates], rotation=25)
    ax4.set(title="Does the activity difference hold each day?", ylabel="Average movement variability (mg)", ylim=(0, None))
    for axis in [ax, ax2, ax3, ax4]:
        axis.set_facecolor("#fcfbf8"); axis.grid(axis="y" if axis != ax3 else "x", alpha=.15); axis.set_axisbelow(True)
    fig.text(.08, .025, "Sleep-like rest = ≥5-minute bouts of low, steady collar movement. Quiet wakefulness can also qualify.\n"
             "Totals depend on the stillness cutoff; sensitivity testing does not identify a clear sleep-duration winner.", fontsize=9, color="#5b6066")
    fig.savefig(dest / "comparison.png", dpi=170, facecolor=fig.get_facecolor())
    plt.close(fig)


def write_report(result, dest):
    p, t = result["cats"]["Peach"], result["cats"]["Toast"]
    increases = {period: 100 * (t[period]["mean_rms_mg"] / p[period]["mean_rms_mg"] - 1)
                 for period in ["all", "night", "day"]}
    daily = pd.DataFrame(result["daily"])
    activity = daily[daily.period == "all"].pivot(index="date", columns="cat", values="mean_rms_mg")
    daily_diff = 100 * (activity.Toast / activity.Peach - 1)
    sensitivity = pd.DataFrame(result["sensitivity"])
    ranges = sensitivity.groupby("cat").rest_hours_per_day.agg(["min", "max"])
    script_path = Path(os.path.relpath(Path(__file__).resolve(), dest.resolve())).as_posix()
    lines = [
        "# Peach and Toast: activity and sleep-like rest",
        "",
        f"Toast recorded **{increases['all']:.0f}% more average collar movement** than Peach across six complete, matched calendar days, August 31–September 5, 2026. The difference was concentrated in daytime: **{increases['day']:.0f}% more**, compared with **{increases['night']:.0f}% more at night**. Their nighttime movement was therefore similar on average.",
        "",
        "Both cats spent a much larger fraction of the night in sustained quiet rest. They accumulated slightly more total rest during daytime because daytime is twice as long. This is an estimate of **sleep-like rest**, which includes some quiet wakefulness; these recordings do not establish actual sleep duration.",
        "",
        "| Average measure | Peach | Toast |",
        "|---|---:|---:|",
        f"| Collar movement variability, all hours | {p['all']['mean_rms_mg']:.1f} mg | {t['all']['mean_rms_mg']:.1f} mg |",
        f"| Time with movement above 20 mg per 24 h | {p['all']['movement_hours_per_period']:.1f} h | {t['all']['movement_hours_per_period']:.1f} h |",
        f"| Sleep-like rest, night (10 p.m.–6 a.m.; 8 h) | {p['night']['rest_hours_per_period']:.1f} h ({p['night']['rest_fraction']:.0%}) | {t['night']['rest_hours_per_period']:.1f} h ({t['night']['rest_fraction']:.0%}) |",
        f"| Sleep-like rest, day (6 a.m.–10 p.m.; 16 h) | {p['day']['rest_hours_per_period']:.1f} h ({p['day']['rest_fraction']:.0%}) | {t['day']['rest_hours_per_period']:.1f} h ({t['day']['rest_fraction']:.0%}) |",
        f"| Sleep-like rest, total per 24 h | {p['all']['rest_hours_per_period']:.1f} h | {t['all']['rest_hours_per_period']:.1f} h |",
        "",
        "Time above the movement threshold is accumulated from five-second intervals and is not continuous walking, exercise time, or wake time. Movement and sleep-like rest do not add to 24 hours: shorter quiet periods fall into neither category.",
        "",
        "![Comparison charts](comparison.png)",
        "",
        "**Behavioral observations**",
        "",
        f"- Toast was more active on **all six days**; the daily difference ranged from {daily_diff.min():.0f}% to {daily_diff.max():.0f}%.",
        "- Both cats had their largest average morning activity peak around **7–8 a.m.**, with another busy period around **6–10 p.m.** The data alone cannot attribute those peaks to meals, play, or other causes.",
        "- **Midnight–4 a.m. was especially quiet** for both. Activity picked up around 4–6 a.m., before the main morning peak.",
        "- Peach had a pronounced midday lull; Toast retained more movement during midday and the later evening.",
        "- **There is no reliable sleep-duration winner.** The small difference between the cats changes direction when the stillness threshold changes.",
        "",
        "**How much do the sleep estimates depend on the method?**",
        "",
        "The quiet-movement distributions for both collars peak near 8–12 mg. A common 20 mg cutoff was chosen above that peak, then compared with 15, 30, and 40 mg. A 10 mg cutoff cuts through the quiet-movement peak and fragments sustained rest, producing much lower totals; it is unsuitable as the main cutoff here. The cutoff is an operational choice, not a clinically validated feline sleep boundary.",
        "",
        "| RMS cutoff; minimum bout 5 min | Peach rest / 24 h | Toast rest / 24 h |",
        "|---|---:|---:|",
    ]
    for threshold in [15, 20, 30, 40]:
        s = sensitivity[(sensitivity.threshold_mg == threshold) & (sensitivity.min_bout_minutes == 5)].set_index("cat")
        lines.append(f"| {threshold} mg | {s.loc['Peach', 'rest_hours_per_day']:.2f} h | {s.loc['Toast', 'rest_hours_per_day']:.2f} h |")
    lines += [
        "",
        f"Across these four cutoffs and minimum bouts of five or ten minutes, Peach's estimates span **{ranges.loc['Peach','min']:.1f}–{ranges.loc['Peach','max']:.1f} h/day** and Toast's **{ranges.loc['Toast','min']:.1f}–{ranges.loc['Toast','max']:.1f} h/day**. These are sensitivity ranges, not confidence intervals or bounds on actual sleep. Both retain substantially higher nighttime rest fractions throughout this range. The threshold-free activity-intensity comparison does not depend on these sleep cutoffs.",
        "",
        "**Data coverage and method**",
        "",
        "- Sources: `CWA-DATA peach.CWA` and `CWA-DATA toast.CWA`. Collar annotations match their filenames. You confirmed continuous wear.",
        "- Both use nominal 25 Hz, ±8 g, three-axis recording. All packet checksums pass. Peach has 15,176,520 samples; Toast has 15,033,000 samples.",
        "- Peach spans August 30 at 14:10:49 to September 6 at 14:10:01. Toast spans August 30 at 13:40:13 to September 6 at 13:38:05. First and last partial calendar days are excluded from the main comparison.",
        "- Toast has one 76.98-second recording interruption on August 31, approximately 16:37:51–16:39:08. Peach has no acquisition gaps. Five-second bins overlapping the gap are excluded from **both** cats, leaving 143 h 58 min 40 s of matched observations (99.985% coverage). Nighttime coverage is 48 h; daytime coverage is 95 h 58 min 40 s.",
        "- Hours are the devices' local wall-clock times, assumed Pacific; the files do not independently establish their timezone or synchronization to an external clock. Nighttime means 22:00–06:00. Each calendar day's night statistic combines 00:00–06:00 and 22:00–24:00.",
        "- Fractional timestamp offsets are corrected, and times are interpolated between valid packet anchors within continuous acquisition segments. Measured median rates are about 25.084 Hz for Peach and 24.855 Hz for Toast. Missing time is preserved. The timing correction follows the [Open Movement reference reader](https://github.com/openmovementproject/openmovement-python/blob/master/src/openmovement/load/cwa_load.py).",
        "- Movement intensity is the mean of five-second vector RMS values: `1000 × sqrt(var(x) + var(y) + var(z))`, with population variances and acceleration measured in g. Subtracting each interval's mean vector reduces dependence on static gravity offsets and fixed collar orientation. Posture changes and collar/head movement still contribute; this is not a measure of distance, steps, or energy use. No full laboratory gain calibration was available.",
        "- Sleep-like rest requires RMS below 20 mg and less than 5° change between consecutive five-second mean acceleration vectors. Bouts must span at least five minutes with at least 90% qualifying quiet intervals. Only internal interruptions up to 30 seconds can connect a bout; those interruptions earn no rest time. Invalid data never bridge a bout. At least 4.9 seconds of sample coverage are required per five-second interval.",
        "- Period hours equal the observed rest fraction multiplied by 8, 16, or 24. This corrects the tiny missing-data imbalance. Day and night estimates therefore compare rates as well as totals.",
        "- Quiet wakefulness may qualify as rest; movement during real sleep may fail the rule. No labeled sleep observations were supplied. Published [feline accelerometer validation research](https://pubmed.ncbi.nlm.nih.gov/37631701/) uses synchronized video to train and assess behavior classification; this report does not apply a validated feline sleep classifier.",
        "- The earlier Toast viewer and exports in the project cover a shorter recording snapshot and use a different heuristic. This comparison is freshly computed from both complete CWA files. The older artifacts are left in place.",
        "",
        "**Daily activity check**",
        "",
        "| Date | Peach mean RMS | Toast mean RMS | Toast relative to Peach |",
        "|---|---:|---:|---:|",
    ]
    for date, row in activity.iterrows():
        lines.append(f"| {date} | {row.Peach:.1f} mg | {row.Toast:.1f} mg | +{daily_diff.loc[date]:.1f}% |")
    lines += [
        "",
        "**Files and reproduction**",
        "",
        f"[Charts](comparison.png) · [Full summary and sensitivity data](comparison.json) · [Analysis script]({script_path})",
        "",
        "From the project folder, run `.venv/bin/python -m cattrack.compare`. The script reads both raw files and regenerates the summary, charts, report, and five-second epoch caches. Add `--reuse-epochs` only when the raw files and extraction code have not changed. Tests: `.venv/bin/python -m unittest discover -s tests -v`.",
    ]
    (dest / "report.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("analysis"))
    parser.add_argument("--reuse-epochs", action="store_true")
    args = parser.parse_args(); dest = args.output; dest.mkdir(exist_ok=True, parents=True)
    data, metadata = {}, {}
    for name in COLORS:
        cache = dest / f"{name.lower()}_epochs.pkl"
        meta_path = dest / f"{name.lower()}_metadata.json"
        if args.reuse_epochs and cache.exists():
            data[name] = pd.read_pickle(cache)
            metadata[name] = json.loads(meta_path.read_text())
        else:
            data[name], metadata[name] = make_epochs(Path(f"CWA-DATA {name.lower()}.CWA"))
            data[name].to_pickle(cache)
            meta_path.write_text(json.dumps(metadata[name], indent=2))
        print(name, json.dumps(metadata[name], indent=2), flush=True)
        gc.collect()
    result, _, _ = analyze(data, metadata)
    (dest / "comparison.json").write_text(json.dumps(result, indent=2))
    plot(result, dest)
    write_report(result, dest)
    print(json.dumps({k:v for k,v in result.items() if k not in ["metadata", "hourly", "daily"]}, indent=2))


if __name__ == "__main__":
    main()
