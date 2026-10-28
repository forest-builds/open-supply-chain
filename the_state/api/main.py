from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from core.config import settings
from fastapi import FastAPI
from payments import PaymentConfig, X402Middleware
from routes import (
    alerts,
    briefs,
    db,
    decisions,
    feedback,
    health,
    incidents,
    sources,
    state,
    watchlists,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


app = FastAPI(
    title="The State API",
    description="Operational intelligence from external signals to decision-ready state",
    version="0.1.0",
    lifespan=lifespan,
    debug=settings.debug,
)

app.include_router(health.router, tags=["health"])
app.include_router(db.router, prefix="/db", tags=["db"])
app.include_router(sources.router, prefix="/sources", tags=["sources"])
app.include_router(incidents.router, prefix="/incidents", tags=["incidents"])
app.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
app.include_router(decisions.router, prefix="/decisions", tags=["decisions"])
app.include_router(state.router, prefix="/state", tags=["state"])
app.include_router(watchlists.router, prefix="/watchlists", tags=["watchlists"])
app.include_router(briefs.router, prefix="/briefs", tags=["briefs"])
app.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
app.add_middleware(
    X402Middleware,
    configs={
        "/decisions/evaluate": PaymentConfig(
            mode=settings.payment_mode,
            wallet_address=settings.x402_wallet_address,
            network=settings.x402_network,
            price_usd=settings.x402_price_usd,
            mock_token=settings.payment_mock_token,
            facilitator_url=settings.x402_facilitator_url,
            description="Evaluate a scored operational decision",
        )
    },
)
