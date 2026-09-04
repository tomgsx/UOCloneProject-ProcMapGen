"""Config serialization, the settings form's one metadata table, and validation.

Every generator setting has exactly one `Setting` entry below: its label, the
group it is drawn under, its plain-language tooltip, and its range. The form
builds its boxes from the range, the tooltip quotes the range, and the
validator enforces the range - one copy, so the three cannot disagree.
"""
from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from gen.config import Config
from gen.water import SEA_Z, TRENCH_Z

# The portable release writes the Felucca MUL layout and nothing else; these
# two Config fields are therefore fixed, not settings, and the form only
# mentions them in its footnote.
MAP_WIDTH, MAP_HEIGHT = 7168, 4096
FIXED_FIELDS = ("width", "height")

# Groups in the order the form draws them.
WORLD = "World"
CONTINENT = "Continent shape"
COAST = "Coastline"
WATER = "Islands and inland water"
ELEVATION = "Elevation"
BIOMES = "Biomes"
TOWNS = "Towns and roads"
GROUPS = (WORLD, CONTINENT, COAST, WATER, ELEVATION, BIOMES, TOWNS)


@dataclass(frozen=True)
class Setting:
    name: str
    label: str
    group: str
    tooltip: str                 # plain-language cause and effect, no range (added on)
    minimum: float
    maximum: float
    step: float = 1
    decimals: int = 0            # 0 = a whole number
    suffix: str = ""             # drawn after the number in its box
    advanced: bool = False       # fine-tuning: the form draws its label in italics
    parts: tuple[str, ...] = ()  # a fixed pair of numbers, one box each ("x", "y")
    ordered: bool = False        # pair only: the first number may not exceed the second
    is_list: bool = False        # a free-length list of whole numbers, typed as text
    max_items: int = 0           # list only
    choices: tuple[tuple[str, str], ...] = ()   # a drop-down: (stored value, label) pairs
    beside: str = ""             # drawn on the row of this other setting, after its box
    short: str = ""              # its label on that shared row
    profile: str = ""            # shown only while temperature_profile has this value

    def format(self, number: float) -> str:
        text = f"{number:.{self.decimals}f}" if self.decimals else str(int(number))
        return text + self.suffix

    def range_text(self) -> str:
        if self.choices:
            return " or ".join(label for _value, label in self.choices)
        span = f"{self.format(self.minimum)} to {self.format(self.maximum)}"
        if self.parts:
            return f"{span} for each of {' and '.join(self.parts)}"
        if self.is_list:
            return f"{span} each, lowest first, up to {self.max_items} levels"
        return span

    def format_value(self, value: Any) -> str:
        if self.choices:
            return dict(self.choices).get(value, str(value))
        if self.parts or self.is_list:
            return ", ".join(self.format(v) for v in value)
        return self.format(value)


def _band_setting(biome: str) -> Setting:
    """The band of one biome: the same two boxes and the same words for all five."""
    return Setting(
        f"{biome}_band", f"{biome.capitalize()} band", BIOMES,
        f"The part of the map, top to bottom, outside which {biome} never forms: 'top' "
        f"is how far down the map it may start and 'bottom' how far down it may reach, "
        f"as fractions of the map height (0.00 is the top edge, 1.00 the bottom edge). "
        f"The band only fences {biome} in; the {biome} fraction decides how much of it "
        f"forms. Inside the band the front stands in from each edge by a varying depth, "
        f"touching the edge at its furthest points and withdrawing into bays elsewhere, "
        f"so {biome} ends irregularly rather than along a straight row. 0.00 to 1.00 "
        f"puts no limit on it.",
        0.0, 1.0, step=0.01, decimals=2, parts=("top", "bottom"), ordered=True,
        beside=f"{biome}_fraction", short="band",
    )


