from fastapi import FastAPI, Query

from app.collector import collect_recent_links
from app.sources import SOURCES


app = FastAPI(
    title="Radar Oylut",
    description="Retorna somente links de matérias recentes.",
    version="2.0.0",
)


@app.get("/")
def home():
    return {
        "servico": "Radar Oylut",
        "status": "online",
        "versao": "2.0.0",
        "rota": "/radar",
    }


@app.get(
    "/saude",
    operation_id="verificarSaude",
)
def saude():
    return {"status": "ok"}


@app.get(
    "/radar",
    response_model=list[str],
    operation_id="buscarLinksRecentes",
)
async def radar(
    horas: int = Query(default=24, ge=1, le=72),
    consulta: str | None = Query(default=None),
    limite: int | None = Query(default=None, ge=1, le=500),
):
    # consulta é mantida apenas para compatibilidade com URLs antigas.
    links = await collect_recent_links(SOURCES, hours=horas)

    if limite:
        links = links[:limite]

    return links
