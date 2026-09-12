# Cat Track

What do Toast and Peach actually do all day? An interactive story about two cats, a pair of Axivity AX3 collars, and six days of activity and rest data.

[Project on todd.sh](https://www.todd.sh/catTrack) · [Public repository](https://github.com/toddsherman/cat-track)

## Run the website

Use Node.js 24 and npm. The website runs entirely in the browser; Python is only needed to regenerate the analysis.

```sh
npm ci
npm run build
npm test
npm run dev
```

Open the local URL printed by the development server. Both `/` and `/catTrack` serve the project. `site/` is the canonical source; `dist/` is generated deployment output.

The page includes hourly activity, daytime versus nighttime rest, a 24-hour timeline with Toast above Peach, meal-time guides, daily comparisons, and a sensitivity explorer. Rest is a motion-based heuristic, not a validated physiological sleep measurement.

## Data and findings

The raw `.CWA` files contain about a week of recordings from each collar. The comparison uses the six complete shared days, August 31–September 5, 2026, with device clocks treated as local Pacific time. Both collars were worn continuously. Night is 10 p.m.–6 a.m.; the 80 seconds of bins overlapping Toast's recording gap are excluded from both cats.

- Toast recorded 26% more average collar movement and about 84 more minutes above the shared movement threshold per day.
- Both cats spent about three-quarters of the night in sustained quiet rest, compared with about two-fifths of daytime.
- Roughly 70% of each cat's daytime rest overlapped with the other's.
- Their 7–8 a.m. activity peak coincides with breakfast around 7:15 a.m. Dinner is usually around 6:30–7 p.m.; meal guides show the household routine, not exact events recorded by the collars.
- Different reasonable rest thresholds reverse which cat appears to rest longer. These data cannot rank the cats against a population or establish the cause of their behavior.

The full methods and limitations appear on the website and in [the analysis report](analysis/report.md), [additional observations](analysis/additional_insights.md), and [the public chart data](site/data.json).

## Reproduce the analysis

The published results were generated with Python 3.9.6 and the dependency versions pinned in `requirements.txt`. Use that Python environment for an exact reproduction. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m cattrack.compare
.venv/bin/python -m cattrack.overlap
.venv/bin/python -m cattrack.insights
.venv/bin/python -m cattrack.build_site_data
npm run build
npm test
```

The first analysis command reads both original CWA files and produces local epoch caches. Later analysis runs can use `python -m cattrack.compare --reuse-epochs`. The caches are reproducible and excluded from Git.

`cattrack/cwa.py` handles the AX3 packet format, fractional timestamps, and actual sample-rate interpolation. Tests cover decoding, missing data, and rest scoring. The site export verifies its aggregates against the original comparison, preserves five-second rest boundaries, and distinguishes missing data from stillness.

## What is included

- `site/`: HTML, CSS, JavaScript, public chart data, and optimized photographs.
- `cattrack/`, `tests/`, and `analysis/`: analysis tools, checks, reports, and summaries.
- `CWA-DATA peach.CWA` and `CWA-DATA toast.CWA`: original collar recordings, about 65 MB each.
- `media/`: full-size photo copies with location and camera-owner metadata removed. Original private copies remain outside version control.
- Root `toast_viewer.*`, `toast_epochs.csv`, and `toast_activity.png`: earlier exploratory Toast-only outputs. They use an older recording window and classifier, and are historical artifacts rather than the source of the published comparison.

The removed video, local credentials, virtual environments, build products, and epoch caches are excluded. See [media provenance](site/assets/README.md) for the website assets.

## Deployment and todd.sh integration

Vercel runs `npm run build` and publishes only `dist/`. Its routes serve the project at `/` and `/catTrack`; raw recordings, analysis files, and full-size source photos are available in GitHub but are not part of the website deployment.

The standalone build uses checked-in copy and links the return bar to todd.sh. It removes the portfolio-only CMS loader from its generated HTML. The canonical source keeps the shared typography, palette, return bar, and fixed-copy slots used by the todd.sh portfolio.

To update a local todd.sh checkout and regenerate its Cat Track content seed:

```sh
node scripts/sync-todd-site.mjs "../Todd dot sh"
```

This writes only `public/catTrack/`, the project thumbnail, and `sanity/content/cat-track.json`. The gallery registration lives in the portfolio's `app/projects.ts`. The sync command does not deploy or import content into Sanity.
