"""Validación del planificador de Metro y de los tiempos GTFS archivados."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_object(file: str):
    source = (ROOT / file).read_text(encoding="utf-8")
    return json.loads(source[source.index("=") + 1:].strip().rstrip(";"))


def test_gtfs_cubre_todos_los_tramos_en_ambos_sentidos():
    catalog = load_object("metro-catalog.js")
    gtfs = load_object("gtfs-segments.js")
    assert len(catalog["stations"]) == 195
    assert gtfs["coverage"]["directedSegments"] == 366
    by_line = {}
    for stop in catalog["stations"]:
        by_line.setdefault(stop["line"], []).append(stop)
    assert len(by_line) == 12
    assert set(by_line) == set(gtfs["headways"])
    for line, stations in by_line.items():
        for a, b in zip(stations, stations[1:]):
            for frm, dest in ((a, b), (b, a)):
                key = frm["id"] + ">" + dest["id"]
                assert key in gtfs["segments"], f"Tramo sin GTFS: {key}"
                assert 0.3 < gtfs["segments"][key] < 10
        assert set(gtfs["headways"][line]) == {"1", "2", "3"}


def test_planificador_navegador_rutas(page):
    page.click("#tab-routes")
    assert page.is_visible("#routesView")
    assert page.is_visible("#routesForm")
    assert page.locator("#routesFrom option").count() == 163
    page.select_option("#routesFrom", "Hidalgo")
    page.select_option("#routesTo", "Pantitlán")
    page.click("#routesForm button[type=submit]")
    page.wait_for_function("document.querySelectorAll('#routesResults .planner-route').length >= 2")
    assert "Ruta recomendada" in page.text_content("#routesResults")
    assert "min" in page.text_content("#routesResults")
    assert "Transbordo" not in page.text_content("#routesMessage")
    page.select_option("#routesPreference", "tranquila")
    assert page.locator("#routesResults .planner-route").count() >= 2
    page.click("#routesSwap")
    assert page.input_value("#routesFrom") == "Pantitlán"
    assert page.input_value("#routesTo") == "Hidalgo"


def test_planificador_fecha_sin_prediccion_no_inventa_nivel(page):
    page.click("#tab-routes")
    page.select_option("#routesFrom", "Hidalgo")
    page.select_option("#routesTo", "Universidad")
    page.click("#routesForm button[type=submit]")
    page.wait_for_selector("#routesResults .planner-route")
    assert "L3" in page.text_content("#routesResults")
    page.evaluate("""() => {
      const el = document.querySelector('#dateInput');
      el.value = '2027-12-31';
      el.dispatchEvent(new Event('change', {bubbles:true}));
    }""")
    page.wait_for_function("document.querySelector('#routesMessage').textContent.includes('fuera del horizonte')")