SETTINGS: tuple[Setting, ...] = (
    Setting(
        "seed", "Seed", WORLD,
        "Starting point for every random choice in the world. The same seed with the "
        "same settings always produces exactly the same map, so note the seed of any "
        "world you want to regenerate.",
        0, 2_147_483_647,
    ),
    Setting(
        "centre", "Continent centre", CONTINENT,
        "Where the main continent sits, as fractions of the map's width (x) and height "
        "(y). 0.50, 0.50 is dead centre; a smaller x moves it west, a smaller y moves "
        "it north.",
        0.05, 0.95, step=0.01, decimals=2, advanced=True, parts=("x", "y"),
    ),
    Setting(
        "radii", "Continent radii", CONTINENT,
        "Half-width (x) and half-height (y) of the continent's base oval, as fractions "
        "of the map's width and height. 0.50 would span the whole map. The coastline "
        "settings then reshape this oval.",
        0.05, 0.5, step=0.01, decimals=2, advanced=True, parts=("x", "y"),
    ),
    Setting(
        "margin", "Ocean margin", CONTINENT,
        "Guaranteed open ocean between any land and the edge of the map. Land then "
        "fades in over roughly the next 200 tiles, so the continent and its islands "
        "stay clear of the border.",
        0, 1000, step=10, suffix=" tiles", advanced=True,
    ),
    Setting(
        "coast_smooth", "Coast smoothing", COAST,
        "Fills narrow water inlets (narrower than about twice this many tiles) and "
        "trims the matching thin land spits, so steep unwalkable coves are rarer. "
        "Higher gives a rounder coastline; 0 leaves the coast fully ragged.",
        0, 8, suffix=" tiles",
    ),
    Setting(
        "coast_amp", "Coast variation", COAST,
        "How far the coastline wanders from the continent's base oval. 0 keeps a "
        "smooth oval; 1 gives a strongly irregular coast with bays and peninsulas; "
        "higher still breaks the outline up further.",
        0.0, 2.0, step=0.05, decimals=2, advanced=True,
    ),
    Setting(
        "coast_detail", "Coast detail", COAST,
        "Strength of the fine, small-scale roughness along the shore. Higher adds "
        "ragged edges and small inlets; 0 leaves only the broad coastal shape.",
        0.0, 1.0, step=0.01, decimals=2, advanced=True,
    ),
    Setting(
        "coast_wavelength", "Coast feature size", COAST,
        "Size of the largest bays and headlands. Larger values give broad, sweeping "
        "coastal shapes; smaller values give many smaller bays and capes.",
        200, 3000, step=50, suffix=" tiles", advanced=True,
    ),
    Setting(
        "islands", "Island count", WATER,
        "Extra islands placed in the open ocean. An island that lands too close to the "
        "continent merges into it, and anything smaller than the minimum island size "
        "is removed, so the final count can be lower.",
        0, 100,
    ),
    Setting(
        "min_island", "Minimum island size", WATER,
        "Any landmass smaller than this is removed. Raise it to clear away tiny "
        "coastal islets; lower it to keep them.",
        0, 10_000, step=50, suffix=" tiles", advanced=True,
    ),
    Setting(
        "min_lake_size", "Minimum lake size", WATER,
        "An enclosed pocket of water inside the landmass becomes a lake when it is at "
        "least this big; smaller pockets are filled with land. These lakes come from "
        "the shape of the coastline, separate from the lake count below.",
        0, 5000, step=10, suffix=" tiles", advanced=True,
    ),
    Setting(
        "rivers", "River count", WATER,
        "Rivers to attempt, each running from a spring at the foot of the hills down "
        "to the sea, or into another river or lake. A river is skipped when no route "
        "to the sea exists, so fewer can appear.",
        0, 100,
    ),
    Setting(
        "lakes", "Lake count", WATER,
        "Extra lakes carved into flat plains away from other water, on top of any "
        "lakes formed by enclosed pockets in the coastline. A lake is skipped when no "
        "room is found for it.",
        0, 100,
    ),
    Setting(
        "hill_fraction", "Hilly land fraction", ELEVATION,
        "Share of the dry land raised into terraced hills, chosen from the most inland, "
        "most rugged ground. 0 gives an entirely flat world.",
        0.0, 1.0, step=0.01, decimals=2,
    ),
    Setting(
        "mountain_fraction", "Mountain fraction", ELEVATION,
        "Share of the dry land that becomes impassable rock mountains. Mountains only "
        "form inside hilly land, so this cannot exceed the hilly land fraction; asking "
        "for more turns every hill to rock.",
        0.0, 1.0, step=0.01, decimals=2,
    ),
    Setting(
        "hill_levels", "Hill terrace levels", ELEVATION,
        "The heights (z) the hilly land steps up through, as a comma-separated list of "
        "whole numbers, lowest first. Each terrace is joined to the next by a ramp; "
        "more levels give more steps, higher values give taller hills.",
        1, 100, advanced=True, is_list=True, max_items=12,
    ),
    Setting(
        "ramp_slope", "Ramp slope", ELEVATION,
        "Height gained per tile on the ramps that join terraces. Lower gives gentler, "
        "longer slopes; 2 is comfortable to walk, and steep ramps are slow or "
        "impassable in game.",
        0.5, 8.0, step=0.5, decimals=1, suffix=" z per tile", advanced=True,
    ),
    Setting(
        "temperature_profile", "Temperature profile", BIOMES,
        "Where the cold and the warm ground lie. 'Coldest at the top' runs from cold "
        "along the top edge to warm along the bottom edge. 'Coldest at the top and "
        "bottom' puts the warmth across the middle of the map with cold along both "
        "edges, for snow at both poles. The zones below it set how far the full cold "
        "and the full heat reach; the temperature bar in the overview pane shows them "
        "and its handles move them. Temperature decides where snow, desert and jungle "
        "go; each biome's band then fences it in. The fractions below are independent "
        "shares of the dry land and need not add up to 1.",
        0, 0, choices=(("north", "Coldest at the top"), ("poles", "Coldest at the top and bottom")),
    ),
    Setting(
        "north_zones", "Temperature zones", BIOMES,
        "Full cold from the top edge down to 'cold to', full heat from 'hot from' down "
        "to the bottom edge, and a steady change between the two, as fractions of the "
        "map height (0.00 is the top edge, 1.00 the bottom edge). 0.00 and 1.00 give "
        "one even gradient from top to bottom.",
        0.0, 1.0, step=0.01, decimals=2, parts=("cold to", "hot from"), ordered=True,
        profile="north",
    ),
    Setting(
        "poles_cold", "Cold zones", BIOMES,
        "Full cold from the top edge down to 'to', and from 'from' down to the bottom "
        "edge, as fractions of the map height (0.00 is the top edge, 1.00 the bottom "
        "edge). The heat zone lies between them, with a steady change on either side.",
        0.0, 1.0, step=0.01, decimals=2, parts=("to", "from"), ordered=True,
        profile="poles",
    ),
    Setting(
        "poles_heat", "Heat zone", BIOMES,
        "Full heat between 'from' and 'to', as fractions of the map height (0.00 is "
        "the top edge, 1.00 the bottom edge), inside the cold zones. 0.50 and 0.50 "
        "give one even change from cold at each edge to a single warmest row.",
        0.0, 1.0, step=0.01, decimals=2, parts=("from", "to"), ordered=True,
        profile="poles",
    ),
    Setting(
        "snow_fraction", "Snow fraction", BIOMES,
        "Share of the dry land covered by snow, placed on the coldest ground inside "
        "the snow band. When the band cuts the cold ground short, the actual share "
        "comes out lower.",
        0.0, 1.0, step=0.01, decimals=2,
    ),
    _band_setting("snow"),
    Setting(
        "desert_fraction", "Desert fraction", BIOMES,
        "Share of the dry land covered by desert, placed on the warmest, driest ground "
        "inside the desert band.",
        0.0, 1.0, step=0.01, decimals=2,
    ),
    _band_setting("desert"),
    Setting(
        "jungle_fraction", "Jungle fraction", BIOMES,
        "Share of the dry land covered by jungle, placed on the warmest, wettest ground "
        "inside the jungle band. When the band cuts that ground short, the actual "
        "share comes out lower.",
        0.0, 1.0, step=0.01, decimals=2,
    ),
    _band_setting("jungle"),
    Setting(
        "forest_fraction", "Forest fraction", BIOMES,
        "Share of the dry land covered by forest, taken from the wettest ground left "
        "after snow, desert and jungle are placed, inside the forest band.",
        0.0, 1.0, step=0.01, decimals=2,
    ),
    _band_setting("forest"),
    Setting(
        "swamp_fraction", "Swamp fraction", BIOMES,
        "Target share of the dry land covered by swamp, as a few large flat inland "
        "patches. Swamp only forms on flat, non-hilly ground away from the coast, "
        "inside the swamp band, so the result can be lower.",
        0.0, 1.0, step=0.01, decimals=2,
    ),
    _band_setting("swamp"),
    Setting(
        "towns", "Town count", TOWNS,
        "Towns to attempt, each on a flat grassy plain near the coast and joined to its "
        "neighbours by roads. Fewer are placed when the spacing rule runs out of valid "
        "sites.",
        0, 100,
    ),
    Setting(
        "town_min_spacing", "Minimum town spacing", TOWNS,
        "No two towns are placed closer together than this. Larger spacing spreads the "
        "towns out and lengthens the roads between them; too large and fewer towns fit.",
        100, 2000, step=50, suffix=" tiles", advanced=True,
    ),
    Setting(
        "road_width", "Road width", TOWNS,
        "Width of the roads between towns at their narrowest, which is about a quarter "
        "of their length; elsewhere they run two tiles wider. Roads always narrow to 3 "
        "tiles where they approach a bridge.",
        1, 7, suffix=" tiles", advanced=True,
    ),
)

