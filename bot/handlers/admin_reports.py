"""Admin reseller usage reports (allocation from DB)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.handlers.admin import _is_admin
from bot.keyboards import labels as btn
from bot.keyboards.common import reseller_report_hub_kb, reseller_report_view_kb
from bot.texts import fa as t
from bot.utils.report_format import (
    format_hub_summary_line,
    format_progress_bar_line,
    format_used_percent,
    usage_percent_int,
)
from db.models import Reseller
from db.repository import PanelRepository, ResellerRepository
from db.session import get_session_factory
from services.quota import QuotaService, QuotaStatus, format_max_clients_admin
from services.reseller_labels import reseller_label

router = Router()


async def _panel_names_for_resellers(session, resellers: list) -> dict[int, str]:
    panel_repo = PanelRepository(session)
    names: dict[int, str] = {}
    for r in resellers:
        if r.panel_id not in names:
            p = await panel_repo.get(r.panel_id)
            names[r.panel_id] = p.name if p else f"#{r.panel_id}"
    return names


async def _load_reseller_stats(
    session, resellers: list[Reseller]
) -> dict[int, QuotaStatus]:
    repo = ResellerRepository(session)
    quota = QuotaService(repo)
    stats: dict[int, QuotaStatus] = {}
    for r in resellers[:20]:
        stats[r.telegram_id] = await quota.status(r)
    return stats


async def _report_hub_content() -> tuple[str, object]:
    async with get_session_factory()() as session:
        rows = await ResellerRepository(session).list_all()
        panel_names = await _panel_names_for_resellers(session, rows)
        stats = await _load_reseller_stats(session, rows)

    if not rows:
        return t.REPORT_HUB_EMPTY, reseller_report_hub_kb([], {}, {})

    lines = [t.REPORT_HUB_HEADER]
    for r in rows[:20]:
        name = r.display_name or str(r.telegram_id)
        p_name = panel_names.get(r.panel_id, f"#{r.panel_id}")
        st = stats.get(r.telegram_id)
        client_count = st.client_count if st is not None else 0
        percent = (
            usage_percent_int(st.used_bytes, st.quota_bytes)
            if st is not None
            else None
        )
        lines.append(
            format_hub_summary_line(
                name,
                p_name,
                is_active=r.is_active,
                client_count=client_count,
                percent=percent,
            )
        )
    if len(rows) > 20:
        lines.append(f"… و {len(rows) - 20} ریسلر دیگر")
    lines.append("")
    lines.append(t.REPORT_HUB_HINT)
    return "\n".join(lines), reseller_report_hub_kb(rows, panel_names, stats)


async def _reseller_report_content(telegram_id: int) -> str | None:
    async with get_session_factory()() as session:
        repo = ResellerRepository(session)
        reseller = await repo.get(telegram_id)
        if not reseller:
            return None
        panel = await PanelRepository(session).get(reseller.panel_id)
        panel_name = panel.name if panel else f"#{reseller.panel_id}"
        st = await QuotaService(repo).status(reseller)

    percent = usage_percent_int(st.used_bytes, st.quota_bytes)
    return t.RESELLER_REPORT.format(
        label=reseller_label(reseller),
        status="فعال" if reseller.is_active else "غیرفعال",
        panel_name=panel_name,
        panel_id=reseller.panel_id,
        client_count=st.client_count,
        max_clients_line=format_max_clients_admin(st),
        quota_gb=st.quota_gb,
        active_gb=st.active_gb,
        lifetime_gb=st.lifetime_gb,
        used_percent=format_used_percent(st.lifetime_bytes, st.quota_bytes),
        progress_bar=format_progress_bar_line(percent),
        remaining_gb=st.remaining_gb,
    )


async def _edit_reseller_report(
    callback: CallbackQuery, telegram_id: int, *, refreshed: bool = False
) -> None:
    if not callback.message:
        await callback.answer()
        return
    text = await _reseller_report_content(telegram_id)
    if text is None:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await callback.message.edit_text(
        text,
        reply_markup=reseller_report_view_kb(telegram_id),
    )
    if refreshed:
        await callback.answer(t.REPORT_UPDATED)
    else:
        await callback.answer()


@router.message(F.text == btn.REPORTS)
@router.message(Command("reports"))
async def reports_menu(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    text, markup = await _report_hub_content()
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("rpt:view:"))
async def report_view(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data:
        await callback.answer()
        return
    try:
        telegram_id = int(callback.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await _edit_reseller_report(callback, telegram_id)


@router.callback_query(F.data.startswith("rpt:refresh:"))
async def report_refresh(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data:
        await callback.answer()
        return
    try:
        telegram_id = int(callback.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await _edit_reseller_report(callback, telegram_id, refreshed=True)


@router.callback_query(F.data == "rpt:back")
async def report_back(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.message:
        await callback.answer()
        return
    text, markup = await _report_hub_content()
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()
