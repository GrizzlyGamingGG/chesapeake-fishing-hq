"""Export the original desktop app's full location directory for the public website."""
import json
from pathlib import Path
from baltimore_fishing_bot import LOCATIONS, MARYLAND_PIER_KEYS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'site' / 'data' / 'locations.json'

def export():
    rows = []
    for key, place in LOCATIONS.items():
        pier = key in MARYLAND_PIER_KEYS
        rows.append({
            'key': place.key,
            'name': place.name,
            'short_name': place.short_name,
            'lat': place.lat,
            'lon': place.lon,
            'is_pier': pier,
            'type': 'Pier / public dock' if pier else 'Fishing location',
            'region': 'Maryland pier' if pier else 'Regional fishing spot',
            'species': list(place.species),
            'has_blue_crab': any('blue crab' in s.lower() for s in place.species),
            'note': place.note,
            'tide_station': place.tide_station,
            'usgs_site': place.usgs_site,
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'count': len(rows), 'piers': sum(x['is_pier'] for x in rows), 'locations': rows}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return rows

if __name__ == '__main__':
    print(f'Exported {len(export())} fishing locations.')
