import os
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi import Query
from fastapi import Request
from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles
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


class BulkRequest(BaseModel):
    identifiers: list[str]


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
app.mount("/ui", StaticFiles(directory="static", html=True), name="ui")


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


@app.get("/aircraft")
async def search_aircraft(
    request: Request,
    manufacturer: str | None = None,
    model: str | None = None,
    owner_name: str | None = None,
    status: str | None = None,
    aircraft_category: str | None = None,
    type_aircraft: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    detail: Literal["standard", "full"] = "standard",
):
    columns = FULL_COLUMNS if detail == "full" else STANDARD_COLUMNS
    filters = []
    params = []

    if manufacturer:
        filters.append("manufacturer ILIKE %s")
        params.append(f"%{manufacturer}%")
    if model:
        filters.append("model ILIKE %s")
        params.append(f"%{model}%")
    if owner_name:
        filters.append("owner_name ILIKE %s")
        params.append(f"%{owner_name}%")
    if status:
        filters.append("status = %s")
        params.append(status)
    if aircraft_category:
        filters.append("aircraft_category = %s")
        params.append(aircraft_category)
    if type_aircraft:
        filters.append("type_aircraft = %s")
        params.append(type_aircraft)

    if not filters:
        raise HTTPException(status_code=400, detail="At least one filter is required")

    where = "WHERE " + " AND ".join(filters)
    sql = f"SELECT {', '.join(columns)} FROM aircraft {where} LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    local_pool = request.app.state.pool
    async with local_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            rows = await cur.fetchall()

    return [dict(zip(columns, row)) for row in rows]


@app.post("/aircraft/bulk")
async def bulk_aircraft(
    body: BulkRequest,
    request: Request,
    detail: Literal["standard", "full"] = "standard",
):
    if not body.identifiers:
        return {}
    if len(body.identifiers) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 identifiers per request")

    columns = FULL_COLUMNS if detail == "full" else STANDARD_COLUMNS
    results = {ident: None for ident in body.identifiers}

    hex_map = {}
    reg_map = {}

    for ident in body.identifiers:
        if re.fullmatch(r"[0-9a-fA-F]{6}", ident):
            hex_map[ident.lower()] = ident
        else:
            normalised = ident.upper().replace("-", "").replace(" ", "")
            if normalised:
                reg_map[normalised] = ident

    local_pool = request.app.state.pool
    async with local_pool.connection() as conn:
        async with conn.cursor() as cur:
            if hex_map:
                sql = f"SELECT {', '.join(columns)} FROM aircraft WHERE icao_hex = ANY(%s)"
                await cur.execute(sql, (list(hex_map.keys()),))
                for row in await cur.fetchall():
                    data = dict(zip(columns, row))
                    original = hex_map.get(data["icao_hex"])
                    if original:
                        results[original] = data

            if reg_map:
                sql = f"SELECT {', '.join(columns)} FROM aircraft WHERE UPPER(REPLACE(registration, '-', '')) = ANY(%s)"
                await cur.execute(sql, (list(reg_map.keys()),))
                for row in await cur.fetchall():
                    data = dict(zip(columns, row))
                    if data["registration"]:
                        normalised = data["registration"].upper().replace("-", "").replace(" ", "")
                        original = reg_map.get(normalised)
                        if original:
                            results[original] = data

    return results


@app.get("/aircraft/{identifier}")
async def get_aircraft(
    identifier: str,
    request: Request,
    detail: Literal["standard", "full"] = "standard",
):
    columns = FULL_COLUMNS if detail == "full" else STANDARD_COLUMNS
    local_pool = request.app.state.pool

    if re.fullmatch(r"[0-9a-fA-F]{6}", identifier):
        sql = f"SELECT {', '.join(columns)} FROM aircraft WHERE icao_hex = %s"
        param = identifier.lower()
    else:
        sql = f"SELECT {', '.join(columns)} FROM aircraft WHERE UPPER(REPLACE(registration, '-', '')) = %s"
        param = identifier.upper().replace("-", "").replace(" ", "")
        if not param:
            raise HTTPException(status_code=400, detail="Invalid identifier")

    async with local_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (param,))
            row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Aircraft not found")
    return dict(zip(columns, row))
