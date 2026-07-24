import os
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
ADMIN_EMAILS = {
    email.strip().lower()
    for email in os.getenv("ADMIN_EMAILS", "").split(",")
    if email.strip()
}
APP_VERSION = "7.0.6"


def headers(key: str, token: str | None = None, prefer: str | None = None) -> dict[str, str]:
    result = {"apikey": key, "Content-Type": "application/json"}
    result["Authorization"] = f"Bearer {token or key}"
    if prefer:
        result["Prefer"] = prefer
    return result


def set_admin_cookies(response: Any, access_token: str, refresh_token: str) -> None:
    common = {
        "httponly": True,
        "secure": COOKIE_SECURE,
        "samesite": "lax",
        "path": "/admin",
    }
    response.set_cookie("oylut_admin_access", access_token, max_age=3600, **common)
    response.set_cookie("oylut_admin_refresh", refresh_token, max_age=60 * 60 * 24 * 30, **common)


def clear_admin_cookies(response: Any) -> None:
    response.delete_cookie("oylut_admin_access", path="/admin")
    response.delete_cookie("oylut_admin_refresh", path="/admin")


async def validate_admin(request: Request):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None, None
    access = request.cookies.get("oylut_admin_access")
    refresh = request.cookies.get("oylut_admin_refresh")
    async with httpx.AsyncClient(timeout=15) as client:
        if access:
            try:
                response = await client.get(
                    f"{SUPABASE_URL}/auth/v1/user",
                    headers=headers(SUPABASE_ANON_KEY, access),
                )
                if response.status_code == 200:
                    user = response.json()
                    if str(user.get("email", "")).lower() in ADMIN_EMAILS:
                        return user, None
            except httpx.HTTPError:
                pass
        if refresh:
            try:
                response = await client.post(
                    f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
                    headers=headers(SUPABASE_ANON_KEY),
                    json={"refresh_token": refresh},
                )
                if response.status_code == 200:
                    payload = response.json()
                    user = payload.get("user") or {}
                    if str(user.get("email", "")).lower() in ADMIN_EMAILS:
                        return user, (payload["access_token"], payload["refresh_token"])
            except httpx.HTTPError:
                pass
    return None, None


async def require_admin(request: Request):
    user, refreshed = await validate_admin(request)
    if not user:
        return None, None, RedirectResponse("/admin/login", status_code=303)
    if not SUPABASE_SERVICE_KEY:
        return user, refreshed, templates.TemplateResponse(
            request=request,
            name="admin/error.html",
            context={"message": "A chave administrativa do banco ainda não foi configurada."},
            status_code=503,
        )
    return user, refreshed, None


def apply_refresh(response: Any, refreshed: tuple[str, str] | None):
    if refreshed:
        set_admin_cookies(response, *refreshed)
    return response


async def db_get(table: str, params: dict[str, str] | None = None) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers(SUPABASE_SERVICE_KEY),
            params=params or {},
        )
    if response.status_code != 200:
        return []
    return response.json()


async def db_insert(table: str, payload: dict) -> bool:
    key = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers(key, prefer="return=minimal"),
            json=payload,
        )
    return response.status_code in (200, 201, 204)


async def db_patch(table: str, filters: dict[str, str], payload: dict) -> bool:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers(SUPABASE_SERVICE_KEY, prefer="return=minimal"),
            params=filters,
            json=payload,
        )
    return response.status_code in (200, 204)


async def db_delete(table: str, filters: dict[str, str]) -> bool:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.delete(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers(SUPABASE_SERVICE_KEY, prefer="return=minimal"),
            params=filters,
        )
    return response.status_code in (200, 204)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def status_effective(profile: dict) -> str:
    status = str(profile.get("subscription_status") or "pending").lower()
    expires = parse_iso(profile.get("subscription_expires_at"))
    if status == "active" and expires and expires.date() < date.today():
        return "expired"
    return status if status in {"active", "pending", "expired", "inactive"} else "pending"


def admin_context(active: str, user: dict, **extra):
    return {"active": active, "admin_email": user.get("email", ""), "version": APP_VERSION, **extra}


@router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request, erro: str | None = Query(default=None)):
    user, refreshed = await validate_admin(request)
    if user:
        response = RedirectResponse("/admin", status_code=303)
        return apply_refresh(response, refreshed)
    return templates.TemplateResponse(
        request=request,
        name="admin/login.html",
        context={"erro": erro},
    )


