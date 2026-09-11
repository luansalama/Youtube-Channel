from pathlib import Path
p = Path('tests/test_video_cutlist_workflow.py')
s = p.read_text(encoding='utf-8')
old = '{"offset_seconds":0,"method":"single-source-canonical-media","confidence":1.0}'
new = '{"offset_seconds":0.001,"method":"single-source-canonical-media","confidence":1.0}'
if s.count(old) != 1:
    raise SystemExit(f'expected one sync fixture, found {s.count(old)}')
p.write_text(s.replace(old, new), encoding='utf-8', newline='\n')
