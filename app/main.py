from fastapi import FastAPI, Query

from app.collector import collect_recent_links
from app.sources import SOURCES


app = FastAPI(
    title="Radar Oylut",
    description="Retorna links publicados nas últimas 24 horas.",
    version="1.1.0",
)


@app.get("/")
def home():
    return {
        "servico": "Radar Oylut",
        "status": "online",
        "versao": "1.1.0",
        "rota": "/radar",
    }


@app.get(
    "/radar",
    response_model=list[str],
    operation_id="buscarLinksRecentes",
)
async def radar(
    horas: int = Query(default=24, ge=1, le=72),
):
    return await collect_recent_links(SOURCES, horas=horas)
