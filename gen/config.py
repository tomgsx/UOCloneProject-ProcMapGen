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
    radii: tuple = (0.30, 0.38)      # ellipse radii as fraction of W, H
    margin: int = 220                # no dry land closer than this to the map edge
    # coastline
    coast_wavelength: float = 900.0  # tiles: size of the largest bays and headlands
    coast_amp: float = 1.0           # how far the coast wanders from the ellipse
    coast_detail: float = 0.22       # fine coastal roughness amplitude
    coast_smooth: int = 2            # inlet-fill radius in tiles (0 = fully ragged coast)
    # islands and inland water
    islands: int = 7
    min_island: int = 400            # tiles: smaller landmasses are removed
    min_lake_size: int = 60          # tiles: smaller enclosed pockets are filled with land
    rivers: int = 12
    lakes: int = 10
    # elevation
    hill_levels: tuple = (5, 10, 15, 20, 30, 40)
    ramp_slope: float = 2.0          # z per tile on ramps
    hill_fraction: float = 0.45      # fraction of dry land in 'hilly' regions
    mountain_fraction: float = 0.09  # fraction of dry land that is rock
    # biomes
    forest_fraction: float = 0.38
    jungle_fraction: float = 0.08
    desert_fraction: float = 0.07
    snow_fraction: float = 0.05
    swamp_fraction: float = 0.02
    # towns and roads
    towns: int = 9
    town_min_spacing: int = 550      # tiles
    road_width: int = 3              # tiles at the narrowest (~1/4 of the length); 2 wider elsewhere
