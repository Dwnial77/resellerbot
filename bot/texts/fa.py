WELCOME_RESELLER = (
    "سلام{display_name}!\n\n"
    "پنل: {panel_name} (#{panel_id})\n"
    "سقف حجم: {quota_gb} GB\n"
    "تخصیص فعال: {active_gb} GB\n"
    "مصرف سهمیه: {lifetime_gb} GB\n"
    "باقی‌مانده: {remaining_gb} GB\n"
    "تعداد سرویس: {client_count}\n"
    "سقف تعداد سرویس: {max_clients_line}\n"
    "{inbounds_summary}"
)

NOT_RESELLER = "شما به‌عنوان ریسلر ثبت نشده‌اید. با ادمین تماس بگیرید."

ADMIN_MENU = (
    "پنل ادمین\n\n"
    "برای دیدن همه دستورات، در چت `/` را بزنید.\n\n"
    "افزودن ریسلر (یک پیام):\n"
    "`5266810479 ali 1 100 1` — آیدی، نام، شماره پنل، سقف GB، اینباند\n"
    "بدون نام: `123456789 1 100 1` — آیدی، پنل، سقف، اینباند\n"
    "فرمت قدیم (پنل 1): `123456789 100 1`\n\n"
    "نمونه دستورات:\n"
    "`/panels` — مدیریت پنل‌های 3x-ui\n"
    "`/list_inbounds 1` — اینباند پنل شماره 1\n"
    "`/set_panel 123456789 2` — تغییر پنل ریسلر (بدون سرویس)\n"
    "`/set_quota 123456789 200`\n"
    "`/subtract_quota 123456789 50` — کاهش سقف\n"
    "`/templates` — قالب‌های ساخت سرویس"
)

BROADCAST_PROMPT = (
    "متن پیام همگانی را بنویسید.\n"
    "این پیام به همه ریسلرهای فعال ارسال می‌شود."
)
BROADCAST_EMPTY = "متن پیام نمی‌تواند خالی باشد."
BROADCAST_TOO_LONG = "متن پیام بیش از حد مجاز تلگرام (4096 کاراکتر) است."
BROADCAST_NO_RECIPIENTS = "هیچ ریسلر فعالی برای ارسال پیام یافت نشد."
BROADCAST_CONFIRM = (
    "تأیید پیام همگانی\n"
    "مخاطبان: {count} ریسلر فعال\n\n"
    "متن:\n{preview}\n\n"
    "ادامه می‌دهید؟"
)
BROADCAST_DONE = (
    "پیام همگانی ارسال شد.\n"
    "موفق: {sent}\n"
    "ناموفق: {failed}\n"
    "مسدود/بدون دسترسی: {blocked}"
)
BROADCAST_CANCELLED = "ارسال پیام همگانی لغو شد."

RESELLER_ADDED = (
    "ریسلر {label} با سقف {quota_gb} GB ثبت شد.\n"
    "پنل: {panel_name} (#{panel_id})\n"
    "مجاز: {allowed_inbounds}\n"
    "متصل هنگام ساخت: {attach_inbounds}"
)

NO_PANEL_ACCESS = (
    "پنل اختصاصی شما در دسترس نیست. با ادمین تماس بگیرید."
)
RESELLER_PANEL_INACTIVE = (
    "پنل {panel_name} (#{panel_id}) غیرفعال است. با ادمین تماس بگیرید."
)
RESELLER_PANEL_MISSING = "پنل #{panel_id} ثبت نشده است. با ادمین تماس بگیرید."
RESELLER_PANEL_NOT_ASSIGNED = (
    "پنل #{panel_id} به حساب شما اختصاص داده نشده. با ادمین تماس بگیرید."
)
RESELLER_PANEL_ASSIGNMENT_INACTIVE = (
    "تخصیص پنل {panel_name} (#{panel_id}) غیرفعال است. با ادمین تماس بگیرید."
)
RESELLER_PANEL_NOT_LOADED = (
    "اتصال به پنل {panel_name} (#{panel_id}) برقرار نیست. "
    "با ادمین تماس بگیرید یا چند لحظه بعد دوباره تلاش کنید."
)
PANEL_INACTIVE_FOR_RESELLER = (
    "پنل {panel_name} (#{panel_id}) غیرفعال است. ابتدا پنل را فعال کنید."
)
SERVICE_NOT_FOUND = "سرویس یافت نشد."
SERVICE_PANEL_UNAVAILABLE = (
    "پنل سرویس (#{panel_id}) در دسترس نیست (غیرفعال یا قطع). با ادمین تماس بگیرید."
)
NO_ACCESSIBLE_SERVICES = (
    "سرویس فعالی روی پنل‌های در دسترس ندارید. با ادمین تماس بگیرید."
)
SERVICE_LIST_HEADER = "سرویس‌های شما ({start}–{end} از {total}):"

