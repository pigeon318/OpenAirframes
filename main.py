import os
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi import Request
from fastapi import HTTPException
from pydantic import BaseModel
from datetime import date
from datetime import datetime
from typing import Literal
import re


class AircraftStandard(BaseModel):
    icao_hex: str
    registration: str | None
    manufacturer: str | None
    model: str | None
    type_aircraft: str | None
    year_manufactured: int | None
    type_engine: str | None
    engine_count: int | None
    seats: int | None
    aircraft_category: str | None
    weight_class: str | None
    owner_name: str | None
    owner_type: str | None
    owner_city: str | None
    owner_state: str | None
    owner_country: str | None
    status: str | None
    certification: str | None
    source: str
 
 
class AircraftFull(AircraftStandard):
    serial_number: str | None
    source_record_id: str | None
    type_aircraft_raw: str | None
    type_engine_raw: str | None
    owner_type_raw: str | None
    status_raw: str | None
    aircraft_category_raw: str | None
    builder_certification: str | None
    builder_certification_raw: str | None
    weight_class_raw: str | None
    last_action_date: date | None
    cert_issue_date: date | None
    airworthiness_date: date | None
    expiration_date: date | None
    created_at: datetime
    updated_at: datetime
 

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
STANDARD_COLUMNS = [
    "icao_hex",
    "registration",
    "manufacturer",
    "model",
    "type_aircraft",
    "year_manufactured",
    "type_engine",
    "engine_count",
    "seats",
    "aircraft_category",
    "weight_class",
    "owner_name",
    "owner_type",
    "owner_city",
    "owner_state",
    "owner_country",
    "status",
    "certification",
    "source",
]
 
FULL_COLUMNS = STANDARD_COLUMNS + [
    "serial_number",
    "source_record_id",
    "type_aircraft_raw",
    "type_engine_raw",
    "owner_type_raw",
    "status_raw",
    "aircraft_category_raw",
    "builder_certification",
    "builder_certification_raw",
    "weight_class_raw",
    "last_action_date",
    "cert_issue_date",
    "airworthiness_date",
    "expiration_date",
    "created_at",
    "updated_at",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = AsyncConnectionPool(DATABASE_URL, open=False)
    await pool.open()
    app.state.pool = pool
    yield
    await pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "OpenAirframes VA0.1"}


@app.get("/health")
async def health():
    return {"status": "Running OpenAirframes VA0.1"}


@app.get("/version")
async def version(request: Request):
    local_pool = request.app.state.pool
    async with local_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT version()")
            row = await cur.fetchone()
            return {"postgres_version": row[0]}


@app.get("/aircraft/{icao_hex}")
async def get_aircraft(
    icao_hex: str,
    request: Request,
    detail: Literal["standard", "full"] = "standard",):
    if not re.fullmatch(r"^[0-9a-f]{6}$", icao_hex):
        raise HTTPException(status_code=400, detail="icao_hex must be 6 lowercase hex characters")
    columns = FULL_COLUMNS if detail == "full" else STANDARD_COLUMNS
    sql = f"SELECT {', '.join(columns)} FROM aircraft WHERE icao_hex = %s"
    local_pool = request.app.state.pool
    async with local_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (icao_hex,))
            row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Aircraft not found")
    return dict(zip(columns, row))
