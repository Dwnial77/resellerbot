from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.keyboards import labels as L
from bot.utils.report_format import format_report_button_label, usage_percent_int
from db.models import Panel, Reseller, ServiceTemplate
from xui.client import VlessConfig

_TELEGRAM_CALLBACK_MAX = 64


def reseller_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=L.CREATE_SERVICE),
                KeyboardButton(text=L.MY_SERVICES),
            ],
            [KeyboardButton(text=L.ACCOUNT_STATUS)],
        ],
        resize_keyboard=True,
    )


def admin_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=L.LIST_RESELLERS),
                KeyboardButton(text=L.REPORTS),
            ],
            [
                KeyboardButton(text=L.SERVICE_TEMPLATES),
                KeyboardButton(text=L.PANELS),
            ],
            [
                KeyboardButton(text=L.SET_PANEL_RESELLER),
                KeyboardButton(text=L.BOT_UPDATE),
            ],
            [
                KeyboardButton(text=L.ADMIN_HELP),
            ],
        ],
        resize_keyboard=True,
    )


def bot_update_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ اعمال و ری‌استارت",
                    callback_data="upd:apply",
                ),
                InlineKeyboardButton(
                    text=L.CANCEL,
                    callback_data="upd:cancel",
                ),
            ],
        ]
    )


def panel_admin_hub_kb(panels: list[Panel]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in panels:
        label = L.panel_hub_row_label(p.id, p.name, is_active=p.is_active)
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"pnl:view:{p.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=L.ADD_PANEL, callback_data="pnl:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def panel_view_kb(panel_id: int, *, is_active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.active_toggle_label(is_active=is_active),
                    callback_data=f"pnl:toggle:{panel_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.LIST_INBOUNDS,
                    callback_data=f"pnl:inbounds:{panel_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.DELETE_PANEL,
                    callback_data=f"pnl:del:{panel_id}",
                ),
            ],
            [InlineKeyboardButton(text=L.BACK, callback_data="pnl:hub")],
        ]
    )


def panel_delete_confirm_kb(panel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.YES_DELETE,
                    callback_data=f"pnl:del_yes:{panel_id}",
                ),
                InlineKeyboardButton(
                    text=L.NO, callback_data=f"pnl:view:{panel_id}"
                ),
            ],
        ]
    )


def panel_wizard_skip_sub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.SKIP_PUBLIC_SUB, callback_data="pnl:wiz_skip_sub"
                )
            ],
            [InlineKeyboardButton(text=L.CANCEL, callback_data="pnl:wiz_cancel")],
        ]
    )


def panel_wizard_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.REGISTER_PANEL, callback_data="pnl:wiz_save"
                ),
                InlineKeyboardButton(text=L.CANCEL, callback_data="pnl:wiz_cancel"),
            ],
        ]
    )


def set_panel_reseller_kb(
    resellers: list[Reseller], panel_names: dict[int, str]
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for r in resellers[:20]:
        name = r.display_name or str(r.telegram_id)
        p_name = panel_names.get(r.panel_id, f"#{r.panel_id}")
        label = f"{name} — پنل {p_name}"
        if len(label) > 40:
            label = label[:37] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"rpnl:res:{r.telegram_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=L.CANCEL, callback_data="rpnl:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def set_panel_pick_panel_kb(panels: list[Panel]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in panels:
        label = f"#{p.id} {p.name}"
        if len(label) > 35:
            label = label[:32] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"rpnl:pan:{p.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=L.CANCEL, callback_data="rpnl:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def set_panel_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=L.CONFIRM, callback_data="rpnl:save"),
                InlineKeyboardButton(text=L.CANCEL, callback_data="rpnl:cancel"),
            ],
        ]
    )


def reseller_admin_hub_kb(
    resellers: list[Reseller], panel_names: dict[int, str]
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for r in resellers[:20]:
        name = r.display_name or str(r.telegram_id)
        p_name = panel_names.get(r.panel_id, f"#{r.panel_id}")
        label = L.reseller_hub_row_label(name, p_name, is_active=r.is_active)
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"rsl:view:{r.telegram_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=L.ADD_RESELLER, callback_data="rsl:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_report_hub_kb(
    resellers: list[Reseller],
    panel_names: dict[int, str],
    stats: dict[int, object],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for r in resellers[:20]:
        name = r.display_name or str(r.telegram_id)
        st = stats.get(r.telegram_id)
        client_count = st.client_count if st is not None else 0
        percent = (
            usage_percent_int(st.used_bytes, st.quota_bytes)
            if st is not None
            else None
        )
        label = format_report_button_label(
            name,
            is_active=r.is_active,
            client_count=client_count,
            percent=percent,
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"rpt:view:{r.telegram_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_report_view_kb(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.REFRESH,
                    callback_data=f"rpt:refresh:{telegram_id}",
                ),
                InlineKeyboardButton(
                    text=L.BACK,
                    callback_data="rpt:back",
                ),
            ],
        ]
    )


