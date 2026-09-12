import sys, json, numpy as np, pandas as pd
sys.path.insert(0,'.')
from cattrack import cwa, sleep

path = sys.argv[1] if len(sys.argv)>1 else 'CWA-DATA.CWA'
h,b,s = cwa.read(path)
name = (h['annotation'].split('=')[-1] or 'unknown').strip()

ep = sleep.epochs(s['t'], s['x'], s['y'], s['z'], b['timestamp']+b['fraction'], b['temperature'])
k = sleep.calibrate(ep)
ep['mmag'] *= k
ep['mg'] = (ep['mmag']-1).clip(lower=0)*1000
ep, params = sleep.classify(ep, move_thr=8.0, angle_thr=0.75)
params['calibration'] = round(float(k),5)

step = (ep.index[1]-ep.index[0]).total_seconds()
for st in ('sleep','rest','active'):
    params[f'{st}_hours'] = round(float((ep['state']==st).sum()*step/3600), 2)
iv = [i for i in sleep.intervals(ep) if i['state']=='sleep']
d = [(i['end']-i['start'])/60 for i in iv]
params.update(sleep_bouts=len(d),
              median_bout_min=round(float(np.median(d)),1) if d else 0,
              longest_bout_min=round(float(max(d)),1) if d else 0)

out = {
  'name': name,
  'device': int(h['device_id']), 'session': int(h['session_id']),
  'rate': h['config_rate_hz'], 'range_g': h['config_range_g'],
  't0': float(ep.index[0].timestamp()), 'step': step,
  'n': len(ep),
  'mg':     [round(float(v),2) for v in ep['mg'].fillna(0)],
  'dangle': [round(float(v),3) for v in ep['dangle'].fillna(0)],
  'temp':   [round(float(v),1) for v in ep['temp'].ffill().bfill().fillna(0)],
  'params': params,
}
json.dump(out, open(f'{name}_viewer.json','w'), separators=(',',':'))
print(json.dumps(params, indent=2))
print(f"\n{len(ep):,} epochs @ {step:.0f}s -> {name}_viewer.json "
      f"({len(open(f'{name}_viewer.json').read())/1024:.0f} KB)")
