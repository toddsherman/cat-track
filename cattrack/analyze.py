import sys, numpy as np, pandas as pd
sys.path.insert(0, '.')
from cattrack import cwa

path = sys.argv[1] if len(sys.argv) > 1 else 'CWA-DATA.CWA'
h, b, s = cwa.read(path)

t = pd.to_datetime(s['t'], unit='s')
x, y, z = s['x'], s['y'], s['z']

print("="*64)
print(f"  {h['annotation']}   device {h['device_id']}   session {h['session_id']}")
print("="*64)
print(f"configured      : {h['config_rate_hz']:.0f} Hz, +/-{h['config_range_g']}g")
print(f"logging window  : {h['logging_start']} -> {h['logging_end']}")
print(f"data starts     : {t[0]}")
print(f"data ends       : {t[-1]}")
span = (s['t'][-1] - s['t'][0])
print(f"span            : {span/3600:.2f} h ({span/86400:.2f} days)")
print(f"samples         : {len(t):,}   packets: {h['n_packets']:,}")
print(f"effective rate  : {len(t)/span:.3f} Hz (nominal 25)")

# ---- integrity -----------------------------------------------------
dt = np.diff(b['timestamp'] + b['fraction'])
nominal = b['count'][:-1] / b['rate_hz'][:-1]
gap = dt - nominal
big = np.where(np.abs(gap) > 1.0)[0]
print(f"\n-- integrity --")
print(f"seq discontinuities : {int((np.diff(b['sequence'].astype(np.int64)) != 1).sum())}")
print(f"block gaps >1s      : {len(big)}")
for i in big[:10]:
    print(f"   at {pd.to_datetime(b['timestamp'][i], unit='s')}  gap {gap[i]:+.1f}s")
ev = b['events'] & 0x01
print(f"resume-logging flags: {int(ev.sum())}")

# ---- housekeeping --------------------------------------------------
print(f"\n-- housekeeping --")
print(f"battery   : {b['battery_v'][0]:.2f} V -> {b['battery_v'][-1]:.2f} V "
      f"(drop {b['battery_v'][0]-b['battery_v'][-1]:.3f} V over {span/3600:.1f} h)")
print(f"temp      : min {b['temperature'].min():.1f}  mean {b['temperature'].mean():.1f}  max {b['temperature'].max():.1f} C")
print(f"light raw : min {b['light'].min()}  median {np.median(b['light']):.0f}  max {b['light'].max()}")

# ---- activity ------------------------------------------------------
mag = np.sqrt(x*x + y*y + z*z)
enmo = np.clip(mag - 1.0, 0, None)
df = pd.DataFrame({'enmo': enmo, 'mag': mag}, index=t)
ep = df.resample('60s').agg(enmo=('enmo','mean'), sd=('mag','std'), n=('enmo','size'))
ep = ep[ep['n'] > 30]
ep['enmo_mg'] = ep['enmo'] * 1000

print(f"\n-- activity (60 s epochs, n={len(ep)}) --")
q = ep['enmo_mg'].quantile([.05,.10,.25,.50,.75,.90,.95,.99])
for k,v in q.items():
    print(f"  p{int(k*100):<3} {v:8.2f} mg")
print(f"  mean {ep['enmo_mg'].mean():.2f} mg   max {ep['enmo_mg'].max():.1f} mg")

for thr in (5, 10, 15, 20, 30):
    frac = (ep['enmo_mg'] < thr).mean()
    print(f"  below {thr:>2} mg : {frac*100:5.1f}%  ({frac*24:.1f} h/day equivalent)")

ep['hour'] = ep.index.hour
hourly = ep.groupby('hour')['enmo_mg'].mean()
print(f"\n-- mean activity by hour of day (mg) --")
for hh in range(24):
    if hh in hourly.index:
        v = hourly[hh]
        bar = '#' * int(min(v, 60) / 1.5)
        print(f"  {hh:02d}:00  {v:7.2f}  {bar}")

ep.to_csv('toast_epochs.csv')
print(f"\nwrote toast_epochs.csv ({len(ep)} rows)")