def reseller_view_kb(
    telegram_id: int, *, is_active: bool, can_change_panel: bool
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=L.active_toggle_label(is_active=is_active),
                callback_data=f"rsl:toggle:{telegram_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=L.EDIT_RESELLER,
                callback_data=f"rsl:edit:{telegram_id}",
            ),
        ],
    ]
    if can_change_panel:
        rows.append(
            [
                InlineKeyboardButton(
                    text=L.CHANGE_PANEL,
                    callback_data=f"rsl:set_panel:{telegram_id}",
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=L.DELETE_RESELLER,
                callback_data=f"rsl:del:{telegram_id}",
            ),
        ],
    )
    rows.append([InlineKeyboardButton(text=L.BACK, callback_data="rsl:hub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_delete_confirm_kb(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.YES_DELETE_FULL,
                    callback_data=f"rsl:del_yes:{telegram_id}",
                ),
                InlineKeyboardButton(
                    text=L.NO, callback_data=f"rsl:view:{telegram_id}"
                ),
            ],
        ]
    )


def reseller_wizard_name_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.NO_DISPLAY_NAME, callback_data="rsl:name_skip"
                )
            ],
            [InlineKeyboardButton(text=L.CANCEL, callback_data="rsl:wiz_cancel")],
        ]
    )


def reseller_wizard_pick_panel_kb(panels: list[Panel]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in panels:
        label = f"#{p.id} {p.name}"
        if len(label) > 35:
            label = label[:32] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"rsl:pan:{p.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=L.CANCEL, callback_data="rsl:wiz_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_wizard_quota_kb() -> InlineKeyboardMarkup:
    volumes = (5, 10, 20, 50, 100)
    row = [
        InlineKeyboardButton(text=f"{v} GB", callback_data=f"rsl:quota:{v}")
        for v in volumes
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [InlineKeyboardButton(text=L.CANCEL, callback_data="rsl:wiz_cancel")],
        ]
    )


def _inbound_toggle_rows(
    inbounds: list[dict],
    selected: set[int],
    *,
    toggle_prefix: str,
    done_callback: str,
    cancel_callback: str,
    done_label: str = L.CONTINUE,
) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    for ib in inbounds[:25]:
        ib_id = int(ib.get("id", ib.get("inboundId", ib.get("inbound_id", 0))))
        if not ib_id:
            continue
        mark = "✓ " if ib_id in selected else ""
        protocol = ib.get("protocol", "")
        port = ib.get("port", "")
        label = f"{mark}#{ib_id} {protocol}:{port}".strip()
        if len(label) > 40:
            label = label[:37] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=label or f"{mark}#{ib_id}",
                    callback_data=f"{toggle_prefix}{ib_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text=done_label, callback_data=done_callback),
            InlineKeyboardButton(text=L.CANCEL, callback_data=cancel_callback),
        ]
    )
    return rows


def reseller_wizard_inbounds_kb(
    inbounds: list[dict], selected: set[int]
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=_inbound_toggle_rows(
            inbounds,
            selected,
            toggle_prefix="rsl:ib:t:",
            done_callback="rsl:ib:done",
            cancel_callback="rsl:wiz_cancel",
            done_label=L.CONTINUE,
        )
    )


def reseller_edit_menu_kb(telegram_id: int) -> InlineKeyboardMarkup:
    tid = telegram_id
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.EDIT_QUOTA,
                    callback_data=f"rsl:ev:quota:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_ADD_QUOTA,
                    callback_data=f"rsl:ev:addq:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.RESET_QUOTA_USAGE,
                    callback_data=f"rsl:ev:resetu:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_MAX_CLIENTS,
                    callback_data=f"rsl:ev:maxc:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_DISPLAY_NAME,
                    callback_data=f"rsl:ev:name:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_ALLOWED_INBOUNDS,
                    callback_data=f"rsl:ev:allow:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_ATTACH_INBOUNDS,
                    callback_data=f"rsl:ev:attach:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.BACK, callback_data=f"rsl:view:{tid}"
                ),
            ],
        ]
    )