PANEL_LIST_HEADER = "پنل‌های 3x-ui:"
PANEL_LIST_EMPTY = "پنلی ثبت نشده است."
PANEL_HUB_HINT = "برای افزودن پنل، «افزودن پنل» را بزنید."
PANEL_NOT_FOUND = "پنل یافت نشد."
PANEL_ADDED = "پنل #{id} ثبت شد: {name}\n{base_url}"
PANEL_DELETED = "پنل #{id} حذف شد."
PANEL_DELETE_CONFIRM = "حذف پنل #{id} ({name})؟"
PANEL_WIZARD_NAME = "نام پنل را وارد کنید (مثلاً پنل اروپا):"
PANEL_WIZARD_URL = (
    "آدرس پنل را وارد کنید:\n"
    "• https://host:2053 یا http://host:2053\n"
    "• یا فقط host:2053 (پیش‌فرض https)"
)
PANEL_WIZARD_TOKEN = "توکن API پنل را وارد کنید:"
PANEL_WIZARD_SUB = (
    "آدرس پایه ساب عمومی را وارد کنید:\n"
    "• https://sub.example.com:2096/save یا http://...\n"
    "• یا فقط host:2096/save (پیش‌فرض https)\n"
    "یا «بدون آدرس ساب عمومی» را بزنید."
)
PANEL_WIZARD_CONFIRM = (
    "تأیید ثبت پنل:\n"
    "نام: {name}\n"
    "آدرس: {base_url}\n"
    "ساب: {sub_public_url}\n\n"
    "پس از تأیید اتصال تست می‌شود."
)
PANEL_WIZARD_CANCELLED = "افزودن پنل لغو شد."
PANEL_EDIT_MENU = "ویرایش پنل #{id} ({name}):"
PANEL_EDIT_NAME_PROMPT = "نام جدید پنل #{id} ({name}):"
PANEL_EDIT_URL_PROMPT = (
    "آدرس جدید پنل #{id}:\n"
    "• https://host:2053 یا http://host:2053\n"
    "• یا فقط host:2053 (پیش‌فرض https)"
)
PANEL_EDIT_TOKEN_PROMPT = "توکن API جدید پنل #{id} ({name}):"
PANEL_EDIT_SUB_PROMPT = (
    "آدرس پایه ساب عمومی پنل #{id}:\n"
    "یا «بدون آدرس ساب عمومی» را بزنید."
)
PANEL_NAME_UPDATED = "نام پنل #{id} به‌روز شد: {name}"
PANEL_URL_UPDATED = "آدرس پنل #{id} ({name}) به‌روز شد:\n{base_url}"
PANEL_TOKEN_UPDATED = "توکن API پنل #{id} ({name}) به‌روز شد."
PANEL_SUB_UPDATED = "ساب عمومی پنل #{id} ({name}): {sub_public_url}"
PANEL_AUTH_FAILED = "اتصال به پنل ناموفق بود:\n{error}"
PANEL_SET_FOR_RESELLER = (
    "پنل ریسلر {label} به {panel_name} (#{panel_id}) تغییر کرد."
)
PANEL_SET_UNCHANGED = "پنل ریسلر {label} از قبل روی {panel_name} (#{panel_id}) است."
PANEL_SET_NOT_ASSIGNED = (
    "پنل #{panel_id} به این ریسلر اختصاص داده نشده. "
    "ابتدا از «مدیریت پنل‌ها» تخصیص دهید."
)
PANEL_SET_BLOCKED_HAS_CLIENTS = (
    "ریسلر {label} الان {client_count} سرویس دارد.\n"
    "برای تغییر پنل ابتدا همه سرویس‌ها را حذف کنید."
)
PANEL_SET_WIZARD_PICK_RESELLER = "ریسلری را برای تغییر پنل انتخاب کنید:"
PANEL_SET_WIZARD_PICK_PANEL = (
    "ریسلر: {label}\n"
    "پنل فعلی: {current_panel_name} (#{current_panel_id})\n"
    "سرویس: {client_count}\n\n"
    "پنل جدید را انتخاب کنید:"
)
PANEL_SET_WIZARD_CONFIRM = (
    "تأیید تغییر پنل:\n"
    "ریسلر: {label}\n"
    "از: {old_panel_name} (#{old_panel_id})\n"
    "به: {new_panel_name} (#{new_panel_id})\n\n"
    "ادامه می‌دهید؟"
)
PANEL_SET_WIZARD_CANCELLED = "تغییر پنل لغو شد."
PANEL_SET_NO_RESELLERS = "ریسلری ثبت نشده است."
PANEL_SET_NO_PANELS = "پنل فعالی برای انتخاب وجود ندارد."
ALLOWED_INBOUNDS_UPDATED = (
    "اینباندهای مجاز ریسلر {label} به {allowed_inbounds} تغییر کرد.\n"
    "متصل هنگام ساخت: {attach_inbounds}{warning}"
)
ATTACH_INBOUNDS_UPDATED = (
    "اینباندهای متصل ریسلر {label} به {attach_inbounds} تنظیم شد."
)
QUOTA_UPDATED = "سقف ریسلر {label} به {quota_gb} GB تغییر کرد."
QUOTA_ADDED = (
    "به سقف ریسلر {label}، {add_gb} GB افزوده شد.\n"
    "سقف جدید: {quota_gb} GB"
)
QUOTA_SUBTRACTED = (
    "از سقف ریسلر {label}، {subtract_gb} GB کم شد.\n"
    "سقف جدید: {quota_gb} GB"
)
QUOTA_USAGE_RESET = (
    "مصرف سهمیه ریسلر {label} ریست شد.\n"
    "مصرف فعلی: {lifetime_gb} GB (برابر تخصیص فعال)\n"
    "باقی‌مانده: {remaining_gb} GB"
)
MAX_CLIENTS_UPDATED = (
    "سقف تعداد سرویس ریسلر {label} به {max_clients} تنظیم شد.{warning}"
)
MAX_CLIENTS_CLEARED = "محدودیت تعداد سرویس برای ریسلر {label} برداشته شد."
NAME_UPDATED = "نام ریسلر به {label} تغییر کرد."
RESELLER_DISABLED = "ریسلر {label} غیرفعال شد."
RESELLER_ENABLED = "ریسلر {label} فعال شد."

