from dataclasses import dataclass


@dataclass
class RiskFactors:
    active_disasters: float = 0.0
    severe_weather: float = 0.0
    historical_frequency: float = 0.0
    population_density: float = 0.0


@dataclass
class RiskResult:
    score: float  # 0-100
    level: str
    factors: dict[str, float]

    @classmethod
    def from_factors(cls, factors: RiskFactors) -> "RiskResult":
        weights = {
            "active_disasters": 0.40,
            "severe_weather": 0.30,
            "historical_frequency": 0.20,
            "population_density": 0.10,
        }
        score = sum(getattr(factors, k) * w for k, w in weights.items())
        level = (
            "critical"
            if score >= 75
            else "high"
            if score >= 50
            else "moderate"
            if score >= 25
            else "low"
        )
        return cls(
            score=round(score, 2),
            level=level,
            factors={k: getattr(factors, k) for k in weights},
        )


class RiskScorer:
    """Computes a composite risk score for a geographic area."""

    async def score(self, lat: float, lon: float, radius_km: float) -> RiskResult:
        # TODO: pull active disasters from OpenFEMA, weather from NOAA, historical data
        factors = RiskFactors()
        return RiskResult.from_factors(factors)