def reseller_edit_quota_kb(telegram_id: int) -> InlineKeyboardMarkup:
    volumes = (5, 10, 20, 50, 100)
    row = [
        InlineKeyboardButton(
            text=f"{v} GB", callback_data=f"rsl:eq:{v}:{telegram_id}"
        )
        for v in volumes
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [
                InlineKeyboardButton(
                    text=L.CANCEL,
                    callback_data=f"rsl:edit_cancel:{telegram_id}",
                ),
            ],
        ]
    )


def reseller_edit_add_quota_kb(telegram_id: int) -> InlineKeyboardMarkup:
    volumes = (5, 10, 20, 50, 100, 500)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for v in volumes:
        row.append(
            InlineKeyboardButton(
                text=f"+{v} GB", callback_data=f"rsl:eaq:{v}:{telegram_id}"
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(
                text=L.CANCEL,
                callback_data=f"rsl:edit_cancel:{telegram_id}",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_reset_quota_confirm_kb(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.YES_RESET,
                    callback_data=f"rsl:resetu:yes:{telegram_id}",
                ),
                InlineKeyboardButton(
                    text=L.NO,
                    callback_data=f"rsl:resetu:no:{telegram_id}",
                ),
            ],
        ]
    )


def reseller_edit_max_clients_kb(telegram_id: int) -> InlineKeyboardMarkup:
    counts = (1, 5, 10, 20, 50)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for n in counts:
        row.append(
            InlineKeyboardButton(
                text=str(n), callback_data=f"rsl:emc:set:{n}:{telegram_id}"
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(
                text=L.UNLIMITED_MAX_CLIENTS,
                callback_data=f"rsl:emc:clear:{telegram_id}",
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=L.CANCEL,
                callback_data=f"rsl:edit_cancel:{telegram_id}",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_edit_inbounds_kb(
    inbounds: list[dict], selected: set[int], telegram_id: int
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=_inbound_toggle_rows(
            inbounds,
            selected,
            toggle_prefix="rsl:eib:t:",
            done_callback="rsl:eib:done",
            cancel_callback=f"rsl:edit_cancel:{telegram_id}",
            done_label=L.SAVE,
        )
    )


def reseller_edit_attach_inbounds_kb(
    inbound_ids: list[int], selected: set[int], telegram_id: int
) -> InlineKeyboardMarkup:
    inbounds = [{"id": i, "protocol": "", "port": ""} for i in inbound_ids]
    return reseller_edit_inbounds_kb(inbounds, selected, telegram_id)


def reseller_wizard_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.REGISTER_RESELLER, callback_data="rsl:wiz_save"
                ),
                InlineKeyboardButton(text=L.CANCEL, callback_data="rsl:wiz_cancel"),
            ],
        ]
    )


def template_admin_hub_kb(templates: list[ServiceTemplate]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for tpl in templates:
        label = tpl.name if len(tpl.name) <= 28 else tpl.name[:25] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 {label}",
                    callback_data=f"atpl:del:{tpl.id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=L.ADD_TEMPLATE, callback_data="atpl:add")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def template_delete_confirm_kb(template_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.YES_DELETE_TEMPLATE,
                    callback_data=f"atpl:del_yes:{template_id}",
                ),
                InlineKeyboardButton(text=L.NO, callback_data="atpl:hub"),
            ],
        ]
    )


def template_wizard_volume_kb() -> InlineKeyboardMarkup:
    volumes = (5, 10, 20, 50, 100)
    row = [
        InlineKeyboardButton(text=f"{v} GB", callback_data=f"atpl:vol:{v}")
        for v in volumes
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [InlineKeyboardButton(text=L.CANCEL, callback_data="atpl:wiz_cancel")],
        ]
    )


def template_wizard_expiry_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="7 روز", callback_data="atpl:exp:7"),
                InlineKeyboardButton(text="30 روز", callback_data="atpl:exp:30"),
                InlineKeyboardButton(text="90 روز", callback_data="atpl:exp:90"),
            ],
            [
                InlineKeyboardButton(text="180 روز", callback_data="atpl:exp:180"),
                InlineKeyboardButton(text="365 روز", callback_data="atpl:exp:365"),
            ],
            [InlineKeyboardButton(text=L.UNLIMITED_EXPIRY, callback_data="atpl:exp:0")],
            [InlineKeyboardButton(text=L.CANCEL, callback_data="atpl:wiz_cancel")],
        ]
    )


