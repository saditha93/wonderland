"""Pricing API routes for the booking service."""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine
from wonderland_common.auth import administrator
from wonderland_common.database import database


router = APIRouter()


class PriceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    price_cents: int = Field(gt=0, le=10000000, strict=True)


class TierDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=80)
    min_guests: int = Field(ge=1, le=5, strict=True)
    max_guests: int = Field(ge=1, le=5, strict=True)
    price_cents: int = Field(gt=0, le=10000000, strict=True)
    active: bool = Field(default=True, strict=True)


@router.get("/ticket-tiers")
def tiers(engine: Engine = Depends(database)):
    with engine.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT * FROM booking.ticket_tiers WHERE active ORDER BY max_guests"
                )
            ).mappings()
        ]


@router.patch("/ticket-tiers/{tier_id}", dependencies=[Depends(administrator)])
def update_price(tier_id: UUID, body: PriceUpdate, engine: Engine = Depends(database)):
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    "UPDATE booking.ticket_tiers SET price_cents=:price,revision=revision+1,updated_at=now() WHERE id=:id RETURNING *"
                ),
                {"id": tier_id, "price": body.price_cents},
            )
            .mappings()
            .first()
        )
        if not row:
            raise HTTPException(404, "Ticket tier not found")
        return dict(row)


@router.get("/admin/ticket-tiers", dependencies=[Depends(administrator)])
def all_tiers(engine: Engine = Depends(database)):
    with engine.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                text("SELECT * FROM booking.ticket_tiers ORDER BY max_guests,name")
            ).mappings()
        ]


def tier_values(body):
    if body.min_guests > body.max_guests:
        raise HTTPException(422, "Minimum guests cannot exceed maximum")
    return body.model_dump()


@router.post(
    "/admin/ticket-tiers", status_code=201, dependencies=[Depends(administrator)]
)
def create_tier(body: TierDefinition, engine: Engine = Depends(database)):
    from sqlalchemy.exc import IntegrityError

    values = {"id": uuid4(), **tier_values(body)}
    try:
        with engine.begin() as conn:
            return dict(
                conn.execute(
                    text("""INSERT INTO booking.ticket_tiers(id,name,min_guests,max_guests,price_cents,active)
                VALUES (:id,:name,:min_guests,:max_guests,:price_cents,:active) RETURNING *"""),
                    values,
                )
                .mappings()
                .one()
            )
    except IntegrityError:
        raise HTTPException(409, "Ticket tier name is already in use") from None


@router.put("/admin/ticket-tiers/{tier_id}", dependencies=[Depends(administrator)])
def replace_tier(
    tier_id: UUID, body: TierDefinition, engine: Engine = Depends(database)
):
    from sqlalchemy.exc import IntegrityError

    try:
        with engine.begin() as conn:
            row = (
                conn.execute(
                    text("""UPDATE booking.ticket_tiers SET name=:name,min_guests=:min_guests,
                max_guests=:max_guests,price_cents=:price_cents,active=:active,revision=revision+1,updated_at=now()
                WHERE id=:id RETURNING *"""),
                    {"id": tier_id, **tier_values(body)},
                )
                .mappings()
                .first()
            )
            if not row:
                raise HTTPException(404, "Ticket tier not found")
            return dict(row)
    except IntegrityError:
        raise HTTPException(409, "Ticket tier name is already in use") from None


@router.get("/admin/sales", dependencies=[Depends(administrator)])
def sales(engine: Engine = Depends(database)):
    with engine.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                text("""SELECT b.tier_id,t.name AS tier_name,b.currency,count(*) AS tickets,
            sum(b.guest_count) AS guests,sum(b.amount_cents) AS revenue_cents FROM booking.bookings b
            JOIN booking.ticket_tiers t ON t.id=b.tier_id
            WHERE b.status='confirmed' GROUP BY b.tier_id,t.name,b.currency ORDER BY tier_name""")
            ).mappings()
        ]
