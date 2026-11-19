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
    assert page.is_visible("#exploreView") and page.is_visible("#reportPanel")
    assert "solo en este dispositivo" in page.text_content("#reportMode")
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
    page.wait_for_selector("#reportPanel:not([hidden])")
    assert "1 reporte" in page.text_content("#reportSummary")        # sigue en este navegador