@router.post("/admin/login")
async def admin_login(request: Request, email: str = Form(...), senha: str = Form(...)):
    email = email.strip().lower()
    if email not in ADMIN_EMAILS:
        return templates.TemplateResponse(
            request=request,
            name="admin/login.html",
            context={"erro": "Acesso administrativo não autorizado."},
            status_code=403,
        )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                headers=headers(SUPABASE_ANON_KEY),
                json={"email": email, "password": senha},
            )
    except httpx.HTTPError:
        response = None
    if not response or response.status_code != 200:
        return templates.TemplateResponse(
            request=request,
            name="admin/login.html",
            context={"erro": "Credenciais inválidas."},
            status_code=401,
        )
    payload = response.json()
    redirect = RedirectResponse("/admin", status_code=303)
    set_admin_cookies(redirect, payload["access_token"], payload["refresh_token"])
    return redirect


@router.post("/admin/sair")
async def admin_logout():
    response = RedirectResponse("/admin/login", status_code=303)
    clear_admin_cookies(response)
    return response


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    user, refreshed, denied = await require_admin(request)
    if denied:
        return denied
    today = date.today().isoformat()
    month_start = date.today().replace(day=1).isoformat()
    profiles = await db_get("profiles", {"select": "id,name,email,subscription_status,subscription_expires_at,created_at", "order": "created_at.desc"})
    usage_today = await db_get("daily_usage", {"select": "user_id,queries_used,usage_date", "usage_date": f"eq.{today}"})
    usage_month = await db_get("daily_usage", {"select": "user_id,queries_used,usage_date", "usage_date": f"gte.{month_start}", "order": "usage_date.asc"})
    feedbacks = await db_get("feedbacks", {"select": "id,status"})
    contacts = await db_get("contacts", {"select": "id,status"})
    events = await db_get("analytics_events", {"select": "event_type,created_at", "created_at": f"gte.{month_start}T00:00:00Z"})

    status_counts = Counter(status_effective(p) for p in profiles)
    daily = defaultdict(int)
    for row in usage_month:
        daily[str(row.get("usage_date"))] += int(row.get("queries_used") or 0)
    created = defaultdict(int)
    for profile in profiles:
        dt = parse_iso(profile.get("created_at"))
        if dt and dt.date() >= date.today() - timedelta(days=30):
            created[dt.date().isoformat()] += 1

    response = templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context=admin_context(
            "dashboard", user,
            cards={
                "users": len(profiles),
                "active": status_counts["active"],
                "pending": status_counts["pending"],
                "queries_today": sum(int(r.get("queries_used") or 0) for r in usage_today),
                "queries_month": sum(int(r.get("queries_used") or 0) for r in usage_month),
                "feedbacks": len(feedbacks),
                "contacts": len(contacts),
            },
            daily_labels=list(daily.keys()),
            daily_values=list(daily.values()),
            user_labels=list(created.keys()),
            user_values=list(created.values()),
            subscription_values=[status_counts[k] for k in ("active", "pending", "expired", "inactive")],
            event_count=len(events),
            updated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
        ),
    )
    return apply_refresh(response, refreshed)


@router.get("/admin/usuarios", response_class=HTMLResponse)
async def admin_users(request: Request):
    user, refreshed, denied = await require_admin(request)
    if denied:
        return denied
    profiles = await db_get("profiles", {"select": "id,name,email,subscription_status,subscription_expires_at,created_at", "order": "created_at.desc"})
    usage = await db_get("daily_usage", {"select": "user_id,queries_used", "usage_date": f"eq.{date.today().isoformat()}"})
    usage_by_user = {row.get("user_id"): int(row.get("queries_used") or 0) for row in usage}
    for profile in profiles:
        profile["effective_status"] = status_effective(profile)
        profile["queries_today"] = usage_by_user.get(profile.get("id"), 0)
    response = templates.TemplateResponse(
        request=request,
        name="admin/users.html",
        context=admin_context("users", user, users=profiles),
    )
    return apply_refresh(response, refreshed)