RESELLER_LIST_HEADER = "ریسلرها:"
RESELLER_LIST_EMPTY = "ریسلری ثبت نشده است."
REPORT_HUB_HEADER = "گزارش‌گیری — ریسلر را انتخاب کنید:"
REPORT_HUB_EMPTY = "ریسلری برای گزارش وجود ندارد."
REPORT_HUB_HINT = "روی هر ریسلر بزنید تا گزارش تعداد سرویس و تخصیص حجم نمایش داده شود."
RESELLER_REPORT = (
    "📈 گزارش ریسلر: {label}\n"
    "وضعیت: {status}\n"
    "پنل پیش‌فرض: {panel_name} (#{panel_id})\n"
    "سهمیه کل: {quota_gb} GB | مصرف: {lifetime_gb} GB | باقی: {remaining_gb} GB\n"
    "{panels_detail}\n"
    "سرویس کل: {client_count}"
)
RESELLER_REPORT_PANEL_LINE = (
    "• {panel_name}: {client_count} سرویس | "
    "تخصیص فعال: {active_gb} GB"
)
REPORT_UPDATED = "گزارش بروزرسانی شد."
RESELLER_HUB_HINT = (
    "روی هر ریسلر بزنید برای مدیریت؛ «افزودن ریسلر» برای ویزارد ثبت."
)
RESELLER_VIEW_DETAIL = (
    "ریسلر: {label}\n"
    "وضعیت: {status}\n"
    "پنل پیش‌فرض: {panel_name} (#{panel_id})\n"
    "{panels_summary}\n"
    "سرویس کل: {client_count}"
)
RESELLER_PANELS_HEADER = "پنل‌های {label}:"
RESELLER_PANEL_VIEW = (
    "ریسلر: {label}\n"
    "پنل: {panel_name} (#{panel_id})\n"
    "وضعیت تخصیص: {status}\n"
    "سرویس روی این پنل: {client_count} | حداکثر: {max_clients}\n"
    "تخصیص فعال روی پنل: {active_gb} GB\n"
    "سهمیه کل ریسلر: {quota_gb} GB | باقی: {remaining_gb} GB\n"
    "مجاز: {allowed_inbounds}\n"
    "متصل: {attach_inbounds}"
)
RESELLER_PANEL_EDIT_MENU = "ویرایش {panel_name} — {label}:"
RESELLER_PANEL_ADD_PICK = "پنل جدید برای این ریسلر انتخاب کنید:"
RESELLER_PANEL_ADD_QUOTA = "سقف حجم (GB) برای این پنل:"
PANEL_ASSIGNMENT_ADDED = (
    "پنل {panel_name} به {label} اضافه شد.\n"
    "سهمیه حجم از سقف کل ریسلر استفاده می‌شود."
)
PANEL_ASSIGNMENT_REMOVED = "تخصیص پنل {panel_name} از {label} حذف شد."
PANEL_CREATE_ALLOWED = "ساخت کلاینت روی {panel_name} — {label} مجاز شد."
PANEL_CREATE_BLOCKED = (
    "ساخت کلاینت جدید روی {panel_name} — {label} ممنوع شد. "
    "سرویس‌های قبلی قابل مدیریت‌اند."
)
PANEL_REMOVE_CONFIRM = "حذف این تخصیص پنل؟ (فقط بدون سرویس)"
PANEL_QUOTA_UPDATED = "سقف {panel_name} — {label}: {quota_gb} GB"
PANEL_QUOTA_ADDED = (
    "سقف {panel_name} — {label}: +{add_gb} GB (جدید: {quota_gb} GB)"
)
PANEL_QUOTA_USAGE_RESET = (
    "مصرف {panel_name} — {label} ریست شد.\n"
    "مصرف: {lifetime_gb} GB | باقی: {remaining_gb} GB"
)
PANEL_ALLOWED_INBOUNDS_UPDATED = (
    "اینباندهای مجاز {panel_name} — {label}:\n{allowed_inbounds}\nمتصل: {attach_inbounds}{warning}"
)
PANEL_ATTACH_INBOUNDS_UPDATED = (
    "اینباندهای متصل {panel_name} — {label}: {attach_inbounds}"
)
PANEL_MAX_CLIENTS_UPDATED = (
    "سقف سرویس {panel_name} — {label}: {max_clients}{warning}"
)
DEFAULT_PANEL_SET = "پنل پیش‌فرض {label}: {panel_name}"
NO_PANEL_AVAILABLE = "پنل جدیدی برای اختصاص وجود ندارد."
PANEL_NOT_LOADED = "اتصال به پنل برقرار نیست."
CREATE_PICK_PANEL = "پنل را برای ساخت سرویس انتخاب کنید:"
WELCOME_RESELLER_MULTI = (
    "سلام{display_name}!\n\n"
    "{quota_block}\n\n"
    "پنل‌ها:\n"
    "{panels_lines}\n"
    "سرویس کل: {client_count}"
)
RESELLER_EDIT_MENU = "ویرایش ریسلر {label} — گزینه را انتخاب کنید:"
RESELLER_EDIT_QUOTA_PROMPT = (
    "سقف حجم (GB) برای {label}:\nیکی از دکمه‌ها را بزنید یا عدد بنویسید:"
)
RESELLER_EDIT_ADD_QUOTA_PROMPT = (
    "افزودن به سقف (GB) برای {label}:\n"
    "یکی از دکمه‌ها را بزنید یا مقدار افزایش را بنویسید:"
)
RESELLER_EDIT_SUBTRACT_QUOTA_PROMPT = (
    "کاهش از سقف (GB) برای {label}:\n"
    "یکی از دکمه‌ها را بزنید یا مقدار کاهش را بنویسید:"
)
RESELLER_RESET_QUOTA_CONFIRM = (
    "ریست مصرف سهمیه برای {label}؟\n\n"
    "مصرف سهمیه برابر تخصیص فعال سرویس‌ها می‌شود.\n"
    "برای پکیج تازه، ابتدا سقف را تنظیم کنید سپس این گزینه را بزنید."
)
RESELLER_EDIT_NAME_PROMPT = (
    "نام نمایشی جدید برای {label} (a-z 0-9 _ -):"
)
RESELLER_EDIT_MAX_CLIENTS_PROMPT = (
    "سقف تعداد سرویس برای {label}:\n"
    "یکی از دکمه‌ها را بزنید، عدد بنویسید، یا «نامحدود»."
)
RESELLER_EDIT_ALLOW_PROMPT = (
    "اینباندهای مجاز — پنل #{panel_id}:\n"
    "روی هر اینباند بزنید (انتخاب/لغو)؛ سپس «ذخیره»."
)
RESELLER_EDIT_ATTACH_PROMPT = (
    "اینباندهای متصل هنگام ساخت (زیرمجموعهٔ مجاز):\n"
    "روی هر مورد بزنید؛ سپس «ذخیره»."
)
RESELLER_EDIT_INBOUNDS_NONE = "حداقل یک اینباند انتخاب کنید."
RESELLER_EDIT_ATTACH_EMPTY_ALLOWED = "ابتدا اینباندهای مجاز را تنظیم کنید."
RESELLER_DELETE_CONFIRM = "حذف کامل ریسلر {label} از دیتابیس؟\nاین عمل برگشت‌پذیر نیست."
RESELLER_DELETED = "ریسلر {label} حذف شد."
RESELLER_DELETE_BLOCKED_HAS_CLIENTS = (
    "ریسلر {label} الان {client_count} سرویس دارد.\n"
    "برای حذف ابتدا همه سرویس‌ها را حذف کنید."
)
RESELLER_WIZARD_TELEGRAM_ID = (
    "مرحله ۱ — آیدی عددی تلگرام ریسلر را وارد کنید:"
)
RESELLER_WIZARD_DISPLAY_NAME = (
    "مرحله ۲ — نام نمایشی (فقط a-z 0-9 _ -) یا «بدون نام»:"
)
RESELLER_WIZARD_PICK_PANEL = "مرحله ۳ — پنل ریسلر را انتخاب کنید:"
RESELLER_WIZARD_QUOTA = (
    "مرحله ۴ — سقف حجم (GB):\n"
    "یکی از دکمه‌ها را بزنید یا عدد بنویسید:"
)
RESELLER_WIZARD_INBOUNDS = (
    "مرحله ۵ — اینباندهای مجاز (پنل #{panel_id}):\n"
    "روی هر اینباند بزنید تا انتخاب/لغو شود؛ سپس «ادامه»."
)
RESELLER_WIZARD_INBOUNDS_EMPTY = "اینبندی در این پنل یافت نشد."
RESELLER_WIZARD_INBOUNDS_NONE_SELECTED = "حداقل یک اینباند انتخاب کنید."
RESELLER_WIZARD_CONFIRM = (
    "تأیید ثبت ریسلر:\n"
    "آیدی: {telegram_id}\n"
    "نام: {display_name}\n"
    "پنل: {panel_name} (#{panel_id})\n"
    "سقف: {quota_gb} GB\n"
    "اینباندها: {inbound_ids}"
)
RESELLER_WIZARD_CANCELLED = "افزودن ریسلر لغو شد."
RESELLER_ALREADY_EXISTS = "این آیدی از قبل ریسلر است؛ از لیست ریسلرها مدیریت کنید."

