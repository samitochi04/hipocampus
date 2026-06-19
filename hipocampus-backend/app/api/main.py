from fastapi import FastAPI

app = FastAPI(title="Hipocampus")

@app.get("/")
async def root():
    return {"status": "running"}