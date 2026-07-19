from fastapi import FastAPI, Query

from app.collector import collect_links


app = FastAPI(
    title="Radar Oylut",
    description=(
        "Retorna links recentes do ClickPB, Jornal da Paraíba, "
        "MaisPB e Portal Correio."
    ),
    version="3.2.0",
)


@app.get("/")
def home():
    return {
        "servico": "Radar Oylut",
        "status": "online",
        "versao": "3.2.0",
        "fontes": {
            "ClickPB": "20 últimas notícias",
            "Jornal da Paraíba": "últimas 24 horas",
            "MaisPB": "20 últimas notícias",
            "Portal Correio": "20 últimas notícias",
        },
        "rota": "/radar",
    }


@app.get("/saude")
def saude():
    return {"status": "ok"}


@app.get(
    "/radar",
    response_model=list[str],
    operation_id="buscarLinksRecentes",
)
async def radar(
    horas: int = Query(
        default=24,
        ge=1,
        le=72,
        description=(
            "Período aplicado somente às matérias "
            "do Jornal da Paraíba."
        ),
    ),
):
    return await collect_links(hours=horas)
