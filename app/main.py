import os
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.collector import collect_news

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SITE_URL = os.getenv("SITE_URL", "https://radar-oylut.onrender.com").rstrip("/")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
DAILY_LIMIT = 18

app = FastAPI(
    title="Radar Oylut",
    description="Radar jornalístico protegido por login.",
    version="5.5.0",
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


def friendly_auth_error(payload: dict, default: str) -> str:
    message = str(
        payload.get("msg")
        or payload.get("message")
        or payload.get("error_description")
        or payload.get("error")
        or ""
    ).lower()

    if "already registered" in message or "already been registered" in message:
        return "Este e-mail já está cadastrado."
    if "invalid email" in message:
        return "Digite um endereço de e-mail válido."
    if "password" in message and (
        "characters" in message or "length" in message or "weak" in message
    ):
        return "A senha não atende aos requisitos de segurança."
    if "signup is disabled" in message:
        return "O cadastro de novos usuários está temporariamente indisponível."
    if "same password" in message:
        return "A nova senha precisa ser diferente da senha atual."
    return default


async def validate_or_refresh_session(request: Request):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None, None, None

    access_token = request.cookies.get("oylut_access_token")
    refresh_token = request.cookies.get("oylut_refresh_token")

    async with httpx.AsyncClient(timeout=15) as client:
        if access_token:
            try:
                user_response = await client.get(
                    f"{SUPABASE_URL}/auth/v1/user",
                    headers=supabase_headers(access_token),
                )
                if user_response.status_code == 200:
                    return user_response.json(), None, access_token
            except httpx.HTTPError:
                pass

        if refresh_token:
            try:
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
                        return user, (new_access, new_refresh), new_access
            except httpx.HTTPError:
                pass

    return None, None, None


async def get_profile(access_token: str, user_id: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=supabase_headers(access_token),
            params={
                "id": f"eq.{user_id}",
                "select": "id,name,email,subscription_status,subscription_expires_at,created_at",
                "limit": "1",
            },
        )
    if response.status_code != 200:
        return {}
    rows = response.json()
    return rows[0] if rows else {}


async def get_daily_usage(access_token: str, user_id: str) -> int:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/daily_usage",
            headers=supabase_headers(access_token),
            params={
                "user_id": f"eq.{user_id}",
                "usage_date": "eq." + __import__("datetime").date.today().isoformat(),
                "select": "queries_used",
                "limit": "1",
            },
        )
    if response.status_code != 200:
        return 0
    rows = response.json()
    return int(rows[0].get("queries_used", 0)) if rows else 0


async def consume_daily_query(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/consume_daily_query",
            headers={
                **supabase_headers(access_token),
                "Prefer": "return=representation",
            },
            json={"p_limit": DAILY_LIMIT},
        )
    if response.status_code != 200:
        return {"allowed": False, "used": DAILY_LIMIT, "remaining": 0}
    payload = response.json()
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    return {
        "allowed": bool(payload.get("allowed", False)),
        "used": int(payload.get("used", DAILY_LIMIT)),
        "remaining": int(payload.get("remaining", 0)),
    }


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user, refreshed, access_token = await validate_or_refresh_session(request)
    if not user or not access_token:
        return RedirectResponse("/login", status_code=303)

    usage = await get_daily_usage(access_token, user["id"])
    response = templates.TemplateResponse(
        request=request,
        name="radar.html",
        context={
            "email": user.get("email", ""),
            "consultas_usadas": usage,
            "consultas_restantes": max(0, DAILY_LIMIT - usage),
            "limite_diario": DAILY_LIMIT,
        },
    )
    if refreshed:
        set_auth_cookies(response, *refreshed)
    return response


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, mensagem: str | None = Query(default=None)):
    user, refreshed, _ = await validate_or_refresh_session(request)
    if user:
        response = RedirectResponse("/", status_code=303)
        if refreshed:
            set_auth_cookies(response, *refreshed)
        return response

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"erro": None, "mensagem": mensagem, "email": ""},
    )


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, email: str = Form(...), senha: str = Form(...)):
    email = email.strip().lower()
    if not SUPABASE_URL or not SUPABASE_KEY:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"erro": "Configuração do Supabase ausente no servidor.", "mensagem": None, "email": email},
            status_code=500,
        )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            auth_response = await client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                headers=supabase_headers(),
                json={"email": email, "password": senha},
            )
    except httpx.HTTPError:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"erro": "Não foi possível conectar ao serviço de autenticação.", "mensagem": None, "email": email},
            status_code=503,
        )

    if auth_response.status_code != 200:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"erro": "E-mail ou senha inválidos.", "mensagem": None, "email": email},
            status_code=401,
        )

    session = auth_response.json()
    response = RedirectResponse("/", status_code=303)
    set_auth_cookies(response, session["access_token"], session["refresh_token"])
    return response


