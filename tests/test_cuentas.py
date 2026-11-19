"""Pruebas del servidor de cuentas (scripts/servidor_cuentas.py) y del inicio de sesión en la página."""

from __future__ import annotations

import http.cookiejar
import http.server
import json
import sqlite3
import threading
import urllib.error
import urllib.request

import pytest

from conftest import ROOT
import servidor_cuentas as sc


@pytest.fixture()
def account_server(tmp_path):
    db = tmp_path / "cuentas.db"
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), sc.make_handler(sc.Store(db)))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/", db
    server.shutdown()
    server.server_close()


def client():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def call(url, method="GET", payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
        try:
            with opener.open(req, timeout=5) as res:
                return res.status, json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as err:
            body = err.read()
            return err.code, (json.loads(body) if body.startswith(b"{") else {})
    return call


def test_password_hash_is_salted_and_checked():
    a, b = sc.hash_password("secreto123"), sc.hash_password("secreto123")
    assert a != b and "secreto123" not in a
    assert sc.check_password("secreto123", a)
    assert not sc.check_password("otra-clave", a)


def test_register_login_and_trips(account_server):
    base, db = account_server
    call = client()
    assert call(base + "api/estado") == (200, {"cuentas": True, "usuario": None})
    assert call(base + "api/viajes")[0] == 401
    status, body = call(base + "api/registro", "POST", {"usuario": "Nayibi", "contrasena": "clave-segura"})
    assert (status, body) == (200, {"usuario": "nayibi"})
    assert call(base + "api/registro", "POST", {"usuario": "nayibi", "contrasena": "otra-clave1"})[0] == 409
    trips = [{"id": "t1", "label": "Casa", "from": {"name": "Hidalgo", "line": "3"}, "to": None}]
    assert call(base + "api/viajes", "PUT", {"viajes": trips})[0] == 200
    assert call(base + "api/viajes", "PUT", {"viajes": [{"id": 1}]})[0] == 400

    other = client()                                    # otro navegador: inicia sesión y ve sus viajes
    assert call(base + "api/salir", "POST")[0] == 200
    assert call(base + "api/estado")[1]["usuario"] is None
    assert other(base + "api/entrar", "POST", {"usuario": "nayibi", "contrasena": "mal-clave"})[0] == 401
    assert other(base + "api/entrar", "POST", {"usuario": "nayibi", "contrasena": "clave-segura"})[0] == 200
    assert other(base + "api/viajes") == (200, {"viajes": trips})

    with sqlite3.connect(db) as con:                     # la base no guarda contraseñas ni tokens en texto
        stored = con.execute("SELECT clave_hash FROM usuarios").fetchone()[0]
    assert stored.startswith("scrypt$") and "clave-segura" not in stored
    assert b"clave-segura" not in db.read_bytes()


def test_reports_are_anonymous_and_limited(account_server):
    base, db = account_server
    call = client()
    url = base + "api/reportes?estacion=Hidalgo&linea=3"
    assert call(url) == (200, {"vacio": 0, "normal": 0, "lleno": 0, "total": 0, "minutos": None, "ventana": 30})
    report = {"estacion": "Hidalgo", "linea": "3", "nivel": "lleno"}
    assert call(base + "api/reportes", "POST", report)[0] == 401          # sin sesión no se reporta
    call(base + "api/registro", "POST", {"usuario": "beto", "contrasena": "clave-segura"})
    assert call(base + "api/reportes", "POST", {**report, "nivel": "a reventar"})[0] == 400
    status, summary = call(base + "api/reportes", "POST", report)
    assert status == 200 and summary["lleno"] == 1 and summary["total"] == 1
    assert call(base + "api/reportes", "POST", report)[0] == 429          # una vez cada 10 minutos
    other = client()
    other(base + "api/registro", "POST", {"usuario": "carla", "contrasena": "clave-segura"})
    other(base + "api/reportes", "POST", {**report, "nivel": "normal"})
    assert call(url)[1]["total"] == 2
    assert call(base + "api/reportes?estacion=Hidalgo&linea=2")[1]["total"] == 0
    with sqlite3.connect(db) as con:                                       # sin usuario en la tabla
        columns = [row[1] for row in con.execute("PRAGMA table_info(reportes)")]
    assert columns == ["estacion", "linea", "nivel", "creado"]


def test_rejects_bad_input_and_locks_after_failures(account_server):
    base, _ = account_server
    call = client()
    assert call(base + "api/registro", "POST", {"usuario": "a", "contrasena": "clave-segura"})[0] == 400
    assert call(base + "api/registro", "POST", {"usuario": "ana", "contrasena": "corta"})[0] == 400
    assert call(base + "api/registro", "POST", {"usuario": "ana", "contrasena": "clave-segura"})[0] == 200
    for _ in range(sc.MAX_FAILURES):
        assert call(base + "api/entrar", "POST", {"usuario": "ana", "contrasena": "equivocada"})[0] == 401
    assert call(base + "api/entrar", "POST", {"usuario": "ana", "contrasena": "clave-segura"})[0] == 429


def test_rejects_other_origins(account_server):
    base, _ = account_server
    req = urllib.request.Request(base + "api/registro", method="POST",
                                 data=json.dumps({"usuario": "eva", "contrasena": "clave-segura"}).encode(),
                                 headers={"Content-Type": "application/json", "Origin": "https://otra-pagina.example"})
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req, timeout=5)
    assert err.value.code == 403


