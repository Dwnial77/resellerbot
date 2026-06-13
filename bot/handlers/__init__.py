from aiogram import Router

from bot.handlers import (
    admin,
    admin_broadcast,
    admin_panels,
    admin_reports,
    admin_reseller_panels,
    admin_resellers,
    admin_set_panel,
    admin_templates,
    admin_update,
    reseller,
    start,
)


def setup_routers() -> Router:
    root = Router()
    root.include_router(start.router)
    root.include_router(admin.router)
    root.include_router(admin_broadcast.router)
    root.include_router(admin_reports.router)
    root.include_router(admin_resellers.router)
    root.include_router(admin_reseller_panels.router)
    root.include_router(admin_set_panel.router)
    root.include_router(admin_panels.router)
    root.include_router(admin_templates.router)
    root.include_router(admin_update.router)
    root.include_router(reseller.router)
    return root
