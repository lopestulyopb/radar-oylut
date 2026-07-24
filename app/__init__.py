"""Inicialização do aplicativo Radar Oylut."""

from app import editorial as _editorial
from app.editorial_overrides import apply as _apply_editorial_overrides

_apply_editorial_overrides(_editorial)
