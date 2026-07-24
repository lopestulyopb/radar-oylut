from __future__ import annotations

import os

from app.main_v708 import app
from app.production import logger, production_middleware

app.version = "8.2.0"
app.middleware("http")(production_middleware)

required = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY")
missing = [name for name in required if not os.getenv(name, "").strip()]
if missing:
    logger.warning("startup_missing_environment variables=%s", ",".join(missing))
else:
    logger.info("startup_ready version=%s", app.version)
