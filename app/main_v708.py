from __future__ import annotations

import asyncio
import os
import time
from collections import Counter
from datetime import date, datetime
from typing import Any

import httpx
from fastapi import Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import app.collector as collector
import app.main as core
from app.admin_v708 import router as admin_v708_router
from app.main_v7 import app

app.include_router(admin_v708_router)
app.version = "7.0.8"

OWNER_UNLIMITED_EMAILS = {
    email.strip().lower()
    for email in os.getenv("UNLIMITED_EMAILS", "lopestulyo@gmail.com").split(",")
    if email.strip()
}

DEFAULT_SETTINGS = {
    "daily_limit": 18,
    "cache_ttl_seconds": 180,
    "default_order": "editor_chefe",
    "app_version": "7.0.8",
    "enabled_sources": ["clickpb", "jornal_paraiba", "maispb", "polemica_paraiba"],
}

SOURCE_CONFIG = {
    "clickpb": ("ClickPB", collector.collect_clickpb_candidates),
    "jornal_paraiba": ("Jornal da Paraíba", collector.collect_jornal_candidates),
    "maispb": ("MaisPB", collector.collect_maispb_candidates),
    "polemica_paraiba": ("Polêmica Paraíba", collector.collect_polemica_candidates),
}

_settings_cache: tuple[float, dict[str, Any]] | None = None
_last_sources_signature: tuple[str, ...] | None = None


def service_headers(prefer: str | None = None) -> dict[str, str]:
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    result = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        result["Prefer"] = prefer
    return result


async def load_settings(force: bool = False) -> dict[str, Any]:
    global _settings_cache
    if not force and _settings_cache and time.monotonic() - _settings_cache[0] < 20:
        return dict(_settings_cache[1])
    settings = dict(DEFAULT_SETTINGS)
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if key and core.SUPABASE_URL:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{core.SUPABASE_URL}/rest/v1/app_settings",
                    headers=service_headers(),
                    params={"select": "setting_key,setting_value"},
                )
            if response.status_code == 200:
                for row in response.json():
                    settings[row["setting_key"]] = row.get("setting_value")
        except httpx.HTTPError:
            pass
    settings["daily_limit"] = int(settings.get("daily_limit") or 18)
    settings["cache_ttl_seconds"] = int(settings.get("cache_ttl_seconds") or 0)
    if settings.get("default_order") not in {"editor_chefe", "recentes"}:
        settings["default_order"] = "editor_chefe"
    enabled = settings.get("enabled_sources")
    if not isinstance(enabled, list):
        settings["enabled_sources"] = list(DEFAULT_SETTINGS["enabled_sources"])
    _settings_cache = (time.monotonic(), settings)
    return dict(settings)


async def consume_query(access_token: str, limit: int) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{core.SUPABASE_URL}/rest/v1/rpc/consume_daily_query",
            headers={**core.supabase_headers(access_token), "Prefer": "return=representation"},
            json={"p_limit": limit},
        )
    if response.status_code != 200:
        return {"allowed": False, "used": limit, "remaining": 0}
    payload = response.json()
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    return {
        "allowed": bool(payload.get("allowed", False)),
        "used": int(payload.get("used", limit)),
        "remaining": int(payload.get("remaining", 0)),
    }


async def update_source_metrics(counts: Counter, elapsed_ms: int) -> None:
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not key or not core.SUPABASE_URL:
        return
    now = datetime.utcnow().isoformat() + "Z"
    async with httpx.AsyncClient(timeout=10) as client:
        for source_key, (source_name, _) in SOURCE_CONFIG.items():
            count = int(counts.get(source_name, 0))
            if count <= 0:
                continue
            try:
                await client.patch(
                    f"{core.SUPABASE_URL}/rest/v1/source_monitor",
                    headers=service_headers("return=minimal"),
                    params={"source_key": f"eq.{source_key}"},
                    json={
                        "last_collection_at": now,
                        "collected_news_count": count,
                        "average_response_ms": elapsed_ms,
                        "status": "online",
                    },
                )
            except httpx.HTTPError:
                pass


async def collect_selected(hours: int, editoria: str, enabled_sources: list[str]) -> list[dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=25) as client:
        tasks = []
        for source_key in enabled_sources:
            config = SOURCE_CONFIG.get(source_key)
            if not config:
                continue
            function = config[1]
            if source_key in {"jornal_paraiba", "polemica_paraiba"}:
                tasks.append(function(client, hours))
            else:
                tasks.append(function(client))
        groups = await asyncio.gather(*tasks) if tasks else []
        candidates, seen = [], set()
        for group in groups:
            for candidate in group:
                if candidate["url"] not in seen and collector.candidate_may_match(candidate, editoria):
                    seen.add(candidate["url"])
                    candidates.append(candidate)
        semaphore = asyncio.Semaphore(10)
        enriched = await asyncio.gather(
            *(collector.enrich_article(client, candidate, hours, semaphore, editoria) for candidate in candidates)
        )
    return [collector.public_item(item) for item in enriched if item]