@app.get("/cadastro", response_class=HTMLResponse)
async def cadastro_page(request: Request):
    user, refreshed, _ = await validate_or_refresh_session(request)
    if user:
        response = RedirectResponse("/", status_code=303)
        if refreshed:
            set_auth_cookies(response, *refreshed)
        return response
    return templates.TemplateResponse(
        request=request,
        name="cadastro.html",
        context={"erro": None, "nome": "", "email": ""},
    )


@app.post("/cadastro", response_class=HTMLResponse)
async def cadastro(
    request: Request,
    nome: str = Form(...),
    email: str = Form(...),
    senha: str = Form(...),
    confirmar_senha: str = Form(...),
):
    nome = " ".join(nome.strip().split())
    email = email.strip().lower()
    context = {"erro": None, "nome": nome, "email": email}

    if len(nome) < 2:
        context["erro"] = "Digite seu nome."
    elif senha != confirmar_senha:
        context["erro"] = "As senhas não são iguais."
    elif len(senha) < 8:
        context["erro"] = "A senha precisa ter pelo menos 8 caracteres."

    if context["erro"]:
        return templates.TemplateResponse(request=request, name="cadastro.html", context=context, status_code=400)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            signup_response = await client.post(
                f"{SUPABASE_URL}/auth/v1/signup",
                headers=supabase_headers(),
                json={
                    "email": email,
                    "password": senha,
                    "data": {"name": nome, "full_name": nome},
                },
            )
    except httpx.HTTPError:
        context["erro"] = "Não foi possível conectar ao serviço de cadastro."
        return templates.TemplateResponse(request=request, name="cadastro.html", context=context, status_code=503)

    try:
        signup_data = signup_response.json()
    except ValueError:
        signup_data = {}

    if signup_response.status_code not in (200, 201):
        context["erro"] = friendly_auth_error(signup_data, "Não foi possível criar sua conta.")
        return templates.TemplateResponse(request=request, name="cadastro.html", context=context, status_code=400)

    if signup_data.get("access_token") and signup_data.get("refresh_token"):
        response = RedirectResponse("/", status_code=303)
        set_auth_cookies(response, signup_data["access_token"], signup_data["refresh_token"])
        return response

    mensagem = quote("Cadastro realizado. Verifique seu e-mail para confirmar a conta.")
    return RedirectResponse(f"/login?mensagem={mensagem}", status_code=303)


@app.get("/esqueci-senha", response_class=HTMLResponse)
async def esqueci_senha_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="esqueci-senha.html",
        context={"erro": None, "mensagem": None, "email": ""},
    )


@app.post("/esqueci-senha", response_class=HTMLResponse)
async def esqueci_senha(request: Request, email: str = Form(...)):
    email = email.strip().lower()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{SUPABASE_URL}/auth/v1/recover",
                headers=supabase_headers(),
                params={"redirect_to": f"{SITE_URL}/redefinir-senha"},
                json={"email": email},
            )
    except httpx.HTTPError:
        return templates.TemplateResponse(
            request=request,
            name="esqueci-senha.html",
            context={"erro": "Não foi possível solicitar a recuperação agora.", "mensagem": None, "email": email},
            status_code=503,
        )

    if response.status_code not in (200, 201):
        return templates.TemplateResponse(
            request=request,
            name="esqueci-senha.html",
            context={"erro": "Não foi possível enviar o link de recuperação.", "mensagem": None, "email": email},
            status_code=400,
        )

    return templates.TemplateResponse(
        request=request,
        name="esqueci-senha.html",
        context={
            "erro": None,
            "mensagem": "Se o e-mail estiver cadastrado, você receberá um link para criar uma nova senha.",
            "email": email,
        },
    )


