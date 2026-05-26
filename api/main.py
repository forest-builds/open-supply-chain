import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.admin import _ingest_noaa_alerts, _ingest_usgs_quakes, admin_router
from api.mcp_server import mcp
from api.chains import chains_router
from api.chat import chat_router
from api.config import settings
from api.routes import router
from api.tools import tools_router

logger = logging.getLogger(__name__)

_NOAA_INTERVAL = 15 * 60   # 15 minutes
_USGS_INTERVAL = 60 * 60   # 1 hour


async def _run_periodically(name: str, fn, interval: int) -> None:
    """Run fn immediately, then every `interval` seconds."""
    while True:
        try:
            await asyncio.to_thread(fn)
        except Exception:
            logger.exception("Scheduled task %s failed", name)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        asyncio.create_task(
            _run_periodically("noaa-alerts", _ingest_noaa_alerts, _NOAA_INTERVAL)
        ),
        asyncio.create_task(
            _run_periodically(
                "usgs-quakes",
                lambda: _ingest_usgs_quakes(days=1, min_magnitude=1.0),
                _USGS_INTERVAL,
            )
        ),
    ]
    yield
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="Open Supply Chain API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(chains_router)
app.include_router(tools_router)
app.include_router(chat_router)
app.include_router(admin_router)

# MCP server — SSE transport for external agent access at /mcp/sse
app.mount("/mcp", mcp.http_app(transport="sse"))
