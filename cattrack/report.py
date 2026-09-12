import sys, numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
sys.path.insert(0,'.')
from cattrack import cwa

path = sys.argv[1] if len(sys.argv)>1 else 'CWA-DATA.CWA'
h,b,s = cwa.read(path)
name = h['annotation'].split('=')[-1] or 'unknown'
t = pd.to_datetime(s['t'], unit='s')
mag = np.sqrt(s['x']**2 + s['y']**2 + s['z']**2)
enmo = np.clip(mag-1.0, 0, None)

df = pd.DataFrame({'enmo':enmo}, index=t)
ep = df.resample('60s').agg(enmo=('enmo','mean'), n=('enmo','size'))
ep = ep[ep['n']>30]; ep['mg'] = ep['enmo']*1000

bt = pd.DataFrame({'temp':b['temperature'],'batt':b['battery_v'],'light':b['light']},
                  index=pd.to_datetime(b['timestamp']+b['fraction'], unit='s')).resample('60s').mean()
ep = ep.join(bt, how='left').ffill()

print(f"=== {name}  |  {t[0]:%Y-%m-%d %H:%M} -> {t[-1]:%Y-%m-%d %H:%M}  ({(s['t'][-1]-s['t'][0])/3600:.1f} h) ===\n")

# distribution shape -> is it bimodal?
lg = np.log10(ep['mg'].clip(lower=0.01))
hist,edges = np.histogram(lg, bins=40)
print("log10(ENMO mg) distribution:")
for c,e in zip(hist,edges):
    if c: print(f"  {10**e:8.2f} mg |{'#'*int(60*c/hist.max())} {c}")

# threshold sweep w/ bout structure
print("\nthreshold sweep (rest = ENMO below X mg, min bout 5 min):")
for thr in (3,5,8,10,15,20):
    rest = ep['mg'] < thr
    grp = (rest != rest.shift()).cumsum()
    bouts = ep.groupby(grp).agg(rest=('mg', lambda v: (v<thr).iloc[0]), mins=('mg','size'))
    rb = bouts[bouts['rest'] & (bouts['mins']>=5)]
    print(f"  <{thr:>2} mg : rest {rest.mean()*100:4.1f}% ({rest.mean()*24:4.1f} h/day) | "
          f"{len(rb):3d} bouts >=5min, median {rb['mins'].median():.0f} min, longest {rb['mins'].max():.0f} min")

# wear check via temperature
print(f"\ntemperature: mean {ep['temp'].mean():.1f} C, "
      f"{(ep['temp']>30).mean()*100:.1f}% of epochs above 30 C (body contact)")
cold = ep[ep['temp']<30]
if len(cold): print(f"  below 30 C: {cold.index[0]:%m-%d %H:%M} -> {cold.index[-1]:%m-%d %H:%M} ({len(cold)} min)")

# ---- plot ----
fig,axes = plt.subplots(3,1, figsize=(14,8), sharex=True,
                        gridspec_kw={'height_ratios':[3,1,1]})
ax=axes[0]
ax.fill_between(ep.index, ep['mg'], color='#4c72b0', lw=0)
ax.axhline(8, color='#c44e52', ls='--', lw=1, label='rest threshold 8 mg')
for d in pd.date_range(ep.index[0].floor('D'), ep.index[-1], freq='D'):
    ax.axvspan(max(d+pd.Timedelta('22h'), ep.index[0]), min(d+pd.Timedelta('30h'), ep.index[-1]),
               color='k', alpha=.07, lw=0)
ax.set_ylabel('ENMO (mg)'); ax.legend(loc='upper right', fontsize=8)
ax.set_title(f'{name} — activity, 60 s epochs (shaded = 22:00–06:00)')
axes[1].plot(ep.index, ep['temp'], color='#dd8452'); axes[1].axhline(30, color='gray', ls=':', lw=1)
axes[1].set_ylabel('temp (C)')
axes[2].plot(ep.index, ep['batt'], color='#55a868'); axes[2].set_ylabel('batt (V)')
axes[2].xaxis.set_major_formatter(mdates.DateFormatter('%b %d\n%H:%M'))
plt.tight_layout(); plt.savefig(f'{name}_activity.png', dpi=130)
ep.to_csv(f'{name}_epochs.csv')
print(f"\nwrote {name}_activity.png and {name}_epochs.csv")
