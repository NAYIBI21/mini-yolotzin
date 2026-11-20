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
    # El selector global restringe el horizonte; forzamos el valor en el DOM
    # sin activar su validador, para comprobar el caso de datos fuera de rango.
    page.evaluate("document.querySelector('#dateInput').value = '2027-12-31'")
    page.click("#routesForm button[type=submit]")
    page.wait_for_function("document.querySelector('#routesMessage').textContent.includes('fuera del horizonte')")
    assert "sin pronóstico" in page.text_content("#routesResults")


def test_aviso_ciudadano_puede_cambiar_recomendacion(page):
    # Reportes y nivel de afluencia siguen siendo datos separados: la alerta
    # influye en la recomendación, sin presentarse como falla confirmada.
    switched = page.evaluate("""() => {
      const routing = window.MINI_YOLOTZIN_ROUTER;
      const graph = routing.buildGraph(
        window.METRO_CATALOG.stations, window.MINI_YOLOTZIN_GTFS, '1');
      const opts = {
        graph, from: 'Hidalgo', to: 'Pantitlán',
        records: window.MINI_YOLOTZIN_DATA.stations, dateIndex: 49
      };
      const normal = routing.recommend(routing.findRoutes(opts), 'equilibrada');
      const withAlert = routing.recommend(routing.findRoutes({
        ...opts, reports: [{
          estacion: 'Chabacano', linea: '9', afluencia: 'lleno',
          tipos: ['tren_detenido']
        }]
      }), 'equilibrada');
      return {
        changed: normal.fingerprint !== withAlert.fingerprint,
        initial: normal.legs.map(l => l.line),
        after: withAlert.legs.map(l => l.line)
      };
    }""")
    assert switched["changed"]
    assert switched["initial"] == ["2", "9"]
    assert switched["after"] == ["2", "1"]
