
from fastapi import FastAPI
from app.sources import SOURCES
from app.collector import collect_links
app=FastAPI(title="Radar Oylut")
@app.get("/")
def home():
    return {"service":"Radar Oylut","status":"online"}
@app.get("/radar")
async def radar():
    return await collect_links(SOURCES)
