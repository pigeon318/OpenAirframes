from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "OpenAirframes VA0.1"}


@app.get("/health")
async def health():
    return {"status": "Running OpenAirfames VA0.1"}
