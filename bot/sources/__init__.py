from .advisories import FCDO, AuswaertigesAmt, CanadaAdvisory, USStateDept
from .aviation import AirTraffic, EASAConflictZones, FAAProhibitions
from .ferries import TallinkFerries
from .gdelt import GDELT
from .news import EstonianNews, USEmbassyTallinn
from .polymarket import Polymarket

ALL_SOURCES = [
    USStateDept(), FCDO(), AuswaertigesAmt(), CanadaAdvisory(),
    USEmbassyTallinn(), EstonianNews(),
    Polymarket(),
    FAAProhibitions(), EASAConflictZones(), AirTraffic(),
    GDELT(),
    TallinkFerries(),
]
