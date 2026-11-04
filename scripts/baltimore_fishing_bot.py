"""
Baltimore + Mid-Atlantic Fishing Alerts Bot

Checks public water/weather data and optionally posts fishing-condition reports to Discord.
Data sources used by this script:
- USGS Water Services: real-time streamflow / gage height where available
- NOAA CO-OPS: tide predictions / observed water levels where available
- National Weather Service API: hourly forecast and active alerts

This is NOT an official dam-release warning system. It is a fishing helper that watches public gauges.
Always check local regulations and use your own judgment around fast water, storms, and boating conditions.
"""
from __future__ import annotations

import argparse
import configparser
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

APP_NAME = "Baltimore + Mid-Atlantic Fishing Alerts"
APP_VERSION = "2.1-md-piers-crab"
BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.ini"
STATE_DIR = BASE_DIR / "state"
STATE_FILE = STATE_DIR / "last_reports.json"
LOG_FILE = BASE_DIR / "baltimore_fishing_bot.log"

PARAM_DISCHARGE = "00060"  # cubic feet per second
PARAM_GAGE_HEIGHT = "00065"  # feet
PARAM_WATER_TEMP = "00010"  # deg C in many USGS feeds

USER_AGENT = "BaltimoreMidAtlanticFishingAlerts/2.0 (local user app; local desktop app)"


@dataclass(frozen=True)
class Location:
    key: str
    name: str
    short_name: str
    lat: float
    lon: float
    species: Tuple[str, ...]
    note: str
    usgs_site: Optional[str] = None
    tide_station: Optional[str] = None


