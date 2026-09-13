from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import create_db_and_tables
from app.routers import audits, auth, keywords, pages, sites


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="Signal SEO API", lifespan=lifespan)

# Dev-only: Next.js runs on a different origin (localhost:3000) than the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sites.router)
app.include_router(pages.router)
app.include_router(audits.router)
app.include_router(keywords.router)


@app.get("/health")
def health():
    return {"status": "ok"}
