"""FastAPI application entrypoint."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes_admin, routes_analytics, routes_auth, routes_feed, routes_image, routes_text
from app.auth import hash_password
from app.config import settings
from app.db import crud
from app.db.database import SessionLocal, init_db

app = FastAPI(
    title=settings.APP_NAME,
    description="Self-hostable, open-source content moderation API with a "
                 "configurable allow/flag/block guardrail policy and a "
                 "human-in-the-loop review dashboard.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    # Bootstrap a default admin account on first run so there's always a way
    # to log into the dashboard. Change ADMIN_USERNAME / ADMIN_PASSWORD via
    # env vars before first startup in any real deployment.
    db = SessionLocal()
    try:
        if not crud.any_users_exist(db):
            crud.create_user(
                db,
                username=settings.ADMIN_USERNAME,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                role="admin",
            )
    finally:
        db.close()


@app.get("/health", tags=["meta"])
async def health():
    return {
        "status": "ok",
        "thresholds": {"flag": settings.THRESHOLD_FLAG, "block": settings.THRESHOLD_BLOCK},
        "database": settings.DATABASE_URL.split("://")[0],
    }


app.include_router(routes_text.router)
app.include_router(routes_image.router)
app.include_router(routes_admin.router)
app.include_router(routes_auth.router)
app.include_router(routes_analytics.router)
app.include_router(routes_feed.router)

# Serve uploaded post images (only visible-post images are ever linked to
# from the feed API, but the folder itself is served plainly for simplicity
# in this demo — see README for production hardening notes).
os.makedirs(settings.MEDIA_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.MEDIA_DIR), name="media")

# ---------------------------------------------------------------------------
# Frontend: clean URLs (no .html) for the human-facing pages, plus a fixed
# /assets path for the shared stylesheet/JS so every page can reference them
# with an absolute path regardless of what clean URL served the page itself.
# ---------------------------------------------------------------------------
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

if os.path.isdir(_frontend_dir):
    app.mount("/assets", StaticFiles(directory=_frontend_dir), name="frontend-assets")

    def _serve_page(filename: str):
        return FileResponse(os.path.join(_frontend_dir, filename))

    @app.get("/", include_in_schema=False)
    async def page_feed():
        return _serve_page("feed.html")

    @app.get("/login", include_in_schema=False)
    async def page_login():
        return _serve_page("login.html")

    @app.get("/signup", include_in_schema=False)
    async def page_signup():
        return _serve_page("signup.html")

    @app.get("/demo", include_in_schema=False)
    async def page_demo():
        return _serve_page("index.html")

    @app.get("/review", include_in_schema=False)
    async def page_review():
        return _serve_page("review.html")

    @app.get("/analytics", include_in_schema=False)
    async def page_analytics():
        return _serve_page("analytics.html")

    @app.get("/admin", include_in_schema=False)
    async def page_admin():
        return _serve_page("admin.html")