TEMPLATE_ADDED = (
    "قالب #{id} ثبت شد: {name}\n"
    "حجم: {volume_gb} GB | انقضا: {expiry_label}"
)
TEMPLATE_LIST_HEADER = "قالب‌های ساخت سرویس (سراسری):"
TEMPLATE_LIST_EMPTY = "قالبی ثبت نشده است."
TEMPLATE_DELETED = "قالب #{id} حذف شد."
TEMPLATE_NOT_FOUND = "قالب یافت نشد."
TEMPLATE_HUB_HINT = "برای افزودن قالب، دکمه «افزودن قالب جدید» را بزنید."
TEMPLATE_DELETE_CONFIRM = (
    "حذف قالب #{id}؟\n"
    "{name} — {volume_gb} GB — {expiry_label}"
)
TEMPLATE_WIZARD_VOLUME = (
    "مرحله ۱ از ۴ — حجم قالب (گیگابایت):\n"
    "یکی از دکمه‌ها را بزنید یا عدد را بنویسید (مثلاً 10):"
)
TEMPLATE_WIZARD_EXPIRY = (
    "مرحله ۲ از ۴ — مدت انقضا:\n"
    "یکی از دکمه‌ها را بزنید یا تعداد روز را بنویسید (0 = نامحدود):"
)
TEMPLATE_WIZARD_NAME = (
    "مرحله ۳ از ۴ — نام دکمه قالب:\n"
    "این متن روی دکمهٔ ریسلر نمایش داده می‌شود.\n"
    "پیشنهاد: `{suggested}`\n\n"
    "نام را بنویسید یا «استفاده از نام پیشنهادی» را بزنید."
)
TEMPLATE_WIZARD_CONFIRM = (
    "مرحله ۴ از ۴ — تأیید ثبت قالب:\n"
    "نام: {name}\n"
    "حجم: {volume_gb} GB\n"
    "انقضا: {expiry_label}\n\n"
    "ثبت شود؟"
)
TEMPLATE_WIZARD_CANCELLED = "افزودن قالب لغو شد."

