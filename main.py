import asyncio
import json
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel


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


class FeedPayload(BaseModel):
    aircraft: list[dict]
    key: str | None = None


class FeederRegistration(BaseModel):
    name: str
    location: str | None = None


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
POSITION_TTL = 60

STANDARD_COLUMNS = [
    "icao_hex", "registration", "manufacturer", "model", "type_aircraft",
    "year_manufactured", "type_engine", "engine_count", "seats",
    "aircraft_category", "weight_class", "owner_name", "owner_type",
    "owner_city", "owner_state", "owner_country", "status", "certification",
    "source",
]

FULL_COLUMNS = STANDARD_COLUMNS + [
    "serial_number", "source_record_id", "type_aircraft_raw", "type_engine_raw",
    "owner_type_raw", "status_raw", "aircraft_category_raw", "builder_certification",
    "builder_certification_raw", "weight_class_raw", "last_action_date",
    "cert_issue_date", "airworthiness_date", "expiration_date", "created_at",
    "updated_at",
]

position_store: dict[str, dict] = {}
feeder_cache: dict[str, dict] = {}
_last_written: dict[str, float] = {}


async def expire_positions():
    while True:
        await asyncio.sleep(10)
        cutoff = time.time() - POSITION_TTL
        expired = [h for h, v in position_store.items() if v["last_seen"] < cutoff]
        for h in expired:
            del position_store[h]


async def cleanup_positions(pool):
    while True:
        await asyncio.sleep(3600)
        async with pool.connection() as conn:
            await conn.execute(
                "DELETE FROM positions WHERE ts < now() - INTERVAL '24 hours'"
            )


async def persist_positions(rows: list[tuple], pool):
    if not rows:
        return
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(
                "INSERT INTO positions (hex, lat, lon, alt_baro, gs, track, vert_rate)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                rows,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = AsyncConnectionPool(DATABASE_URL, open=False)
    await pool.open()
    app.state.pool = pool
    t1 = asyncio.create_task(expire_positions())
    t2 = asyncio.create_task(cleanup_positions(pool))
    yield
    t1.cancel()
    t2.cancel()
    await pool.close()


app = FastAPI(lifespan=lifespan)
app.mount("/ui", StaticFiles(directory="static", html=True), name="ui")


async def resolve_feeder(key: str, pool) -> dict | None:
    if key in feeder_cache:
        return feeder_cache[key]
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name FROM feeders WHERE key = %s", (key,)
            )
            row = await cur.fetchone()
    if row is None:
        return None
    feeder = {"id": row[0], "name": row[1]}
    feeder_cache[key] = feeder
    return feeder


async def update_feeder_stats(key: str, aircraft_count: int, pool):
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """UPDATE feeders
                   SET last_seen_at = NOW(),
                       aircraft_count = %s,
                       message_count = message_count + %s
                   WHERE key = %s""",
                (aircraft_count, aircraft_count, key),
            )


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


@app.post("/feeders/register")
async def register_feeder(body: FeederRegistration, request: Request):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Name too long")

    key = secrets.token_urlsafe(32)
    local_pool = request.app.state.pool
    async with local_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO feeders (key, name, location) VALUES (%s, %s, %s)",
                (key, name, body.location),
            )

    return {"key": key, "name": name}


@app.post("/feed")
async def feed(body: FeedPayload, request: Request):
    key = request.headers.get("X-Feeder-Key", "") or (body.key or "")
    if not key:
        raise HTTPException(status_code=401, detail="X-Feeder-Key header required")

    local_pool = request.app.state.pool
    feeder = await resolve_feeder(key, local_pool)
    if feeder is None:
        raise HTTPException(status_code=403, detail="Invalid feeder key")

    now = time.time()
    accepted = 0
    to_persist: list[tuple] = []

    for ac in body.aircraft:
        hex_code = ac.get("hex", "").strip().lower()
        if not hex_code or len(hex_code) != 6:
            continue

        lat = ac.get("lat")
        lon = ac.get("lon")
        if lat is None or lon is None:
            continue

        seen_pos = ac.get("seen_pos", 0)
        if seen_pos > 30:
            continue

        flight = (ac.get("flight") or "").strip() or None

        alt_baro = ac.get("alt_baro") or ac.get("altitude")
        gs = ac.get("gs") or ac.get("speed")
        track = ac.get("track")
        vert_rate = ac.get("vert_rate")

        position_store[hex_code] = {
            "hex": hex_code,
            "flight": flight,
            "lat": lat,
            "lon": lon,
            "alt_baro": alt_baro,
            "gs": gs,
            "track": track,
            "vert_rate": vert_rate,
            "squawk": ac.get("squawk"),
            "category": ac.get("category"),
            "rssi": ac.get("rssi"),
            "feeder": feeder["name"],
            "feeder_id": feeder["id"],
            "last_seen": now - seen_pos,
        }

        if now - _last_written.get(hex_code, 0) >= 10:
            _last_written[hex_code] = now
            to_persist.append((hex_code, lat, lon, alt_baro, gs, track, vert_rate))

        accepted += 1

    asyncio.create_task(update_feeder_stats(key, accepted, local_pool))
    asyncio.create_task(persist_positions(to_persist, local_pool))
    return {"accepted": accepted}


@app.get("/stats")
async def get_stats(request: Request):
    local_pool = request.app.state.pool
    async with local_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM aircraft")
            total = (await cur.fetchone())[0]
    live = sum(1 for v in position_store.values() if time.time() - v["last_seen"] < POSITION_TTL)
    return {"total_aircraft": total, "live_aircraft": live}


@app.get("/live/track/{hex_code}")
async def live_track(hex_code: str, request: Request):
    if not re.fullmatch(r"[0-9a-fA-F]{6}", hex_code):
        raise HTTPException(status_code=400, detail="Invalid ICAO hex")
    local_pool = request.app.state.pool
    async with local_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT lat, lon, alt_baro FROM positions"
                " WHERE hex = %s AND ts > now() - INTERVAL '30 minutes'"
                " ORDER BY ts ASC",
                (hex_code.lower(),),
            )
            rows = await cur.fetchall()
    return [{"lat": r[0], "lon": r[1], "alt": r[2]} for r in rows]


@app.get("/live/aircraft")
async def live_aircraft():
    now = time.time()
    active = [v for v in position_store.values() if now - v["last_seen"] < POSITION_TTL]
    return active


@app.get("/live/stream")
async def live_stream(request: Request):
    async def generator():
        while True:
            if await request.is_disconnected():
                break
            now = time.time()
            active = [v for v in position_store.values() if now - v["last_seen"] < POSITION_TTL]
            yield f"data: {json.dumps(active)}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/live/feeders")
async def live_feeders(request: Request):
    local_pool = request.app.state.pool
    async with local_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """SELECT name, last_seen_at, aircraft_count, message_count
                   FROM feeders
                   WHERE last_seen_at > NOW() - INTERVAL '5 minutes'
                   ORDER BY last_seen_at DESC"""
            )
            rows = await cur.fetchall()
    return [
        {
            "name": r[0],
            "last_seen_at": r[1].isoformat() if r[1] else None,
            "aircraft_count": r[2],
            "message_count": r[3],
        }
        for r in rows
    ]


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
