"""Phase 3: train one daily demand model per distinct Metro station.

Run: python scripts/build_all_stations.py --csv afluencia_simple.csv
Produces model-data-all.js and model-coverage-report.json; does not replace
production model-data.js until the results have been reviewed.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    "gomezfarias": "gomezfarias",
    "ninosheroespoderjudicialcdmx": "ninosheroes",
    "uamazcapotzalco": "uamazcapotzalco",
    "mixhiuca": "mixiuhca",
}

def repair(value):
    if not isinstance(value, str):
        return value
    try:
        return value.encode("latin-1").decode("utf-8") if "Ã" in value else value
    except (UnicodeError, ValueError):
        return value

def key(value):
    value = unicodedata.normalize("NFKD", repair(value))
    plain = value.encode("ascii", "ignore").decode().lower()
    plain = re.sub(r"[^a-z0-9]", "", plain)
    return ALIASES.get(plain, plain)

def features(dates):
    d = pd.DatetimeIndex(dates)
    y = d.dayofyear.to_numpy()
    return pd.DataFrame({
        "month": d.month, "dow": d.dayofweek, "day": d.day,
        "weekend": (d.dayofweek >= 5).astype(int),
        "sin_year": np.sin(2 * np.pi * y / 365.25),
        "cos_year": np.cos(2 * np.pi * y / 365.25),
    })

def train_station(name, series, future_dates):
    series = series.sort_index().astype(float)
    if len(series) < 365:
        raise ValueError(f"{name}: insufficient history ({len(series)} days)")
    cutoff = series.index.max() - pd.Timedelta(days=179)
    train, test = series[series.index < cutoff], series[series.index >= cutoff]
    if len(train) < 180 or len(test) < 90:
        raise ValueError(f"{name}: insufficient chronological train/test data")
    reference = train.groupby([train.index.month, train.index.dayofweek]).mean()
    fallback = float(train.mean())
    baseline = np.array([reference.get((dt.month, dt.dayofweek), fallback) for dt in test.index])
    model = RandomForestRegressor(n_estimators=100, max_depth=14,
                                  min_samples_leaf=4, random_state=42, n_jobs=1)
    model.fit(features(train.index), train.values)
    estimated = np.maximum(0, model.predict(features(test.index)))
    future = np.maximum(0, model.predict(features(future_dates)))
    low, high = train.quantile([.33, .67]).tolist()
    p25, median, p75 = train.quantile([.25, .5, .75]).tolist()
    recent = series[series.index >= series.index.max()-pd.DateOffset(months=17)].resample("MS").mean()
    def rounded(x):
        return int(round(float(x)))
    def rmse(y, p):
        return rounded(np.sqrt(mean_squared_error(y, p)))
    return {
        "name": name,
        "summary": {
            "mean": rounded(train.mean()), "median": rounded(median),
            "p25": rounded(p25), "p75": rounded(p75),
            "lowThreshold": rounded(low), "highThreshold": rounded(high),
            "observations": int(len(series))
        },
        "metrics": {
            "baselineMae": rounded(mean_absolute_error(test, baseline)),
            "baselineRmse": rmse(test, baseline),
            "modelMae": rounded(mean_absolute_error(test, estimated)),
            "modelRmse": rmse(test, estimated),
            "testStart": test.index.min().strftime("%Y-%m-%d"),
            "testEnd": test.index.max().strftime("%Y-%m-%d")
        },
        "history": [{"month": dt.strftime("%Y-%m"), "value": rounded(v)}
                    for dt, v in recent.items()],
        "predictions": {
            dt.strftime("%Y-%m-%d"): {
                "value": rounded(p),
                "level": "baja" if p < low else ("media" if p < high else "alta")
            } for dt, p in zip(future_dates, future)
        }
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=ROOT/"afluencia_simple.csv")
    parser.add_argument("--catalog", type=Path, default=ROOT/"metro-catalog.js")
    parser.add_argument("--output", type=Path, default=ROOT/"model-data-all.js")
    parser.add_argument("--report", type=Path, default=ROOT/"model-coverage-report.json")
    args = parser.parse_args()
    frame = pd.read_csv(args.csv, usecols=["fecha", "linea", "estacion", "afluencia"])
    frame["fecha"] = pd.to_datetime(frame["fecha"], errors="coerce")
    frame["afluencia"] = pd.to_numeric(frame["afluencia"], errors="coerce")
    frame["estacion"] = frame["estacion"].map(repair)
    frame["stationKey"] = frame["estacion"].map(key)
    frame = frame.dropna(subset=["fecha", "afluencia", "stationKey"])
    frame = frame[frame["afluencia"] >= 0]
    duplicates = int(frame.duplicated(["fecha", "linea", "estacion"]).sum())
    if duplicates:
        raise ValueError(f"Source has {duplicates} duplicate date-line-station rows; inspect before training")
    raw = args.catalog.read_text(encoding="utf-8").strip()
    catalog = json.loads(raw.split("window.METRO_CATALOG=", 1)[1].rstrip(";"))
    names = {}
    for entry in catalog["stations"]:
        k = key(entry["name"])
        names.setdefault(k, entry["name"])
    daily = frame.groupby(["stationKey", "fecha"], sort=True)["afluencia"].sum()
    historical = set(frame["stationKey"])
    missing = sorted(set(names) - historical)
    unmatched = sorted(historical - set(names))
    end = frame["fecha"].max()
    future = pd.date_range(end + pd.Timedelta(days=1), periods=366, freq="D")
    stations, errors = [], {}
    for station_key, station_name in sorted(names.items(), key=lambda p: p[1]):
        if station_key not in historical:
            continue
        try:
            station_series = daily.loc[station_key]
            stations.append(train_station(station_name, station_series, future))
        except ValueError as exc:
            errors[station_name] = str(exc)
    report = {
        "sourceRows": int(len(frame)), "sourceEndDate": end.strftime("%Y-%m-%d"),
        "catalogStationNames": len(names), "historicalStationNames": len(historical),
        "modeledStationNames": len(stations), "missingCatalogKeys": missing,
        "unmatchedHistoricalKeys": unmatched, "trainingErrors": errors,
        "duplicateKeys": duplicates,
        "forecastStart": future.min().strftime("%Y-%m-%d"),
        "forecastEnd": future.max().strftime("%Y-%m-%d"),
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if len(stations) != len(names):
        raise RuntimeError("Not all catalog stations could be modeled; see model-coverage-report.json")
    payload = {
        "generatedAt": pd.Timestamp.now(tz="America/Mexico_City").isoformat(),
        "source": {"name": "Afluencia diaria del Metro CDMX — base simple",
                   "publisher": "SEMOVI CDMX", "license": "CC BY 4.0"},
        "dataset": {"rows": int(len(frame)), "validRows": int(len(frame)),
                    "startDate": frame["fecha"].min().strftime("%Y-%m-%d"),
                    "endDate": end.strftime("%Y-%m-%d"),
                    "lines": int(frame["linea"].nunique()),
                    "stations": len(stations), "duplicateKeys": duplicates,
                    "nulls": {}, "selectedLine": "Todas",
                    "selectedRows": int(len(frame)),
                    "forecastStart": future.min().strftime("%Y-%m-%d"),
                    "forecastEnd": future.max().strftime("%Y-%m-%d")},
        "model": {"name": "Random Forest Regressor", "trees": 100,
                  "features": ["mes", "día de semana", "día", "fin de semana", "ciclo anual"],
                  "validation": "Partición cronológica: últimos 180 días",
                  "seed": 42},
        "stations": stations
    }
    args.output.write_text("window.MINI_YOLOTZIN_DATA = " +
                           json.dumps(payload, ensure_ascii=False, separators=(",", ":")) +
                           ";\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
