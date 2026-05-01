import requests
import time
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

# ═══════════════════════════════════════════
#  تحميل المتغيرات من ملف .env
# ═══════════════════════════════════════════
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")
CAPITAL   = float(os.getenv("CAPITAL", 1000))

if not BOT_TOKEN or not CHAT_ID:
    raise ValueError("❌ BOT_TOKEN أو CHAT_ID غير موجودين في ملف .env")

# ═══════════════════════════════════════════
#  متغيرات الحالة
# ═══════════════════════════════════════════
daily_loss_pct     = 0.0
consecutive_losses = 0
trades_today       = 0
bot_stopped        = False

# ═══════════════════════════════════════════
#  إرسال رسالة Telegram
# ═══════════════════════════════════════════
def send(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    })

# ═══════════════════════════════════════════
#  1. فحص Killzone (London / NY)
# ═══════════════════════════════════════════
def check_killzone():
    now  = datetime.now(timezone.utc)
    hour = now.hour

    if 7 <= hour < 10:
        return "🇬🇧 London Killzone", True

    if 12 <= hour < 15:
        return "🇺🇸 New York Killzone", True

    return None, False

# ═══════════════════════════════════════════
#  2. فحص أخبار Forex Factory (مبسط)
# ═══════════════════════════════════════════
def check_news():
    now = datetime.now(timezone.utc)
    high_impact_hours = [14, 15, 18, 20]

    for h in high_impact_hours:
        news_time = now.replace(hour=h, minute=30, second=0)
        diff = abs((news_time - now).total_seconds() / 60)
        if diff <= 30:
            return True, f"⚠️ خبر USD قريب ({h}:30 UTC)"

    return False, None

# ═══════════════════════════════════════════
#  3. جلب سعر XAUUSD
# ═══════════════════════════════════════════
def get_price():
    try:
        r = requests.get("https://api.metals.live/v1/spot/gold", timeout=5)
        return round(r.json()["price"], 2)
    except:
        return None

# ═══════════════════════════════════════════
#  4. Checklist كاملة
# ═══════════════════════════════════════════
def build_checklist(killzone_name, price):
    now         = datetime.now(timezone.utc)
    risk_amount = round(CAPITAL * 0.01, 2)

    checklist = f"""
📋 <b>CHECKLIST — XAUUSD</b>
🕐 {now.strftime('%H:%M')} UTC

💰 السعر الحالي: <b>{price}$</b>
📍 الجلسة: <b>{killzone_name}</b>

━━━━━━━━━━━━━━━━━━━
<b>✅ فلاتر الدخول — راجع يدوياً:</b>

1️⃣ Daily Bias محدد؟ (Bullish / Bearish)
   → افتح Daily وتحقق من BOS/CHOCH

2️⃣ Liquidity Sweep واضح؟
   → هل تم كسر High/Low سابق؟

3️⃣ Displacement قوي؟ (+3 شمعات)
   → هل في اندفاع قوي بعد السويب؟

4️⃣ FVG أو OB واضح؟
   → حدد المنطقة على الشارت

5️⃣ شمعة تأكيد؟
   → Engulfing أو Pinbar أو Strong Close

6️⃣ HTF Confluence؟ (4H أو Daily)
   → هل الـ 4H يوافق؟

7️⃣ SMT مع DXY؟
   → افتح DXY وقارن

━━━━━━━━━━━━━━━━━━━
<b>📊 إدارة المخاطر:</b>
💵 رأس المال: {CAPITAL}$
⚠️ مخاطرة 1%: <b>{risk_amount}$</b>
🎯 R:R لا يقل عن 1:3
📌 TP1 عند 1:2 → أغلق 50%
📌 انقل SL إلى Breakeven
📌 TP2 عند Liquidity Pool التالية

━━━━━━━━━━━━━━━━━━━
<b>📈 إحصائيات اليوم:</b>
🔢 صفقات اليوم: {trades_today}
📉 خسارة اليوم: {daily_loss_pct}%
🔴 خسائر متتالية: {consecutive_losses}

━━━━━━━━━━━━━━━━━━━
⚡ <b>القرار النهائي لك أنت!</b>
لا تدخل إلا إذا ✅ كل النقاط
    """
    return checklist

# ═══════════════════════════════════════════
#  5. تحذير إيقاف
# ═══════════════════════════════════════════
def send_stop_warning(reason):
    msg = f"""
🛑 <b>STOP TRADING — توقف الآن!</b>

❌ السبب: {reason}

قواعدك تقول: توقف فوراً!
لا تفتح أي صفقة جديدة اليوم 🚫
    """
    send(msg)

# ═══════════════════════════════════════════
#  الحلقة الرئيسية
# ═══════════════════════════════════════════
def main():
    global bot_stopped, daily_loss_pct, consecutive_losses, trades_today

    send("🤖 <b>بوت XAUUSD شغّال!</b>\nسيرسل تنبيهات Killzone تلقائياً ✅")

    last_reset = datetime.now(timezone.utc).date()

    while True:
        now_date = datetime.now(timezone.utc).date()

        # ريست يومي منتصف الليل
        if now_date != last_reset:
            daily_loss_pct     = 0.0
            consecutive_losses = 0
            trades_today       = 0
            bot_stopped        = False
            last_reset         = now_date
            send("🌅 <b>يوم جديد!</b> تم ريست الإحصائيات ✅")

        if bot_stopped:
            time.sleep(60)
            continue

        if consecutive_losses >= 2:
            bot_stopped = True
            send_stop_warning("خسرت صفقتين متتاليتين")
            time.sleep(60)
            continue

        if daily_loss_pct >= 3.0:
            bot_stopped = True
            send_stop_warning(f"تجاوزت 3% خسارة يومية ({daily_loss_pct}%)")
            time.sleep(60)
            continue

        killzone_name, in_killzone = check_killzone()

        if in_killzone:
            has_news, news_msg = check_news()

            if has_news:
                send(f"⚠️ <b>Killzone نشطة لكن...</b>\n{news_msg}\n\n🚫 انتظر انتهاء الخبر!")
            else:
                price = get_price()
                if price:
                    checklist = build_checklist(killzone_name, price)
                    send(checklist)

        time.sleep(300)

if __name__ == "__main__":
    main()
