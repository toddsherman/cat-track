import sys, json, pathlib
src = pathlib.Path(sys.argv[1] if len(sys.argv)>1 else 'toast_viewer.json')
d = json.loads(src.read_text())
tpl = pathlib.Path('cattrack/viewer_template.html').read_text()
name = d['name'][:1].upper()+d['name'][1:]
html = (tpl.replace('__DATA__', json.dumps(d, separators=(',',':')))
           .replace('__NAME__', name)
           .replace('__DEVICE__', str(d['device']))
           .replace('__SESSION__', str(d['session'])))
out = pathlib.Path(f"{d['name']}_viewer.html"); out.write_text(html)
print(f"{out}  ({len(html)/1024:.0f} KB)")
