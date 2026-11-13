"""Configuración común de las pruebas de Mini Yolotzin.

Ejecutar desde la raíz del repositorio:
    pip install -r requirements.txt -r requirements-dev.txt
    python -m playwright install chromium
    pytest
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import socketserver
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load_js_object(path: Path) -> dict:
    """Lee archivos del tipo `window.NOMBRE = {...};`."""
    text = path.read_text(encoding="utf-8")
    start = text.index("=", text.index("window.")) + 1
    body = text[start:].strip()
    if body.endswith(";"):
        body = body[:-1]
    # metro-catalog.js puede llevar un comentario antes de la asignación.
    return json.loads(body)


@pytest.fixture(scope="session")
def model_data() -> dict:
    return load_js_object(ROOT / "model-data.js")


@pytest.fixture(scope="session")
def catalog() -> dict:
    return load_js_object(ROOT / "metro-catalog.js")


@pytest.fixture(scope="session")
def weather() -> dict:
    return load_js_object(ROOT / "weather-summary.js")


# ---------- Servidor local y navegador para las pruebas de la página ----------

class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # sin ruido en la salida de pytest
        pass


@pytest.fixture(scope="session")
def site_url():
    """Sirve el repositorio por http, como GitHub Pages (necesario para el service worker)."""
    handler = functools.partial(_QuietHandler, directory=str(ROOT))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{server.server_address[1]}/"
        server.shutdown()


@pytest.fixture(scope="session")
def browser():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as p:
        # En entornos con un Chromium ya instalado, se puede indicar su ruta con PW_CHROMIUM_PATH.
        executable = os.environ.get("PW_CHROMIUM_PATH") or None
        browser = p.chromium.launch(executable_path=executable)
        yield browser
        browser.close()


@pytest.fixture()
def page(browser, site_url):
    """Página nueva con perfil creado; falla la prueba si hay errores de JavaScript."""
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    # Ecobici en vivo se sustituye por datos de prueba: las pruebas no dependen de internet.
    context.ecobici_mode = "ok"

    def ecobici(route):
        if context.ecobici_mode == "fail":
            return route.abort()
        name = "station_information" if "station_information" in route.request.url else "station_status"
        route.fulfill(path=str(ROOT / "tests" / "fixtures" / f"ecobici_{name}.json"),
                      headers={"access-control-allow-origin": "*", "content-type": "application/json"})
    context.route("https://gbfs.mex.lyftbikes.com/**", ecobici)
    page = context.new_page()
    page.set_default_timeout(5000)   # si algo falla, que se reporte rápido
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.goto(site_url)
    page.fill("#profileNameInput", "Prueba")
    page.click(".profile-submit")
    yield page
    context.close()
    ignorable = ("ERR_INTERNET_DISCONNECTED", "ERR_FAILED")   # red cortada a propósito en algunas pruebas
    assert not [e for e in errors if not any(x in e for x in ignorable)], f"Errores de JavaScript: {errors}"


def set_date(page, iso: str) -> None:
    page.fill("#dateInput", iso)
    page.dispatch_event("#dateInput", "change")


def model_value(model_data: dict, line: str, name: str, iso: str) -> int:
    from datetime import date
    record = next(r for r in model_data["stations"] if r["line"] == line and r["name"] == name)
    offset = (date.fromisoformat(iso) - date.fromisoformat(model_data["dataset"]["forecastStart"])).days
    return record["predictions"][offset]
