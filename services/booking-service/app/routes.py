"""Compose booking features without changing their public API paths."""

from fastapi import APIRouter
from . import reservations, checkout, tickets, pricing, profiles

router = APIRouter()
for feature in (reservations, checkout, tickets, pricing, profiles):
    router.include_router(feature.router)