@router.get("/admin/assinaturas", response_class=HTMLResponse)
async def admin_subscriptions(request: Request, status: str = Query(default="todas")):
    user, refreshed, denied = await require_admin(request)
    if denied:
        return denied
    profiles = await db_get("profiles", {"select": "id,name,email,subscription_status,subscription_expires_at,created_at", "order": "created_at.desc"})
    for profile in profiles:
        profile["effective_status"] = status_effective(profile)
    if status != "todas":
        profiles = [p for p in profiles if p["effective_status"] == status]
    response = templates.TemplateResponse(
        request=request,
        name="admin/subscriptions.html",
        context=admin_context("subscriptions", user, users=profiles, selected_status=status),
    )
    return apply_refresh(response, refreshed)


@router.post("/admin/usuarios/{user_id}/assinatura")
async def update_subscription(
    request: Request,
    user_id: str,
    status: str = Form(...),
    expires_at: str = Form(default=""),
    return_to: str = Form(default="/admin/assinaturas"),
):
    _, _, denied = await require_admin(request)
    if denied:
        return denied
    if status not in {"active", "pending", "inactive"}:
        status = "pending"
    payload = {"subscription_status": status, "subscription_expires_at": expires_at or None}
    await db_patch("profiles", {"id": f"eq.{user_id}"}, payload)
    return RedirectResponse(return_to, status_code=303)


@router.post("/admin/usuarios/{user_id}/excluir")
async def delete_user(request: Request, user_id: str = ""):
    _, _, denied = await require_admin(request)
    if denied:
        return denied
    await db_delete("profiles", {"id": f"eq.{user_id}"})
    return RedirectResponse("/admin/usuarios", status_code=303)


@router.get("/admin/feedback", response_class=HTMLResponse)
async def admin_feedback(request: Request, tipo: str = Query(default="todos"), status: str = Query(default="todos")):
    user, refreshed, denied = await require_admin(request)
    if denied:
        return denied
    params = {"select": "*", "order": "created_at.desc"}
    if tipo != "todos":
        params["feedback_type"] = f"eq.{tipo}"
    if status != "todos":
        params["status"] = f"eq.{status}"
    rows = await db_get("feedbacks", params)
    response = templates.TemplateResponse(
        request=request,
        name="admin/feedback.html",
        context=admin_context("feedback", user, items=rows, selected_type=tipo, selected_status=status),
    )
    return apply_refresh(response, refreshed)


@router.get("/admin/contato", response_class=HTMLResponse)
async def admin_contacts(request: Request, assunto: str = Query(default="todos"), status: str = Query(default="todos")):
    user, refreshed, denied = await require_admin(request)
    if denied:
        return denied
    params = {"select": "*", "order": "created_at.desc"}
    if assunto != "todos":
        params["subject"] = f"eq.{assunto}"
    if status != "todos":
        params["status"] = f"eq.{status}"
    rows = await db_get("contacts", params)
    response = templates.TemplateResponse(
        request=request,
        name="admin/contacts.html",
        context=admin_context("contacts", user, items=rows, selected_subject=assunto, selected_status=status),
    )
    return apply_refresh(response, refreshed)


@router.post("/admin/{table}/{item_id}/status")
async def update_message_status(request: Request, table: str, item_id: str, status: str = Form(...)):
    _, _, denied = await require_admin(request)
    if denied:
        return denied
    if table not in {"feedbacks", "contacts"} or status not in {"novo", "analisado", "resolvido"}:
        return JSONResponse({"detail": "Operação inválida"}, status_code=400)
    await db_patch(table, {"id": f"eq.{item_id}"}, {"status": status})
    destination = "/admin/feedback" if table == "feedbacks" else "/admin/contato"
    return RedirectResponse(destination, status_code=303)


@router.post("/admin/{table}/{item_id}/excluir")
async def delete_message(request: Request, table: str, item_id: str):
    _, _, denied = await require_admin(request)
    if denied:
        return denied
    if table not in {"feedbacks", "contacts"}:
        return JSONResponse({"detail": "Operação inválida"}, status_code=400)
    await db_delete(table, {"id": f"eq.{item_id}"})
    destination = "/admin/feedback" if table == "feedbacks" else "/admin/contato"
    return RedirectResponse(destination, status_code=303)


