from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import Counter
from datetime import datetime
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
logger = logging.getLogger("radar_oylut")

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
_collection_locks: dict[tuple[int, str, tuple[str, ...]], asyncio.Lock] = {}


def service_headers(prefer: str | None = None) -> dict[str, str]:
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    result = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        result["Prefer"] = prefer
    return result


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


async def load_settings(force: bool = False) -> dict[str, Any]:
    global _settings_cache
    if not force and _settings_cache and time.monotonic() - _settings_cache[0] < 20:
        return dict(_settings_cache[1])
    settings = dict(DEFAULT_SETTINGS)
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if key and core.SUPABASE_URL:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get(
                    f"{core.SUPABASE_URL}/rest/v1/app_settings",
                    headers=service_headers(),
                    params={"select": "setting_key,setting_value"},
                )
            if response.status_code == 200:
                for row in response.json():
                    settings[row["setting_key"]] = row.get("setting_value")
            else:
                logger.warning("settings_load_failed status=%s", response.status_code)
        except (httpx.HTTPError, ValueError, KeyError):
            logger.exception("settings_load_error")
    settings["daily_limit"] = _safe_int(settings.get("daily_limit"), 18, 1, 10000)
    settings["cache_ttl_seconds"] = _safe_int(settings.get("cache_ttl_seconds"), 180, 0, 3600)
    if settings.get("default_order") not in {"editor_chefe", "recentes"}:
        settings["default_order"] = "editor_chefe"
    enabled = settings.get("enabled_sources")
    if not isinstance(enabled, list):
        enabled = list(DEFAULT_SETTINGS["enabled_sources"])
    settings["enabled_sources"] = [key for key in enabled if key in SOURCE_CONFIG]
    _settings_cache = (time.monotonic(), settings)
    return dict(settings)


async def consume_query(access_token: str, limit: int) -> dict:
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(
                f"{core.SUPABASE_URL}/rest/v1/rpc/consume_daily_query",
                headers={**core.supabase_headers(access_token), "Prefer": "return=representation"},
                json={"p_limit": limit},
            )
    except httpx.HTTPError:
        logger.exception("usage_consume_error")
        return {"allowed": False, "used": limit, "remaining": 0}
    if response.status_code != 200:
        logger.warning("usage_consume_failed status=%s", response.status_code)
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
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not key or not core.SUPABASE_URL:
        return
    now = datetime.utcnow().isoformat() + "Z"
    async with httpx.AsyncClient(timeout=8) as client:
        tasks = []
        for source_key, (source_name, _) in SOURCE_CONFIG.items():
            count = int(counts.get(source_name, 0))
            if count <= 0:
                continue
            tasks.append(
                client.patch(
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
            )
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            failures = sum(isinstance(result, Exception) for result in results)
            if failures:
                logger.warning("source_metrics_partial_failure failures=%s", failures)


async def collect_selected(hours: int, editoria: str, enabled_sources: list[str]) -> list[dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=25) as client:
        tasks = []
        source_keys = []
        for source_key in enabled_sources:
            config = SOURCE_CONFIG.get(source_key)
            if not config:
                continue
            function = config[1]
            source_keys.append(source_key)
            if source_key in {"jornal_paraiba", "polemica_paraiba"}:
                tasks.append(function(client, hours))
            else:
                tasks.append(function(client))
        results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []
        groups = []
        for source_key, result in zip(source_keys, results):
            if isinstance(result, Exception):
                logger.warning("source_collection_failed source=%s error=%s", source_key, type(result).__name__)
                continue
            groups.append(result)

        candidates, seen = [], set()
        for group in groups:
            for candidate in group:
                url = candidate.get("url")
                if url and url not in seen and collector.candidate_may_match(candidate, editoria):
                    seen.add(url)
                    candidates.append(candidate)
                    if len(candidates) >= 240:
                        break
            if len(candidates) >= 240:
                break

        semaphore = asyncio.Semaphore(10)
        enriched = await asyncio.gather(
            *(collector.enrich_article(client, candidate, hours, semaphore, editoria) for candidate in candidates),
            return_exceptions=True,
        )
    valid = []
    for item in enriched:
        if isinstance(item, Exception):
            logger.debug("article_enrichment_failed error=%s", type(item).__name__)
        elif item:
            valid.append(collector.public_item(item))
    return valid


async def get_or_collect_news(hours: int, editoria: str, enabled_sources: list[str]) -> list[dict]:
    cached = core.get_cached_news(hours, editoria)
    if cached is not None:
        return cached
    signature = tuple(enabled_sources)
    key = (hours, editoria, signature)
    lock = _collection_locks.setdefault(key, asyncio.Lock())
    async with lock:
        cached = core.get_cached_news(hours, editoria)
        if cached is not None:
            return cached
        collected = await collect_selected(hours, editoria, enabled_sources)
        core.set_cached_news(hours, editoria, collected)
        return collected


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
    profile, usage = await asyncio.gather(
        core.get_profile(access_token, user["id"]),
        core.get_daily_usage(access_token, user["id"]),
    )
    subscription = core.normalize_subscription(profile)
    email = str(user.get("email") or "").strip().lower()
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

    email = str(user.get("email") or "").strip().lower()
    unlimited = email in OWNER_UNLIMITED_EMAILS
    limit = int(settings["daily_limit"])
    used_before = await core.get_daily_usage(access_token, user["id"])
    if not unlimited and used_before >= limit:
        return JSONResponse({"detail": "Limite diário atingido.", "used": used_before, "remaining": 0, "limit": limit}, status_code=429)

    enabled_sources = sorted(settings["enabled_sources"])
    signature = tuple(enabled_sources)
    if signature != _last_sources_signature:
        core._news_cache.clear()
        _collection_locks.clear()
        _last_sources_signature = signature
    core.NEWS_CACHE_TTL_SECONDS = int(settings["cache_ttl_seconds"])

    started = time.perf_counter()
    try:
        noticias_coletadas = await get_or_collect_news(horas, editoria, enabled_sources)
        noticias = core.consolidate_and_rank(noticias_coletadas, order=ordenar)
    except Exception:
        logger.exception("radar_execution_failed user_id=%s hours=%s editoria=%s", user.get("id"), horas, editoria)
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

    response = JSONResponse({"noticias": noticias, "ordenacao": ordenar, "usage": usage_payload, "elapsed_ms": elapsed_ms})
    if refreshed:
        core.set_auth_cookies(response, *refreshed)
    return response
