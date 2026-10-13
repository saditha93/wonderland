from typing import Literal
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine
from wonderland_common.auth import administrator
from wonderland_common.database import database

router = APIRouter()


class Attraction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=10, max_length=2000)
    category: str = Field(min_length=2, max_length=80)
    thrill_level: Literal["gentle", "moderate", "high"]
    minimum_age: int = Field(ge=0, le=120, strict=True)
    minimum_height_cm: int = Field(ge=0, le=250, strict=True)
    operational_status: Literal["open", "maintenance", "retired"] = "open"


@router.get("/attractions")
def catalog(
    q: str = Query(default="", max_length=100), engine: Engine = Depends(database)
):
    with engine.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                text("""
            SELECT * FROM attractions.attractions WHERE operational_status <> 'retired'
            AND (name ILIKE :q OR category ILIKE :q) ORDER BY name LIMIT 100
        """),
                {"q": f"%{q}%"},
            ).mappings()
        ]


@router.get("/attractions/{attraction_id}")
def detail(attraction_id: UUID, engine: Engine = Depends(database)):
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT * FROM attractions.attractions WHERE id=:id AND operational_status <> 'retired'"
                ),
                {"id": attraction_id},
            )
            .mappings()
            .first()
        )
    if not row:
        raise HTTPException(404, "Attraction not found")
    return dict(row)


@router.post("/attractions", status_code=201, dependencies=[Depends(administrator)])
def create(body: Attraction, engine: Engine = Depends(database)):
    with engine.begin() as conn:
        return dict(
            conn.execute(
                text("""INSERT INTO attractions.attractions
            (id,name,description,category,thrill_level,minimum_age,minimum_height_cm,operational_status)
            VALUES (:id,:name,:description,:category,:thrill_level,:minimum_age,:minimum_height_cm,:operational_status)
            RETURNING *"""),
                {"id": uuid4(), **body.model_dump()},
            )
            .mappings()
            .one()
        )


@router.put("/attractions/{attraction_id}", dependencies=[Depends(administrator)])
def update(attraction_id: UUID, body: Attraction, engine: Engine = Depends(database)):
    with engine.begin() as conn:
        row = (
            conn.execute(
                text("""UPDATE attractions.attractions SET name=:name, description=:description,
            category=:category, thrill_level=:thrill_level, minimum_age=:minimum_age,
            minimum_height_cm=:minimum_height_cm, operational_status=:operational_status, updated_at=now()
            WHERE id=:id RETURNING *"""),
                {"id": attraction_id, **body.model_dump()},
            )
            .mappings()
            .first()
        )
        if not row:
            raise HTTPException(404, "Attraction not found")
        return dict(row)


@router.delete("/attractions/{attraction_id}", dependencies=[Depends(administrator)])
def retire(attraction_id: UUID, engine: Engine = Depends(database)):
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    "UPDATE attractions.attractions SET operational_status='retired',updated_at=now() WHERE id=:id RETURNING *"
                ),
                {"id": attraction_id},
            )
            .mappings()
            .first()
        )
        if not row:
            raise HTTPException(404, "Attraction not found")
        return dict(row)
