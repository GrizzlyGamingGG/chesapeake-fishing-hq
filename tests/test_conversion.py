"""Offline smoke tests. No weather requests or Discord messages are sent."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import baltimore_fishing_bot as bot
import update_reports

class ConversionTests(unittest.TestCase):
    def test_directory(self):
        data = json.loads((ROOT / 'site/data/locations.json').read_text())
        self.assertEqual(len(bot.LOCATIONS), 78)
        self.assertEqual(data['count'], 78)
        self.assertEqual(data['piers'], 31)
        self.assertEqual(len([x for x in data['locations'] if x['has_blue_crab']]), 35)
        self.assertIn('jonas_green_pier', bot.MARYLAND_PIER_KEYS)
        self.assertTrue(any('Blue crab' in s for s in bot.LOCATIONS['jonas_green_pier'].species))

    def test_no_live_score_when_data_missing(self):
        place = bot.LOCATIONS['jonas_green_pier']
        with patch.object(bot,'fetch_nws_hourly',return_value={'periods':[], 'error':'offline'}), patch.object(bot,'fetch_nws_alerts',return_value={'alerts':[], 'error':'offline'}):
            rep=update_reports.calculate(place, {}, {})
        self.assertIsNone(rep['score'])
        self.assertEqual(rep['status'],'unavailable')

    def test_reuses_original_crab_calculation(self):
        place=bot.LOCATIONS['jonas_green_pier']
        wx={'periods':[{'shortForecast':'Mostly Clear','temperature':74}],
            'open_meteo':{'current':{'temperature_2m':74,'wind_speed_10m':6,'wind_gusts_10m':10,'pressure_msl':1017,'cloud_cover':35,'weather_code':1}}}
        with patch.object(bot,'fetch_nws_hourly',return_value=wx), patch.object(bot,'fetch_nws_alerts',return_value={'alerts':[]}):
            rep=update_reports.calculate(place, {}, {})
        self.assertIsNotNone(rep['score'])
        self.assertIsNotNone(rep['blue_crab_score'])
        self.assertEqual(len(rep['species_scores']),len(place.species))

    def test_no_private_config_bundled(self):
        self.assertFalse((ROOT / 'config.ini').exists())
        self.assertFalse((ROOT / 'scripts/config.ini').exists())
        self.assertFalse(any(ROOT.rglob('*.log')))

if __name__=='__main__':
    unittest.main()
