from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.config import settings
from app.database import create_db_and_tables, engine
from app.routers import (
    admin,
    alerts,
    audits,
    auth,
    auth_google,
    billing,
    google_data,
    google_integration,
    keywords,
    opportunities,
    pages,
    pricing,
    site_health,
    sites,
    suggestions,
    webhooks,
)
from app.services.billing import seed_default_products


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    with Session(engine) as session:
        seed_default_products(session)
    yield


app = FastAPI(title="Signal SEO API", lifespan=lifespan)

# The frontend always runs on a different origin than this API (even in dev:
# localhost:3000 vs 8000) - allowed origins come from CORS_ORIGINS (comma-
# separated), see app/config.py.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(auth_google.router)
app.include_router(sites.router)
app.include_router(pages.router)
app.include_router(audits.router)
app.include_router(keywords.router)
app.include_router(suggestions.router)
app.include_router(alerts.router)
app.include_router(opportunities.router)
app.include_router(site_health.router)
app.include_router(google_integration.router)
app.include_router(google_data.router)
app.include_router(pricing.router)
app.include_router(billing.router)
app.include_router(webhooks.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}
