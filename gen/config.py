"""Generator configuration: every tunable in one dataclass.

Every field here is read by the generator and shown on the GUI form, except
`width`/`height`, which the app fixes to the Felucca MUL layout. The form's
labels, groups, tooltips and ranges live in gui/config_io.py, one entry per
field - add a field here and that table must grow with it (the GUI tests
enforce the pairing).

Retired fields, dropped from old presets when they load (gui/config_io.py):
- sea_z / trench_z: the shoreline ruleset hardcodes the water surface at -5
  and the seafloor at -15 (gen/water.py SEA_Z/TRENCH_Z); nothing read them.
- lake_hole_range: only its minimum ever mattered - it is `min_lake_size` now.
"""
from dataclasses import dataclass

@dataclass
class Config:
    seed: int = 7
    width: int = 7168          # tiles - fixed by the MUL format
    height: int = 4096
    # continent shape
    centre: tuple = (0.40, 0.50)     # fraction of W, H
    radii: tuple = (0.30, 0.32)      # ellipse radii as fraction of W, H
    margin: int = 150                # no dry land closer than this to the map edge
    # coastline
    coast_wavelength: float = 800.0  # tiles: size of the largest bays and headlands
    coast_amp: float = 0.95          # how far the coast wanders from the ellipse
    coast_detail: float = 0.22       # fine coastal roughness amplitude
    coast_smooth: int = 2            # inlet-fill radius in tiles (0 = fully ragged coast)
    # islands and inland water
    islands: int = 4
    min_island: int = 400            # tiles: smaller landmasses are removed
    min_lake_size: int = 300         # tiles: smaller enclosed pockets are filled with land
    rivers: int = 12
    lakes: int = 6
    # elevation
    hill_levels: tuple = (5, 10, 15, 20, 30, 40)
    ramp_slope: float = 2.0          # z per tile on ramps
    hill_fraction: float = 0.45      # fraction of dry land in 'hilly' regions
    mountain_fraction: float = 0.09  # fraction of dry land that is rock
    # biomes, in the order they are placed. Each has a share of the dry land and a
    # band: the part of the map, top and bottom as fractions of the map height (0 is
    # the top edge), outside which it never forms.
    temperature_profile: str = "poles"   # "north": coldest at the top; "poles": coldest at the top and bottom
    north_zones: tuple = (0.0, 1.0)      # "north": full cold down to the first, full heat from the second
    poles_cold: tuple = (0.10, 0.90)     # "poles": full cold down to the first and up from the second
    poles_heat: tuple = (0.5, 0.5)       # "poles": full heat between the two
    snow_fraction: float = 0.08
    snow_band: tuple = (0.0, 1.0)
    desert_fraction: float = 0.07
    desert_band: tuple = (0.0, 1.0)
    jungle_fraction: float = 0.08
    jungle_band: tuple = (0.0, 1.0)
    forest_fraction: float = 0.38
    forest_band: tuple = (0.0, 1.0)
    swamp_fraction: float = 0.02
    swamp_band: tuple = (0.0, 1.0)
    # towns and roads
    towns: int = 9
    town_min_spacing: int = 550      # tiles
    road_width: int = 3              # tiles at the narrowest (~1/4 of the length); 2 wider elsewhere