CREATE_PICK_TEMPLATE = (
    "یک قالب آماده انتخاب کنید، یا «ورود دستی» برای وارد کردن حجم و انقضا.\n"
    "حداقل حجم سرویس: 20 GB."
)
CREATE_CANCELLED = "ساخت سرویس لغو شد."
CREATE_VOLUME_PROMPT = (
    "حجم سرویس را به گیگابایت وارد کنید (حداقل 20 GB، مثلاً 20):"
)
CREATE_VOLUME_TOO_LOW = "حداقل حجم سرویس 20 GB است."
CREATE_EXPIRY_PROMPT = "تعداد روز انقضا را وارد کنید (0 = نامحدود):"
CREATE_CLIENT_NAME_PROMPT = (
    "نام سرویس را وارد کنید (فقط حروف انگلیسی، عدد، زیرخط و -)\n"
    "مثال: myvpn → ایمیل: {prefix}-client-myvpn\n\n"
    "یا «نام تصادفی» را بزنید."
)
CREATE_CONFIRM = (
    "تأیید ساخت سرویس:\n"
    "ایمیل: `{email_preview}`\n"
    "{template_line}"
    "حجم: {volume_gb} GB\n"
    "انقضا: {expiry_label}\n"
    "اینباندهای متصل: {inbounds}\n\n"
    "ادامه می‌دهید؟"
)
EMAIL_TAKEN = "این نام سرویس قبلاً استفاده شده. نام دیگری انتخاب کنید."
# SERVICE_CREATED is built via format_delivery_message in bot/utils/format_delivery.py
DELETE_CONFIRM = (
    "آیا از حذف سرویس `{email}` مطمئن هستید؟\n"
    "این کار قابل بازگشت نیست.\n\n"
    "{refund_hint}\n\n"
    "قانون: اگر مصرف واقعی ترافیک کمتر از {threshold_gb} GB باشد، "
    "سهمیهٔ همان سرویس به حساب شما برمی‌گردد."
)
DELETE_CONFIRM_REFUND_YES = (
    "مصرف فعلی: {used}\n"
    "با حذف، سهمیهٔ این سرویس به حساب شما برمی‌گردد."
)
DELETE_CONFIRM_REFUND_NO = (
    "مصرف فعلی: {used}\n"
    "مصرف از {threshold_gb} GB یا بیشتر است؛ سهمیه برنمی‌گردد."
)
DELETE_CONFIRM_REFUND_UNKNOWN = (
    "مصرف ترافیک از پنل خوانده نشد.\n"
    "در صورت حذف، سهمیه فقط در صورت مصرف زیر آستانه برمی‌گردد."
)
CREATE_SESSION_EXPIRED = (
    "اطلاعات ساخت ناقص یا منقضی شده است. از «ساخت سرویس» دوباره شروع کنید."
)
QR_CHOOSE = "کانفیگ VLESS را برای دریافت QR انتخاب کنید:"
QR_NOT_AVAILABLE = "کانفیگ VLESS برای این سرویس یافت نشد."
QR_SENT = "QR ارسال شد."
QR_CAPTION = (
    "{remark_line}اسکن در v2rayNG / Hiddify — "
    "برای بروزرسانی خودکار از لینک ساب استفاده کنید."
)
DELIVERY_GUIDE_WITH_SUB = (
    "━━━━━━━━━━━━━━━━\n"
    "📌 راهنمای استفاده (برای مشتری)\n\n"
    "✅ روش پیشنهادی — لینک ساب\n"
    "با لینک ساب بالا، لیست کانفیگ‌ها خودکار بروز می‌شود. "
    "اگر سرور یا اینباند عوض شد، فقط در اپ VPN دکمه بروزرسانی (Update) را بزنید.\n\n"
    "مراحل:\n"
    "۱) لینک ساب بالا را کپی کنید\n"
    "۲) در اپ VPN اضافه کنید:\n"
    "• v2rayNG (اندروید): + → Subscription → Paste URL → ✓ → Update\n"
    "• Hiddify: + → Add subscription / From clipboard → Paste → Update\n"
    "• v2rayN (ویندوز): Subscription group → Add → Paste URL → Update subscription\n"
    "۳) یک بار Update بزنید تا کانفیگ‌ها لود شوند\n\n"
    "📲 روش جایگزین — QR یا کانفیگ تکی\n"
    "هر کانفیگ VLESS را جدا کپی کنید یا QR آن را اسکن کنید (دکمه «QR کانفیگ»). "
    "این روش خودکار بروز نمی‌شود؛ با تغییر سرور باید لینک جدید بگیرید."
)
DELIVERY_GUIDE_NO_SUB = (
    "━━━━━━━━━━━━━━━━\n"
    "📌 راهنمای استفاده (برای مشتری)\n\n"
    "لینک ساب در دسترس نیست. هر کانفیگ VLESS را جدا کپی کنید "
    "یا QR آن را اسکن کنید (دکمه «QR کانفیگ»).\n\n"
    "با تغییر تنظیمات سرور، لینک جدید را از فروشنده بگیرید."
)