@router.get("/admin/estatisticas", response_class=HTMLResponse)
async def admin_statistics(request: Request, dias: int = Query(default=30, ge=7, le=365)):
    user, refreshed, denied = await require_admin(request)
    if denied:
        return denied
    since = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    events = await db_get("analytics_events", {"select": "*", "created_at": f"gte.{since}", "order": "created_at.asc"})
    usage = await db_get("daily_usage", {"select": "user_id,queries_used,usage_date", "usage_date": f"gte.{(date.today()-timedelta(days=dias)).isoformat()}"})
    profiles = await db_get("profiles", {"select": "id,name,email"})
    names = {p.get("id"): p.get("name") or p.get("email") or "Usuário" for p in profiles}

    editorial = Counter()
    hours = Counter()
    periods = Counter()
    copies = Counter()
    event_types = Counter()
    for event in events:
        event_types[event.get("event_type") or "outro"] += 1
        metadata = event.get("metadata") or {}
        for item in metadata.get("editorias", []) if isinstance(metadata.get("editorias"), list) else []:
            editorial[item] += 1
        if metadata.get("hours"):
            periods[str(metadata["hours"])] += 1
        dt = parse_iso(event.get("created_at"))
        if dt:
            hours[f"{dt.hour:02d}h"] += 1
        if event.get("event_type") in {"copy_article", "copy_results"}:
            title = str(metadata.get("title") or "Resultados completos")
            copies[title] += 1

    usage_by_user = Counter()
    for row in usage:
        usage_by_user[names.get(row.get("user_id"), "Usuário")] += int(row.get("queries_used") or 0)

    response = templates.TemplateResponse(
        request=request,
        name="admin/statistics.html",
        context=admin_context(
            "statistics", user,
            days=dias,
            total_events=len(events),
            total_queries=sum(usage_by_user.values()),
            editorial=editorial.most_common(),
            hours=sorted(hours.items()),
            periods=periods.most_common(),
            users=usage_by_user.most_common(),
            copies=copies.most_common(20),
            event_types=event_types,
        ),
    )
    return apply_refresh(response, refreshed)


@router.post("/feedback")
async def submit_feedback(
    request: Request,
    feedback_type: str = Form(...),
    news_text: str = Form(...),
    comment: str = Form(default=""),
):
    user_id = None
    user_email = None
    access = request.cookies.get("oylut_access_token")
    if access:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers(SUPABASE_ANON_KEY, access))
            if response.status_code == 200:
                user = response.json()
                user_id, user_email = user.get("id"), user.get("email")
        except httpx.HTTPError:
            pass
    await db_insert("feedbacks", {
        "user_id": user_id,
        "user_email": user_email,
        "feedback_type": feedback_type,
        "news_text": news_text.strip(),
        "comment": comment.strip() or None,
        "status": "novo",
        "browser": request.headers.get("user-agent", "")[:500],
        "app_version": APP_VERSION,
    })
    return RedirectResponse("/static/mensagem-enviada.html", status_code=303)


@router.post("/contato")
async def submit_contact(
    request: Request,
    subject: str = Form(...),
    message: str = Form(...),
):
    user_id = None
    user_email = None
    access = request.cookies.get("oylut_access_token")
    if access:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers(SUPABASE_ANON_KEY, access))
            if response.status_code == 200:
                user = response.json()
                user_id, user_email = user.get("id"), user.get("email")
        except httpx.HTTPError:
            pass
    await db_insert("contacts", {
        "user_id": user_id,
        "user_email": user_email,
        "subject": subject,
        "message": message.strip(),
        "status": "novo",
        "browser": request.headers.get("user-agent", "")[:500],
        "app_version": APP_VERSION,
    })
    return RedirectResponse("/static/mensagem-enviada.html", status_code=303)


@router.post("/analytics/event")
async def analytics_event(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False}, status_code=400)
    access = request.cookies.get("oylut_access_token")
    user_id = None
    if access:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers(SUPABASE_ANON_KEY, access))
            if response.status_code == 200:
                user_id = response.json().get("id")
        except httpx.HTTPError:
            pass
    event_type = str(payload.get("event_type") or "")[:60]
    if event_type not in {"search", "copy_results", "copy_article", "result_filter"}:
        return JSONResponse({"ok": False}, status_code=400)
    await db_insert("analytics_events", {
        "user_id": user_id,
        "event_type": event_type,
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        "app_version": APP_VERSION,
    })
    return {"ok": True}
