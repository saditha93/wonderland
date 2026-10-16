"""Profiles API routes for the booking service."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine
from wonderland_common.auth import Identity, visitor
from wonderland_common.database import database


router = APIRouter()


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    display_name: str = Field(min_length=1, max_length=80)
    preferred_language: str = Field(pattern=r"^(en|si|ta)$", default="en")


@router.get("/identity")
def identity_info(identity: Identity = Depends(visitor)):
    return {
        "subject": identity.subject,
        "role": identity.role,
        "mode": identity.mode,
    }


@router.get("/profile")
def get_profile(
    identity: Identity = Depends(visitor), engine: Engine = Depends(database)
):
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT display_name,preferred_language,updated_at FROM booking.visitor_profiles WHERE owner_id=:owner"
                ),
                {"owner": identity.subject},
            )
            .mappings()
            .first()
        )
    return (
        dict(row)
        if row
        else {"display_name": "", "preferred_language": "en", "updated_at": None}
    )


@router.put("/profile")
def save_profile(
    body: ProfileUpdate,
    identity: Identity = Depends(visitor),
    engine: Engine = Depends(database),
):
    with engine.begin() as conn:
        return dict(
            conn.execute(
                text("""INSERT INTO booking.visitor_profiles(owner_id,display_name,preferred_language)
            VALUES (:owner,:name,:lang) ON CONFLICT(owner_id) DO UPDATE SET display_name=EXCLUDED.display_name,
            preferred_language=EXCLUDED.preferred_language,updated_at=now() RETURNING display_name,preferred_language,updated_at"""),
                {
                    "owner": identity.subject,
                    "name": body.display_name,
                    "lang": body.preferred_language,
                },
            )
            .mappings()
            .one()
        )
