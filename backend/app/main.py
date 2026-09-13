from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import create_db_and_tables
from app.routers import audits, auth, pages, sites


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="Signal SEO API", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(sites.router)
app.include_router(pages.router)
app.include_router(audits.router)


@app.get("/health")
def health():
    return {"status": "ok"}