USAGE_ALERT_RESELLER = (
    "اعلان\n\n"
    "{threshold}٪ سقف حجم ریسلر شما مصرف شده.\n"
    "مصرف سهمیه: {used_gb} از {quota_gb} GB ({percent}٪)"
)
USAGE_ALERT_RESELLER_PANEL = (
    "اعلان\n\n"
    "{threshold}٪ سقف حجم پنل {panel_name} مصرف شده.\n"
    "مصرف سهمیه: {used_gb} از {quota_gb} GB ({percent}٪)"
)
USAGE_ALERT_CLIENT = (
    "اعلان\n\n"
    "{threshold}٪ حجم سرویس مصرف شده.\n"
    "سرویس: {email}\n"
    "مصرف: {used} از {total} ({percent}٪)"
)
SERVICE_DELETED = "سرویس حذف شد."
SERVICE_DELETED_QUOTA_REFUNDED = (
    "سرویس حذف شد.\n"
    "{refund_gb} GB سهمیه به حساب شما برگشت."
)
SERVICE_ENABLED = "سرویس فعال شد."
SERVICE_DISABLED = "سرویس غیرفعال شد."
EXPIRY_CHOOSE_MODE = (
    "سرویس: `{email}`\n"
    "انقضای فعلی: {expiry_label}\n\n"
    "روش تغییر انقضا را انتخاب کنید:"
)
EXPIRY_PROMPT_ADD_DAYS = "چند روز به انقضا اضافه شود؟ (عدد صحیح، مثلاً 30):"
EXPIRY_PROMPT_SET_DATE = (
    "تاریخ انقضای جدید را وارد کنید (YYYY-MM-DD)\n"
    "یا 0 برای نامحدود:"
)
EXPIRY_UPDATED = "انقضا به‌روز شد.\nجدید: {expiry_label}"
ADD_TRAFFIC_CHOOSE = (
    "سرویس: `{email}`\n"
    "سقف فعلی: {current_gb} GB\n"
    "باقی‌مانده سهمیه: {remaining_gb} GB\n\n"
    "چند گیگابایت به این سرویس اضافه شود؟"
)
ADD_TRAFFIC_PROMPT = (
    "حجم اضافه را به گیگابایت وارد کنید (مثلاً 10):"
)
ADD_TRAFFIC_CONFIRM = (
    "تأیید افزودن ترافیک:\n"
    "سرویس: `{email}`\n"
    "افزودن: {add_gb} GB\n"
    "سقف فعلی: {current_gb} GB → جدید: {new_gb} GB\n"
    "باقی‌مانده سهمیه: {remaining_before_gb} → {remaining_after_gb} GB\n\n"
    "ادامه می‌دهید؟"
)
ADD_TRAFFIC_OK = (
    "ترافیک اضافه شد.\n"
    "سقف جدید سرویس: {new_total_gb} GB\n"
    "باقی‌مانده سهمیه: {remaining_gb} GB"
)
REDUCE_TRAFFIC_CHOOSE = (
    "سرویس: `{email}`\n"
    "سقف فعلی: {current_gb} GB\n"
    "مصرف فعلی: {used_gb} GB\n"
    "باقی‌مانده سهمیه: {remaining_gb} GB\n\n"
    "چند گیگابایت از این سرویس کم شود؟"
)
REDUCE_TRAFFIC_PROMPT = (
    "حجم کاهش را به گیگابایت وارد کنید (مثلاً 10):"
)
REDUCE_TRAFFIC_CONFIRM = (
    "تأیید کاهش ترافیک:\n"
    "سرویس: `{email}`\n"
    "کاهش: {remove_gb} GB\n"
    "سقف فعلی: {current_gb} GB → جدید: {new_gb} GB\n"
    "مصرف فعلی: {used_gb} GB\n"
    "باقی‌مانده سهمیه: {remaining_before_gb} → {remaining_after_gb} GB\n\n"
    "ادامه می‌دهید؟"
)
REDUCE_TRAFFIC_OK = (
    "ترافیک کاهش یافت.\n"
    "سقف جدید سرویس: {new_total_gb} GB\n"
    "باقی‌مانده سهمیه: {remaining_gb} GB"
)
EDIT_MENU = (
    "ویرایش سرویس `{email}`\n\n"
    "limitIp فعلی: {limit_ip_label}\n"
    "کامنت: {comment_label}"
)
RESET_TRAFFIC_CONFIRM = (
    "آیا مصرف ترافیک سرویس `{email}` ریست شود؟\n"
    "این کار قابل بازگشت نیست."
)
TRAFFIC_RESET_OK = "ترافیک سرویس ریست شد."
LIMIT_IP_PROMPT = "limitIp جدید را وارد کنید (0 = نامحدود، مثلاً 2):"
LIMIT_IP_UPDATED = "limitIp به {limit_ip_label} تغییر کرد."
COMMENT_PROMPT = "کامنت را وارد کنید (خالی = حذف کامنت، حداکثر ۲۰۰ کاراکتر):"
COMMENT_UPDATED = "کامنت ذخیره شد."
NO_SERVICES = "هنوز سرویسی نساخته‌اید."
INVALID_INPUT = "ورودی نامعتبر است. دوباره تلاش کنید."
RATE_LIMITED = "تعداد درخواست زیاد است. چند ثانیه صبر کنید."

