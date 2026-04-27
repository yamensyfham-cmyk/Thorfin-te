#!/data/data/com.termux/files/usr/bin/python3
"""
github_python_bot.py - بوت تيليجرام لنشر أدوات Python الجديدة
يستخدم HTTP API مباشرة (لا يحتاج api_id/api_hash)
"""

import os, sys, json, time, logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ==========================================
#  ⚙️  الإعدادات – عدل القيم التالية مباشرة
# ==========================================

# 1. توكن البوت من @BotFather
BOT_TOKEN = "8143927082:AAFe6A3peGWkhnRdUEWrdUiv86bcGfs9TXY"

# 2. معرف القناة (@username أو المعرف الرقمي مثل -100xxxxxx)
CHANNEL = "@thorfin963"  # ← عدل إلى قناتك

# 3. توكن GitHub (اختياري)
GITHUB_TOKEN = ""

# 4. رابط DeepSeek AI
AI_URL = "https://viscodev.x10.mx/claude/claude-sonnet.php"
AI_UID = "12345"

# 5. الفاصل الزمني بين الدورات (ساعات)
INTERVAL_HOURS = 1

# ==========================================
#  لا تعدل ما تحت هذا السطر
# ==========================================

BASE_DIR   = Path(__file__).parent
SEEN_FILE  = BASE_DIR / "seen_repos.json"
PENDING_FILE = BASE_DIR / "pending_repos.json"
LOG_FILE   = BASE_DIR / "bot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

# --- استيراد requests ---
try:
    import requests
except ImportError:
    log.error("المكتبات غير مثبتة. شغل: pip install requests")
    sys.exit(1)

# --- دوال مساعدة للإرسال عبر تيليجرام ---
def send_telegram_message(text: str, parse_mode="Markdown", disable_web_page_preview=False):
    """يرسل رسالة إلى القناة ويعيد True/False"""
    if not BOT_TOKEN:
        log.error("❌ BOT_TOKEN فارغ")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHANNEL,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview
    }
    try:
        r = requests.post(url, data=data, timeout=15)
        if r.status_code == 200:
            return True
        else:
            log.warning(f"⚠️ Telegram API returned {r.status_code}: {r.text}")
            if r.status_code == 429:  # FloodWait
                retry_after = r.json().get("parameters", {}).get("retry_after", 5)
                log.warning(f"     ⏳ FloodWait: {retry_after} ثانية")
                time.sleep(retry_after + 1)
                return send_telegram_message(text, parse_mode, disable_web_page_preview)  # retry once
            return False
    except Exception as e:
        log.error(f"❌ فشل الاتصال بتيليجرام: {e}")
        return False

# --- إدارة البيانات ---
def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()

def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(list(seen), ensure_ascii=False))

def load_pending() -> list:
    if PENDING_FILE.exists():
        return json.loads(PENDING_FILE.read_text())
    return []

def save_pending(pending: list):
    PENDING_FILE.write_text(json.dumps(pending, ensure_ascii=False))

# --- البحث في GitHub ---
def search_github(days: int = 2) -> list:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    query = f"language:Python created:>{since} stars:>10"
    url   = "https://api.github.com/search/repositories"
    params = {"q": query, "sort": "stars", "order": "desc", "per_page": 8}
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "TermuxHTTPBot/1.0"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.error(f"❌ فشل البحث في GitHub: {e}")
        return []

    repos = []
    for item in data.get("items", []):
        repos.append({
            "id":          str(item["id"]),
            "name":        item["full_name"],
            "url":         item["html_url"],
            "description": item.get("description") or "لا يوجد وصف",
            "stars":       item.get("stargazers_count", 0),
            "topics":      item.get("topics", []),
            "readme_url":  f"https://raw.githubusercontent.com/{item['full_name']}/HEAD/README.md",
        })
    return repos

def get_readme(url: str, max_chars: int = 700) -> str:
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "TermuxHTTPBot/1.0"})
        if r.status_code != 200:
            return ""
        lines = [l for l in r.text.splitlines() if not l.strip().startswith("[![")]
        return "\n".join(lines)[:max_chars]
    except Exception:
        return ""