LOCATIONS: Dict[str, Location] = {
    'conowingo_dam': Location(
        key='conowingo_dam',
        name='Conowingo Dam / Lower Susquehanna, MD',
        short_name='Conowingo',
        lat=39.6579,
        lon=-76.1744,
        species=('Striped bass', 'Shad', 'Blue catfish', 'Smallmouth bass', 'Largemouth bass'),
        note='Approx. 1.2 hr from Baltimore. Big-water current/tailrace style spot. Flow can change fast.',
        usgs_site='01578310',
    ),
    'deer_creek': Location(
        key='deer_creek',
        name='Deer Creek / Susquehanna State Park, MD',
        short_name='Deer Creek',
        lat=39.6323,
        lon=-76.4116,
        species=('Smallmouth bass', 'Trout', 'Fallfish', 'Shad seasonally'),
        note='Approx. 1 hr from Baltimore. Creek conditions can spike after storms.',
        usgs_site='01580000',
    ),
    'gunpowder_falls': Location(
        key='gunpowder_falls',
        name='Little Gunpowder / Gunpowder Falls, MD',
        short_name='Gunpowder',
        lat=39.5054,
        lon=-76.4318,
        species=('Trout', 'Smallmouth bass', 'Sunfish'),
        note='Approx. 30-50 min from Baltimore. Cold-water trout/creek fishing; avoid high flows.',
        usgs_site='01584500',
    ),
    'prettyboy_reservoir': Location(
        key='prettyboy_reservoir',
        name='Prettyboy Reservoir, MD',
        short_name='Prettyboy',
        lat=39.6348,
        lon=-76.7497,
        species=('Smallmouth bass', 'Largemouth bass', 'Trout', 'Perch', 'Bluegill'),
        note='Approx. 45 min from Baltimore. Reservoir score is weather/alert based unless you add a nearby gauge.',
    ),
    'liberty_reservoir': Location(
        key='liberty_reservoir',
        name='Liberty Reservoir, MD',
        short_name='Liberty Reservoir',
        lat=39.3893,
        lon=-76.8886,
        species=('Striped bass', 'Largemouth bass', 'Smallmouth bass', 'Crappie', 'Catfish'),
        note='Approx. 40 min from Baltimore. Reservoir score is weather/alert based.',
    ),
    'loch_raven_reservoir': Location(
        key='loch_raven_reservoir',
        name='Loch Raven Reservoir, MD',
        short_name='Loch Raven',
        lat=39.4376,
        lon=-76.5514,
        species=('Largemouth bass', 'Chain pickerel', 'Crappie', 'Bluegill', 'Yellow perch'),
        note='Approx. 25 min from Baltimore. Reservoir score is weather/alert based.',
    ),
    'patapsco_elkridge': Location(
        key='patapsco_elkridge',
        name='Patapsco River near Elkridge, MD',
        short_name='Patapsco',
        lat=39.2215,
        lon=-76.703,
        species=('Smallmouth bass', 'Catfish', 'Sunfish', 'White perch lower river'),
        note='Approx. 25 min from Baltimore. Urban river conditions change quickly after rain.',
        usgs_site='01589035',
    ),
    'baltimore_harbor': Location(
        key='baltimore_harbor',
        name='Baltimore Harbor / Middle Branch, MD',
        short_name='Baltimore Harbor',
        lat=39.2666,
        lon=-76.578,
        species=('White perch', 'Striped bass seasonally', 'Blue catfish', 'Channel catfish'),
        note='Local. Tide movement, wind, and storms matter more than river CFS here.',
        tide_station='8574680',
    ),
    'annapolis_bay': Location(
        key='annapolis_bay',
        name='Annapolis / Severn River / Bay Bridge area, MD',
        short_name='Annapolis',
        lat=38.9836,
        lon=-76.4816,
        species=('Striped bass', 'White perch', 'Bluefish seasonally', 'Croaker seasonally'),
        note='Approx. 45 min from Baltimore. Bay tide/weather reference south of Baltimore.',
        tide_station='8575512',
    ),
    'sandy_point_bay_bridge': Location(
        key='sandy_point_bay_bridge',
        name='Sandy Point / Chesapeake Bay Bridge, MD',
        short_name='Sandy Point',
        lat=39.0185,
        lon=-76.3991,
        species=('Striped bass', 'White perch', 'Bluefish seasonally', 'Spot seasonally'),
        note='Approx. 45 min from Baltimore. Strong wind against tide can make rough water.',
        tide_station='8575512',
    ),
    'cambridge_choptank': Location(
        key='cambridge_choptank',
        name='Cambridge / Choptank River, MD',
        short_name='Choptank',
        lat=38.5729,
        lon=-76.0763,
        species=('Striped bass', 'White perch', 'Blue catfish', 'Snakehead nearby', 'Croaker seasonally'),
        note='Approx. 1.5-2 hr from Baltimore. Tidal river; moving tide is usually key.',
        tide_station='8571892',
    ),
    'solomons_island': Location(
        key='solomons_island',
        name='Solomons Island / Patuxent River, MD',
        short_name='Solomons',
        lat=38.3185,
        lon=-76.4541,
        species=('Striped bass', 'White perch', 'Speckled trout seasonally', 'Bluefish seasonally'),
        note='Approx. 1.5-2 hr from Baltimore. Lower Chesapeake tidal/current spot.',
        tide_station='8577330',
    ),
    'chesapeake_beach': Location(
        key='chesapeake_beach',
        name='Chesapeake Beach / North Beach, MD',
        short_name='Chesapeake Beach',
        lat=38.6873,
        lon=-76.533,
        species=('Striped bass', 'White perch', 'Spot', 'Bluefish seasonally'),
        note='Approx. 1.2 hr from Baltimore. Bay-shore wind and tide matter a lot.',
        tide_station='8575512',
    ),
    'ocean_city_inlet': Location(
        key='ocean_city_inlet',
        name='Ocean City Inlet, MD',
        short_name='Ocean City Inlet',
        lat=38.3285,
        lon=-75.0913,
        species=('Flounder', 'Striped bass seasonally', 'Bluefish', 'Tautog', 'Sheepshead'),
        note='Approx. 2.5-3 hr from Baltimore. Inlet current can be powerful; fish moving tide.',
        tide_station='8570283',
    ),
    'assateague_surf': Location(
        key='assateague_surf',
        name='Assateague Island Surf, MD',
        short_name='Assateague',
        lat=38.0834,
        lon=-75.2045,
        species=('Striped bass seasonally', 'Bluefish', 'Red drum seasonally', 'Kingfish', 'Sharks seasonally'),
        note='Approx. 3 hr from Baltimore. Surf conditions depend on wind, swell, and tide.',
        tide_station='8570283',
    ),
    'deep_creek_lake': Location(
        key='deep_creek_lake',
        name='Deep Creek Lake, Western MD',
        short_name='Deep Creek',
        lat=39.5019,
        lon=-79.3672,
        species=('Smallmouth bass', 'Largemouth bass', 'Walleye', 'Pike', 'Yellow perch'),
        note='Approx. 3.5 hr from Baltimore. Large freshwater lake; score is weather/alert based.',
    ),
    'north_branch_potomac_cumberland': Location(
        key='north_branch_potomac_cumberland',
        name='North Branch Potomac near Cumberland, MD',
        short_name='N Branch Potomac',
        lat=39.6529,
        lon=-78.7636,
        species=('Trout', 'Smallmouth bass', 'Walleye', 'Catfish'),
        note='Approx. 2.5 hr from Baltimore. Mountain river conditions change after rain/releases.',
        usgs_site='01603000',
    ),
    'potomac_hancock': Location(
        key='potomac_hancock',
        name='Potomac River at Hancock, MD',
        short_name='Potomac Hancock',
        lat=39.7007,
        lon=-78.1761,
        species=('Smallmouth bass', 'Walleye', 'Muskie', 'Catfish'),
        note='Approx. 2 hr from Baltimore. Big river smallmouth/current conditions.',
        usgs_site='01613000',
    ),
    'potomac_point_of_rocks': Location(
        key='potomac_point_of_rocks',
        name='Potomac River at Point of Rocks, MD',
        short_name='Point of Rocks',
        lat=39.2732,
        lon=-77.5395,
        species=('Smallmouth bass', 'Walleye', 'Catfish', 'Carp'),
        note='Approx. 1.2 hr from Baltimore. Great big-river access; watch rising water.',
        usgs_site='01638500',
    ),
    'potomac_little_falls': Location(
        key='potomac_little_falls',
        name='Potomac River near Little Falls / DC, MD',
        short_name='Little Falls Potomac',
        lat=38.9496,
        lon=-77.1278,
        species=('Smallmouth bass', 'Catfish', 'Striped bass seasonally', 'Snakehead tidal areas'),
        note='Approx. 1 hr from Baltimore. Big-water rocks/current; unsafe at high flows.',
        usgs_site='01646500',
    ),
    'tidal_potomac_dc': Location(
        key='tidal_potomac_dc',
        name='Tidal Potomac / Washington DC',
        short_name='Tidal Potomac',
        lat=38.873,
        lon=-77.0215,
        species=('Blue catfish', 'Snakehead', 'Largemouth bass', 'Striped bass seasonally'),
        note='Approx. 1 hr from Baltimore. Tidal urban river; moving tide helps.',
        tide_station='8594900',
    ),
    'shenandoah_millville': Location(
        key='shenandoah_millville',
        name='Shenandoah River at Millville, WV',
        short_name='Shenandoah',
        lat=39.2868,
        lon=-77.7875,
        species=('Smallmouth bass', 'Largemouth bass', 'Catfish', 'Muskie'),
        note='Approx. 1.5-2 hr from Baltimore. Float/current conditions are important.',
        usgs_site='01636500',
    ),
    'susquehanna_harrisburg': Location(
        key='susquehanna_harrisburg',
        name='Susquehanna River at Harrisburg, PA',
        short_name='Susquehanna Harrisburg',
        lat=40.2548,
        lon=-76.8863,
        species=('Smallmouth bass', 'Catfish', 'Walleye', 'Muskie'),
        note='Approx. 1.5 hr from Baltimore. Major smallmouth river; high water gets dangerous.',
        usgs_site='01570500',
    ),
    'juniata_newport': Location(
        key='juniata_newport',
        name='Juniata River at Newport, PA',
        short_name='Juniata Newport',
        lat=40.476,
        lon=-77.1305,
        species=('Smallmouth bass', 'Catfish', 'Muskie', 'Walleye'),
        note='Approx. 2-2.5 hr from Baltimore. Clear-water smallmouth/current spot.',
        usgs_site='01567000',
    ),
    'raystown_branch_saxton': Location(
        key='raystown_branch_saxton',
        name='Raystown Branch Juniata at Saxton, PA',
        short_name='Raystown Branch',
        lat=40.2135,
        lon=-78.246,
        species=('Smallmouth bass', 'Trout', 'Walleye', 'Catfish'),
        note='Approx. 3 hr from Baltimore. River near Raystown area with flow gauge.',
        usgs_site='01562000',
    ),
    'raystown_lake': Location(
        key='raystown_lake',
        name='Raystown Lake, PA',
        short_name='Raystown Lake',
        lat=40.4131,
        lon=-78.0103,
        species=('Striped bass', 'Smallmouth bass', 'Largemouth bass', 'Lake trout', 'Walleye'),
        note='Approx. 2.5-3 hr from Baltimore. Large reservoir; score is weather/alert based.',
    ),
    'delaware_river_trenton': Location(
        key='delaware_river_trenton',
        name='Delaware River at Trenton, NJ',
        short_name='Delaware Trenton',
        lat=40.2184,
        lon=-74.7659,
        species=('Striped bass seasonally', 'Smallmouth bass', 'Catfish', 'Shad seasonally'),
        note='Approx. 2.5 hr from Baltimore. Major river/tidal transition nearby.',
        usgs_site='01463500',
    ),
    'schuylkill_philly': Location(
        key='schuylkill_philly',
        name='Schuylkill River at Philadelphia, PA',
        short_name='Schuylkill Philly',
        lat=39.9645,
        lon=-75.18,
        species=('Catfish', 'Smallmouth bass', 'Carp', 'Striped bass lower river'),
        note='Approx. 1.5-2 hr from Baltimore. Urban river; avoid storm runoff.',
        usgs_site='01474500',
    ),
    'brandywine_wilmington': Location(
        key='brandywine_wilmington',
        name='Brandywine Creek at Wilmington, DE',
        short_name='Brandywine',
        lat=39.7646,
        lon=-75.5603,
        species=('Smallmouth bass', 'Trout stocked sections', 'Catfish', 'Sunfish'),
        note='Approx. 1.2 hr from Baltimore. Creek/urban river flow can rise quickly.',
        usgs_site='01481500',
    ),
    'lewes_cape_henlopen': Location(
        key='lewes_cape_henlopen',
        name='Lewes / Cape Henlopen, DE',
        short_name='Lewes',
        lat=38.7826,
        lon=-75.1193,
        species=('Flounder', 'Striped bass seasonally', 'Bluefish', 'Tautog', 'Croaker'),
        note='Approx. 2.5 hr from Baltimore. Delaware Bay/ocean-side tide and wind spot.',
        tide_station='8557380',
    ),
    'indian_river_inlet': Location(
        key='indian_river_inlet',
        name='Indian River Inlet, DE',
        short_name='Indian River Inlet',
        lat=38.6105,
        lon=-75.0705,
        species=('Flounder', 'Striped bass seasonally', 'Bluefish', 'Tautog', 'Sheepshead'),
        note='Approx. 2.5-3 hr from Baltimore. Inlet current can be fast; fish moving water safely.',
        tide_station='8558690',
    ),
    'delaware_bay_broadkill': Location(
        key='delaware_bay_broadkill',
        name='Delaware Bay / Broadkill Beach, DE',
        short_name='Broadkill Bay',
        lat=38.8082,
        lon=-75.203,
        species=('Striped bass seasonally', 'Black drum seasonally', 'Weakfish', 'Croaker', 'Flounder'),
        note='Approx. 2.5 hr from Baltimore. Bay surf/wind/tide conditions matter.',
        tide_station='8557380',
    ),
    'cape_may': Location(
        key='cape_may',
        name='Cape May / Delaware Bay, NJ',
        short_name='Cape May',
        lat=38.9351,
        lon=-74.906,
        species=('Striped bass seasonally', 'Flounder', 'Bluefish', 'Tautog', 'Black drum seasonally'),
        note='Approx. 3-3.5 hr from Baltimore. Big bay/ocean mix; tide movement is key.',
        tide_station='8536110',
    ),
    'atlantic_city': Location(
        key='atlantic_city',
        name='Atlantic City / Absecon Inlet, NJ',
        short_name='Atlantic City',
        lat=39.3643,
        lon=-74.4229,
        species=('Striped bass seasonally', 'Flounder', 'Bluefish', 'Tautog', 'Weakfish'),
        note='Approx. 3 hr from Baltimore. Inlet/surf conditions depend on tide and wind.',
        tide_station='8534720',
    ),
    'sandy_hook_raritan': Location(
        key='sandy_hook_raritan',
        name='Sandy Hook / Raritan Bay, NJ',
        short_name='Sandy Hook',
        lat=40.4665,
        lon=-74.0094,
        species=('Striped bass', 'Bluefish', 'Fluke', 'Blackfish', 'Weakfish'),
        note='Approx. 3.5-4 hr from Baltimore. Strong tidal water and surf/bay wind exposure.',
        tide_station='8531680',
    ),
    'long_island_sound': Location(
        key='long_island_sound',
        name='Long Island Sound / Port Jefferson, NY',
        short_name='Long Island Sound',
        lat=40.9500,
        lon=-73.0767,
        species=('Striped bass', 'Bluefish', 'Fluke', 'Porgy', 'Blackfish', 'Sharks seasonally'),
        note='Approx. 4.5-5.5 hr from Baltimore. Tidal Sound water; wind/current matter.',
        tide_station='8514560',
    ),
    'long_island_sound_stamford': Location(
        key='long_island_sound_stamford',
        name='Long Island Sound / Stamford Harbor, CT',
        short_name='LIS Stamford CT',
        lat=41.0534,
        lon=-73.5387,
        species=('Striped bass', 'Bluefish', 'Fluke', 'Porgy', 'Blackfish', 'Sharks seasonally'),
        note='Approx. 4-5 hr from Baltimore. Connecticut-side western Long Island Sound; tide/current and wind matter.',
        tide_station='8469198',
    ),
    'lake_anna': Location(
        key='lake_anna',
        name='Lake Anna, VA',
        short_name='Lake Anna',
        lat=38.1118,
        lon=-77.8336,
        species=('Largemouth bass', 'Striped bass', 'Crappie', 'Catfish', 'White perch'),
        note='Approx. 2.5-3 hr from Baltimore. Reservoir score is weather/alert based.',
    ),
    'rappahannock_fredericksburg': Location(
        key='rappahannock_fredericksburg',
        name='Rappahannock River near Fredericksburg, VA',
        short_name='Rappahannock',
        lat=38.3048,
        lon=-77.4605,
        species=('Smallmouth bass', 'Largemouth bass', 'Shad seasonally', 'Striped bass seasonally', 'Catfish'),
        note='Approx. 2 hr from Baltimore. Fall-line/tidal transition nearby; watch flows.',
        usgs_site='01668000',
    ),
    'james_river_cartersville': Location(
        key='james_river_cartersville',
        name='James River at Cartersville, VA',
        short_name='James Cartersville',
        lat=37.6693,
        lon=-78.0864,
        species=('Smallmouth bass', 'Flathead catfish', 'Blue catfish', 'Muskie'),
        note='Approx. 3.5 hr from Baltimore. Big river float/current reference above Richmond.',
        usgs_site='02035000',
    ),
    'james_river_richmond': Location(
        key='james_river_richmond',
        name='James River near Richmond, VA',
        short_name='James Richmond',
        lat=37.5407,
        lon=-77.433,
        species=('Striped bass seasonally', 'Shad seasonally', 'Smallmouth bass', 'Blue catfish', 'Flathead catfish'),
        note='Approx. 3 hr from Baltimore. Fall-line/current spot; high water is dangerous.',
        usgs_site='02037500',
    ),
    'smith_mountain_lake': Location(
        key='smith_mountain_lake',
        name='Smith Mountain Lake, VA',
        short_name='Smith Mountain',
        lat=37.0435,
        lon=-79.6045,
        species=('Striped bass', 'Largemouth bass', 'Smallmouth bass', 'Catfish', 'Crappie'),
        note='Approx. 4.5-5 hr from Baltimore. Large reservoir; score is weather/alert based.',
    ),
    'chincoteague_assateague_va': Location(
        key='chincoteague_assateague_va',
        name='Chincoteague / VA Assateague, VA',
        short_name='Chincoteague',
        lat=37.9332,
        lon=-75.3788,
        species=('Flounder', 'Red drum seasonally', 'Speckled trout', 'Bluefish', 'Striped bass seasonally'),
        note='Approx. 3.5 hr from Baltimore. Barrier island/surf/back-bay conditions.',
    ),
    'virginia_beach_rudee': Location(
        key='virginia_beach_rudee',
        name='Virginia Beach / Rudee Inlet, VA',
        short_name='Virginia Beach',
        lat=36.8322,
        lon=-75.9713,
        species=('Red drum seasonally', 'Cobia seasonally', 'Flounder', 'Bluefish', 'Striped bass seasonally'),
        note='Approx. 4.5-5 hr from Baltimore. Oceanfront/inlet wind, tide, and storms matter.',
        tide_station='8638863',
    ),
    'chesapeake_bay_bridge_tunnel': Location(
        key='chesapeake_bay_bridge_tunnel',
        name='Chesapeake Bay Bridge-Tunnel, VA',
        short_name='CBBT',
        lat=36.9665,
        lon=-76.1134,
        species=('Cobia seasonally', 'Red drum seasonally', 'Sheepshead', 'Tautog', 'Striped bass seasonally'),
        note='Approx. 4.5-5 hr from Baltimore. Big-water structure; marine weather matters.',
        tide_station='8638863',
    ),
    'nags_head_obx': Location(
        key='nags_head_obx',
        name="Nags Head / Jennette's Pier, NC",
        short_name='Nags Head',
        lat=35.9574,
        lon=-75.6241,
        species=('Red drum seasonally', 'Bluefish', 'Spanish mackerel seasonally', 'Sea mullet', 'Sharks seasonally'),
        note='Approx. 5.5-6 hr from Baltimore. Surf/pier conditions; use as a road-trip watch spot.',
        tide_station='8651370',
    ),
    'oregon_inlet_obx': Location(
        key='oregon_inlet_obx',
        name='Oregon Inlet / Outer Banks, NC',
        short_name='Oregon Inlet',
        lat=35.7952,
        lon=-75.548,
        species=('Red drum seasonally', 'Bluefish', 'Flounder', 'Speckled trout', 'Offshore species by charter'),
        note='Approx. 5.5-6 hr from Baltimore. Inlet/ocean conditions can change fast.',
        tide_station='8651370',
    ),
}


