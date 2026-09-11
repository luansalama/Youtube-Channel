from pathlib import Path
p = Path('tests/test_video_cutlist_workflow.py')
s = p.read_text(encoding='utf-8')
old = '{"offset_seconds":0,"method":"single-source-canonical-media","confidence":1.0}'
new = '{"offset_seconds":0.001,"method":"single-source-canonical-media","confidence":1.0}'
if s.count(old) != 1:
    raise SystemExit(f'expected one sync fixture, found {s.count(old)}')
s = s.replace(old, new)
extra = r'''


def test_server_cutlist_generate_endpoint_starts_detached_semantic_job(tmp_path, monkeypatch):
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from cstudio.server import Handler

    root, video_id = _root(tmp_path)
    captured = {}
    def fake_start_job(root_arg, slug, job_type, **params):
        captured.update({"root": root_arg, "slug": slug, "job_type": job_type, **params})
        return {"id":"job-cutlist","status":"running","type":job_type,"slug":slug}
    monkeypatch.setattr(J, "start_job", fake_start_job)
    Handler.root = root
    Handler.csrf_token = "csrf-cutlist"
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps({"slug":"cutlist-flow","video_id":video_id,"request":"preserve payoff","runner":"codex","model":"gpt-x","reasoning_effort":"high"}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/action/video-cutlist-generate",
            data=payload, headers={"Content-Type":"application/json","Accept":"application/json"}, method="POST",
        )
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
        assert data["ok"] is True and data["job"]["id"] == "job-cutlist"
        assert captured["job_type"] == "video-cutlist"
        assert captured["video_id"] == video_id
        assert captured["runner"] == "codex" and captured["model"] == "gpt-x" and captured["reasoning_effort"] == "high"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
'''
if 'def test_server_cutlist_generate_endpoint_starts_detached_semantic_job' not in s:
    s += extra
p.write_text(s, encoding='utf-8', newline='\n')