def remove_route(path: str, method: str) -> None:
    app.router.routes[:] = [
        route for route in app.router.routes
        if not (getattr(route, "path", None) == path and method in getattr(route, "methods", set()))
    ]


remove_route("/", "GET")
remove_route("/radar", "GET")


@app.get("/", response_class=HTMLResponse)
async def home_v708(request: Request):
    user, refreshed, access_token = await core.validate_or_refresh_session(request)
    if not user or not access_token:
        return RedirectResponse("/login", status_code=303)
    settings = await load_settings()
    profile = await core.get_profile(access_token, user["id"])
    subscription = core.normalize_subscription(profile)
    usage = await core.get_daily_usage(access_token, user["id"])
    email = str(user.get("email") or "").lower()
    unlimited = email in OWNER_UNLIMITED_EMAILS
    limit = int(settings["daily_limit"])
    response = core.templates.TemplateResponse(
        request=request,
        name="radar_v708.html",
        context={
            "email": user.get("email", ""),
            "consultas_usadas": usage,
            "consultas_restantes": max(0, limit - usage),
            "limite_diario": limit,
            "consultas_ilimitadas": unlimited,
            "subscription_active": subscription["is_active"],
            "default_order": settings["default_order"],
        },
    )
    if refreshed:
        core.set_auth_cookies(response, *refreshed)
    return response


@app.get("/radar", operation_id="buscarNoticiasRecentesV708")
async def radar_v708(
    request: Request,
    horas: int = Query(default=24, ge=1, le=24),
    editoria: str = Query(default="todas", pattern="^(todas|seguranca|servico|esportes|politica|geral)$"),
    ordenar: str | None = Query(default=None, pattern="^(editor_chefe|recentes)$"),
):
    global _last_sources_signature
    user, refreshed, access_token = await core.validate_or_refresh_session(request)
    if not user or not access_token:
        return JSONResponse({"detail": "Não autenticado"}, status_code=401)
    settings = await load_settings()
    ordenar = ordenar or settings["default_order"]
    profile = await core.get_profile(access_token, user["id"])
    subscription = core.normalize_subscription(profile)
    if not subscription["is_active"]:
        return JSONResponse({"detail": "Sua assinatura não está ativa. Consulte Minha Conta."}, status_code=403)

    email = str(user.get("email") or "").lower()
    unlimited = email in OWNER_UNLIMITED_EMAILS
    limit = int(settings["daily_limit"])
    used_before = await core.get_daily_usage(access_token, user["id"])
    if not unlimited and used_before >= limit:
        return JSONResponse({"detail": "Limite diário atingido.", "used": used_before, "remaining": 0, "limit": limit}, status_code=429)

    enabled_sources = sorted(settings["enabled_sources"])
    signature = tuple(enabled_sources)
    if signature != _last_sources_signature:
        core._news_cache.clear()
        _last_sources_signature = signature
    core.NEWS_CACHE_TTL_SECONDS = int(settings["cache_ttl_seconds"])

    started = time.perf_counter()
    try:
        noticias_coletadas = core.get_cached_news(horas, editoria)
        if noticias_coletadas is None:
            noticias_coletadas = await collect_selected(horas, editoria, enabled_sources)
            core.set_cached_news(horas, editoria, noticias_coletadas)
        noticias = core.consolidate_and_rank(noticias_coletadas, order=ordenar)
    except Exception:
        return JSONResponse({"detail": "Não foi possível executar o Radar agora."}, status_code=503)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    counts = Counter()
    for item in noticias:
        for source in item.get("fontes", []):
            counts[source.get("nome") or source.get("fonte") or ""] += 1
    asyncio.create_task(update_source_metrics(counts, elapsed_ms))

    if unlimited:
        usage_payload = {"used": used_before, "remaining": None, "limit": None, "unlimited": True}
    else:
        consumption = await consume_query(access_token, limit)
        if not consumption["allowed"]:
            return JSONResponse({"detail": "Limite diário atingido.", "used": consumption["used"], "remaining": 0, "limit": limit}, status_code=429)
        usage_payload = {**consumption, "limit": limit, "unlimited": False}

    response = JSONResponse({"noticias": noticias, "ordenacao": ordenar, "usage": usage_payload})
    if refreshed:
        core.set_auth_cookies(response, *refreshed)
    return response