def template_wizard_name_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.USE_SUGGESTED_NAME,
                    callback_data="atpl:use_suggested_name",
                )
            ],
            [InlineKeyboardButton(text=L.CANCEL, callback_data="atpl:wiz_cancel")],
        ]
    )


def template_wizard_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.REGISTER_TEMPLATE, callback_data="atpl:wiz_save"
                ),
                InlineKeyboardButton(text=L.CANCEL, callback_data="atpl:wiz_cancel"),
            ],
        ]
    )


def create_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=L.CANCEL, callback_data="create:cancel")],
        ]
    )


def template_picker_kb(templates: list[ServiceTemplate]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=tpl.name, callback_data=f"tpl:{tpl.id}")]
        for tpl in templates
    ]
    rows.append(
        [InlineKeyboardButton(text=L.MANUAL_ENTRY, callback_data="create:manual")]
    )
    rows.append(
        [InlineKeyboardButton(text=L.CANCEL, callback_data="create:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def client_name_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.RANDOM_NAME, callback_data="create:auto_name"
                )
            ],
            [
                InlineKeyboardButton(
                    text=L.CANCEL, callback_data="create:cancel"
                )
            ],
        ]
    )


def confirm_create_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=L.CONFIRM, callback_data="create:confirm"),
                InlineKeyboardButton(text=L.CANCEL, callback_data="create:cancel"),
            ]
        ]
    )


def service_list_kb(emails: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for email in emails[:20]:
        short = email if len(email) <= 28 else email[:25] + "..."
        rows.append(
            [InlineKeyboardButton(text=short, callback_data=f"svc:{email}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def expiry_mode_kb(email: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.ADD_DAYS, callback_data=f"exp_add:{email}"
                ),
                InlineKeyboardButton(
                    text=L.NEW_DATE, callback_data=f"exp_date:{email}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.UNLIMITED_EXPIRY, callback_data=f"exp_unlim:{email}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.CANCEL, callback_data=f"exp_cancel:{email}"
                ),
            ],
        ]
    )


def delete_confirm_kb(email: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.YES_DELETE_SERVICE,
                    callback_data=f"del_confirm:{email}",
                ),
                InlineKeyboardButton(
                    text=L.NO, callback_data=f"del_cancel:{email}"
                ),
            ],
        ]
    )


def reset_traffic_confirm_kb(email: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.YES_RESET,
                    callback_data=f"edit_reset_ok:{email}",
                ),
                InlineKeyboardButton(
                    text=L.NO, callback_data=f"edit_reset_no:{email}"
                ),
            ],
        ]
    )


def service_edit_kb(email: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.RESET_TRAFFIC, callback_data=f"edit_reset:{email}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_LIMIT_IP, callback_data=f"edit_limit:{email}"
                ),
                InlineKeyboardButton(
                    text=L.EDIT_COMMENT, callback_data=f"edit_comment:{email}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.BACK, callback_data=f"edit_back:{email}"
                )
            ],
        ]
    )


def _qr_button_label(cfg: VlessConfig, index: int) -> str:
    if cfg.remark:
        label = cfg.remark
        if len(label) > 24:
            label = label[:21] + "..."
        return f"📲 QR {label}"
    return f"📲 QR {index + 1}"


def _qr_callback_data(email: str, index: int) -> str:
    data = f"qr:{email}:{index}"
    if len(data) > _TELEGRAM_CALLBACK_MAX:
        raise ValueError("callback_data too long for QR button")
    return data


def vless_qr_kb(email: str, configs: list[VlessConfig]) -> InlineKeyboardMarkup:
    rows = []
    for i, cfg in enumerate(configs):
        try:
            cb = _qr_callback_data(email, i)
        except ValueError:
            continue
        rows.append(
            [InlineKeyboardButton(text=_qr_button_label(cfg, i), callback_data=cb)]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_detail_kb(email: str, *, enabled: bool = True) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=L.LINK, callback_data=f"link:{email}"),
                InlineKeyboardButton(
                    text=L.TRAFFIC, callback_data=f"traffic:{email}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.QR_CONFIG, callback_data=f"qr_menu:{email}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.CHANGE_EXPIRY, callback_data=f"exp:{email}"
                ),
                InlineKeyboardButton(
                    text=L.EDIT_SERVICE, callback_data=f"edit:{email}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.active_toggle_label(is_active=enabled),
                    callback_data=f"disable:{email}" if enabled else f"enable:{email}",
                )
            ],
            [InlineKeyboardButton(text=L.DELETE, callback_data=f"del:{email}")],
            [InlineKeyboardButton(text=L.BACK, callback_data="svc:back")],
        ]
    )