SETTING_BY_NAME: dict[str, Setting] = {setting.name: setting for setting in SETTINGS}


def settings_in(group: str) -> tuple[Setting, ...]:
    return tuple(setting for setting in SETTINGS if setting.group == group)


def tooltip_html(setting: Setting) -> str:
    """The tooltip as the form shows it: the explanation, then the range and the
    default. Rich text so Qt word-wraps it (a plain-text tooltip is one long line)."""
    default = config_dict(Config())[setting.name]
    return (
        f"<p style='white-space:normal'>{html.escape(setting.tooltip)}</p>"
        f"<p style='white-space:normal'><b>Range:</b> {html.escape(setting.range_text())}"
        f"<br><b>Default:</b> {html.escape(setting.format_value(default))}</p>"
    )


def fixed_note() -> str:
    """The footnote under the form: what is not a setting, and why some are italic."""
    return (
        f"Map size is fixed at {MAP_WIDTH} × {MAP_HEIGHT} tiles (the Felucca MUL "
        f"layout); the water surface sits at z {SEA_Z} and the seafloor at z {TRENCH_Z}. "
        "Italic settings are fine-tuning: the defaults suit most worlds."
    )


def config_dict(config: Config) -> dict[str, Any]:
    return asdict(config)


# Keys older presets and portable-settings.json files may still carry.
RETIRED_KEYS = ("sea_z", "trench_z")


