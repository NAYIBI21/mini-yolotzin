"""Mide si el clima cambia la afluencia diaria del Metro y si mejora la estimación.

El resultado NO entra al modelo: solo se publica un resumen (weather-summary.js)
para que la interfaz explique, con cifras medidas, por qué el clima no se usa.

Fuente del clima: reanálisis ERA5 vía Open-Meteo (CC BY 4.0), 5 zonas de la CDMX.
El Servicio Meteorológico Nacional no permite descargas automáticas.

Uso:
    python scripts/analizar_clima.py [ruta/al/afluencia_simple.csv] [ruta/clima.json]

Si no se indica el archivo de clima, se descarga y se guarda en clima_openmeteo.json
(ignorado por Git). Tarda unos tres minutos.
"""

from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_model_data as model  # noqa: E402  (reutiliza limpieza, variables y parámetros)

ROOT = Path(__file__).resolve().parents[1]
WEATHER_CACHE = ROOT / "clima_openmeteo.json"
OUTPUT_PATH = ROOT / "weather-summary.js"
CATALOG_PATH = ROOT / "metro-catalog.js"

# Zonas de la ciudad (lat, lon): centro, norte, sur, oriente, poniente.
ZONES = [
    ("Centro", 19.4326, -99.1332),
    ("Norte", 19.4950, -99.1190),
    ("Sur", 19.3320, -99.1780),
    ("Oriente", 19.4050, -99.0550),
    ("Poniente", 19.4030, -99.2000),
]
WEATHER_VARS = ["precipitation_sum", "precipitation_hours", "temperature_2m_max", "temperature_2m_min"]
RAIN_MM = 10      # día lluvioso
HEAVY_MM = 25     # lluvia fuerte (umbral del SMN)
DRY_MM = 1        # día seco
HOT_C = 28        # día caluroso
MILD_C = 25       # día templado


def download_weather(start: str, end: str) -> list[dict]:
    lats = ",".join(str(z[1]) for z in ZONES)
    lons = ",".join(str(z[2]) for z in ZONES)
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lats}&longitude={lons}&start_date={start}&end_date={end}"
        f"&daily={','.join(WEATHER_VARS)}&timezone=America%2FMexico_City"
    )
    with urllib.request.urlopen(url, timeout=180) as response:
        data = json.load(response)
    WEATHER_CACHE.write_text(json.dumps(data), encoding="utf-8")
    return data


def station_key(name: str) -> str:
    """Misma clave que usa index.html para relacionar el CSV con el catálogo."""
    k = unicodedata.normalize("NFD", name.split("/")[0])
    k = re.sub(r"[^a-z0-9]", "", "".join(c for c in k if unicodedata.category(c) != "Mn").lower())
    return {"mixhiuca": "mixiuhca"}.get(k, k)


