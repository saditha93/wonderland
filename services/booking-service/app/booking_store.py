"""Owned booking lookup and the public response fields."""

from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Path
from sqlalchemy import text

PARK_TIMEZONE = ZoneInfo("Asia/Colombo")
Reference = Annotated[str, Path(pattern=r"^WL-[A-F0-9]{32}$")]
PUBLIC_COLUMNS = (
    "reference",
    "tier_id",
    "tier_name",
    "tier_revision",
    "guest_count",
    "visit_date",
    "time_slot",
    "amount_cents",
    "currency",
    "status",
    "payment_status",
    "created_at",
    "confirmed_at",
)


def public_booking(row):
    return {key: row[key] for key in PUBLIC_COLUMNS}


def find_owned_booking(conn, reference, identity, lock=False):
    row = (
        conn.execute(
            text(
                "SELECT * FROM booking.bookings WHERE reference=:reference AND owner_id=:owner"
                + (" FOR UPDATE" if lock else "")
            ),
            {"reference": reference, "owner": identity.subject},
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(404, "Booking not found")
    return dict(row)
