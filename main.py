import os
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi import Request

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")



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
