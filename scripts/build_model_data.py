"""Build the compact browser dataset used by the Mini Yolotzin demo.

The raw CSV is an input artifact and is intentionally not shipped with the site.
The output contains only aggregate history, validation metrics and precomputed
future estimates for every station-line record of the Metro that has enough
recent data (option A: one model per station and line, as the official
resource publishes it).

Usage:
    python scripts/build_model_data.py [ruta/al/afluencia_simple.csv] [ruta/de/salida.js]
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "afluencia_simple.csv"
OUTPUT_PATH = ROOT / "model-data.js"
SOURCE_URL = (
    "https://datos.cdmx.gob.mx/dataset/f2046fd5-51b5-4876-b008-bd65d95f9a02/"
    "resource/0e8ffe58-28bb-4dde-afcd-e5f5b4de4ccb"
)
DOWNLOAD_URL = SOURCE_URL + "/download/0e8ffe58-28bb-4dde-afcd-e5f5b4de4ccb.csv"

# Estaciones destacadas de la versión original (se muestran primero en la interfaz).
FEATURED = [
    ("3", "Indios Verdes"),
    ("3", "La Raza"),
    ("3", "Hidalgo"),
    ("3", "Centro Médico"),
    ("3", "Universidad"),
]

TEST_DAYS = 180            # validación cronológica: últimos 180 días observados
FORECAST_DAYS = 366        # horizonte de pronóstico
MIN_TRAIN_DAYS = 365       # días válidos mínimos para entrenar
MIN_TEST_DAYS = 90         # días válidos mínimos para validar
MAX_STALE_DAYS = 30        # si el último dato válido es más antiguo, no se pronostica
RF_PARAMS = dict(n_estimators=160, max_depth=14, min_samples_leaf=4, random_state=42, n_jobs=-1)


def repair_mojibake(value: object) -> object:
    if not isinstance(value, str) or "Ã" not in value:
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def features(dates: pd.Series | pd.DatetimeIndex) -> pd.DataFrame:
    dates = pd.DatetimeIndex(dates)
    day_of_year = dates.day_of_year.to_numpy()
    return pd.DataFrame(
        {
            "month": dates.month,
            "dow": dates.day_of_week,
            "day": dates.day,
            "weekend": (dates.day_of_week >= 5).astype(int),
            "sin_year": np.sin(2 * np.pi * day_of_year / 365.25),
            "cos_year": np.cos(2 * np.pi * day_of_year / 365.25),
        }
    )


def rounded(value: float) -> int:
    return int(round(float(value)))


def line_code(label: str) -> str:
    """'Línea 3' -> '3', 'Línea A' -> 'A'."""
    return label.replace("Línea", "").strip()


def fold(text: str) -> str:
    """Quita acentos y mayúsculas para comparar nombres."""
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").casefold()


def unify_station_names(valid: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """El recurso oficial cambió la escritura de algunos nombres el 2023-06-01
    (p. ej. «Gómez Farías» → «Gómez Farias», «Peñón Viejo» → «Peñón viejo»).
    Dentro de cada línea, los nombres que solo difieren en acentos o mayúsculas
    se unifican con la forma que aparece primero en el tiempo."""
    first_seen = valid.groupby(["linea", "estacion"])["fecha"].min().reset_index()
    first_seen["key"] = first_seen["estacion"].map(fold)
    canonical, renamed = {}, []
    for (line, _), group in first_seen.groupby(["linea", "key"]):
        group = group.sort_values("fecha")
        target = group["estacion"].iloc[0]
        for variant in group["estacion"].iloc[1:]:
            canonical[(line, variant)] = target
            renamed.append({"line": line, "from": variant, "to": target})
    if canonical:
        keys = list(zip(valid["linea"], valid["estacion"]))
        valid = valid.assign(estacion=[canonical.get(key, key[1]) for key in keys])
    return valid, renamed


def build_record(line: str, station: str, frame: pd.DataFrame, max_date: pd.Timestamp,
                 forecast_dates: pd.DatetimeIndex) -> tuple[dict | None, dict | None]:
    """Train and validate one station-line record. Returns (record, skipped)."""
    data = frame[["fecha", "afluencia"]].sort_values("fecha").drop_duplicates("fecha", keep="last")
    zero_days = int((data["afluencia"] <= 0).sum())
    # Los días con afluencia 0 corresponden a cierres (obras, contingencias): no son demanda baja.
    data = data[data["afluencia"] > 0]
    base = {"name": station, "line": line}

    if data.empty:
        return None, {**base, "reason": "sin registros con afluencia", "lastDate": None}
    last_date = data["fecha"].max()
    if (max_date - last_date).days > MAX_STALE_DAYS:
        return None, {**base, "reason": "sin datos recientes (posible cierre)", "lastDate": last_date.strftime("%Y-%m-%d")}

    cutoff = last_date - pd.DateOffset(days=TEST_DAYS - 1)
    train = data[data["fecha"] < cutoff]
    test = data[data["fecha"] >= cutoff]
    if len(train) < MIN_TRAIN_DAYS or len(test) < MIN_TEST_DAYS:
        return None, {**base, "reason": "historial insuficiente para validar", "lastDate": last_date.strftime("%Y-%m-%d")}

    baseline_table = train.assign(month=train["fecha"].dt.month, dow=train["fecha"].dt.day_of_week).groupby(["month", "dow"])["afluencia"].mean()
    station_mean = float(train["afluencia"].mean())
    baseline_pred = [baseline_table.get((date.month, date.day_of_week), station_mean) for date in test["fecha"]]

    model = RandomForestRegressor(**RF_PARAMS)
    model.fit(features(train["fecha"]), train["afluencia"])
    model_pred = model.predict(features(test["fecha"]))
    future_pred = np.maximum(0, model.predict(features(forecast_dates)))

    q33, q67 = train["afluencia"].quantile([0.33, 0.67]).tolist()
    q25, median, q75 = train["afluencia"].quantile([0.25, 0.5, 0.75]).tolist()
    recent = (
        data[data["fecha"] >= last_date - pd.DateOffset(months=17)]
        .set_index("fecha")["afluencia"].resample("MS").mean().dropna()
    )

    record = {
        **base,
        "summary": {
            "mean": rounded(station_mean),
            "median": rounded(median),
            "p25": rounded(q25),
            "p75": rounded(q75),
            "lowThreshold": rounded(q33),
            "highThreshold": rounded(q67),
            "observations": int(len(data)),
            "closedDays": zero_days,
        },
        "metrics": {
            "baselineMae": rounded(mean_absolute_error(test["afluencia"], baseline_pred)),
            "baselineRmse": rounded(root_mean_squared_error(test["afluencia"], baseline_pred)),
            "modelMae": rounded(mean_absolute_error(test["afluencia"], model_pred)),
            "modelRmse": rounded(root_mean_squared_error(test["afluencia"], model_pred)),
            "testStart": test["fecha"].min().strftime("%Y-%m-%d"),
            "testEnd": test["fecha"].max().strftime("%Y-%m-%d"),
        },
        "history": [{"month": d.strftime("%Y-%m"), "value": rounded(v)} for d, v in recent.items()],
        # Alineado con dataset.forecastStart, un valor por día. El nivel (baja/media/alta)
        # se calcula en el navegador con lowThreshold/highThreshold, con la misma regla de antes.
        "predictions": [rounded(v) for v in future_pred],
    }
    return record, None


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else CSV_PATH
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else OUTPUT_PATH
    frame = pd.read_csv(csv_path, dtype={"linea": "string", "estacion": "string"})
    for column in ["mes", "linea", "estacion"]:
        if column in frame:
            frame[column] = frame[column].map(repair_mojibake)
    # El recurso oficial cambió la etiqueta “Línea” por “Linea” el 2023-06-01.
    frame["linea"] = frame["linea"].str.strip().str.replace(r"^Linea ", "Línea ", regex=True)
    frame["estacion"] = frame["estacion"].str.strip()
    frame["fecha"] = pd.to_datetime(frame["fecha"], errors="coerce")
    frame["afluencia"] = pd.to_numeric(frame["afluencia"], errors="coerce")

    nulls = {key: int(value) for key, value in frame.isna().sum().items()}
    valid = frame.dropna(subset=["fecha", "linea", "estacion", "afluencia"]).copy()
    valid, renamed = unify_station_names(valid)
    for item in renamed:
        print(f"Nombre unificado en {item['line']}: {item['from']} → {item['to']}")
    max_date = valid["fecha"].max()
    forecast_dates = pd.date_range(max_date + pd.DateOffset(days=1), periods=FORECAST_DAYS, freq="D")

    records, skipped = [], []
    groups = valid.groupby(["linea", "estacion"], sort=True)
    for index, ((line_label, station), group) in enumerate(groups, start=1):
        record, skip = build_record(line_code(line_label), station, group, max_date, forecast_dates)
        (records if record else skipped).append(record or skip)
        print(f"[{index}/{groups.ngroups}] Línea {line_code(line_label)} · {station}: {'ok' if record else skip['reason']}", flush=True)

    missing = [f"{line} {name}" for line, name in FEATURED if not any(r["line"] == line and r["name"] == name for r in records)]
    if missing:
        raise RuntimeError(f"Estaciones destacadas sin modelo: {missing}")

    payload = {
        "generatedAt": pd.Timestamp.now(tz="America/Mexico_City").isoformat(),
        "source": {
            "name": "Afluencia diaria del Metro CDMX — base simple",
            "publisher": "Secretaría de Movilidad de la Ciudad de México",
            "url": SOURCE_URL,
            "downloadUrl": DOWNLOAD_URL,
            "license": "CC BY 4.0",
        },
        "dataset": {
            "rows": int(len(frame)),
            "validRows": int(len(valid)),
            "startDate": valid["fecha"].min().strftime("%Y-%m-%d"),
            "endDate": max_date.strftime("%Y-%m-%d"),
            "lines": int(valid["linea"].nunique()),
            "stations": int(valid["estacion"].nunique()),
            "records": int(groups.ngroups),
            "modeledRecords": len(records),
            "skippedRecords": len(skipped),
            "zeroRows": int((valid["afluencia"] <= 0).sum()),
            "duplicateKeys": int(valid.duplicated(["fecha", "linea", "estacion"]).sum()),
            "renamedStations": renamed,
            "nulls": nulls,
            "forecastStart": forecast_dates.min().strftime("%Y-%m-%d"),
            "forecastEnd": forecast_dates.max().strftime("%Y-%m-%d"),
            "forecastDays": FORECAST_DAYS,
        },
        "model": {
            "name": "Random Forest Regressor",
            "trees": RF_PARAMS["n_estimators"],
            "features": ["mes", "día de la semana", "día del mes", "fin de semana", "ciclo anual"],
            "validation": f"Partición cronológica por estación y línea: últimos {TEST_DAYS} días observados",
            "unit": "Un modelo por estación y línea, como publica el recurso oficial",
            "seed": RF_PARAMS["random_state"],
            "rules": {
                "zeroDays": "Los días con afluencia 0 (cierres) se excluyen del entrenamiento y la validación.",
                "minTrainDays": MIN_TRAIN_DAYS,
                "minTestDays": MIN_TEST_DAYS,
                "maxStaleDays": MAX_STALE_DAYS,
            },
        },
        "featured": [{"line": line, "name": name} for line, name in FEATURED],
        "stations": records,
        "skipped": skipped,
    }

    output_path.write_text(
        "window.MINI_YOLOTZIN_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["dataset"], ensure_ascii=False, indent=2))
    print(f"Modelados: {len(records)} · Omitidos: {len(skipped)}")
    for item in skipped:
        print("  omitido:", item)
    gains = [(r["metrics"]["baselineMae"] - r["metrics"]["modelMae"]) / r["metrics"]["baselineMae"] for r in records if r["metrics"]["baselineMae"]]
    print(f"El modelo supera a la línea base en {sum(g > 0 for g in gains)} de {len(gains)} registros")


if __name__ == "__main__":
    main()
