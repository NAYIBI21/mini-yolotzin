"""Coherencia de los archivos de datos publicados con la página."""

from __future__ import annotations

import csv
from datetime import date, timedelta

import build_model_data as model
from conftest import ROOT


def test_model_data_structure(model_data):
    ds = model_data["dataset"]
    assert ds["modeledRecords"] == len(model_data["stations"])
    assert ds["modeledRecords"] + ds["skippedRecords"] == ds["records"]
    start = date.fromisoformat(ds["forecastStart"])
    assert date.fromisoformat(ds["forecastEnd"]) == start + timedelta(days=ds["forecastDays"] - 1)
    assert date.fromisoformat(ds["endDate"]) + timedelta(days=1) == start
    for record in model_data["stations"]:
        assert len(record["predictions"]) == ds["forecastDays"], record["name"]
        assert all(isinstance(v, int) and v >= 0 for v in record["predictions"]), record["name"]
        s = record["summary"]
        assert 0 < s["lowThreshold"] <= s["highThreshold"], record["name"]
        assert record["metrics"]["modelMae"] >= 0 and record["metrics"]["baselineMae"] >= 0


def test_featured_stations_present(model_data):
    ids = {(r["line"], r["name"]) for r in model_data["stations"]}
    for featured in model_data["featured"]:
        assert (featured["line"], featured["name"]) in ids


def test_every_catalog_station_has_a_model_record(model_data, catalog):
    """Los nombres del CSV oficial y del catálogo difieren (acentos, signos); station_key los relaciona."""
    model_keys = {(r["line"], model.station_key(r["name"])) for r in model_data["stations"]}
    catalog_keys = {(c["line"], model.station_key(c["name"])) for c in catalog["stations"]}
    assert catalog_keys - model_keys == set()
    assert model_keys - catalog_keys == set()


def test_event_adjustments_are_consistent(model_data):
    horizon = set(model_data["events"]["calendar"])
    minimum = model_data["events"]["minEditions"]
    for record in model_data["stations"]:
        for adj in record.get("eventAdjustments", []):
            assert adj["date"] in horizon
            if adj["factor"] is None:
                assert adj["editions"] < minimum
            else:
                assert adj["editions"] >= minimum and adj["factor"] > 0


def test_events_csv_rows_are_valid(model_data):
    model_keys = {(r["line"], model.station_key(r["name"])) for r in model_data["stations"]}
    seen = set()
    with open(ROOT / "eventos.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "eventos.csv está vacío"
    for row in rows:
        date.fromisoformat(row["fecha"])  # formato AAAA-MM-DD
        assert row["grupo"] and row["nombre"] and row["recinto"], row
        assert row["tipo"] in {"deportivo", "concierto", "marcha", "cívico"}, row
        assert row["fuente"].strip(), f"Evento sin fuente: {row['fecha']} {row['nombre']}"
        assert (row["fecha"], row["grupo"]) not in seen, f"Evento duplicado: {row['fecha']} {row['grupo']}"
        seen.add((row["fecha"], row["grupo"]))
        for item in row["estaciones"].split(";"):
            line, name = item.split("|", 1)
            assert (line, model.station_key(name)) in model_keys, f"Estación desconocida en eventos.csv: {item}"


def test_calendar_labels_inside_horizon(model_data):
    ds = model_data["dataset"]
    for iso in model_data["calendar"]:
        assert ds["forecastStart"] <= iso <= ds["forecastEnd"]


def test_weather_summary_supports_decision(weather):
    """El clima solo puede entrar al modelo si mejora la estimación (regla de AGENTS.md)."""
    assert weather["records"] > 0
    assert weather["validation"]["changePct"] >= 0, "Si el clima ya mejora la estimación, revisar la decisión y AGENTS.md"


def test_service_worker_lists_existing_files():
    text = (ROOT / "sw.js").read_text(encoding="utf-8")
    files = text[text.index("FILES = [") + 9:text.index("];", text.index("FILES = ["))]
    for item in [f.strip().strip("'\"") for f in files.split(",") if f.strip()]:
        if item in ("./",):
            continue
        assert (ROOT / item.removeprefix("./")).exists(), f"sw.js guarda un archivo que no existe: {item}"