# Maryland public fishing piers and public wharf/dock access. Coordinates approximate.
# Do not interpret location inclusion as live access, pier opening, or legal-crabbing confirmation.
MARYLAND_PIER_KEYS = (
    'jonas_green_pier',
    'fort_smallwood_pier',
    'downs_park_pier',
    'sandy_point_pier',
    'north_point_crystal_pier',
    'canton_pier',
    'broening_park_pier',
    'coxs_point_pier',
    'matapeake_pier',
    'romancoke_pier',
    'deale_wharf',
    'north_beach_pier',
    'solomons_fishing_pier',
    'kings_landing_pier',
    'lower_marlboro_wharf',
    'gatewood_preserve_pier',
    'point_lookout_pier',
    'janes_island_access',
    'havre_congress_pier',
    'hutchins_park_pier',
    'crisfield_city_dock',
    'sharptown_pier',
    'tyaskin_pier',
    'pocomoke_milburn_pier',
    'pocomoke_shad_landing',
    'ocean_city_inlet_pier',
    'ocean_city_3rd_pier',
    'ocean_city_9th_pier',
    'ocean_city_convention_pier',
    'ocean_city_northside_pier',
    'smallwood_sweden_point_pier',
)
LOCATIONS.update({
    'jonas_green_pier': Location(key='jonas_green_pier', name='Jonas and Anne Catharine Green Park Fishing Pier, Annapolis MD', short_name='Jonas Green Pier',
        lat=39.0052, lon=-76.485, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='Severn River, 288-foot public fishing pier. Check park gate hours.', tide_station='8575512'),
    'fort_smallwood_pier': Location(key='fort_smallwood_pier', name='Fort Smallwood Park Fishing Pier, Pasadena MD', short_name='Fort Smallwood Pier',
        lat=39.2305, lon=-76.5236, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='380-foot fishing pier near the mouth of the Patapsco. Park entry/hours apply.', tide_station='8574680'),
    'downs_park_pier': Location(key='downs_park_pier', name='Downs Park Fishing Pier, Pasadena MD', short_name='Downs Park Pier',
        lat=39.1187, lon=-76.4339, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='Chesapeake Bay fishing pier. Park entrance fees and seasonal hours may apply.', tide_station='8575512'),
    'sandy_point_pier': Location(key='sandy_point_pier', name='Sandy Point State Park Fishing Pier, Annapolis MD', short_name='Sandy Point Pier',
        lat=39.0138, lon=-76.4014, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='Bay Bridge area; fish from designated pier/shore. Check park access and wind.', tide_station='8575512'),
    'north_point_crystal_pier': Location(key='north_point_crystal_pier', name='North Point State Park Crystal Pier, Edgemere MD', short_name='Crystal Pier',
        lat=39.1952, lon=-76.4327, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='IMPORTANT: end of Crystal Pier closed for repairs until further notice; only use accessible sections.', tide_station='8574680'),
    'canton_pier': Location(key='canton_pier', name='Canton Waterfront Park Recreational Pier, Baltimore MD', short_name='Canton Pier',
        lat=39.2772, lon=-76.572, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='Fishing pier on Baltimore Harbor. Check fish consumption advisories.', tide_station='8574680'),
    'broening_park_pier': Location(key='broening_park_pier', name='Broening Park Fishing Pier / Middle Branch, Baltimore MD', short_name='Broening Pier',
        lat=39.2457, lon=-76.6178, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='Designated fishing pier near Hanover Street bridge; check shoreline access.', tide_station='8574680'),
    'coxs_point_pier': Location(key='coxs_point_pier', name='Coxs Point Park Fishing Access, Essex MD', short_name='Coxs Point',
        lat=39.2882, lon=-76.4588, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='Back River fishing access; verify current dock/pier conditions before travel.', tide_station='8574680'),
    'matapeake_pier': Location(key='matapeake_pier', name='Matapeake Fishing Pier, Stevensville MD', short_name='Matapeake Pier',
        lat=38.956, lon=-76.3539, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='650-foot lighted fishing and crabbing pier. Parking fee; pier open 24 hours.', tide_station='8575512'),
    'romancoke_pier': Location(key='romancoke_pier', name='Romancoke Fishing Pier, Stevensville MD', short_name='Romancoke Pier',
        lat=38.9005, lon=-76.3606, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='600-foot pier on Eastern Bay. Parking fee; posted hours 6 AM-9 PM.', tide_station='8575512'),
    'deale_wharf': Location(key='deale_wharf', name='Deale Wharf Fishing Access, Deale MD', short_name='Deale Wharf',
        lat=38.7731, lon=-76.5592, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='Rockhold Creek wharf. Pier repair project ongoing in 2026; verify access before travel.', tide_station='8575512'),
    'north_beach_pier': Location(key='north_beach_pier', name='North Beach Fishing Pier, North Beach MD', short_name='North Beach Pier',
        lat=38.7071, lon=-76.533, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='Lower-level fishing deck requires a fishing pass; pier closes at dark.', tide_station='8575512'),
    'solomons_fishing_pier': Location(key='solomons_fishing_pier', name='Solomons Public Fishing and Crabbing Pier, Solomons MD', short_name='Solomons Pier',
        lat=38.3219, lon=-76.4551, species=('Striped bass seasonally', 'White perch', 'Croaker seasonally', 'Spot seasonally', 'Blue crab'),
        note='Patuxent River boat-ramp pier. Seasonal pier hours; launch area is not fishing area.', tide_station='8577330'),
    'kings_landing_pier': Location(key='kings_landing_pier', name='Kings Landing Park Fishing Pier, Huntingtown MD', short_name='Kings Landing Pier',
        lat=38.6427, lon=-76.664, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='Patuxent River fishing/crabbing pier. Park and pier close before evening.', tide_station='8577330'),
    'lower_marlboro_wharf': Location(key='lower_marlboro_wharf', name='Lower Marlboro Wharf Fishing Pier, Owings MD', short_name='Lower Marlboro Wharf',
        lat=38.6542, lon=-76.676, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='Public wharf on the Patuxent; dawn to dusk, no overnight parking.', tide_station='8577330'),
    'gatewood_preserve_pier': Location(key='gatewood_preserve_pier', name='Gatewood Preserve Fishing Pier, Prince Frederick MD', short_name='Gatewood Pier',
        lat=38.5646, lon=-76.5355, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='Wooden pier reached by footpath and stairs. Pier may be inaccessible at low tide.', tide_station='8577330'),
    'point_lookout_pier': Location(key='point_lookout_pier', name='Point Lookout State Park Fishing Pier, Scotland MD', short_name='Point Lookout Pier',
        lat=38.0532, lon=-76.3255, species=('Striped bass seasonally', 'White perch', 'Croaker seasonally', 'Spot seasonally', 'Blue crab'),
        note='710-foot fishing pier; operates roughly mid-April to mid-December. No night fishing.', tide_station='8577330'),
    'janes_island_access': Location(key='janes_island_access', name='Janes Island State Park Marina / Daugherty Creek, Crisfield MD', short_name='Janes Island Dock',
        lat=37.9789, lon=-75.8619, species=('Striped bass seasonally', 'White perch', 'Croaker seasonally', 'Spot seasonally', 'Blue crab'),
        note='Fishing and handline crabbing access around marina/bulkhead. Follow posted zones.', tide_station='8571892'),
    'havre_congress_pier': Location(key='havre_congress_pier', name='Congress Street Fishing Pier, Havre de Grace MD', short_name='Congress St Pier',
        lat=39.5446, lon=-76.0901, species=('White perch', 'Blue catfish', 'Channel catfish', 'Largemouth bass'),
        note='Public fishing pier at end of Congress Street, Susquehanna tidal river.', tide_station='8574680'),
    'hutchins_park_pier': Location(key='hutchins_park_pier', name='Frank J. Hutchins Park Fishing Piers, Havre de Grace MD', short_name='Hutchins Park',
        lat=39.547, lon=-76.0885, species=('White perch', 'Blue catfish', 'Channel catfish', 'Largemouth bass'),
        note='Public park with fishing piers along Susquehanna River.', tide_station='8574680'),
    'crisfield_city_dock': Location(key='crisfield_city_dock', name='Crisfield City Dock Fishing Access, Crisfield MD', short_name='Crisfield Dock',
        lat=37.976, lon=-75.8571, species=('Striped bass seasonally', 'White perch', 'Croaker seasonally', 'Spot seasonally', 'Blue crab'),
        note='Public city dock / depot at end of West Main Street.', tide_station='8571892'),
    'sharptown_pier': Location(key='sharptown_pier', name='Sharptown Fishing Pier and Town Dock, Sharptown MD', short_name='Sharptown Pier',
        lat=38.5408, lon=-75.7198, species=('White perch', 'Blue catfish', 'Channel catfish', 'Largemouth bass'),
        note='Public pier off Ferry Street on Nanticoke River; low-salinity river.', tide_station='8571892'),
    'tyaskin_pier': Location(key='tyaskin_pier', name='Tyaskin Park Fishing Pier, Tyaskin MD', short_name='Tyaskin Pier',
        lat=38.3124, lon=-75.8902, species=('Striped bass seasonally', 'White perch', 'Spot seasonally', 'Blue catfish', 'Blue crab'),
        note='Public park pier by Wetipquin Creek; check local access.', tide_station='8571892'),
    'pocomoke_milburn_pier': Location(key='pocomoke_milburn_pier', name='Pocomoke River State Park Milburn Landing Pier, Pocomoke City MD', short_name='Milburn Pier',
        lat=38.1015, lon=-75.4663, species=('White perch', 'Blue catfish', 'Channel catfish', 'Largemouth bass'),
        note='Public fishing pier; Milburn Landing seasonal April-mid-December sunrise-sunset.', tide_station=None),
    'pocomoke_shad_landing': Location(key='pocomoke_shad_landing', name='Pocomoke River State Park Shad Landing Pier, Snow Hill MD', short_name='Shad Landing',
        lat=38.1424, lon=-75.4405, species=('White perch', 'Blue catfish', 'Channel catfish', 'Largemouth bass'),
        note='River-side marina fishing access (separate from stocked trout pond).', tide_station=None),
    'ocean_city_inlet_pier': Location(key='ocean_city_inlet_pier', name='Ocean City Inlet Park Fishing Pier, Ocean City MD', short_name='OC Inlet Pier',
        lat=38.3267, lon=-75.0875, species=('Flounder', 'Bluefish seasonally', 'Spot', 'Striped bass seasonally', 'Blue crab'),
        note='Public inlet fishing access; strong current and exposed wind.', tide_station='8570283'),
    'ocean_city_3rd_pier': Location(key='ocean_city_3rd_pier', name='Ocean City 3rd Street Bayside Pier, Ocean City MD', short_name='OC 3rd St Pier',
        lat=38.3346, lon=-75.0883, species=('Flounder', 'Bluefish seasonally', 'Spot', 'Striped bass seasonally', 'Blue crab'),
        note='Public bayside fishing pier on Chicago Avenue near 3rd Street.', tide_station='8570283'),
    'ocean_city_9th_pier': Location(key='ocean_city_9th_pier', name='Ocean City 9th Street Fishing Pier, Ocean City MD', short_name='OC 9th St Pier',
        lat=38.3403, lon=-75.0891, species=('Flounder', 'Bluefish seasonally', 'Spot', 'Striped bass seasonally', 'Blue crab'),
        note='Public bayside fishing pier on 9th Street.', tide_station='8570283'),
    'ocean_city_convention_pier': Location(key='ocean_city_convention_pier', name='Ocean City Convention Center Bayside Pier, Ocean City MD', short_name='OC 40th St Pier',
        lat=38.371, lon=-75.0729, species=('Flounder', 'Bluefish seasonally', 'Spot', 'Striped bass seasonally', 'Blue crab'),
        note='Public bayside bulkhead/pier behind convention center; fishing/crabbing on high tide.', tide_station='8570283'),
    'ocean_city_northside_pier': Location(key='ocean_city_northside_pier', name='Northside Park Fishing Pier (125th Street), Ocean City MD', short_name='OC Northside Pier',
        lat=38.4314, lon=-75.0556, species=('Flounder', 'Bluefish seasonally', 'Spot', 'Striped bass seasonally', 'Blue crab'),
        note='Public pier near recreation center; light fishing and crabbing.', tide_station='8570283'),
    'smallwood_sweden_point_pier': Location(key='smallwood_sweden_point_pier', name='Smallwood State Park Sweden Point Marina Fishing Piers, Marbury MD', short_name='Sweden Point Piers',
        lat=38.5512, lon=-77.1858, species=('White perch', 'Blue catfish', 'Channel catfish', 'Largemouth bass'),
        note='Stationary fishing piers along tidal Potomac. Check marina rules.', tide_station=None),
})

