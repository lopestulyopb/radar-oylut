import os
from typing import Any

import httpx
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.collector import collect_news

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"

app = FastAPI(
    title="Radar Oylut",
    description="Radar jornalístico protegido por login.",
    version="5.2.0",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def supabase_headers(access_token: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def set_auth_cookies(response: Any, access_token: str, refresh_token: str) -> None:
    common = {
        "httponly": True,
        "secure": COOKIE_SECURE,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie("oylut_access_token", access_token, max_age=3600, **common)
    response.set_cookie(
        "oylut_refresh_token",
        refresh_token,
        max_age=60 * 60 * 24 * 30,
        **common,
    )


def clear_auth_cookies(response: Any) -> None:
    response.delete_cookie("oylut_access_token", path="/")
    response.delete_cookie("oylut_refresh_token", path="/")


async def validate_or_refresh_session(request: Request):
    access_token = request.cookies.get("oylut_access_token")
    refresh_token = request.cookies.get("oylut_refresh_token")

    async with httpx.AsyncClient(timeout=15) as client:
        if access_token:
            user_response = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers=supabase_headers(access_token),
            )
            if user_response.status_code == 200:
                return user_response.json(), None

        if refresh_token:
            refresh_response = await client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
                headers=supabase_headers(),
                json={"refresh_token": refresh_token},
            )
            if refresh_response.status_code == 200:
                session = refresh_response.json()
                new_access = session.get("access_token")
                new_refresh = session.get("refresh_token")
                user = session.get("user")
                if new_access and new_refresh and user:
                    return user, (new_access, new_refresh)

    return None, None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user, refreshed = await validate_or_refresh_session(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    response = templates.TemplateResponse(
        request=request,
        name="radar.html",
        context={"email": user.get("email", "")},
    )
    if refreshed:
        set_auth_cookies(response, *refreshed)
    return response


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user, refreshed = await validate_or_refresh_session(request)
    if user:
        response = RedirectResponse("/", status_code=303)
        if refreshed:
            set_auth_cookies(response, *refreshed)
        return response

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"erro": None},
    )


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, email: str = Form(...), senha: str = Form(...)):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"erro": "Configuração do Supabase ausente no servidor."},
            status_code=500,
        )

    async with httpx.AsyncClient(timeout=15) as client:
        auth_response = await client.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers=supabase_headers(),
            json={"email": email.strip(), "password": senha},
        )

    if auth_response.status_code != 200:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"erro": "E-mail ou senha inválidos."},
            status_code=401,
        )

    session = auth_response.json()
    response = RedirectResponse("/", status_code=303)
    set_auth_cookies(
        response,
        session["access_token"],
        session["refresh_token"],
    )
    return response


@app.post("/sair")
async def sair():
    response = RedirectResponse("/login", status_code=303)
    clear_auth_cookies(response)
    return response


@app.get("/saude")
def saude():
    return {"status": "ok", "versao": "5.2.0"}


@app.get("/radar", operation_id="buscarNoticiasRecentes")
async def radar(request: Request, horas: int = Query(default=24, ge=1, le=24)):
    user, refreshed = await validate_or_refresh_session(request)
    if not user:
        return JSONResponse({"detail": "Não autenticado"}, status_code=401)

    noticias = await collect_news(hours=horas)
    response = JSONResponse(noticias)
    if refreshed:
        set_auth_cookies(response, *refreshed)
    return response
