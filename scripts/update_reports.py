"""Refresh public fishing reports using the existing Baltimore desktop app scoring.

Only the PUBLIC derived fields are exported; no config.ini, Discord webhooks,
credentials, application state, or private machine data are read or copied.
Failure to reach a data provider is not reported as a successful 'live' rating.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

os.environ['TZ'] = 'America/New_York'
if hasattr(time, 'tzset'):
    time.tzset()

import baltimore_fishing_bot as bot
from export_locations import export

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'site' / 'data' / 'reports.json'

# A contact email is optional but helps NWS identify public API users.
contact = os.environ.get('WEBSITE_CONTACT_EMAIL', '').strip()
bot.USER_AGENT = f'BaltimoreFishingPublicWebsite/1.0 ({contact or "public fishing conditions website"})'


def _number(value: Any, precision: int = 1):
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(value)
        return round(number, precision) if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def _safe(fn, key: str):
    try:
        return (fn(key), None)
    except Exception as exc:
        return (None, str(exc)[:240])


def _data_sources(loc, usgs, tide, weather, alerts):
    return {
        'weather': bool((weather.get('open_meteo') or {}).get('current') or weather.get('periods')),
        'usgs': bool((usgs or {}).get('values')) if loc.usgs_site else None,
        'tide': bool((tide or {}).get('predictions')) if loc.tide_station else None,
        'alerts': not bool(alerts.get('error')),
    }


def calculate(loc, tide_by_station, usgs_by_site):
    # The original score_location function computes all species and blue crab indices.
    weather = bot.fetch_nws_hourly(loc.lat, loc.lon)
    alerts = bot.fetch_nws_alerts(loc.lat, loc.lon)
    tide = tide_by_station.get(loc.tide_station) if loc.tide_station else None
    usgs = usgs_by_site.get(loc.usgs_site) if loc.usgs_site else None
    sources = _data_sources(loc, usgs, tide, weather, alerts)
    available = any(sources.get(k) is True for k in ('weather', 'usgs', 'tide'))
    partial = any(sources.get(k) is False for k in ('weather', 'usgs', 'tide', 'alerts'))
    report = bot.score_location(loc, usgs, tide, weather, alerts) if available else {}
    species = report.get('species_results') or []
    crab = next((s for s in species if 'blue crab' in str(s.get('name', '')).lower()), None)
    details = report.get('weather_details') or {}
    weather_summary = report.get('weather') or {}
    return {
        'key': loc.key,
        'status': 'unavailable' if not available else ('partial' if partial else 'updated'),
        'score': report.get('score') if available else None,
        'bucket': report.get('bucket') if available else None,
        'hazards': (report.get('hazards') or [])[:5],
        'reasons': (report.get('reasons') or [])[:6],
        'temperature_f': _number(details.get('temp'), 0),
        'feels_like_f': _number(details.get('feels'), 0),
        'wind_mph': _number(details.get('wind'), 0),
        'wind_gust_mph': _number(details.get('gust'), 0),
        'wind_direction': details.get('wind_dir'),
        'cloud_cover_pct': _number(details.get('clouds'), 0),
        'rain_chance_pct': _number(details.get('pop3'), 0),
        'pressure_hpa': _number(details.get('pressure'), 1),
        'pressure_trend': details.get('pressure_trend'),
        'weather_text': weather_summary.get('text') or 'Weather unavailable',
        'water_temp_f': _number(report.get('water_temp_f'), 0),
        'water_temp_source': report.get('water_temp_source'),
        'tide_summary': report.get('tide'),
        'tide_observed_ft': _number(report.get('tide_observed_ft'), 2),
        'flow_cfs': _number(report.get('flow_cfs'), 0),
        'flow_trend_pct': _number(report.get('flow_trend_percent'), 1),
        'gage_ft': _number(report.get('gage_ft'), 2),
        'species_scores': [
            {'name': str(s.get('name') or ''), 'score': s.get('score'), 'rating': s.get('rating')}
            for s in species
        ],
        'blue_crab_score': crab.get('score') if crab else None,
        'alerts': [
            {'event': str(a.get('event') or '')[:120], 'severity': str(a.get('severity') or '')[:30]}
            for a in (alerts.get('alerts') or [])[:5]
        ],
        'sources_available': sources,
        'source_urls': {
            'nws': weather.get('source_url'),
            'noaa': tide.get('source_url') if tide else None,
            'usgs': usgs.get('source_url') if usgs else None,
            'open_meteo': (weather.get('open_meteo') or {}).get('source_url'),
        },
        'provider_errors': [
            str(msg)[:220] for msg in (
                weather.get('error'), weather.get('open_meteo_error'),
                alerts.get('error'), (tide or {}).get('prediction_error'),
                (tide or {}).get('water_level_error')
            ) if msg
        ][:4],
    }


def main():
    export()
    tide_ids = sorted({loc.tide_station for loc in bot.LOCATIONS.values() if loc.tide_station})
    usgs_ids = sorted({loc.usgs_site for loc in bot.LOCATIONS.values() if loc.usgs_site})
    tides, usgs = {}, {}
    print(f'Collecting {len(tide_ids)} tide stations and {len(usgs_ids)} USGS gauges...', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        tasks = {executor.submit(_safe, bot.fetch_noaa_tide, x): ('tide', x) for x in tide_ids}
        tasks.update({executor.submit(_safe, bot.fetch_usgs, x): ('usgs', x) for x in usgs_ids})
        for task in concurrent.futures.as_completed(tasks):
            typ, key = tasks[task]
            val, err = task.result()
            (tides if typ == 'tide' else usgs)[key] = val
            if err: print(f'{typ} {key}: {err}', flush=True)

    rows = []
    places = list(bot.LOCATIONS.values())
    print(f'Calculating {len(places)} original app locations...', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(calculate, loc, tides, usgs): loc for loc in places}
        for n, future in enumerate(concurrent.futures.as_completed(futures), 1):
            loc = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {'key': loc.key, 'status': 'unavailable', 'score': None,
                          'blue_crab_score': None, 'provider_errors': [str(exc)[:180]],
                          'species_scores': [], 'sources_available': {}}
            rows.append(result)
            if n % 10 == 0: print(f'Processed {n}/{len(places)}', flush=True)
    rows.sort(key=lambda row: list(bot.LOCATIONS).index(row['key']))
    active = sum(x['score'] is not None for x in rows)
    payload = {
        'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
        'time_zone': 'America/New_York',
        'total': len(rows),
        'rated': active,
        'partial': sum(x['status'] == 'partial' for x in rows),
        'method': 'Existing Baltimore desktop app score_location() and build_species_results()',
        'reports': rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(f'Wrote {OUT}; {active}/{len(rows)} locations have available source data.', flush=True)
    # A deployed site with no valid source data would look live but not be useful.
    # Keep publishing data marked unavailable so the UI can clearly flag outages.
    return 0

if __name__ == '__main__':
    sys.exit(main())