def upgrade_legacy(value: dict[str, Any]) -> dict[str, Any]:
    """Translate a settings dict written by an older release into today's fields:
    the locked sea levels are dropped, and only the minimum of the old lake-hole
    range ever did anything, so it becomes the minimum lake size."""
    value = dict(value)
    for key in RETIRED_KEYS:
        value.pop(key, None)
    if "lake_hole_range" in value:
        pair = value.pop("lake_hole_range")
        if "min_lake_size" not in value and isinstance(pair, (tuple, list)) and pair:
            value["min_lake_size"] = pair[0]
    return value


def normalize_config_dict(value: dict[str, Any]) -> dict[str, Any]:
    defaults = config_dict(Config())
    value = upgrade_legacy(value)
    unknown = set(value) - set(defaults)
    if unknown:
        raise ValueError(f"Unknown setting(s): {', '.join(sorted(unknown))}")
    result = defaults | value
    for field in fields(Config):
        default = defaults[field.name]
        current = result[field.name]
        if isinstance(default, tuple):
            if not isinstance(current, (tuple, list)):
                label = SETTING_BY_NAME[field.name].label
                raise ValueError(f"{label} must be a comma-separated list.")
            result[field.name] = tuple(current)
    validate_config_dict(result)
    return result


def validate_config_dict(value: dict[str, Any]) -> None:
    if int(value["width"]) != MAP_WIDTH or int(value["height"]) != MAP_HEIGHT:
        raise ValueError(
            f"Portable releases currently support only {MAP_WIDTH}×{MAP_HEIGHT} Felucca maps."
        )
    for setting in SETTINGS:
        current = value[setting.name]
        within = f"{setting.label} must be between {setting.range_text()}."
        if setting.choices:
            if current not in dict(setting.choices):
                raise ValueError(f"{setting.label} must be {setting.range_text()}.")
        elif setting.parts:
            if len(current) != len(setting.parts):
                raise ValueError(f"{setting.label} needs {len(setting.parts)} values.")
            if any(not setting.minimum <= float(v) <= setting.maximum for v in current):
                raise ValueError(within)
            if setting.ordered and float(current[0]) > float(current[1]):
                raise ValueError(
                    f"{setting.label}: '{setting.parts[0]}' must not be below '{setting.parts[1]}'."
                )
        elif setting.is_list:
            levels = tuple(int(v) for v in current)
            if not levels or len(levels) > setting.max_items:
                raise ValueError(f"{setting.label} needs 1 to {setting.max_items} values.")
            if tuple(sorted(set(levels))) != levels:
                raise ValueError(f"{setting.label} must be unique and ascending.")
            if any(not setting.minimum <= v <= setting.maximum for v in levels):
                raise ValueError(within)
        elif not setting.minimum <= float(current) <= setting.maximum:
            raise ValueError(within)
    # the heat zone of the two-pole profile lies inside its cold zones
    cold_to, cold_from = (float(v) for v in value["poles_cold"])
    hot_from, hot_to = (float(v) for v in value["poles_heat"])
    if hot_from < cold_to or hot_to > cold_from:
        raise ValueError("Heat zone must lie between the Cold zones.")


def make_config(value: dict[str, Any]) -> Config:
    return Config(**normalize_config_dict(value))


def save_preset(path: Path, config: Config) -> None:
    path.write_text(json.dumps(config_dict(config), indent=2), encoding="utf-8")


def load_preset(path: Path) -> Config:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Preset root must be a JSON object.")
    return make_config(value)