# Blue crab is a crabbing species, not a finfish. Enable only at tidal areas.
MARYLAND_BLUE_CRAB_EXISTING_KEYS = ('annapolis_bay', 'assateague_surf', 'baltimore_harbor', 'cambridge_choptank', 'chesapeake_beach', 'chincoteague_assateague_va', 'ocean_city_inlet', 'sandy_point_bay_bridge', 'solomons_island', 'tidal_potomac_dc')
for _crab_key in MARYLAND_BLUE_CRAB_EXISTING_KEYS:
    _old = LOCATIONS[_crab_key]
    if not any(s.casefold() == "blue crab" for s in _old.species):
        LOCATIONS[_crab_key] = Location(key=_old.key, name=_old.name, short_name=_old.short_name,
            lat=_old.lat, lon=_old.lon, species=_old.species + ("Blue crab",),
            note=_old.note, usgs_site=_old.usgs_site, tide_station=_old.tide_station)

DEFAULT_CONFIG = {
    "Bot": {
        "check_every_minutes": "60",
        "post_on_start": "false",
        "post_every_check": "true",
        "score_change_to_alert": "10",
    },
    "Discord": {
        "enabled": "false",
        "webhook_url": "https://discord.com/api/webhooks/your_webhook_here",
        "username": APP_NAME,
    },
    "Locations": {f"{key}_enabled": "true" for key in LOCATIONS},
    "LocationWebhooks": {key: "" for key in LOCATIONS},
    "FlowThresholds": {
        # Starter fishing/safety thresholds. Tune these after watching each gauge for a few trips.
        'conowingo_dam' + "_good_min_cfs": '25000',
        'conowingo_dam' + "_high_flow_cfs": '90000',
        'deer_creek' + "_good_min_cfs": '30',
        'deer_creek' + "_high_flow_cfs": '600',
        'gunpowder_falls' + "_good_min_cfs": '35',
        'gunpowder_falls' + "_high_flow_cfs": '600',
        'patapsco_elkridge' + "_good_min_cfs": '100',
        'patapsco_elkridge' + "_high_flow_cfs": '1500',
        'north_branch_potomac_cumberland' + "_good_min_cfs": '500',
        'north_branch_potomac_cumberland' + "_high_flow_cfs": '8000',
        'potomac_hancock' + "_good_min_cfs": '1500',
        'potomac_hancock' + "_high_flow_cfs": '25000',
        'potomac_point_of_rocks' + "_good_min_cfs": '2000',
        'potomac_point_of_rocks' + "_high_flow_cfs": '35000',
        'potomac_little_falls' + "_good_min_cfs": '2500',
        'potomac_little_falls' + "_high_flow_cfs": '45000',
        'shenandoah_millville' + "_good_min_cfs": '1200',
        'shenandoah_millville' + "_high_flow_cfs": '20000',
        'susquehanna_harrisburg' + "_good_min_cfs": '15000',
        'susquehanna_harrisburg' + "_high_flow_cfs": '120000',
        'juniata_newport' + "_good_min_cfs": '1000',
        'juniata_newport' + "_high_flow_cfs": '20000',
        'raystown_branch_saxton' + "_good_min_cfs": '300',
        'raystown_branch_saxton' + "_high_flow_cfs": '7000',
        'delaware_river_trenton' + "_good_min_cfs": '5000',
        'delaware_river_trenton' + "_high_flow_cfs": '60000',
        'schuylkill_philly' + "_good_min_cfs": '500',
        'schuylkill_philly' + "_high_flow_cfs": '15000',
        'brandywine_wilmington' + "_good_min_cfs": '100',
        'brandywine_wilmington' + "_high_flow_cfs": '4000',
        'rappahannock_fredericksburg' + "_good_min_cfs": '500',
        'rappahannock_fredericksburg' + "_high_flow_cfs": '15000',
        'james_river_cartersville' + "_good_min_cfs": '3000',
        'james_river_cartersville' + "_high_flow_cfs": '50000',
        'james_river_richmond' + "_good_min_cfs": '4000',
        'james_river_richmond' + "_high_flow_cfs": '60000',
    },
    "Safety": {
        "use_nws_alerts": "true",
        "bad_wind_mph": "20",
    },
}

CFG = configparser.ConfigParser()


def ensure_config() -> None:
    changed = False
    if CONFIG_FILE.exists():
        CFG.read(CONFIG_FILE, encoding="utf-8")
    for section, values in DEFAULT_CONFIG.items():
        if not CFG.has_section(section):
            CFG.add_section(section)
            changed = True
        for key, value in values.items():
            if not CFG.has_option(section, key):
                CFG.set(section, key, value)
                changed = True
    if changed or not CONFIG_FILE.exists():
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            CFG.write(f)


def log(message: str) -> None:
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def cfg_bool(section: str, option: str, fallback: bool) -> bool:
    try:
        return CFG.getboolean(section, option, fallback=fallback)
    except Exception:
        return fallback


def cfg_int(section: str, option: str, fallback: int) -> int:
    try:
        return CFG.getint(section, option, fallback=fallback)
    except Exception:
        return fallback


def cfg_float(section: str, option: str, fallback: float) -> float:
    try:
        return CFG.getfloat(section, option, fallback=fallback)
    except Exception:
        return fallback


def cfg_str(section: str, option: str, fallback: str = "") -> str:
    try:
        return CFG.get(section, option, fallback=fallback).strip()
    except Exception:
        return fallback


