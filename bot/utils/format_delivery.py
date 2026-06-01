import html

from xui.client import ClientDelivery

# Use HTML so VLESS URLs (underscores in flow, etc.) are not truncated by Markdown.
DELIVERY_PARSE_MODE = "HTML"

NO_VLESS = "(کانفیگ VLESS از پنل دریافت نشد)"
NO_SUB_NO_CONFIG = (
    "(لینک ساب دریافت نشد — XUI_SUB_PUBLIC_URL را در .env تنظیم کنید، "
    "مثلاً https://sub.example.com:2096/save/)"
)
NO_SUB_NO_SUBID = "(لینک ساب دریافت نشد — subId کلاینت در پنل یافت نشد)"


def _code(text: str) -> str:
    return f"<code>{html.escape(text)}</code>"


def format_delivery_message(
    email: str,
    delivery: ClientDelivery,
    *,
    created: bool = False,
    sub_public_url_configured: bool = True,
) -> str:
    header = "سرویس با موفقیت ساخته شد." if created else f"لینک‌های سرویس {_code(email)}:"

    if delivery.vless_configs:
        parts: list[str] = []
        for cfg in delivery.vless_configs:
            if cfg.remark:
                parts.append(f"<b>{html.escape(cfg.remark)}</b>")
            parts.append(_code(cfg.link))
        vless_block = "\n\n".join(parts)
    else:
        vless_block = html.escape(NO_VLESS)

    if delivery.subscription_links:
        sub_block = "\n".join(_code(link) for link in delivery.subscription_links)
    elif not sub_public_url_configured:
        sub_block = html.escape(NO_SUB_NO_CONFIG)
    else:
        sub_block = html.escape(NO_SUB_NO_SUBID)

    return (
        f"{header}\n\n"
        f"ایمیل: {_code(email)}\n\n"
        f"کانفیگ VLESS:\n{vless_block}\n\n"
        f"لینک سابسکریپشن:\n{sub_block}"
    )
