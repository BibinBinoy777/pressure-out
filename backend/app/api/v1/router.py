"""Versioned `/api/v1` API router aggregator (Phases 2 through 7)."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.comments import router as comments_router
from app.api.v1.communities import router as communities_router
from app.api.v1.feed import router as feed_router
from app.api.v1.health import router as health_router
from app.api.v1.me import router as me_router
from app.api.v1.memes import router as memes_router
from app.api.v1.moderation import router as moderation_router
from app.api.v1.translations import router as translations_router
from app.api.v1.workplace import router as workplace_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.posts import router as posts_router
from app.api.v1.profiles import router as profiles_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(me_router)
api_v1_router.include_router(profiles_router)
api_v1_router.include_router(posts_router)
api_v1_router.include_router(communities_router)
api_v1_router.include_router(comments_router)
api_v1_router.include_router(notifications_router)
api_v1_router.include_router(feed_router)
api_v1_router.include_router(memes_router)
api_v1_router.include_router(moderation_router)
api_v1_router.include_router(translations_router)
api_v1_router.include_router(workplace_router)
