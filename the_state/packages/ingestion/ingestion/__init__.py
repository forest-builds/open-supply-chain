from ingestion.base import NormalizedSignal, NormalizerProtocol
from ingestion.nyc import NycOpenDataCollector, SocrataClient

__all__ = [
    "NormalizedSignal",
    "NormalizerProtocol",
    "NycOpenDataCollector",
    "SocrataClient",
]
