from fastapi import FastAPI, Query
from app.config import settings
from app.models import RadarResponse
from app.service import run_radar

app = FastAPI(
    title=settings.app_name,
    version="3.0.0",
    description="Radar jornalístico de João Pessoa e da Paraíba orientado para produção de televisão.",
)


@app.get("/")
def root():
    return {
        "servico": settings.app_name,
        "status": "online",
        "versao": "3.0.0",
        "documentacao": "/docs",
        "exemplo": "/radar?consulta=Jo%C3%A3o%20Pessoa&horas=24&limite=20",
    }


@app.get("/saude")
def health():
    return {"status": "ok"}


@app.get("/radar", response_model=RadarResponse, operation_id="consultarRadar")
async def radar(
    consulta: str = Query(default="João Pessoa", min_length=2, max_length=120),
    horas: int = Query(default=24, ge=1, le=168),
    limite: int = Query(default=20, ge=1, le=50),
):
    return await run_radar(consulta, horas, limite)
