from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.admin import admin_router
from api.chains import chains_router
from api.chat import chat_router
from api.config import settings
from api.routes import router
from api.tools import tools_router
from the_state.mount import the_state_app

app = FastAPI(title="Open Supply Chain API")

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

# the-state: NYC operational-decision product, mounted as-is (own DB, own
# schema). See the_state/README.md for what this is and isn't yet merged
# with.
app.mount("/the-state", the_state_app)
