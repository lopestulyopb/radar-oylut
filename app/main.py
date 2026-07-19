from fastapi import FastAPI, Query

from app.collector import collect_links


app = FastAPI(
    title="Radar Oylut",
    description=(
        "Retorna notícias publicadas no período solicitado "
        "pelo ClickPB, Jornal da Paraíba, MaisPB e Portal Correio."
    ),
    version="4.0.0",
)


@app.get("/")
def home():
    return {
        "servico": "Radar Oylut",
        "status": "online",
        "versao": "4.0.0",
        "fontes": {
            "ClickPB": "notícias do período solicitado",
            "Jornal da Paraíba": "notícias do período solicitado",
            "MaisPB": "notícias do período solicitado",
            "Portal Correio": "notícias do período solicitado",
        },
        "periodo_padrao": "24 horas",
        "rota": "/radar",
        "exemplo": "/radar?horas=24",
    }


@app.get("/saude")
def saude():
    return {
        "status": "ok",
        "versao": "4.0.0",
    }


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
            "Período em horas aplicado a todas as fontes."
        ),
    ),
):
    return await collect_links(hours=horas)