@app.get("/redefinir-senha", response_class=HTMLResponse)
async def redefinir_senha_page(request: Request):
    return templates.TemplateResponse(request=request, name="redefinir-senha.html", context={"erro": None})


@app.post("/redefinir-senha", response_class=HTMLResponse)
async def redefinir_senha(
    request: Request,
    access_token: str = Form(...),
    senha: str = Form(...),
    confirmar_senha: str = Form(...),
):
    if senha != confirmar_senha:
        return templates.TemplateResponse(
            request=request,
            name="redefinir-senha.html",
            context={"erro": "As senhas não são iguais."},
            status_code=400,
        )
    if len(senha) < 8:
        return templates.TemplateResponse(
            request=request,
            name="redefinir-senha.html",
            context={"erro": "A senha precisa ter pelo menos 8 caracteres."},
            status_code=400,
        )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            update_response = await client.put(
                f"{SUPABASE_URL}/auth/v1/user",
                headers=supabase_headers(access_token),
                json={"password": senha},
            )
    except httpx.HTTPError:
        update_response = None

    if not update_response or update_response.status_code != 200:
        return templates.TemplateResponse(
            request=request,
            name="redefinir-senha.html",
            context={"erro": "O link expirou ou não foi possível atualizar a senha."},
            status_code=400,
        )

    return RedirectResponse(
        "/login?mensagem=" + quote("Senha atualizada. Entre com sua nova senha."),
        status_code=303,
    )


@app.get("/minha-conta", response_class=HTMLResponse)
async def minha_conta(request: Request):
    user, refreshed, access_token = await validate_or_refresh_session(request)
    if not user or not access_token:
        return RedirectResponse("/login", status_code=303)

    profile = await get_profile(access_token, user["id"])
    usage = await get_daily_usage(access_token, user["id"])
    response = templates.TemplateResponse(
        request=request,
        name="minha-conta.html",
        context={
            "nome": profile.get("name") or user.get("user_metadata", {}).get("name") or "",
            "email": profile.get("email") or user.get("email", ""),
            "subscription_status": profile.get("subscription_status") or "pendente",
            "subscription_expires_at": profile.get("subscription_expires_at"),
            "consultas_usadas": usage,
            "consultas_restantes": max(0, DAILY_LIMIT - usage),
            "limite_diario": DAILY_LIMIT,
        },
    )
    if refreshed:
        set_auth_cookies(response, *refreshed)
    return response


@app.post("/sair")
async def sair():
    response = RedirectResponse("/login", status_code=303)
    clear_auth_cookies(response)
    return response


@app.get("/saude")
def saude():
    return {"status": "ok", "versao": "5.5.0"}


@app.get("/radar", operation_id="buscarNoticiasRecentes")
async def radar(
    request: Request,
    horas: int = Query(default=24, ge=1, le=24),
    editoria: str = Query(default="todas", pattern="^(todas|seguranca|servico|esportes|politica|geral)$"),
):
    user, refreshed, access_token = await validate_or_refresh_session(request)
    if not user or not access_token:
        return JSONResponse({"detail": "Não autenticado"}, status_code=401)

    used_before = await get_daily_usage(access_token, user["id"])
    if used_before >= DAILY_LIMIT:
        return JSONResponse(
            {"detail": "Limite diário atingido.", "used": used_before, "remaining": 0, "limit": DAILY_LIMIT},
            status_code=429,
        )

    try:
        noticias = await collect_news(hours=horas, editoria=editoria)
    except Exception:
        return JSONResponse({"detail": "Não foi possível executar o Radar agora."}, status_code=503)

    consumption = await consume_daily_query(access_token)
    if not consumption["allowed"]:
        return JSONResponse(
            {"detail": "Limite diário atingido.", "used": consumption["used"], "remaining": 0, "limit": DAILY_LIMIT},
            status_code=429,
        )

    response = JSONResponse({
        "noticias": noticias,
        "usage": {
            "used": consumption["used"],
            "remaining": consumption["remaining"],
            "limit": DAILY_LIMIT,
        },
    })
    if refreshed:
        set_auth_cookies(response, *refreshed)
    return response