@pytest.mark.parametrize("path", [".git/config", "scripts/servidor_cuentas.py", "tests/conftest.py",
                                  "%2e%2e/etc/passwd", "icons/../.git/HEAD", "cuentas.db"])
def test_serves_only_public_files(account_server, path):
    base, _ = account_server
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(base + path, timeout=5)
    assert err.value.code == 404


def test_serves_the_page(account_server):
    base, _ = account_server
    for path in ("", "model-data.js", "manifest.webmanifest", "icons/icon-192.png"):
        with urllib.request.urlopen(base + path, timeout=5) as res:
            assert res.status == 200
    assert (ROOT / "index.html").read_bytes() == urllib.request.urlopen(base, timeout=5).read()


def test_database_must_stay_outside_repo(monkeypatch):
    monkeypatch.setattr("sys.argv", ["servidor_cuentas.py", "--db", str(ROOT / "cuentas.db")])
    with pytest.raises(SystemExit):
        sc.main()
    assert not (ROOT / "cuentas.db").exists()


@pytest.mark.pagina
def test_login_in_page_keeps_trips(browser, account_server):
    base, _ = account_server
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.route("https://gbfs.mex.lyftbikes.com/**", lambda route: route.abort())
    page = context.new_page()
    page.set_default_timeout(5000)
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(base)
    page.wait_for_selector("#accountUser")                  # con servidor, se pide iniciar sesión
    page.fill("#accountUser", "nayibi")
    page.fill("#accountPassword", "corta")
    page.click("#registerButton")
    assert "8 caracteres" in page.text_content("#accountError")
    page.fill("#accountPassword", "clave-segura")
    page.click("#registerButton")
    page.wait_for_selector("#profileOverlay.hidden", state="attached")
    assert page.text_content("#profileDisplayName") == "nayibi"
    page.click("#tab-explore")
    page.click("#saveStation")
    assert page.locator(".trip-item").count() == 1

    # Reportar cómo está (solo con el servidor y con sesión).
    page.click("#reportButton")
    page.wait_for_function("document.querySelector('#reportSummary').textContent.includes('Aún no hay reportes')")
    page.click('.report-level[data-level="lleno"]')
    page.click("#reportSend")
    page.wait_for_function("document.querySelector('#reportSummary').textContent.includes('Mayoría: lleno')")
    assert "Gracias" in page.text_content("#reportMessage")

    # Otro dispositivo (contexto nuevo, sin localStorage): al entrar recupera el viaje del servidor.
    page2 = browser.new_context().new_page()
    page2.goto(base)
    page2.wait_for_selector("#accountUser")
    page2.fill("#accountUser", "nayibi")
    page2.fill("#accountPassword", "equivocada")
    page2.click("#accountForm button[type=submit]")
    page2.wait_for_function("document.querySelector('#accountError').textContent.includes('incorrectos')")
    page2.fill("#accountPassword", "clave-segura")
    page2.click("#accountForm button[type=submit]")
    page2.wait_for_selector("#profileOverlay.hidden", state="attached")
    page2.wait_for_function("document.querySelectorAll('.trip-item').length === 1")
    page2.context.close()

    page.reload()                                           # la sesión sigue al recargar
    page.wait_for_function("document.querySelector('#profileDisplayName').textContent === 'nayibi'")
    page.click("#profileButton")
    page.click("#logoutButton")
    page.wait_for_selector("#accountUser")
    assert page.locator(".trip-item").count() == 0          # al salir no quedan viajes de la cuenta
    page.click("#noAccountButton")                          # se puede seguir sin cuenta
    page.fill("#profileNameInput", "Invitada")
    page.click("#profileForm .profile-submit")
    assert page.text_content("#profileDisplayName") == "Invitada"
    context.close()
    assert not errors, errors
