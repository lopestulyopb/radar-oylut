from __future__ import annotations

import json
import time
from datetime import datetime

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.admin import (
    SUPABASE_SERVICE_KEY,
    SUPABASE_URL,
    admin_context,
    apply_refresh,
    db_get,
    db_patch,
    require_admin,
    templates,
)

router = APIRouter()

SOURCE_LABELS = {
    "clickpb": "ClickPB",
    "jornal_paraiba": "Jornal da Paraíba",
    "maispb": "MaisPB",
    "polemica_paraiba": "Polêmica Paraíba",
}


def _service_headers(prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


async def _upsert(table: str, payload: dict, conflict: str) -> bool:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_service_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": conflict},
            json=payload,
        )
    return response.status_code in (200, 201, 204)


def _setting_value(rows: list[dict], key: str, default):
    for row in rows:
        if row.get("setting_key") == key:
            return row.get("setting_value", default)
    return default


@router.get("/admin/fontes", response_class=HTMLResponse)
async def admin_sources(request: Request):
    user, refreshed, denied = await require_admin(request)
    if denied:
        return denied
    sources = await db_get("source_monitor", {"select": "*", "order": "source_name.asc"})
    response = templates.TemplateResponse(
        request=request,
        name="admin/sources.html",
        context=admin_context("sources", user, sources=sources),
    )
    return apply_refresh(response, refreshed)


@router.post("/admin/fontes/testar")
async def test_sources(request: Request):
    _, _, denied = await require_admin(request)
    if denied:
        return denied

    sources = await db_get("source_monitor", {"select": "source_key,source_name,source_url,enabled"})
    async with httpx.AsyncClient(
        timeout=15,
        follow_redirects=True,
        headers={"User-Agent": "Radar Oylut/7.0.8"},
    ) as client:
        for source in sources:
            if not source.get("enabled", True):
                continue
            started = time.perf_counter()
            status = "offline"
            try:
                response = await client.get(source["source_url"])
                elapsed = int((time.perf_counter() - started) * 1000)
                if 200 <= response.status_code < 400:
                    status = "online" if elapsed < 5000 else "instavel"
                elif response.status_code < 500:
                    status = "instavel"
            except httpx.HTTPError:
                elapsed = int((time.perf_counter() - started) * 1000)
            await db_patch(
                "source_monitor",
                {"source_key": f"eq.{source['source_key']}"},
                {
                    "status": status,
                    "last_checked_at": datetime.utcnow().isoformat() + "Z",
                    "average_response_ms": elapsed,
                },
            )
    return RedirectResponse("/admin/fontes", status_code=303)


@router.post("/admin/fontes/{source_key}/alternar")
async def toggle_source(request: Request, source_key: str, enabled: str = Form(...)):
    _, _, denied = await require_admin(request)
    if denied:
        return denied
    new_enabled = enabled.lower() == "true"
    await db_patch("source_monitor", {"source_key": f"eq.{source_key}"}, {"enabled": new_enabled})

    sources = await db_get("source_monitor", {"select": "source_key,enabled"})
    enabled_sources = [row["source_key"] for row in sources if row.get("enabled")]
    await _upsert(
        "app_settings",
        {
            "setting_key": "enabled_sources",
            "setting_value": enabled_sources,
            "description": "Fontes habilitadas na coleta",
        },
        "setting_key",
    )
    return RedirectResponse("/admin/fontes", status_code=303)


@router.get("/admin/configuracoes", response_class=HTMLResponse)
async def admin_settings(request: Request):
    user, refreshed, denied = await require_admin(request)
    if denied:
        return denied
    rows = await db_get("app_settings", {"select": "*", "order": "setting_key.asc"})
    settings = {
        "daily_limit": int(_setting_value(rows, "daily_limit", 18)),
        "cache_ttl_seconds": int(_setting_value(rows, "cache_ttl_seconds", 180)),
        "default_order": str(_setting_value(rows, "default_order", "editor_chefe")),
        "app_version": str(_setting_value(rows, "app_version", "7.0.8")),
    }
    response = templates.TemplateResponse(
        request=request,
        name="admin/settings.html",
        context=admin_context("settings", user, settings=settings),
    )
    return apply_refresh(response, refreshed)


@router.post("/admin/configuracoes")
async def save_settings(
    request: Request,
    daily_limit: int = Form(...),
    cache_ttl_seconds: int = Form(...),
    default_order: str = Form(...),
    app_version: str = Form(...),
):
    _, _, denied = await require_admin(request)
    if denied:
        return denied

    daily_limit = max(1, min(daily_limit, 1000))
    cache_ttl_seconds = max(0, min(cache_ttl_seconds, 86400))
    if default_order not in {"editor_chefe", "recentes"}:
        default_order = "editor_chefe"
    app_version = app_version.strip() or "7.0.8"

    payloads = [
        ("daily_limit", daily_limit, "Limite diário padrão de pesquisas por usuário"),
        ("cache_ttl_seconds", cache_ttl_seconds, "Tempo do cache de notícias em segundos"),
        ("default_order", default_order, "Ordenação padrão do Radar"),
        ("app_version", app_version, "Versão exibida no painel"),
    ]
    for key, value, description in payloads:
        await _upsert(
            "app_settings",
            {"setting_key": key, "setting_value": value, "description": description},
            "setting_key",
        )
    return RedirectResponse("/admin/configuracoes?salvo=1", status_code=303)
