from datetime import datetime
from mcp.server.fastmcp import Context


def _parse_date(date_str: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str[:19], fmt[:len(date_str[:19])])
        except ValueError:
            continue
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _trend_direction(values: list[float]) -> str:
    if len(values) < 2:
        return "single measurement"
    delta = values[-1] - values[0]
    pct = abs(delta) / (abs(values[0]) + 1e-9) * 100
    if pct < 5:
        return "stable"
    return "worsening" if delta > 0 else "improving"


async def analyze_lab_trends(
    patient_history: dict,
    ctx: Context = None,
) -> dict:
    """Detect progressive lab abnormalities over time in a patient's FHIR observation history.

    Groups observations by test name, sorts by date, and identifies trends
    (worsening, improving, stable) and persistent abnormalities — patterns
    that single-point-in-time readings miss entirely.
    """

    observations = patient_history.get("observations", [])
    if not observations:
        return {"trends": [], "persistent_abnormalities": [], "summary": "No observations found."}

    # Group by test name
    grouped: dict[str, list] = {}
    for obs in observations:
        name = obs.get("name", "Unknown")
        if name == "Unknown" or not obs.get("date"):
            continue
        grouped.setdefault(name, []).append(obs)

    trends = []
    persistent_abnormalities = []

    for test_name, entries in grouped.items():
        # Sort by date ascending
        dated = [(e, _parse_date(e.get("date", ""))) for e in entries]
        dated = [(e, d) for e, d in dated if d is not None]
        if not dated:
            continue
        dated.sort(key=lambda x: x[1])

        values_raw = []
        for e, _ in dated:
            val_str = e.get("value", "")
            try:
                numeric = float(str(val_str).split()[0])
                values_raw.append(numeric)
            except (ValueError, IndexError):
                pass

        abnormal_entries = [e for e, _ in dated if e.get("abnormal")]
        abnormal_count = len(abnormal_entries)
        total_count = len(dated)

        if total_count < 2:
            continue

        date_span_days = (dated[-1][1] - dated[0][1]).days
        date_span_years = round(date_span_days / 365.25, 1)

        trend_entry = {
            "test": test_name,
            "measurement_count": total_count,
            "span_years": date_span_years,
            "first_value": dated[0][0].get("value", ""),
            "first_date": dated[0][0].get("date", "")[:10],
            "latest_value": dated[-1][0].get("value", ""),
            "latest_date": dated[-1][0].get("date", "")[:10],
            "abnormal_count": abnormal_count,
        }

        if values_raw and len(values_raw) >= 2:
            trend_entry["trend"] = _trend_direction(values_raw)

        trends.append(trend_entry)

        # Flag persistent abnormality: >50% of readings are abnormal over >1 year
        if abnormal_count >= 2 and abnormal_count / total_count >= 0.5 and date_span_years >= 1:
            persistent_abnormalities.append({
                "test": test_name,
                "abnormal_readings": abnormal_count,
                "total_readings": total_count,
                "span_years": date_span_years,
                "significance": "Persistent abnormality over multiple years — warrants investigation for underlying systemic cause",
            })

    # Sort: persistent abnormalities first, then by abnormal count
    trends.sort(key=lambda x: (-x["abnormal_count"], -x["measurement_count"]))

    worsening = [t for t in trends if t.get("trend") == "worsening" and t["abnormal_count"] > 0]

    return {
        "trends": trends[:20],
        "persistent_abnormalities": persistent_abnormalities,
        "worsening_abnormal_trends": worsening,
        "summary": (
            f"Analyzed {len(trends)} lab series. "
            f"Found {len(persistent_abnormalities)} persistent abnormalities "
            f"and {len(worsening)} worsening trends."
        ),
    }
