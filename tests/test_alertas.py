"""Yolotzin Alerta ahora es la sección «¿Cómo va?» dentro de la app (antes, alertas.html aparte)."""
from pathlib import Path

import pytest

from conftest import ROOT


def test_alertas_html_redirects_to_app():
    html = (ROOT / "alertas.html").read_text(encoding="utf-8")
    assert 'url=./#como-va' in html and 'href="./#como-va"' in html   # los enlaces viejos siguen funcionando
    assert "<script" not in html


@pytest.mark.pagina
def test_report_without_server_stays_on_this_device(page):
    page.click("#alertButton")                                         # botón «🚨 ¿Cómo va?» del encabezado
    assert page.is_visible("#reportPanel")                             # se abre como ventana, sobre la pestaña actual
    assert "solo en este celular" in page.text_content("#reportMode")
    assert "no verificados" not in page.text_content("#reportPanel")
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url) if "/api/" in r.url else None)
    page.click('.report-level[data-level="lleno"]')
    page.click('.incident[data-incident="accidente"]')
    page.click("#reportSend")
    summary = page.text_content("#reportSummary")
    assert "Mayoría: lleno" in summary and "Accidente o persona lesionada (1)" in summary
    assert "911" in page.text_content("#reportPanel")
    assert requests == []                                              # sin servidor no se envía nada
    page.reload()
    page.goto(page.url.split("#")[0] + "#como-va")
    page.reload()
    page.wait_for_selector("#reportOverlay:not([hidden])")
    assert "1 reporte" in page.text_content("#reportSummary")        # sigue en este navegador


@pytest.mark.pagina
def test_como_va_only_opens_on_demand(page):
    page.click("#tab-explore")
    assert page.locator("#exploreView #reportPanel").count() == 0     # no está dentro de la ficha
    assert not page.is_visible("#reportPanel")
    assert page.locator("#reportButton").count() == 0                # un solo botón: «🚨 ¿Cómo va?»
    page.click("#alertButton")
    assert page.is_visible("#reportPanel")
    page.select_option("#reportStationSelect", "3|Hidalgo")           # se puede elegir otra estación ahí mismo
    assert "Hidalgo · Línea 3" in page.text_content("#reportStation")
    page.keyboard.press("Escape")
    assert not page.is_visible("#reportPanel")
    page.click("#alertButton")
    page.click("#reportClose")
    assert not page.is_visible("#reportPanel")


@pytest.mark.pagina
def test_header_fits_on_phone(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("document.getElementById('installApp').hidden = false")   # como en iPhone/Android
    boxes = [page.locator(sel).bounding_box() for sel in (".brand .logo", "#alertButton", "#installApp", "#profileButton")]
    for left, right in zip(boxes, boxes[1:]):
        assert left["x"] + left["width"] <= right["x"] + 1, "botones encimados en el encabezado"
    assert boxes[-1]["x"] + boxes[-1]["width"] <= 390
