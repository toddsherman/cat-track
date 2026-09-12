"""Rest/sleep classification for collar-mounted accelerometry.

Three-state heuristic:
  active        - ENMO at or above the movement threshold
  rest (awake)  - still, but posture is shifting
  likely sleep  - still AND posture held steady, sustained

The posture test is adapted from the van Hees HDCZA sleep algorithm: take the
sensor's z-angle, roll a median over it, and look at how much that median moves.
A sleeping animal holds a posture; a quietly awake one keeps making small
adjustments even when its ENMO reads as motionless.
"""
import numpy as np
import pandas as pd

EPOCH = '5s'
ANGLE_WIN = '5min'      # rolling median window for posture
MIN_SLEEP = 5 * 60      # seconds; shorter still-periods are naps-in-progress, not scored
MAX_BREAK = 60          # seconds of movement tolerated inside a sleep bout


def epochs(t, x, y, z, temp_idx=None, temp=None, epoch=EPOCH):
    mag = np.sqrt(x*x + y*y + z*z)
    enmo = np.clip(mag - 1.0, 0, None)
    angle = np.degrees(np.arctan2(z, np.sqrt(x*x + y*y)))

    df = pd.DataFrame({'enmo': enmo, 'angle': angle, 'mag': mag},
                      index=pd.to_datetime(t, unit='s'))
    ep = df.resample(epoch).agg(enmo=('enmo', 'mean'), angle=('angle', 'median'),
                                mmag=('mag', 'mean'), sd=('mag', 'std'),
                                n=('enmo', 'size'))
    ep = ep[ep['n'] > 0].copy()
    ep['mg'] = ep['enmo'] * 1000
    if temp is not None:
        ts = pd.Series(temp, index=pd.to_datetime(temp_idx, unit='s'))
        ep['temp'] = ts.resample(epoch).mean().reindex(ep.index).interpolate()
    return ep


def calibrate(ep):
    """Scale so that the stillest stretches read 1.000 g. Returns the factor."""
    still = ep[ep['sd'] < ep['sd'].quantile(0.05)]
    if len(still) < 10:
        return 1.0
    return 1.0 / still['mmag'].median()


def classify(ep, move_thr=None, angle_thr=None):
    ep = ep.copy()
    if move_thr is None:
        # valley between the two modes of the log-ENMO distribution
        lg = np.log10(ep['mg'].clip(lower=0.01))
        hist, edges = np.histogram(lg[lg > -1.5], bins=30)
        lo = int(np.argmax(hist[:len(hist)//2])) if hist[:len(hist)//2].size else 0
        hi = len(hist)//2 + int(np.argmax(hist[len(hist)//2:]))
        valley = lo + int(np.argmin(hist[lo:hi])) if hi > lo else lo
        move_thr = float(10 ** edges[valley + 1])
        move_thr = float(np.clip(move_thr, 3, 20))

    # 5-min rolling median of posture angle, differenced over 1 min: how far
    # the animal's held posture drifted. Frozen posture -> ~0; fidgeting -> degrees.
    lag = max(1, int(60 / (ep.index[1] - ep.index[0]).total_seconds()))
    roll = ep['angle'].rolling(ANGLE_WIN, center=True, min_periods=3).median()
    ep['dangle'] = roll.diff(lag).abs().fillna(0)
    if angle_thr is None:
        still0 = ep['dangle'][ep['mg'] < move_thr]
        angle_thr = float(np.clip(still0.quantile(0.60) if len(still0) else 1.0, 0.2, 5.0))

    ep['still'] = ep['mg'] < move_thr
    ep['steady'] = ep['dangle'] < angle_thr
    ep['sleep_raw'] = ep['still'] & ep['steady']

    # bridge short interruptions, then drop bouts that are too brief
    step = (ep.index[1] - ep.index[0]).total_seconds()
    v = ep['sleep_raw'].to_numpy().copy()
    grp = np.r_[0, np.cumsum(np.diff(v.astype(int)) != 0)]
    for g in np.unique(grp):
        m = grp == g
        if not v[m][0] and m.sum() * step <= MAX_BREAK:
            v[m] = True
    grp = np.r_[0, np.cumsum(np.diff(v.astype(int)) != 0)]
    for g in np.unique(grp):
        m = grp == g
        if v[m][0] and m.sum() * step < MIN_SLEEP:
            v[m] = False
    ep['sleep'] = v

    ep['state'] = np.where(ep['sleep'], 'sleep',
                   np.where(ep['still'], 'rest', 'active'))
    return ep, {'move_thr_mg': move_thr, 'angle_thr_deg': angle_thr}


def intervals(ep, col='state'):
    """Collapse per-epoch labels into [start, end, state] runs."""
    s = ep[col]
    grp = (s != s.shift()).cumsum()
    out = []
    step = (ep.index[1] - ep.index[0]).total_seconds()
    for _, block in ep.groupby(grp):
        out.append({'start': block.index[0].timestamp(),
                    'end': block.index[-1].timestamp() + step,
                    'state': block[col].iloc[0]})
    return out
