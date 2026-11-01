from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.routes.auth import router as auth_router
from app.api.routes.companies import router as companies_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.discovery import router as discovery_router
from app.api.routes.drafts import router as drafts_router
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(companies_router)
app.include_router(dashboard_router)
app.include_router(discovery_router)
app.include_router(drafts_router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("startup")
def create_single_user_if_missing() -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.id == 1))
        if user is None:
            db.add(
                User(
                    id=1,
                    username=settings.default_username,
                    password_hash=hash_password(settings.default_password),
                )
            )
            db.commit()
        elif user.username != settings.default_username:
            raise RuntimeError(
                "DEFAULT_USERNAME does not match the existing single-user account"
            )
