import shutil
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from cstudio import core as C
from cstudio import dashboard as D
from cstudio.server import Handler


REPO = Path(__file__).resolve().parents[1]


def _harness(tmp_path):
    root = tmp_path / "harness"
    shutil.copytree(REPO / "studio", root / "studio")
    shutil.copytree(REPO / "templates", root / "templates")
    C.create_production(
        str(root),
        "UI test",
        slug="ui-test",
        source_url="https://www.twitch.tv/alanzoka/videos",
    )
    return str(root)


def test_dashboard_uses_external_assets_and_csrf(tmp_path):
    root = _harness(tmp_path)
    page = D.render(root, "production", "ui-test", csrf_token="csrf-test")
    assert '/static/dashboard.css?v=2' in page
    assert '/static/dashboard.js?v=2' in page
    assert '<script>' not in page
    assert 'style=' not in page
    assert 'name="csrf_token" value="csrf-test"' in page
    assert "Próxima ação" in page
    assert "dark" not in page.lower() or 'content="dark"' in page


def test_twitch_page_uses_partial_live_run_polling(tmp_path):
    root = _harness(tmp_path)
    page = D.render(root, "twitch", "ui-test", csrf_token="csrf-test")
    assert "Twitch Ingest" in page
    assert '/ui/twitch-run?slug=ui-test' in page
    assert "location.reload" not in page
    assert "name='threads'" in page
    assert ">8 workers</option>" in page
    fragment = D.render_twitch_run(root, "ui-test")
    assert 'data-twitch-live' in fragment
    assert 'data-running="false"' in fragment


def test_dashboard_static_assets_are_packaged_sources():
    css = REPO / "cstudio" / "static" / "dashboard.css"
    js = REPO / "cstudio" / "static" / "dashboard.js"
    assert css.is_file() and css.stat().st_size > 10_000
    assert js.is_file() and js.stat().st_size > 2_000
    text = js.read_text(encoding="utf-8")
    assert "fetch(endpoint" in text
    assert "location.reload" not in text
    assert "prefers-reduced-motion" in text



def test_server_serves_static_assets_csp_and_enforces_form_csrf(tmp_path):
    root = _harness(tmp_path)
    Handler.root = root
    Handler.csrf_token = "csrf-server-test"
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(base + "/?page=production&slug=ui-test") as response:
            page = response.read().decode("utf-8")
            csp = response.headers.get("Content-Security-Policy", "")
        assert "script-src 'self'" in csp
        assert "unsafe-inline" not in csp
        assert 'name="csrf_token" value="csrf-server-test"' in page

        with urllib.request.urlopen(base + "/static/dashboard.css") as response:
            assert response.headers.get_content_type() == "text/css"
            assert len(response.read()) > 10_000

        bad = urllib.request.Request(
            base + "/action/maintain",
            data=urllib.parse.urlencode({"slug": "ui-test"}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            urllib.request.urlopen(bad)
            assert False, "POST sem CSRF deveria falhar"
        except urllib.error.HTTPError as exc:
            assert exc.code == 400

        good = urllib.request.Request(
            base + "/action/maintain",
            data=urllib.parse.urlencode({"slug": "ui-test", "csrf_token": "csrf-server-test"}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(good) as response:
            assert response.status == 200  # urllib seguiu o 303 para o dashboard
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
