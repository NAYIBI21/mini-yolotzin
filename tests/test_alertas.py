"""Pruebas de humo del prototipo Yolotzin Alerta (sin backend)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_alertas_pagina_y_enlace():
    html = (ROOT / "alertas.html").read_text(encoding="utf-8")
    home = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "<!doctype html>" in html.lower()
    assert 'id="reportForm"' in html
    assert 'id="station"' in html
    assert 'id="feed"' in html
    assert 'href="./alertas.html"' in home


def test_alertas_tipos_y_catalogo():
    html = (ROOT / "alertas.html").read_text(encoding="utf-8")
    assert '<script src="./metro-catalog.js"></script>' in html
    for kind in (
        "Estación saturada",
        "Retraso o tren detenido",
        "Estación cerrada",
        "Servicio suspendido",
        "Accidente o emergencia",
        "Otra incidencia",
    ):
        assert kind in html


def test_alertas_prototipo_local_y_seguridad():
    html = (ROOT / "alertas.html").read_text(encoding="utf-8")
    assert "TTL=60*60*1000" in html
    assert "localStorage.setItem(KEY" in html
    assert "p.textContent=r.details" in html
    assert "No se comparten con otros usuarios" in html
    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html
