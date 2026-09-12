"""Compare simultaneous daytime rest; run after python -m cattrack.compare."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

from cattrack.compare import score_rest, STEP


def main():
    out = Path("analysis")
    comparison = json.loads((out / "comparison.json").read_text())
    idx = pd.date_range(comparison["analysis_start"], comparison["analysis_end_exclusive"],
                        freq="5s", inclusive="left")
    full, aligned = {}, {}
    for name in ["Peach", "Toast"]:
        ep = pd.read_pickle(out / f"{name.lower()}_epochs.pkl")
        ep["rest"], _ = score_rest(ep)
        full[name], aligned[name] = ep, ep.reindex(idx)
    p, t = aligned["Peach"], aligned["Toast"]
    daytime = (idx.hour >= 6) & (idx.hour < 22)
    valid = (p.valid & t.valid).to_numpy()
    mask = daytime & valid
    pr, tr = p.rest.to_numpy(dtype=bool), t.rest.to_numpy(dtype=bool)
    states = pr.astype(int) + 2 * tr.astype(int)
    names = ["Neither resting", "Peach only", "Toast only", "Both resting"]
    state_hours = {label: float((states[mask] == n).mean() * 16) for n, label in enumerate(names)}
    hourly = []
    for hour in range(6, 22):
        m = mask & (idx.hour == hour)
        hourly.append({"hour": hour, "both_rest_fraction": float((pr[m] & tr[m]).mean()),
                       "peach_rest_fraction": float(pr[m].mean()), "toast_rest_fraction": float(tr[m].mean())})
    dates = pd.date_range(idx[0].floor("D"), idx[-1].floor("D"), freq="D")
    daily = []
    for date in dates:
        m = mask & (idx.normalize() == date)
        daily.append({"date": str(date.date()), "both_rest_hours_per_16h": float((pr[m] & tr[m]).mean()*16),
                      "paired_observed_hours": float(m.sum()*STEP/3600)})
    sensitivity = []
    for threshold in [15, 20, 30, 40]:
        for duration in [5, 10]:
            rr = [pd.Series(score_rest(full[n], threshold, duration)[0], index=full[n].index)
                  .reindex(idx).to_numpy(dtype=bool)[mask] for n in full]
            a, b = rr
            sensitivity.append({"rms_threshold_mg": threshold, "minimum_bout_minutes": duration,
                "both_rest_hours_per_16h": float((a & b).mean()*16),
                "fraction_peach_rest_overlapping": float((a & b).sum()/a.sum()),
                "fraction_toast_rest_overlapping": float((a & b).sum()/b.sum())})
    result = {"analysis_start": comparison["analysis_start"], "analysis_end_exclusive": comparison["analysis_end_exclusive"],
        "daytime": "06:00–22:00 device-local clock", "method": comparison["rest_rule"],
        "paired_daytime_hours": float(mask.sum()*STEP/3600),
        "state_hours_per_16h": state_hours,
        "fraction_peach_rest_overlapping": float((pr[mask] & tr[mask]).sum()/pr[mask].sum()),
        "fraction_toast_rest_overlapping": float((pr[mask] & tr[mask]).sum()/tr[mask].sum()),
        "daily": daily, "hourly": hourly, "sensitivity": sensitivity,
        "interpretation": "Sleep-like rest from collar stillness. Shared timing does not establish sleeping in the same place or interaction."}
    (out / "daytime_overlap.json").write_text(json.dumps(result, indent=2) + "\n")

    colors = ["#e9e7e2", "#dc8054", "#527993", "#765b94", "#242424"]
    fig, ax = plt.subplots(figsize=(13, 5.5), facecolor="#fcfbf8")
    ax.set_facecolor("#fcfbf8")
    for i, date in enumerate(dates):
        m = daytime & (idx.normalize() == date)
        row = np.where(valid[m], states[m], 4)
        ax.imshow(row[np.newaxis, :], extent=[6, 22, len(dates)-i-.76, len(dates)-i-.24],
                  cmap=ListedColormap(colors), vmin=0, vmax=4, aspect="auto", interpolation="nearest")
        ax.text(22.2, len(dates)-i-.5, f"{daily[i]['both_rest_hours_per_16h']:.1f} h", va="center", fontsize=11, color="#765b94", weight="bold")
    ax.set_xlim(6, 23); ax.set_ylim(0, len(dates))
    ax.set_xticks([6, 8, 10, 12, 14, 16, 18, 20, 22], ["6 a.m.", "8", "10", "Noon", "2 p.m.", "4", "6", "8", "10 p.m."])
    ax.set_yticks(np.arange(len(dates))+.5, [d.strftime("%b %d") for d in dates[::-1]])
    ax.tick_params(length=0, pad=10)
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.legend(handles=[Patch(color=colors[i], label=names[i]) for i in [3,1,2,0]],
              loc="upper left", bbox_to_anchor=(0, 1.17), ncol=4, frameon=False)
    fig.suptitle("About 70% of each cat’s daytime rest overlaps the other’s", x=.09, y=.97,
                 ha="left", fontsize=17, weight="bold")
    fig.text(.09, .035, "Purple = simultaneous sleep-like rest; average 4.6 hours per 16-hour day. Right labels show each day's overlap.\n"
             "Five-second intervals, Aug 31–Sep 5, 2026. Quiet wakefulness can qualify; dark mark = missing data.", fontsize=9, color="#5b6066")
    fig.subplots_adjust(left=.09, right=.96, bottom=.17, top=.77)
    fig.savefig(out / "daytime_overlap.png", dpi=170, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(json.dumps({k: v for k,v in result.items() if k not in ["hourly", "sensitivity"]}, indent=2))


if __name__ == "__main__":
    main()