def load_ridership(csv_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(csv_path, dtype={"linea": "string", "estacion": "string"})
    for column in ["linea", "estacion"]:
        frame[column] = frame[column].map(model.repair_mojibake)
    frame["linea"] = frame["linea"].str.strip().str.replace(r"^Linea ", "Línea ", regex=True)
    frame["estacion"] = frame["estacion"].str.strip()
    frame["fecha"] = pd.to_datetime(frame["fecha"], errors="coerce")
    frame["afluencia"] = pd.to_numeric(frame["afluencia"], errors="coerce")
    frame = frame.dropna(subset=["fecha", "linea", "estacion", "afluencia"])
    frame, _ = model.unify_station_names(frame)
    return frame[frame["afluencia"] > 0]


def with_weather(dates: pd.Series, weather: pd.DataFrame) -> pd.DataFrame:
    X = model.features(dates).reset_index(drop=True)
    w = weather.reindex(pd.DatetimeIndex(dates)).reset_index(drop=True)
    for column in WEATHER_VARS:
        X[column] = w[column].values
    return X


def spread(values: pd.Series) -> dict:
    values = values.dropna() * 100
    return {"median": round(float(values.median()), 1), "p10": round(float(values.quantile(.1)), 1),
            "p90": round(float(values.quantile(.9)), 1), "records": int(len(values))}


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else model.CSV_PATH
    ridership = load_ridership(csv_path)
    start, end = ridership["fecha"].min().strftime("%Y-%m-%d"), ridership["fecha"].max().strftime("%Y-%m-%d")
    if len(sys.argv) > 2:
        raw = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    else:
        raw = download_weather(start, end)
    raw = raw if isinstance(raw, list) else [raw]
    zones = []
    for (label, _, _), zone in zip(ZONES, raw):
        daily = pd.DataFrame(zone["daily"])
        daily["time"] = pd.to_datetime(daily["time"])
        zones.append({"label": label, "lat": zone["latitude"], "lon": zone["longitude"], "weather": daily.set_index("time")})

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))["stations"]
    coords = {(c["line"], station_key(c["name"])): (c["lat"], c["lon"]) for c in catalog}

    def nearest_zone(line: str, name: str) -> dict:
        lat, lon = coords.get((line, station_key(name)), (ZONES[0][1], ZONES[0][2]))
        return min(zones, key=lambda z: (z["lat"] - lat) ** 2 + ((z["lon"] - lon) * math.cos(math.radians(lat))) ** 2)

    rows, residuals = [], []
    groups = ridership.groupby(["linea", "estacion"])
    for index, ((line_label, station), group) in enumerate(groups, start=1):
        line = model.line_code(line_label)
        weather = nearest_zone(line, station)["weather"]
        group = group.sort_values("fecha")
        last = group["fecha"].max()
        cutoff = last - pd.DateOffset(days=model.TEST_DAYS - 1)
        train_all, test = group[group["fecha"] < cutoff], group[group["fecha"] >= cutoff]
        if len(train_all) < model.MIN_TRAIN_DAYS or len(test) < model.MIN_TEST_DAYS:
            continue
        recent = train_all[train_all["fecha"] >= model.TRAIN_START]
        train = recent if len(recent) >= model.MIN_TRAIN_DAYS else train_all
        weights = np.where(train["fecha"] >= cutoff - pd.DateOffset(days=model.RECENT_DAYS), model.RECENT_WEIGHT, 1.0)

        # Misma metodología del modelo publicado, con y sin variables de clima.
        base = RandomForestRegressor(**model.RF_PARAMS).fit(model.features(train["fecha"]), train["afluencia"], sample_weight=weights)
        climate = RandomForestRegressor(**model.RF_PARAMS).fit(with_weather(train["fecha"], weather), train["afluencia"], sample_weight=weights)
        pred_base = base.predict(model.features(test["fecha"]))
        pred_climate = climate.predict(with_weather(test["fecha"], weather))
        w = weather.reindex(pd.DatetimeIndex(test["fecha"]))
        rainy = w["precipitation_sum"].to_numpy() >= RAIN_MM
        rows.append({
            "mae_base": mean_absolute_error(test["afluencia"], pred_base),
            "mae_climate": mean_absolute_error(test["afluencia"], pred_climate),
            "rain_base": mean_absolute_error(test["afluencia"][rainy], pred_base[rainy]) if rainy.any() else np.nan,
            "rain_climate": mean_absolute_error(test["afluencia"][rainy], pred_climate[rainy]) if rainy.any() else np.nan,
        })
        # Efecto sin depender del modelo con clima: error relativo del modelo base por tipo de día.
        residuals.append(pd.DataFrame({
            "record": f"{line}|{station}",
            "ratio": test["afluencia"].to_numpy() / pred_base - 1,
            "rain": w["precipitation_sum"].to_numpy(),
            "tmax": w["temperature_2m_max"].to_numpy(),
            "weekday": test["fecha"].dt.day_of_week.to_numpy() < 5,
        }))
        print(f"[{index}/{groups.ngroups}] Línea {line} · {station}", flush=True)

    r = pd.DataFrame(rows)
    a = pd.concat(residuals)
    a = a[a["weekday"]]
    by = lambda mask: a[mask].groupby("record")["ratio"].mean()
    dry, rain, heavy = by(a["rain"] < DRY_MM), by(a["rain"] >= RAIN_MM), by(a["rain"] >= HEAVY_MM)
    hot, mild = by(a["tmax"] >= HOT_C), by(a["tmax"] < MILD_C)
    network = a.groupby(a["rain"] >= RAIN_MM)["ratio"].mean()
    days = lambda mask: int(round(mask.sum() / a["record"].nunique()))

    summary = {
        "generatedAt": pd.Timestamp.now(tz="America/Mexico_City").isoformat(),
        "source": {
            "name": "Reanálisis ERA5 vía Open-Meteo (archivo histórico diario)",
            "url": "https://open-meteo.com/en/docs/historical-weather-api",
            "license": "CC BY 4.0",
            "zones": [z["label"] for z in zones],
            "note": "Cada estación usa la zona más cercana. El Servicio Meteorológico Nacional no permite descargas automáticas.",
        },
        "period": {"testStart": (ridership["fecha"].max() - pd.DateOffset(days=model.TEST_DAYS - 1)).strftime("%Y-%m-%d"), "testEnd": end},
        "records": int(len(r)),
        "validation": {
            "maeWithout": int(round(r["mae_base"].sum())),
            "maeWith": int(round(r["mae_climate"].sum())),
            "changePct": round((r["mae_climate"].sum() / r["mae_base"].sum() - 1) * 100, 1),
            "improvedRecords": int((r["mae_climate"] < r["mae_base"]).sum()),
            "rainyDaysChangePct": round((r["rain_climate"].sum() / r["rain_base"].sum() - 1) * 100, 1),
        },
        "effects": {
            "rain": {"thresholdMm": RAIN_MM, "weekdaysPerRecord": days(a["rain"] >= RAIN_MM),
                     "networkPct": round(float((network.get(True, np.nan) - network.get(False, np.nan)) * 100), 1),
                     "byStation": spread(rain - dry)},
            "heavyRain": {"thresholdMm": HEAVY_MM, "weekdaysPerRecord": days(a["rain"] >= HEAVY_MM), "byStation": spread(heavy - dry)},
            "heat": {"thresholdC": HOT_C, "weekdaysPerRecord": days(a["tmax"] >= HOT_C), "byStation": spread(hot - mild)},
        },
        "decision": "El clima no se usa en el modelo: con el clima real del periodo de prueba, la estimación empeora.",
    }
    OUTPUT_PATH.write_text("window.MINI_YOLOTZIN_WEATHER = " + json.dumps(summary, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
