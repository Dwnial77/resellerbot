# Reseller Bot for 3x-ui v3.2.0



**نسخه ربات:** 1.0.0 — تاریخچه در [CHANGELOG.md](CHANGELOG.md)



**مخزن:** [github.com/Dwnial77/resellerbot](https://github.com/Dwnial77/resellerbot) — مجوز: [MIT](LICENSE)

Reseller Bot ربات تلگرامی است که لایهٔ ریسلر را روی پنل 3x-ui اضافه می‌کند: به‌جای دادن دسترسی مستقیم پنل به هر فروشنده، ادمین ریسلرها را با سقف حجم، اینباند مجاز و (در صورت نیاز) چند پنل جدا تعریف می‌کند؛ ریسلر فقط از تلگرام سرویس می‌سازد و مدیریت می‌کند. ربات با API نسخه v3.2.0 کار می‌کند، داده را در SQLite نگه می‌دارد، برای سرور لینوکس systemd و اسکریپت scripts/install.sh دارد، و ادمین می‌تواند نسخهٔ جدید را با آپلود ZIP از منوی ربات به‌روز کند.



ربات تلگرام ریسلر برای پنل [3x-ui (MHSanaei)](https://github.com/MHSanaei/3x-ui) نسخه **v3.2.0**. می‌توانید **چند پنل** داشته باشید؛ هر ریسلر به **یک پنل** متصل است. هر ریسلر سقف حجم مشخص دارد؛ برای هر ریسلر دو لیست اینباند تعریف می‌شود:



- **مجاز** (`allowed_inbound_ids`): مجموعه‌ای که اعتبارسنجی روی آن انجام می‌شود

- **متصل هنگام ساخت** (`attach_inbound_ids`): اینباندهایی که با `inboundIds` روی کلاینت جدید وصل می‌شوند (زیرمجموعهٔ مجاز)



## پیش‌نیاز



- Python 3.11+

- پنل 3x-ui **v3.2.0** با inbound آماده

- **API Token** از پنل (توصیه‌شده) یا یوزر/پس ادمین

- توکن ربات از [@BotFather](https://t.me/BotFather)



## نصب سریع (لینوکس / VPS)



اسکریپت [`scripts/install.sh`](scripts/install.sh) کاربر سیستم، virtualenv، systemd و فایل `.env` اولیه را آماده می‌کند.



```bash

# وابستگی‌ها (Debian/Ubuntu)

sudo apt update && sudo apt install -y git python3 python3-venv python3-pip



# کلون و نصب

sudo git clone https://github.com/Dwnial77/resellerbot.git /opt/resellerbot

cd /opt/resellerbot

sudo bash scripts/install.sh



# تنظیم توکن ربات و پنل

sudo nano /opt/resellerbot/.env

sudo systemctl restart resellerbot

sudo journalctl -u resellerbot -f

```



گزینه‌های اسکریپت: `--dir PATH` (پیش‌فرض `/opt/resellerbot`)، `--no-start` (بدون استارت سرویس).



اگر مخزن **private** است، قبل از `git clone` روی VPS کلید SSH یا Personal Access Token را برای GitHub تنظیم کنید.



### sudoers (آپدیت ZIP از تلگرام)



برای ری‌استارت خودکار بعد از آپلود ZIP در ربات:



```text

resellerbot ALL=(root) NOPASSWD: /bin/systemctl restart resellerbot

```



```bash

sudo visudo -f /etc/sudoers.d/resellerbot

```



## نصب دستی (ویندوز / توسعه)



```bash

git clone https://github.com/Dwnial77/resellerbot.git

cd resellerbot

python -m venv .venv

# Windows:

.venv\Scripts\activate

# Linux/macOS:

# source .venv/bin/activate

pip install -r requirements.txt

copy .env.example .env    # Windows

# cp .env.example .env    # Linux

# مقادیر .env را پر کنید

python -m bot.main

```



## تنظیم `.env`



| متغیر | توضیح |

|--------|--------|

| `BOT_TOKEN` | توکن ربات تلگرام |

| `ADMIN_TELEGRAM_IDS` | آیدی عددی ادمین‌ها، با کاما |

| `XUI_BASE_URL` | آدرس **پنل اول** (هنگام اولین اجرا در DB ذخیره می‌شود) |

| `XUI_API_TOKEN` | توکن API پنل اول |

| `XUI_SUB_PUBLIC_URL` | آدرس پایه ساب عمومی؛ ربات `subId` را به انتها می‌چسباند |

| `XUI_DEFAULT_INBOUND_IDS` | پیش‌فرض اینباند (معمولاً `1`) |

| `XUI_VERIFY_SSL` | بررسی گواهی SSL پنل (`true` / `false`) |

| `XUI_AUTO_VISION_FLOW` | flow خودکار `xtls-rprx-vision` برای VLESS مناسب |

| `XUI_AUTO_RESELLER_GROUP` | گروه پنل به نام `{display_name}-{telegram_id}` |

| `DATABASE_URL` | پیش‌فرض SQLite در `./data/bot.db` |

| `CREATE_RATE_LIMIT` | حداکثر ساخت سرویس در دقیقه (پیش‌فرض `5`) |

| `USAGE_ALERT_ENABLED` | اعلان مصرف ۸۰٪ / ۹۰٪ |

| `USAGE_ALERT_INTERVAL_SECONDS` | فاصله بررسی اعلان‌ها (ثانیه) |

| `UPDATE_ZIP_MAX_BYTES` | حداکثر حجم ZIP آپدیت از تلگرام |

| `SYSTEMD_SERVICE_NAME` | نام سرویس systemd (پیش‌فرض `resellerbot`) |

| `ALLOW_UPDATE_DOWNGRADE` | اجازه نصب نسخه قدیمی‌تر از ZIP |



جزئیات بیشتر و مقادیر پیش‌فرض در [`.env.example`](.env.example).



## استقرار دستی لینوکس (بدون install.sh)



اگر ترجیح می‌دهید مرحله‌به‌مرحله نصب کنید، همان مراحل داخل [`scripts/install.sh`](scripts/install.sh) را دستی انجام دهید: کاربر `resellerbot`، venv، [`deploy/resellerbot.service`](deploy/resellerbot.service)، `systemctl enable --now resellerbot`.



ری‌استارت:



```bash

sudo systemctl restart resellerbot

```



## آپدیت ربات (ZIP از GitHub)



1. در [Releases](https://github.com/Dwnial77/resellerbot/releases) فایل `resellerbot-X.Y.Z.zip` را دانلود کنید.

2. در تلگرام: **⬆️ آپدیت ربات** یا `/bot_update` — ZIP را بفرستید.

3. **اعمال و ری‌استارت** — سرویس ری‌استارت می‌شود؛ هنگام بالا آمدن کد و وابستگی‌ها به‌روز می‌شوند (`.env` و `data/bot.db` حفظ می‌شوند).

4. `/version` — نسخه فعلی.



ساخت ZIP برای ریلیز (روی ماشین توسعه):



```bash

bash scripts/build_release_zip.sh

# خروجی: dist/resellerbot-1.0.0.zip

```



**توجه:** روی سرور production فقط ZIP یا فقط `git pull` — هر دو با هم توصیه نمی‌شود.



## استفاده — ادمین



در چت با ربات **`/`** را بزنید تا لیست دستورات با توضیح کوتاه نمایش داده شود. ادمین‌ها دستورات مدیریتی بیشتری می‌بینند (ثبت خودکار هنگام استارت ربات).



1. `/start` یا `/admin` — منوی ادمین

2. **پنل‌ها** (دکمه منو) یا `/panels` — افزودن پنل دوم و بعدی با ویزارد (نام، URL، توکن، ساب)

3. **لیست ریسلرها** (دکمه منو) یا `/list_resellers` — هاب مدیریت: انتخاب ریسلر → **ویرایش ریسلر** (سقف حجم، سقف تعداد سرویس، نام، اینباندها)، فعال/غیرفعال، حذف، تغییر پنل؛ **افزودن ریسلر** با ویزارد

   - مسیر سریع (یک پیام): `5266810479 ali 1 100 1` — آیدی، نام، پنل، سقف GB، اینباند

   - بدون نام: `123456789 1 100 1` | فرمت قدیم (پنل 1): `123456789 100 1`

4. `/list_inbounds 2` — اینباندهای پنل شماره `2` (پیش‌فرض: `1`)

5. **تغییر پنل ریسلر** — دکمه منو یا `/set_panel` (ویزارد: انتخاب ریسلر → پنل → تأیید). مسیر سریع: `/set_panel 123456789 2`. فقط وقتی **هیچ سرویسی** ندارد (وجود `panel_id` قبلی مانع نیست)

6. دستورات `/set_quota` / `set_max_clients` / `set_name` / `set_allowed_inbounds` / … همچنان از چت کار می‌کنند (همان منطق دکمه‌های ویرایش)

7. **قالب‌های سرویس** — سراسری (فقط حجم/انقضا)؛ ساخت روی پنل همان ریسلر

8. **⬆️ آپدیت ربات** — آپلود ZIP ریلیز GitHub و ری‌استارت (`/bot_update`, `/version`)



**امنیت:** توکن پنل‌ها در فایل SQLite (`data/bot.db`) ذخیره می‌شود؛ دسترسی به سرور و بکاپ DB را محدود کنید.



### گروه‌بندی در پنل (ریسلر)



وقتی ریسلر **نام نمایشی** دارد (مثلاً `ali`)، هر سرویس جدید در پنل 3x-ui داخل گروه **`ali-5266810479`** قرار می‌گیرد (`نام-آیدی_تلگرام`). اگر نام نداشته باشد، گروه فقط همان آیدی عددی است.



غیرفعال‌سازی:



```env

XUI_AUTO_RESELLER_GROUP=false

```



## استفاده — ریسلر



1. `/start` — نمایش سقف و باقی‌مانده

2. **ساخت سرویس** — اگر ادمین قالب تعریف کرده باشد: انتخاب قالب با یک کلیک (حجم و انقضا از پیش پر می‌شود) یا **ورود دستی**؛ سپس **نام سرویس** → تأیید. بدون قالب: همان جریان دستی (حجم GB → روز انقضا، `0` = نامحدود)

   - نام دلخواه: مثلاً `myvpn` → ایمیل `ali-client-myvpn` (اگر نام ریسلر `ali` باشد)

   - دکمه **نام تصادفی** برای پسوند خودکار

3. **سرویس‌های من** — لینک (VLESS + سابسکریپشن)، **QR هر کانفیگ VLESS** (عکس در تلگرام، جدا از لینک ساب)، ترافیک، **تغییر انقضا**، **ویرایش سرویس** (ریست ترافیک با تأیید، limitIp، کامنت)، فعال/غیرفعال، حذف (با تأیید)

4. **اعلان خودکار** — وقتی **۸۰٪** یا **۹۰٪** سقف حجم ریسلر (مجموع تخصیص سرویس‌ها) یا ترافیک واقعی یک سرویس از پنل مصرف شد، پیام «اعلان» در تلگرام ارسال می‌شود (هر آستانه یک‌بار تا زمان افت مصرف زیر ۷۵٪)



الگوی ایمیل: `{نام_ریسلر}-client-{نام_شما}` — بدون نام ریسلر: `r{telegram_id}-client-{نام}`



## API پنل (v3.2.0)



ربات از این endpointها استفاده می‌کند:



- `POST /panel/api/clients/add`

- `POST /panel/api/clients/groups/create` — ساخت گروه ریسلر

- `POST /panel/api/clients/groups/bulkAdd` — اختصاص کلاینت به گروه

- `POST /panel/api/clients/del/:email`

- `POST /panel/api/clients/update/:email` — به‌روزرسانی کلاینت (فعال/غیرفعال، limitIp، کامنت)

- `POST /panel/api/clients/resetTraffic/:email` — ریست مصرف ترافیک

- `GET /panel/api/clients/traffic/:email`

- `GET /panel/api/clients/links/:email` — کانفیگ VLESS

- `GET /panel/api/clients/subLinks/:subId` — URL سابسکریپشن

- `GET /panel/api/clients/get/:email` — fallback برای `subId` کلاینت‌های قدیمی



فیلد `totalGB` در بدنه درخواست **بر حسب بایت** است (مثلاً ۱۰ GB = `10737418240`).



### لینک سابسکریپشن



ربات لینک ساب را از **`subId` کلاینت** + **`XUI_SUB_PUBLIC_URL`** می‌سازد:



```env

XUI_SUB_PUBLIC_URL=https://sub.example.com:2096/save/

```



نتیجه برای `subId=abc123`: `https://sub.example.com:2096/save/abc123`



این همان آدرسی است که در پنل 3x-ui در بخش Subscription (مسیر/پورت ساب) تنظیم می‌کنید — معمولاً **جدا از** `XUI_BASE_URL` پنل است.



در صورت نیاز، API `subLinks` هم امتحان می‌شود و در صورت موفقیت به لیست اضافه می‌شود.



### Flow خودکار (Vision / Reality)



هنگام **ساخت سرویس جدید**، ربات لیست اینباندها را از پنل می‌خواند. اگر **همه** اینباندهای انتخاب‌شده از نوع **VLESS + TCP + TLS یا Reality** باشند، فیلد `flow` کلاینت به‌صورت خودکار `xtls-rprx-vision` تنظیم می‌شود (مطابق منطق پنل 3x-ui).



اگر ترکیب اینباندها نامناسب باشد (مثلاً xHTTP کنار TCP-Reality)، flow خالی می‌ماند تا اتصال خراب نشود.



غیرفعال‌سازی:



```env

XUI_AUTO_VISION_FLOW=false

```



## چک‌لیست تست دستی



- [ ] پنل v3.2.0 بالا است و inbound با `id=1` وجود دارد

- [ ] API Token در `.env` تنظیم شده و ربات بدون خطای auth بالا می‌آید

- [ ] ادمین ریسلر X با سقف ۱۰۰ GB و Y با ۳۰۰ GB روی inbound `1` تعریف می‌کند

- [ ] X دو سرویس ۴۰+۴۰ GB می‌سازد؛ سرویس سوم ۳۰ GB رد می‌شود

- [ ] Y مستقل از X کلاینت می‌سازد

- [ ] X نمی‌تواند سرویس Y را حذف کند

- [ ] پس از ساخت، کانفیگ VLESS و لینک سابسکریپشن دریافت می‌شود



## ساختار



```

bot/          — تلگرام (handlers, keyboards, FSM)

db/           — SQLite + migrations

services/     — quota، updater، panel registry

xui/          — کلاینت HTTP پنل

deploy/       — systemd unit

scripts/      — install.sh، build_release_zip.sh

tests/

```



## امنیت



- اعتبار پنل فقط در سرور ربات نگهداری می‌شود.

- ریسلرها فقط به کلاینت‌های ثبت‌شده در DB خودشان دسترسی دارند.

- محدودیت نرخ ساخت: `CREATE_RATE_LIMIT` در دقیقه (پیش‌فرض ۵).


