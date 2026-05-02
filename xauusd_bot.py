import os
import time
import logging
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

PAIRS = [
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "AUDUSD", "NZDUSD", "USDCAD", "GBPJPY", "EURJPY", "XAGUSD"
]

KILLZONES = {
    "Asia":   (0, 3),
    "London": (7, 10),
    "NY":     (12, 15),
}

HIGH_IMPACT_NEWS_HOURS = []


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=data, timeout=10)
        log.info(f"Telegram: {r.status_code}")
    except Exception as e:
        log.error(f"خطأ: {e}")


def get_price(pair):
    try:
        if pair == "XAUUSD":
            r = requests.get("https://api.metals.live/v1/spot/gold", timeout=5)
            return round(float(r.json()[0].get("price", 0)), 2)
        elif pair == "XAGUSD":
            r = requests.get("https://api.metals.live/v1/spot/silver", timeout=5)
            return round(float(r.json()[0].get("price", 0)), 2)
        else:
            base = pair[:3]
            quote = pair[3:]
            r = requests.get(f"https://open.er-api.com/v6/latest/{base}", timeout=5)
            data = r.json()
            if data.get("result") == "success":
                return round(float(data["rates"].get(quote, 0)), 5)
    except Exception as e:
        log.error(f"خطأ سعر {pair}: {e}")
    return None


def get_session(hour):
    for name, (start, end) in KILLZONES.items():
        if start <= hour < end:
            return f"🎯 {name} Killzone"
    return None


def is_news_time(hour, minute):
    for news_hour in HIGH_IMPACT_NEWS_HOURS:
        news_minutes = news_hour * 60
        current_minutes = hour * 60 + minute
        if abs(current_minutes - news_minutes) <= 30:
            return True
    return False


def analyze_with_gemini(pair, price, session, time_utc, hour, minute):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

    news_status = "❌ يوجد خبر قريب!" if is_news_time(hour, minute) else "✅ لا يوجد خبر"
    session_status = f"✅ نعم — {session}" if session else "❌ لا"

    prompt = f"""
أنت محلل فوريكس خبير يستخدم استراتيجية ICT / Smart Money الكاملة.

الزوج: {pair}
السعر الحالي: {price}
الوقت: {time_utc} UTC
الجلسة: {session if session else 'خارج Killzone'}

طبق هذه المراحل:

🔴 المرحلة 0: الإطار الكبير
- الاتجاه على Weekly وDaily؟

🔴 المرحلة 1: Daily Bias
- Bias = Bullish / Bearish / Neutral؟
- BOS أو CHOCH؟
- DXY اتجاه؟

🔴 المرحلة 2: حالة السوق
- Trending أم Range؟
- قريب من Weekly High/Low؟

🔴 المرحلة 3: Setup
- Liquidity Sweep؟
- Displacement قوي؟
- MSS أو BOS؟
- FVG واضح؟

🔴 المرحلة 4: منطقة الدخول
- OB أو FVG أو Breaker الأقرب؟
- شمعة التأكيد المطلوبة؟

🔴 المرحلة 5: الفلاتر الـ 6
1. داخل Killzone؟ {session_status}
2. لا يوجد News؟ {news_status}
3. R:R لا يقل عن 1:3؟
4. SMT مع DXY؟
5. HTF Confluence مع 4H أو Daily؟
6. حجم الشمعة أكبر من المتوسط؟

🔴 المرحلة 6: إدارة المخاطر
- Entry:
- SL:
- TP1 (1:2):
- TP2:
- R:R النهائي:

📊 الخلاصة:
- قرار: LONG / SHORT / لا تدخل
- نسبة الثقة: X%
- سبب موجز

⚠️ مخاطرة 1% فقط — صفقة واحدة — انتظر التأكيد.
"""

    body = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(url, json=body, timeout=30)
        result = r.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        log.error(f"خطأ Gemini ({pair}): {e}")
        return None


def main():
    send_message(
        "🤖 <b>بوت الفوريكس AI — يعمل الآن</b>\n\n"
        "📋 الاستراتيجية: ICT / Smart Money\n"
        "🎯 الأزواج: XAUUSD | EURUSD | GBPUSD | USDJPY | وأكثر\n"
        "⏰ Killzones: London 07-10 | NY 12-15 | Asia 00-03 UTC\n\n"
        "✅ البوت يراقب السوق..."
    )

    sent_sessions = {}

    while True:
        now = datetime.now(timezone.utc)
        hour = now.hour
        minute = now.minute
        time_utc = now.strftime("%H:%M")
        session = get_session(hour)
        session_key = f"{now.date()}_{session}"

        if not session:
            log.info("خارج Killzone — انتظار...")
            time.sleep(300)
            continue

        if is_news_time(hour, minute):
            send_message("⚠️ <b>خبر مهم قريب — البوت متوقف 30 دقيقة</b>")
            time.sleep(1800)
            continue

        for pair in PAIRS:
            pair_key = f"{pair}_{session_key}"
            if pair_key in sent_sessions:
                continue

            price = get_price(pair)
            if not price:
                continue

            log.info(f"تحليل {pair} @ {price}")
            analysis = analyze_with_gemini(pair, price, session, time_utc, hour, minute)

            if analysis:
                header = f"📊 <b>تحليل {pair}</b>\n💰 السعر: <b>{price}</b>\n🕐 {time_utc} UTC\n📍 {session}\n{'='*25}\n\n"
                msg = header + analysis
                if len(msg) > 4000:
                    send_message(msg[:4000])
                    time.sleep(2)
                    send_message(msg[4000:])
                else:
                    send_message(msg)
                sent_sessions[pair_key] = True
                time.sleep(5)

        time.sleep(60)


if __name__ == "__main__":
    main()