VERSION_INFO = "نسخه ربات: {version}"

BOT_UPDATE_MENU = (
    "آپدیت ربات (نسخه فعلی: {version})\n\n"
    "روش آپدیت را انتخاب کنید:\n"
    "• GitHub — آخرین release از {repo}\n"
    "• ZIP — آپلود دستی فایل ریلیز (حداکثر {max_mb} مگابایت)"
)
BOT_UPDATE_PROMPT = (
    "آپلود ZIP ریلیز\n\n"
    "فایل ZIP را بفرستید (حداکثر {max_mb} مگابایت).\n"
    "پس از تأیید، سرویس ری‌استارت می‌شود و آپدیت هنگام بالا آمدن اعمال می‌شود."
)
BOT_UPDATE_GITHUB_FETCHING = (
    "در حال دریافت آخرین release از GitHub…\n"
    "مخزن: `{repo}`"
)
BOT_UPDATE_GITHUB_DISABLED = "آپدیت خودکار GitHub غیرفعال است."
BOT_UPDATE_NOT_ZIP = "لطفاً یک فایل ZIP بفرستید."
BOT_UPDATE_TOO_LARGE = "حجم فایل بیش از حد مجاز است."
BOT_UPDATE_READY = (
    "بسته آماده است.\n"
    "فعلی: {current}\n"
    "هدف: {target}\n"
    "فایل: {filename}\n\n"
    "با «اعمال و ری‌استارت» ادامه دهید."
)
BOT_UPDATE_CANCELLED = "آپدیت لغو شد."
BOT_UPDATE_NO_PENDING = "بسته‌ای در صف نیست."
BOT_UPDATE_RESTARTING = (
    "در حال ری‌استارت سرویس `{service}`…\n"
    "پس از بالا آمدن، نسخه {target} اعمال می‌شود."
)
BOT_UPDATE_RESTART_MANUAL = (
    "ری‌استارت خودکار انجام نشد.\n"
    "نسخه هدف: {target}\n"
    "جزئیات: {detail}\n\n"
    "دستی: sudo systemctl restart {service}"
)
BOT_UPDATE_RESULT_OK = (
    "ربات به‌روز شد: {previous} → {new_version}\n{message}"
)
BOT_UPDATE_RESULT_FAIL = "آپدیت ناموفق بود ({previous}): {message}"
