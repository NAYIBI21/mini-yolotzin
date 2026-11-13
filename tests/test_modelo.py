"""Funciones del script del modelo (scripts/build_model_data.py)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

import build_model_data as model


@pytest.mark.parametrize("year, expected", [(2025, date(2025, 4, 20)), (2026, date(2026, 4, 5)), (2027, date(2027, 3, 28))])
def test_easter(year, expected):
    assert model.easter_sunday(year) == expected


def test_mexican_holidays_2026():
    holidays, special, periods = model.mexican_calendar(range(2026, 2027))
    assert holidays[date(2026, 2, 2)] == "Día de la Constitución"
    assert holidays[date(2026, 3, 16)] == "Natalicio de Benito Juárez"
    assert holidays[date(2026, 11, 16)] == "Día de la Revolución"
    assert special[date(2026, 4, 3)] == "Viernes Santo"
    assert special[date(2026, 12, 12)] == "Día de la Virgen de Guadalupe"
    assert periods[date(2026, 12, 25)] == "Vacaciones de invierno"


def test_calendar_features_and_bridge():
    features = model.features(pd.DatetimeIndex(["2026-11-13", "2026-11-16", "2026-11-17"]))
    assert list(features["bridge"]) == [1, 0, 0]       # viernes antes del lunes festivo
    assert list(features["holiday"]) == [0, 1, 0]
    assert model.calendar_labels(pd.DatetimeIndex(["2026-11-16"]))["2026-11-16"] == "Día festivo: Día de la Revolución"


@pytest.mark.parametrize("csv_name, catalog_name", [
    ("Gómez Farías", "Gomez Farías"),
    ("UAM-Azcapotzalco", "UAM Azcapotzalco"),
    ("Niños Héroes", "Niños Héroes/Poder Judicial CDMX"),
    ("Mixiuhca", "Mixhiuca"),
    ("Isabel la Católica", "Isabel La Católica"),
])
def test_station_key_matches_csv_and_catalog(csv_name, catalog_name):
    assert model.station_key(csv_name) == model.station_key(catalog_name)


def test_unify_station_names_uses_first_spelling():
    frame = pd.DataFrame({
        "fecha": pd.to_datetime(["2023-05-31", "2023-06-01"]),
        "linea": ["Línea 1", "Línea 1"],
        "estacion": ["Gómez Farías", "Gómez Farias"],
        "afluencia": [10, 12],
    })
    unified, renamed = model.unify_station_names(frame)
    assert set(unified["estacion"]) == {"Gómez Farías"}
    assert renamed == [{"line": "Línea 1", "from": "Gómez Farias", "to": "Gómez Farías"}]


def _synthetic_series(days: int = 900, base: float = 10000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    values = [base * (0.5 if d.day_of_week >= 5 else 1) * rng.uniform(.95, 1.05) for d in dates]
    return pd.DataFrame({"fecha": dates, "afluencia": np.round(values)})


def test_build_record_excludes_closures_and_predicts_horizon():
    """Datos sintéticos solo para probar el código; no se publican."""
    data = _synthetic_series()
    data.loc[100:129, "afluencia"] = 0                # un mes cerrado por obras
    max_date = data["fecha"].max()
    horizon = pd.date_range(max_date + pd.Timedelta(days=1), periods=30)
    record, skip = model.build_record("3", "Prueba", data, max_date, horizon)
    assert skip is None
    assert record["summary"]["closedDays"] == 30
    assert len(record["predictions"]) == 30
    weekday = [v for d, v in zip(horizon, record["predictions"]) if d.day_of_week < 5]
    weekend = [v for d, v in zip(horizon, record["predictions"]) if d.day_of_week >= 5]
    assert np.mean(weekday) > np.mean(weekend) * 1.5     # aprende la diferencia hábil / fin de semana


def test_build_record_skips_stale_station():
    data = _synthetic_series(days=500)
    max_date = data["fecha"].max() + pd.Timedelta(days=60)  # el resto de la red tiene datos más recientes
    record, skip = model.build_record("12", "Cerrada", data, max_date, pd.date_range(max_date, periods=5))
    assert record is None and "sin datos recientes" in skip["reason"]


def test_event_adjustment_uses_past_editions():
    data = _synthetic_series(days=1000, base=5000)
    event_days = [pd.Timestamp("2024-06-15"), pd.Timestamp("2025-06-14"), pd.Timestamp("2026-06-13")]
    for day in event_days[:2]:
        data.loc[data["fecha"] == day, "afluencia"] *= 3   # dos ediciones pasadas triplican la afluencia
    max_date = data["fecha"].max()
    future = pd.Timestamp(max_date + pd.Timedelta(days=10))
    events = [{"fecha": d, "grupo": "Prueba", "stations": [("9", "prueba")]} for d in event_days[:2] + [future]]
    horizon = pd.date_range(max_date + pd.Timedelta(days=1), periods=20)
    record, _ = model.build_record("9", "Prueba", data, max_date, horizon, events)
    adjustment = next(a for a in record["eventAdjustments"] if a["date"] == future.strftime("%Y-%m-%d"))
    assert adjustment["editions"] == 2 and adjustment["factor"] == pytest.approx(3, rel=.15)