def get_url(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def get_json(url: str, timeout: int = 20) -> Any:
    return json.loads(get_url(url, timeout=timeout))


def parse_iso_time(text: str) -> Optional[dt.datetime]:
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def load_state() -> Dict[str, Any]:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_state(state: Dict[str, Any]) -> None:
    try:
        STATE_DIR.mkdir(exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as exc:
        log(f"Could not save state: {exc}")


def enabled_locations() -> List[Location]:
    ensure_config()
    return [loc for key, loc in LOCATIONS.items() if cfg_bool("Locations", f"{key}_enabled", True)]


def fetch_usgs(site: str) -> Dict[str, Any]:
    params = urllib.parse.urlencode({
        "format": "json",
        "sites": site,
        "parameterCd": ",".join([PARAM_DISCHARGE, PARAM_GAGE_HEIGHT, PARAM_WATER_TEMP]),
        "period": "P2D",
        "siteStatus": "all",
    })
    url = f"https://waterservices.usgs.gov/nwis/iv/?{params}"
    data = get_json(url)
    readings: Dict[str, Any] = {"site": site, "source_url": url, "values": {}}
    series = data.get("value", {}).get("timeSeries", [])
    for ts in series:
        var = ts.get("variable", {})
        codes = var.get("variableCode", [])
        code = codes[0].get("value") if codes else ""
        name = var.get("variableName", code)
        unit = ""
        try:
            unit = var.get("unit", {}).get("unitCode", "")
        except Exception:
            unit = ""
        vals = []
        for block in ts.get("values", []):
            for row in block.get("value", []):
                val = row.get("value")
                when = parse_iso_time(row.get("dateTime", ""))
                try:
                    fval = float(val)
                except Exception:
                    continue
                vals.append({"value": fval, "time": when.isoformat() if when else row.get("dateTime", "")})
        vals.sort(key=lambda r: r.get("time") or "")
        if vals:
            readings["values"][code] = {"name": name, "unit": unit, "latest": vals[-1], "history": vals[-96:]}
    return readings


_NOAA_TIDE_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def fetch_noaa_tide(station: str) -> Dict[str, Any]:
    # Same NOAA station serves many piers. Share snapshots for five minutes to
    # avoid dozens of duplicate requests during a full dashboard refresh.
    cached = _NOAA_TIDE_CACHE.get(station)
    if cached and time.monotonic() - cached[0] < 300:
        return cached[1]

    now = dt.datetime.now()
    begin_date = now.strftime("%Y%m%d")
    common = {
        "application": "BaltimoreFishingAlerts",
        "station": station,
        "time_zone": "lst_ldt",
        "units": "english",
        "format": "json",
    }
    pred_params = dict(common)
    pred_params.update({
        "product": "predictions",
        "begin_date": begin_date,
        "range": "48",
        "datum": "MLLW",
        "interval": "hilo",
    })
    obs_params = dict(common)
    obs_params.update({
        "product": "water_level",
        "date": "latest",
        "datum": "MLLW",
    })
    met_params = dict(common)
    met_params.update({
        "product": "air_temperature",
        "date": "latest",
    })
    pred_url = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?" + urllib.parse.urlencode(pred_params)
    obs_url = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?" + urllib.parse.urlencode(obs_params)
    met_url = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?" + urllib.parse.urlencode(met_params)
    tide: Dict[str, Any] = {"station": station, "predictions": [], "source_url": pred_url}
    try:
        pred = get_json(pred_url)
        tide["predictions"] = pred.get("predictions", [])
    except Exception as exc:
        tide["prediction_error"] = str(exc)
    try:
        obs = get_json(obs_url)
        rows = obs.get("data", [])
        if rows:
            tide["water_level"] = rows[-1]
    except Exception as exc:
        tide["water_level_error"] = str(exc)
    try:
        met = get_json(met_url)
        rows = met.get("data", [])
        if rows:
            tide["air_temperature"] = rows[-1]
    except Exception:
        pass
    _NOAA_TIDE_CACHE[station] = (time.monotonic(), tide)
    return tide


def fetch_nws_hourly(lat: float, lon: float) -> Dict[str, Any]:
    """Return NWS hourly forecast plus richer Open-Meteo weather details.

    Some marine / bridge / open-water coordinates are outside the regular NWS
    point forecast grid and api.weather.gov returns HTTP 404.  Returning a
    normal error object lets the fishing score still post using tide/water data.
    Open-Meteo is added as a secondary weather source so coastal/tide reports
    can show pressure, clouds, visibility, rain chance, wind gusts, etc., closer
    to the Texoma-style fishing report.
    """
    point_url = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
    result: Dict[str, Any] = {"source_url": point_url, "periods": []}
    try:
        point = get_json(point_url)
        hourly_url = point.get("properties", {}).get("forecastHourly")
        if hourly_url:
            hourly = get_json(hourly_url)
            periods = hourly.get("properties", {}).get("periods", [])
            result.update({"source_url": hourly_url, "periods": periods[:12]})
        else:
            result["error"] = "No NWS hourly forecast URL found"
    except urllib.error.HTTPError as exc:
        result["error"] = f"NWS point lookup HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        result["error"] = f"NWS forecast error: {exc}"

    # Add richer weather details. This should never stop a report from posting.
    om = fetch_open_meteo_weather(lat, lon)
    if om.get("error"):
        result["open_meteo_error"] = om.get("error")
    else:
        result["open_meteo"] = om
    return result


def open_meteo_url(lat: float, lon: float) -> str:
    params = {
        "latitude": f"{lat:.5f}",
        "longitude": f"{lon:.5f}",
        "current": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "precipitation",
            "rain",
            "weather_code",
            "cloud_cover",
            "visibility",
            "pressure_msl",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
        ]),
        "hourly": ",".join([
            "temperature_2m",
            "precipitation_probability",
            "precipitation",
            "pressure_msl",
            "cloud_cover",
            "visibility",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
        ]),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "past_days": "2",
        "forecast_days": "2",
        "timezone": "auto",
    }
    return "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)


def fetch_open_meteo_weather(lat: float, lon: float) -> Dict[str, Any]:
    url = open_meteo_url(lat, lon)
    try:
        data = get_json(url, timeout=20)
        if not isinstance(data, dict):
            return {"source_url": url, "error": "Open-Meteo returned a non-JSON object"}
        data["source_url"] = url
        data["_source_note"] = "Live Open-Meteo weather"
        return data
    except Exception as exc:
        return {"source_url": url, "error": f"Open-Meteo weather error: {exc}"}

def fetch_nws_alerts(lat: float, lon: float) -> Dict[str, Any]:
    url = f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}"
    try:
        data = get_json(url)
        features = data.get("features", [])
        alerts = []
        for feat in features:
            props = feat.get("properties", {})
            alerts.append({
                "event": props.get("event", "Alert"),
                "severity": props.get("severity", ""),
                "headline": props.get("headline", ""),
            })
        return {"source_url": url, "alerts": alerts}
    except Exception as exc:
        return {"source_url": url, "alerts": [], "error": str(exc)}


def latest_usgs_value(usgs: Dict[str, Any], code: str) -> Optional[float]:
    try:
        return float(usgs["values"][code]["latest"]["value"])
    except Exception:
        return None


def usgs_trend_percent(usgs: Dict[str, Any], code: str) -> Optional[float]:
    try:
        hist = usgs["values"][code]["history"]
        if len(hist) < 3:
            return None
        latest = float(hist[-1]["value"])
        # Pick a value roughly 12-24 hours ago if present.
        base = float(hist[max(0, len(hist) - 24)]["value"])
        if base == 0:
            return None
        return ((latest - base) / base) * 100.0
    except Exception:
        return None


def flow_thresholds(key: str) -> Tuple[Optional[float], Optional[float]]:
    good = cfg_float("FlowThresholds", f"{key}_good_min_cfs", math.nan)
    high = cfg_float("FlowThresholds", f"{key}_high_flow_cfs", math.nan)
    return (None if math.isnan(good) else good, None if math.isnan(high) else high)


def tide_window(tide: Dict[str, Any]) -> Dict[str, Any]:
    now = dt.datetime.now()
    preds = []
    for row in tide.get("predictions", []):
        t = None
        raw = row.get("t")
        try:
            t = dt.datetime.strptime(raw, "%Y-%m-%d %H:%M")
        except Exception:
            pass
        if not t:
            continue
        try:
            v = float(row.get("v"))
        except Exception:
            v = None
        preds.append({"time": t, "height": v, "type": row.get("type", "")})
    preds.sort(key=lambda r: r["time"])
    prev = next((p for p in reversed(preds) if p["time"] <= now), None)
    nxt = next((p for p in preds if p["time"] > now), None)
    result = {"previous": prev, "next": nxt}
    if prev and nxt:
        total = (nxt["time"] - prev["time"]).total_seconds()
        elapsed = (now - prev["time"]).total_seconds()
        frac = max(0.0, min(1.0, elapsed / total)) if total > 0 else None
        result["phase_fraction"] = frac
        result["moving"] = frac is not None and 0.15 <= frac <= 0.85
        result["near_slack"] = frac is not None and (frac < 0.12 or frac > 0.88)
        result["hours_to_next"] = (nxt["time"] - now).total_seconds() / 3600.0
        result["incoming"] = prev.get("type") == "L" and nxt.get("type") == "H"
        result["outgoing"] = prev.get("type") == "H" and nxt.get("type") == "L"
    return result


OPEN_METEO_WEATHER_CODES: Dict[int, str] = {
    0: "Clear",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Freezing Fog",
    51: "Light Drizzle",
    53: "Drizzle",
    55: "Heavy Drizzle",
    56: "Freezing Drizzle",
    57: "Freezing Drizzle",
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    66: "Freezing Rain",
    67: "Freezing Rain",
    71: "Light Snow",
    73: "Snow",
    75: "Heavy Snow",
    77: "Snow Grains",
    80: "Chance Showers",
    81: "Showers",
    82: "Heavy Showers",
    85: "Snow Showers",
    86: "Snow Showers",
    95: "Thunderstorms",
    96: "Thunderstorms / Hail",
    99: "Severe Thunderstorms / Hail",
}


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(round(float(value)))
    except Exception:
        return None


def weather_code_text(code: Any) -> str:
    try:
        return OPEN_METEO_WEATHER_CODES.get(int(code), f"Weather code {int(code)}")
    except Exception:
        return "Weather unavailable"


