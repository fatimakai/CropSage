"""Production-style provider adapters for CropSage evidence collection."""

from .common import FetchOutcome, LocationTarget
from .fortyguard import fetch_fortyguard
from .nasa_power import fetch_nasa_power
from .open_meteo import fetch_open_meteo
from .ssurgo import fetch_ssurgo

__all__ = [
    "FetchOutcome",
    "LocationTarget",
    "fetch_fortyguard",
    "fetch_nasa_power",
    "fetch_open_meteo",
    "fetch_ssurgo",
]
