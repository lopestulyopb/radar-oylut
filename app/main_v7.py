from app.main import app
from app.admin import router as admin_router

app.include_router(admin_router)