def wind_dir_text(degrees: Any) -> str:
    deg = _to_float(degrees)
    if deg is None:
        return "Unknown"
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((deg + 11.25) // 22.5) % 16]


def visibility_to_miles(value: Any) -> Optional[float]:
    v = _to_float(value)
    if v is None:
        return None
    # Open-Meteo visibility is normally meters. If a future response is already
    # in miles, keep the number sane.
    if v <= 20:
        return v
    return v / 1609.344


def _om_current(weather: Dict[str, Any]) -> Dict[str, Any]:
    om = weather.get("open_meteo") or {}
    return om.get("current") or {}


def _om_hourly(weather: Dict[str, Any]) -> Dict[str, Any]:
    om = weather.get("open_meteo") or {}
    return om.get("hourly") or {}


def _om_hour_index(weather: Dict[str, Any]) -> int:
    current_time = str(_om_current(weather).get("time") or "")
    times = _om_hourly(weather).get("time") or []
    if current_time and current_time in times:
        return times.index(current_time)
    if times:
        return min(len(times) - 1, max(0, len(times) // 2))
    return 0


def _hourly_value(weather: Dict[str, Any], key: str, idx: int) -> Optional[float]:
    values = _om_hourly(weather).get(key) or []
    if not values:
        return None
    idx = max(0, min(len(values) - 1, idx))
    return _to_float(values[idx])


def _next_hours_max(weather: Dict[str, Any], key: str, idx: int, hours: int = 3) -> Optional[float]:
    values = _om_hourly(weather).get(key) or []
    nums = []
    for x in values[idx: idx + max(1, hours)]:
        val = _to_float(x)
        if val is not None:
            nums.append(val)
    return max(nums) if nums else None


def _next_hours_sum(weather: Dict[str, Any], key: str, idx: int, hours: int = 3) -> float:
    values = _om_hourly(weather).get(key) or []
    total = 0.0
    for x in values[idx: idx + max(1, hours)]:
        total += _to_float(x) or 0.0
    return total


def _recent_sum(weather: Dict[str, Any], key: str, idx: int, hours: int = 24) -> float:
    values = _om_hourly(weather).get(key) or []
    start = max(0, idx - hours)
    total = 0.0
    for x in values[start:idx + 1]:
        total += _to_float(x) or 0.0
    return total


def _pressure_trend(weather: Dict[str, Any], idx: int) -> Tuple[str, Optional[float]]:
    now = _to_float(_om_current(weather).get("pressure_msl"))
    if now is None:
        now = _hourly_value(weather, "pressure_msl", idx)
    old = _hourly_value(weather, "pressure_msl", max(0, idx - 3))
    if now is None or old is None:
        return "unknown", None
    change = now - old
    if change <= -1.0:
        return "falling", change
    if change >= 1.0:
        return "rising", change
    return "stable", change


def estimate_water_temp_from_weather(weather: Dict[str, Any]) -> Tuple[Optional[float], str]:
    temps = _om_hourly(weather).get("temperature_2m") or []
    idx = _om_hour_index(weather)
    start = max(0, idx - 48)
    nums = [_to_float(x) for x in temps[start:idx + 1]]
    nums = [x for x in nums if x is not None]
    if not nums:
        return None, "unknown"
    recent = nums[-24:] if len(nums) >= 24 else nums
    recent_avg = sum(recent) / max(1, len(recent))
    two_day_avg = sum(nums) / len(nums)
    # Coastal water changes slower than air; this is only an estimated fishing
    # condition signal when no real water temp feed is configured.
    estimated = (recent_avg * 0.40) + (two_day_avg * 0.60)
    return round(estimated, 1), "estimated from recent air temps"


def moon_phase() -> Tuple[str, int, int]:
    today = dt.datetime.utcnow().date()
    known_new_moon = dt.date(2000, 1, 6)
    days = (today - known_new_moon).days
    age = days % 29.53058867
    illumination = int(round((1 - math.cos(2 * math.pi * age / 29.53058867)) / 2 * 100))
    if age < 1.85:
        name = "New Moon"
    elif age < 5.54:
        name = "Waxing Crescent"
    elif age < 9.23:
        name = "First Quarter"
    elif age < 12.92:
        name = "Waxing Gibbous"
    elif age < 16.61:
        name = "Full Moon"
    elif age < 20.30:
        name = "Waning Gibbous"
    elif age < 23.99:
        name = "Last Quarter"
    elif age < 27.68:
        name = "Waning Crescent"
    else:
        name = "New Moon"
    return name, int(round(age)), illumination


def sun_window_bonus(local_time: Optional[dt.datetime] = None) -> Tuple[int, str]:
    local_time = local_time or dt.datetime.now()
    hour = local_time.hour + local_time.minute / 60.0
    if 5.5 <= hour <= 8.5:
        return 8, "Low-light morning bite window"
    if 18.0 <= hour <= 21.0:
        return 8, "Low-light evening bite window"
    if hour < 5.5:
        return 3, "Pre-sunrise/early low-light period"
    return 0, "Outside the main sunrise/sunset bite window"


def moon_bonus(phase_name: str, illumination: int) -> Tuple[int, str]:
    if phase_name in ("New Moon", "Full Moon"):
        return 5, f"{phase_name} can improve feeding windows"
    if illumination >= 70:
        return 2, "Bright moon may help night/early bite"
    return 0, "Moon is neutral"


def weather_details(weather: Dict[str, Any]) -> Dict[str, Any]:
    """Return rich weather fields used by the Texoma-style Discord report."""
    idx = _om_hour_index(weather)
    current = _om_current(weather)
    om = weather.get("open_meteo") or {}
    if current:
        temp = _to_float(current.get("temperature_2m"))
        feels = _to_float(current.get("apparent_temperature"))
        wind = _to_float(current.get("wind_speed_10m"))
        gust = _to_float(current.get("wind_gusts_10m"))
        wind_dir = wind_dir_text(current.get("wind_direction_10m"))
        clouds = _to_float(current.get("cloud_cover"))
        pressure = _to_float(current.get("pressure_msl"))
        p_trend, p_change = _pressure_trend(weather, idx)
        pop3 = _next_hours_max(weather, "precipitation_probability", idx, 3)
        precip3 = _next_hours_sum(weather, "precipitation", idx, 3)
        rain24 = _recent_sum(weather, "precipitation", idx, 24)
        rain48 = _recent_sum(weather, "precipitation", idx, 48)
        visibility_mi = visibility_to_miles(current.get("visibility"))
        if visibility_mi is None:
            visibility_mi = visibility_to_miles(_hourly_value(weather, "visibility", idx))
        moon_name, moon_age, moon_illum = moon_phase()
        sun_score, sun_note = sun_window_bonus()
        moon_score, moon_note = moon_bonus(moon_name, moon_illum)
        water_temp, water_source = estimate_water_temp_from_weather(weather)
        return {
            "text": weather_code_text(current.get("weather_code")),
            "source": om.get("_source_note") or "Live Open-Meteo weather",
            "temp": temp,
            "feels": feels,
            "wind": wind,
            "gust": gust,
            "wind_dir": wind_dir,
            "clouds": clouds,
            "pressure": pressure,
            "pressure_trend": p_trend,
            "pressure_change_3h": p_change,
            "pop3": pop3,
            "precip3": precip3,
            "rain24": rain24,
            "rain48": rain48,
            "visibility_mi": visibility_mi,
            "sun_score": sun_score,
            "sun_note": sun_note,
            "moon_name": moon_name,
            "moon_age": moon_age,
            "moon_illumination": moon_illum,
            "moon_score": moon_score,
            "moon_note": moon_note,
            "water_temp_estimate": water_temp,
            "water_temp_source": water_source,
        }

    periods = weather.get("periods") or []
    p0 = periods[0] if periods else {}
    moon_name, moon_age, moon_illum = moon_phase()
    _, sun_note = sun_window_bonus()
    _, moon_note = moon_bonus(moon_name, moon_illum)
    return {
        "text": p0.get("shortForecast") or p0.get("detailedForecast") or "Weather unavailable",
        "source": "NWS hourly forecast" if periods else "Weather unavailable",
        "temp": _to_float(p0.get("temperature")),
        "feels": None,
        "wind": None,
        "gust": None,
        "wind_dir": str(p0.get("windDirection") or "Unknown"),
        "clouds": None,
        "pressure": None,
        "pressure_trend": "unknown",
        "pressure_change_3h": None,
        "pop3": None,
        "precip3": 0.0,
        "rain24": 0.0,
        "rain48": 0.0,
        "visibility_mi": None,
        "sun_score": 0,
        "sun_note": sun_note,
        "moon_name": moon_name,
        "moon_age": moon_age,
        "moon_illumination": moon_illum,
        "moon_score": 0,
        "moon_note": moon_note,
        "water_temp_estimate": None,
        "water_temp_source": "unknown",
    }


def summarize_weather(hourly: Dict[str, Any]) -> Dict[str, Any]:
    details = weather_details(hourly)
    text = details.get("text") or "Weather unavailable"
    wind_mph = int(round(details.get("wind") or 0))
    temp = _to_int(details.get("temp"))
    lower = text.lower()
    delta = 0
    reasons = []
    bad = False

    if any(word in lower for word in ["thunder", "storm", "hail"]):
        delta -= 30
        bad = True
        reasons.append("thunderstorms")
    elif any(word in lower for word in ["heavy rain", "heavy showers"]):
        delta -= 12
        reasons.append("heavy rain")
    elif any(word in lower for word in ["cloud", "overcast"]):
        delta += 4
        reasons.append("cloud cover")
    elif any(word in lower for word in ["sunny", "clear"]):
        delta -= 2

    bad_wind = cfg_int("Safety", "bad_wind_mph", 20)
    if wind_mph >= bad_wind:
        delta -= 15
        bad = True
        reasons.append(f"wind {wind_mph} mph")
    elif 5 <= wind_mph <= 15:
        delta += 5
        reasons.append("good chop/wind")

    pop3 = details.get("pop3")
    if isinstance(pop3, (int, float)):
        if pop3 <= 15:
            delta += 2
            reasons.append("low rain chance next 3 hours")
        elif pop3 >= 65:
            delta -= 6
            reasons.append("high rain chance")

    pressure_trend = details.get("pressure_trend")
    if pressure_trend == "falling":
        delta += 4
        reasons.append("pressure is falling")
    elif pressure_trend == "stable":
        delta += 2
        reasons.append("pressure is stable")
    elif pressure_trend == "rising":
        delta -= 2
        reasons.append("pressure is rising")

    if details.get("sun_score"):
        delta += int(details.get("sun_score") or 0)
        reasons.append(details.get("sun_note") or "low-light bite window")
    if details.get("moon_score"):
        delta += int(details.get("moon_score") or 0)
        reasons.append(details.get("moon_note") or "moon phase helps")

    if isinstance(temp, int) and (temp < 35 or temp > 96):
        delta -= 5
        reasons.append("temperature extreme")

    wind_text = "n/a"
    if details.get("wind") is not None:
        wind_text = f"{details.get('wind'):.0f} mph from {details.get('wind_dir') or 'Unknown'}"
        if details.get("gust") is not None:
            wind_text += f", gusts {details.get('gust'):.0f} mph"

    return {
        "text": text,
        "wind": wind_text,
        "temp": temp,
        "score_delta": delta,
        "bad": bad,
        "reasons": reasons[:8],
        "details": details,
    }

def score_location(loc: Location, usgs: Optional[Dict[str, Any]], tide: Optional[Dict[str, Any]], weather: Dict[str, Any], alerts: Dict[str, Any]) -> Dict[str, Any]:
    score = 50
    reasons: List[str] = []
    hazards: List[str] = []

    flow = latest_usgs_value(usgs, PARAM_DISCHARGE) if usgs else None
    stage = latest_usgs_value(usgs, PARAM_GAGE_HEIGHT) if usgs else None
    water_temp_c = latest_usgs_value(usgs, PARAM_WATER_TEMP) if usgs else None
    trend = usgs_trend_percent(usgs, PARAM_DISCHARGE) if usgs else None

    good_min, high_flow = flow_thresholds(loc.key)
    if flow is not None:
        if high_flow is not None and flow > high_flow:
            score -= 22
            hazards.append("flow is above the configured high-water mark")
        elif good_min is not None and flow >= good_min:
            score += 10
            reasons.append("moving water")
        elif good_min is not None and flow < good_min:
            score -= 8
            reasons.append("low/slower flow")
        if trend is not None:
            if trend > 250:
                score -= 12
                hazards.append("flow is rising very fast")
            elif 15 <= trend <= 150 and (not high_flow or flow < high_flow):
                score += 6
                reasons.append("fresh rising water")
            elif trend < -10:
                score += 3
                reasons.append("falling/clearing water")
    elif loc.usgs_site:
        reasons.append("USGS flow unavailable")

    tw = tide_window(tide) if tide else {}
    if tide:
        if tw.get("moving"):
            score += 8
            if tw.get("incoming"):
                reasons.append("incoming tide moving")
            elif tw.get("outgoing"):
                reasons.append("outgoing tide moving")
            else:
                reasons.append("moving tide")
        if tw.get("near_slack"):
            score -= 5
            reasons.append("near slack tide")

    wsum = summarize_weather(weather or {})
    details = wsum.get("details") or weather_details(weather or {})
    score += int(wsum.get("score_delta", 0))
    for r in wsum.get("reasons", []):
        if r and r not in reasons:
            reasons.append(r)
    if wsum.get("bad"):
        hazards.append("weather/wind risk")

    active_alerts = alerts.get("alerts", []) if alerts else []
    dangerous_words = ["flood", "thunderstorm", "tornado", "marine warning", "small craft", "gale", "storm warning"]
    hit_alerts = []
    if cfg_bool("Safety", "use_nws_alerts", True):
        for alert in active_alerts:
            event = str(alert.get("event", "")).lower()
            if any(word in event for word in dangerous_words):
                hit_alerts.append(alert.get("event", "Weather alert"))
        if hit_alerts:
            score -= 25
            hazards.append("active NWS alert: " + ", ".join(hit_alerts[:3]))

    score = max(0, min(100, score))
    if hazards or score < 40:
        bucket = "BAD"
        color = "red"
    elif score < 65:
        bucket = "OK"
        color = "yellow"
    else:
        bucket = "GOOD"
        color = "green"

    observed_level = None
    try:
        observed_level = float((tide or {}).get("water_level", {}).get("v"))
    except Exception:
        observed_level = None

    real_water_temp = (water_temp_c * 9 / 5 + 32) if water_temp_c is not None else None
    water_temp_f = real_water_temp if real_water_temp is not None else details.get("water_temp_estimate")
    water_source = "USGS measured" if real_water_temp is not None else details.get("water_temp_source", "unknown")

    report: Dict[str, Any] = {
        "key": loc.key,
        "name": loc.name,
        "short_name": loc.short_name,
        "score": score,
        "bucket": bucket,
        "color": color,
        "reasons": reasons[:8],
        "hazards": hazards[:6],
        "flow_cfs": flow,
        "gage_ft": stage,
        "water_temp_f": water_temp_f,
        "water_temp_source": water_source,
        "flow_trend_percent": trend,
        "weather": wsum,
        "weather_details": details,
        "tide": format_tide_summary(tw),
        "tide_details": tw,
        "tide_observed_ft": observed_level,
        "species": list(loc.species),
        "note": loc.note,
        "updated": dt.datetime.now().astimezone().strftime("%Y-%m-%d %I:%M %p %Z"),
        "nws_alerts": active_alerts,
        "nws_error": alerts.get("error") if alerts else None,
        "weather_error": weather.get("error") or weather.get("open_meteo_error"),
        "sources": {
            "usgs_site": loc.usgs_site,
            "tide_station": loc.tide_station,
            "nws_forecast": weather.get("source_url"),
            "nws_alerts": alerts.get("source_url") if alerts else None,
            "open_meteo": (weather.get("open_meteo") or {}).get("source_url"),
        },
    }
    report["species_results"] = build_species_results(report)
    return report

def format_tide_summary(tw: Dict[str, Any]) -> Optional[str]:
    if not tw:
        return None
    nxt = tw.get("next")
    if not nxt:
        return "Tide data unavailable"
    typ = "high" if nxt.get("type") == "H" else "low" if nxt.get("type") == "L" else "tide"
    hours = tw.get("hours_to_next")
    height = nxt.get("height")
    time_s = nxt.get("time").strftime("%I:%M %p") if hasattr(nxt.get("time"), "strftime") else "soon"
    direction = "incoming" if tw.get("incoming") else "outgoing" if tw.get("outgoing") else "moving"
    htxt = f" {height:.1f} ft" if isinstance(height, (int, float)) else ""
    if isinstance(hours, (int, float)):
        return f"{direction}; next {typ} at {time_s}{htxt} ({hours:.1f} hrs)"
    return f"next {typ} at {time_s}{htxt}"


def check_location(loc: Location) -> Dict[str, Any]:
    usgs = None
    tide = None
    errors = []
    if loc.usgs_site:
        try:
            usgs = fetch_usgs(loc.usgs_site)
        except Exception as exc:
            errors.append(f"USGS error: {exc}")
    if loc.tide_station:
        try:
            tide = fetch_noaa_tide(loc.tide_station)
        except Exception as exc:
            errors.append(f"NOAA tide error: {exc}")
    try:
        weather = fetch_nws_hourly(loc.lat, loc.lon)
    except Exception as exc:
        weather = {"error": str(exc), "periods": []}
        errors.append(f"NWS forecast error: {exc}")
    try:
        alerts = fetch_nws_alerts(loc.lat, loc.lon)
    except Exception as exc:
        alerts = {"error": str(exc), "alerts": []}
        errors.append(f"NWS alerts error: {exc}")
    result = score_location(loc, usgs, tide, weather, alerts)
    result["errors"] = errors
    return result


def _score_label(score: int, safety_bad: bool = False) -> Tuple[str, str]:
    if safety_bad:
        return "UNSAFE", "🚨"
    if score >= 78:
        return "EXCELLENT", "🟢"
    if score >= 63:
        return "GOOD", "🟡"
    if score >= 45:
        return "OK", "🟡"
    return "POOR", "🔴"


def build_species_results(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    base = int(report.get("score") or 0)
    details = report.get("weather_details") or {}
    tw = report.get("tide_details") or {}
    month = dt.datetime.now().month
    wind = _to_float(details.get("wind")) or 0.0
    water_temp = _to_float(report.get("water_temp_f"))
    low_light = bool(details.get("sun_score"))
    tide_moving = bool(tw.get("moving"))
    safety = bool(report.get("hazards"))
    results: List[Dict[str, Any]] = []

    for sp in report.get("species") or []:
        name = str(sp).strip()
        lower = name.lower()
        score = base
        if tide_moving and any(x in lower for x in ["striped", "bluefish", "fluke", "porgy", "blackfish", "shark", "red drum", "kingfish"]):
            score += 5
        if low_light and any(x in lower for x in ["striped", "catfish", "shark", "bluefish", "red drum"]):
            score += 4
        if 6 <= wind <= 16 and any(x in lower for x in ["striped", "bluefish", "shark", "red drum"]):
            score += 4

        if "blue crab" in lower:
            # Advisory activity index, not a catch guarantee, harvest permission,
            # verified pier access, or crab-count observation.
            local_today = dt.datetime.now().date()
            if local_today.month in (1, 2, 3) or (local_today.month == 12 and local_today.day > 15):
                score = 5  # Cold-season / season-check advisory, not permission to harvest
            else:
                # Blue crabs are more active in warm water and around moving tides.
                # Only trust measured water temperature for strong thermal bonuses.
                if month in (6, 7, 8, 9):
                    score += 13
                elif month in (5, 10):
                    score += 5
                elif month in (4, 11, 12):
                    score -= 16
                if tide_moving:
                    score += 11
                elif tw.get("near_slack"):
                    score -= 6
                if water_temp is not None:
                    source = str(report.get("water_temp_source") or "").lower()
                    measured = "measured" in source
                    if water_temp < 50:
                        score -= 30
                    elif water_temp < 60:
                        score -= 16
                    elif 68 <= water_temp <= 82:
                        score += 9 if measured else 3
                    elif water_temp > 88:
                        score -= 8
                if wind >= 20:
                    score -= 10
        elif "shark" in lower:
            if month in (6, 7, 8, 9, 10):
                score += 10
            elif month in (5, 11):
                score += 2
            else:
                score -= 18
            if water_temp is not None:
                if water_temp >= 65:
                    score += 8
                elif water_temp < 55:
                    score -= 15
            if tide_moving:
                score += 4
        elif "striped" in lower or "striper" in lower:
            if month in (3, 4, 5, 10, 11, 12):
                score += 8
            elif month in (7, 8):
                score -= 4
            if water_temp is not None and water_temp > 80:
                score -= 8
        elif "bluefish" in lower:
            if month in (5, 6, 7, 8, 9, 10):
                score += 7
        elif "fluke" in lower or "summer flounder" in lower:
            if month in (5, 6, 7, 8, 9):
                score += 8
            else:
                score -= 8
        elif "porgy" in lower or "scup" in lower:
            if month in (6, 7, 8, 9, 10):
                score += 6
        elif "blackfish" in lower or "tautog" in lower:
            if month in (4, 5, 10, 11):
                score += 10
            elif month in (7, 8):
                score -= 8
        elif "trout" in lower:
            if water_temp is not None and water_temp > 68:
                score -= 16
            elif water_temp is not None and 45 <= water_temp <= 62:
                score += 8
        elif "catfish" in lower:
            if water_temp is not None and water_temp >= 65:
                score += 6
            if low_light:
                score += 4

        score = int(max(0, min(100, round(score))))
        if safety:
            score = min(score, 35)
        rating, emoji = _score_label(score, safety_bad=safety)
        results.append({"name": name, "score": score, "rating": rating, "emoji": emoji})
    return results


def format_number(value: Optional[float], suffix: str = "") -> str:
    if value is None:
        return "n/a"
    if abs(value) >= 1000:
        return f"{value:,.0f}{suffix}"
    if abs(value) >= 100:
        return f"{value:.0f}{suffix}"
    return f"{value:.1f}{suffix}"


def _fmt_num(value: Any, digits: int = 0, suffix: str = "") -> str:
    val = _to_float(value)
    if val is None:
        return "n/a"
    return f"{val:.{digits}f}{suffix}"


def format_discord_report(report: Dict[str, Any]) -> str:
    """Format Baltimore/Mid-Atlantic reports with full Texoma-style detail."""
    emoji = {"GOOD": "🟢", "OK": "🟡", "BAD": "🔴"}.get(report.get("bucket"), "⚪")
    name = report.get("name", "Fishing Location")
    bucket = report.get("bucket", "UNKNOWN")
    score = report.get("score", "n/a")
    checked = report.get("updated", dt.datetime.now().strftime("%Y-%m-%d %I:%M %p"))
    note = report.get("note") or "Location-based water, weather, tide, and fishing report"

    species_results = report.get("species_results") or build_species_results(report)
    species_lines = []
    for item in species_results[:8]:
        species_lines.append(f"• {item['name']}: {item['emoji']} **{item['rating']}** ({item['score']}/100)")
    if len(species_results) > 8:
        species_lines.append(f"• +{len(species_results) - 8} more species")
    species_text = "\n".join(species_lines) or "• No species configured"
    crab_item = next((item for item in species_results if item["name"].casefold() == "blue crab"), None)
    crab_line = (
        f"\n**Blue Crab / Crabbing:** {crab_item['emoji']} **{crab_item['rating']}** ({crab_item['score']}/100)"
        "\n_Advisory activity estimate based on season, tide, weather and estimated/measured temperature."
        " Check current MD DNR crabbing rules, gear, hours and pier access before harvesting._"
        if crab_item else ""
    )

    reasons = report.get("reasons") or []
    hazards = report.get("hazards") or []
    good_text = "\n".join(f"✅ {x}" for x in reasons[:6]) or "✅ No major positives found"
    bad_text = "\n".join(f"⚠️ {x}" for x in hazards[:4]) or "⚠️ No major negatives found"
    safety_block = ""
    if hazards:
        safety_block = "\n\n**Safety Flags**\n" + "\n".join(f"🚨 {x}" for x in hazards[:4])

    details = report.get("weather_details") or {}
    sources = report.get("sources") or {}
    source_bits = []
    if sources.get("usgs_site"):
        source_bits.append(f"USGS site {sources['usgs_site']}")
    if sources.get("tide_station"):
        source_bits.append(f"NOAA tide station {sources['tide_station']}")
    source_text = "; ".join(source_bits) or "configured location water data"

    tw = report.get("tide_details") or {}
    tide_stage = "n/a"
    frac = tw.get("phase_fraction")
    if isinstance(frac, (int, float)):
        tide_stage = f"{frac * 100:.0f}% through tide"
        if tw.get("near_slack"):
            tide_stage += "; near slack"
        elif tw.get("moving"):
            tide_stage += "; moving water"
    tide_status = "MOVING" if tw.get("moving") else "SLACK" if tw.get("near_slack") else "n/a"
    tide = report.get("tide") or "n/a"

    flow = format_number(report.get("flow_cfs"), " cfs")
    gage = format_number(report.get("gage_ft"), " ft")
    trend = format_number(report.get("flow_trend_percent"), "%")
    water_temp = format_number(report.get("water_temp_f"), "°F")
    water_source = report.get("water_temp_source") or "unknown"
    obs_level = format_number(report.get("tide_observed_ft"), " ft")

    pchange = details.get("pressure_change_3h")
    pchange_text = "unknown" if pchange is None else f"{pchange:+.1f} hPa / 3h"
    wind_text = "n/a"
    if details.get("wind") is not None:
        wind_text = f"{_fmt_num(details.get('wind'), 0, ' mph')} from {details.get('wind_dir') or 'Unknown'}"
        if details.get("gust") is not None:
            wind_text += f", gusts {_fmt_num(details.get('gust'), 0, ' mph')}"

    nws_lines = []
    for alert in (report.get("nws_alerts") or [])[:3]:
        event = alert.get("event", "Weather Alert")
        sev = alert.get("severity", "")
        headline = alert.get("headline") or event
        if headline != event:
            nws_lines.append(f"• **{event}** ({sev}) — {headline[:130]}")
        else:
            nws_lines.append(f"• **{event}** ({sev})")
    nws_text = "\n".join(nws_lines) or "• No active NWS alerts found for this location"

    msg = f"""**🎣 Fishing Report — {name}**
**Overall:** {emoji} **{bucket}** ({score}/100)
**Checked:** {checked}
**Note:** {note}{safety_block}

**Species Ratings**
{species_text}{crab_line}

**Water / Tide / Flow**
• Water status: **{tide_status}**
• Tide: {tide}
• Tide stage: {tide_stage}
• Observed level: {obs_level}
• Flow: {flow}; Gage: {gage}; Flow trend: {trend}
• Water temp: {water_temp} ({water_source})
• Water data source: {source_text}

**Weather / Bite Factors**
• Weather: {details.get('text') or 'n/a'}
• Weather source: {details.get('source') or 'n/a'}
• Air temp: {_fmt_num(details.get('temp'), 0, '°F')}, feels like {_fmt_num(details.get('feels'), 0, '°F')}
• Wind: {wind_text}
• Pressure: {_fmt_num(details.get('pressure'), 0, ' hPa')} ({details.get('pressure_trend') or 'unknown'}, {pchange_text})
• Clouds: {_fmt_num(details.get('clouds'), 0, '%')}; Visibility: {_fmt_num(details.get('visibility_mi'), 1, ' mi')}
• Rain chance next 3h: {_fmt_num(details.get('pop3'), 0, '%')}; recent rain {details.get('rain24', 0.0):.2f} in/24h
• Sun: {details.get('sun_note') or 'n/a'}
• Moon: {details.get('moon_name') or 'n/a'} — {details.get('moon_illumination', 'n/a')}% lit; {details.get('moon_note') or 'n/a'}

**NWS Active Alerts**
{nws_text}

**Why**
{good_text}
{bad_text}

_Not an official warning. Check conditions and regulations before fishing._"""

    if report.get("weather_error"):
        msg += "\n_Note: one weather source failed, so the bot used the available weather/tide data._"
    return msg.strip()

def post_discord(content: str, webhook_url: str, username: Optional[str] = None) -> bool:
    if not webhook_url or "your_webhook_here" in webhook_url:
        return False
    payload = {"content": content[:1900]}
    if username:
        payload["username"] = username
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except Exception as exc:
        log(f"Discord post failed: {exc}")
        return False


def should_post(report: Dict[str, Any], state: Dict[str, Any], force: bool = False) -> bool:
    if force:
        return True
    if cfg_bool("Bot", "post_every_check", True):
        return True
    last = state.get(report["key"], {})
    if not last:
        return cfg_bool("Bot", "post_on_start", False)
    if last.get("bucket") != report.get("bucket"):
        return True
    threshold = cfg_int("Bot", "score_change_to_alert", 10)
    try:
        return abs(int(report["score"]) - int(last.get("score", report["score"]))) >= threshold
    except Exception:
        return False


def check_all(post: bool = False, force_post: bool = False, only_key: Optional[str] = None) -> List[Dict[str, Any]]:
    ensure_config()
    state = load_state()
    reports: List[Dict[str, Any]] = []
    for loc in enabled_locations():
        if only_key and loc.key != only_key:
            continue
        log(f"Checking {loc.name}...")
        report = check_location(loc)
        reports.append(report)
        log(f"{loc.short_name}: {report['bucket']} {report['score']}/100")
        if post and cfg_bool("Discord", "enabled", False) and should_post(report, state, force=force_post):
            webhook = cfg_str("LocationWebhooks", loc.key, "") or cfg_str("Discord", "webhook_url", "")
            username = cfg_str("Discord", "username", APP_NAME)
            post_discord(format_discord_report(report), webhook, username=username)
        state[loc.key] = {
            "score": report.get("score"),
            "bucket": report.get("bucket"),
            "updated": report.get("updated"),
            "flow_cfs": report.get("flow_cfs"),
        }
    save_state(state)
    return reports


def print_reports(reports: List[Dict[str, Any]]) -> None:
    for report in reports:
        print()
        print(format_discord_report(report).replace("**", ""))
        if report.get("errors"):
            print("Errors: " + "; ".join(report["errors"]))


def run_loop(post: bool) -> None:
    minutes = max(15, cfg_int("Bot", "check_every_minutes", 60))
    log(f"Starting loop. Check interval: {minutes} minutes")
    while True:
        try:
            check_all(post=post)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            log(f"Loop error: {exc}")
        time.sleep(minutes * 60)


def main(argv: Optional[List[str]] = None) -> int:
    ensure_config()
    parser = argparse.ArgumentParser(description=f"{APP_NAME} v{APP_VERSION}")
    parser.add_argument("--once", action="store_true", help="Check once and print reports")
    parser.add_argument("--loop", action="store_true", help="Run forever")
    parser.add_argument("--post", action="store_true", help="Post matching reports to Discord if enabled in config.ini")
    parser.add_argument("--force-post", action="store_true", help="Post even if score/status did not change")
    parser.add_argument("--location", choices=sorted(LOCATIONS), help="Only check one location")
    args = parser.parse_args(argv)
    if args.loop:
        run_loop(post=args.post)
        return 0
    reports = check_all(post=args.post, force_post=args.force_post, only_key=args.location)
    print_reports(reports)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