# --- التحليل ---
def analyze(repo: dict, readme: str) -> str:
    prompt = (
        f"أداة Python على GitHub:\n"
        f"الاسم: {repo['name']}\n"
        f"الوصف: {repo['description']}\n"
        f"النجوم: {repo['stars']}\n"
        f"المواضيع: {', '.join(repo['topics'])}\n"
        f"README:\n{readme}\n\n"
        f"اكتب شرحاً بالعربية في 15 سطر: ما تفعله الأداة، لمن هي مفيدة،كيفية استعمالاها وخطوات التنزيل  "
        f"ميزتها الرئيسية. ابدأ مباشرة بلا مقدمة."
    )
    try:
        r = requests.get(
            AI_URL, params={"uid": AI_UID, "message": prompt},
            headers={"User-Agent": "TermuxHTTPBot/1.0"}, timeout=30
        )
        text = r.text.strip()
        try:
            j = json.loads(text)
            return j.get("result") or j.get("response") or j.get("text") or text[:600]
        except Exception:
            return text[:600]
    except Exception as e:
        return f"⚠️ تعذّر التحليل: {e}"

# --- تنسيق الرسالة ---
def format_msg(repo: dict, analysis: str) -> str:
    stars = "⭐" * min(repo["stars"] // 100, 8)
    tags  = " ".join(f"#{t.replace('-','_')}" for t in repo["topics"][:5])
    return (
        f"🐍 **أداة Python جديدة**\n\n"
        f"📦 [{repo['name']}]({repo['url']})\n"
        f"⭐ {repo['stars']:,} نجمة {stars}\n\n"
        f"🤖 **التحليل:**\n{analysis}\n\n"
        f"{tags}\n"
        f"━━━━━━━━━━━━━━━"
    )

# --- دورة العمل ---
def run_cycle():
    log.info("🔍 بدء دورة البحث...")
    seen = load_seen()
    pending = load_pending()

    # 1. جلب الأدوات الجديدة وإضافتها للطابور
    repos = search_github(days=2)
    for r in repos:
        rid = r["id"]
        if rid not in seen and not any(p["id"] == rid for p in pending):
            pending.append(r)
            log.info(f"  ➕ أُضيفت للطابور: {r['name']}")

    if not pending:
        log.info("⏳ الطابور فارغ. لا شيء للإرسال الآن.")
        return

    # 2. أخذ أول أداة من الطابور وإرسالها
    repo = pending.pop(0)
    log.info(f"  📤 إرسال: {repo['name']} ({repo['stars']} ⭐)")

    readme   = get_readme(repo["readme_url"])
    analysis = analyze(repo, readme)
    msg      = format_msg(repo, analysis)

    success = send_telegram_message(msg, parse_mode="Markdown", disable_web_page_preview=False)
    if success:
        seen.add(repo["id"])
        log.info("     ✅ أُرسلت")
    else:
        log.error("     ❌ فشل الإرسال، نعيد الأداة إلى رأس الطابور")
        pending.insert(0, repo)  # حاول لاحقاً

    # 3. حفظ الحالة
    save_seen(seen)
    save_pending(pending)

    log.info(f"🏁 انتهت الدورة. تبقى {len(pending)} أداة في الطابور.")

# --- الحلقة الرئيسية (متزامنة) ---
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN غير موجود. ضع التوكن في الكود أو متغير البيئة.")
        sys.exit(1)

    # عرض حالة البوت
    try:
        r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=10)
        if r.status_code == 200:
            bot_info = r.json()["result"]
            log.info(f"✅ تم الاتصال بالبوت: @{bot_info['username']}")
        else:
            log.error("❌ فشل الاتصال بالبوت. تأكد من التوكن.")
            sys.exit(1)
    except Exception as e:
        log.error(f"❌ خطأ في الاتصال: {e}")
        sys.exit(1)

    while True:
        try:
            run_cycle()
        except Exception as e:
            log.error(f"❌ خطأ في الدورة: {e}")

        log.info(f"💤 الانتظار {INTERVAL_HOURS} ساعة...")
        time.sleep(INTERVAL_HOURS * 3600)

# --- نقطة الدخول ---
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("🛑 تم الإيقاف يدوياً.")
┌
