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
TWELVE_KEY = os.getenv("TWELVE_DATA_KEY")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

PAIRS = [
    "XAU/USD", "EUR/USD", "GBP/USD", "USD/JPY",
    "USD/CHF", "AUD/USD", "NZD/USD", "USD/CAD",
    "GBP/JPY", "EUR/JPY"
]

KILLZONES = {
    "Asia":   (0, 3),
    "London": (7, 10),
    "NY":     (12, 15),
}


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=data, timeout=10)
        log.info(f"Telegram: {r.status_code}")
    except Exception as e:
        log.error(f"خطأ إرسال: {e}")


def get_candles(pair, interval="1h", outputsize=50):
    """جلب بيانات OHLC الحقيقية من Twelve Data"""
    try:
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": pair,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": TWELVE_KEY,
            "format": "JSON"
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data.get("status") == "ok":
            return data["values"]  # قائمة شموع OHLC
    except Exception as e:
        log.error(f"خطأ Twelve Data ({pair}): {e}")
    return None


def calculate_indicators(candles):
    """حساب المؤشرات الحقيقية من بيانات الشموع"""
    if not candles or len(candles) < 10:
        return None

    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    opens = [float(c["open"]) for c in candles]
    volumes = [float(c.get("volume", 0)) for c in candles]

    current = closes[0]
    prev_close = closes[1]

    # ✅ BOS — Break of Structure
    recent_high = max(highs[1:6])
    recent_low = min(lows[1:6])
    bos_bullish = current > recent_high
    bos_bearish = current < recent_low

    # ✅ FVG — Fair Value Gap
    fvg_bullish = lows[0] > highs[2]   # gap صاعد
    fvg_bearish = highs[0] < lows[2]   # gap هابط

    # ✅ OB — Order Block (آخر شمعة عكسية قبل اندفاع)
    ob_bullish = opens[1] > closes[1] and current > highs[1]
    ob_bearish = opens[1] < closes[1] and current < lows[1]

    # ✅ Liquidity Sweep
    sweep_high = highs[0] > max(highs[1:4]) and closes[0] < max(highs[1:4])
    sweep_low = lows[0] < min(lows[1:4]) and closes[0] > min(lows[1:4])

    # ✅ Displacement — شموع قوية متتالية
    displacement_up = all(closes[i] > opens[i] for i in range(3))
    displacement_down = all(closes[i] < opens[i] for i in range(3))

    # ✅ Bias اليومي
    avg_20 = sum(closes[:20]) / 20
    bias = "Bullish" if current > avg_20 else "Bearish"

    # ✅ حجم الشمعة
    avg_volume = sum(volumes[1:10]) / 9 if volumes[1] > 0 else 0
    strong_volume = volumes[0] > avg_volume * 1.2 if avg_volume > 0 else True

    # ✅ Weekly High/Low (تقريبي من آخر 120 شمعة H1)
    weekly_high = max(highs[:120]) if len(highs) >= 120 else max(highs)
    weekly_low = min(lows[:120]) if len(lows) >= 120 else min(lows)
    near_weekly_high = current > weekly_high * 0.998
    near_weekly_low = current < weekly_low * 1.002

    # ✅ ATR للـ SL و TP
    atr = sum([highs[i] - lows[i] for i in range(14)]) / 14

    return {
        "current": current,
        "prev_close": prev_close,
        "bias": bias,
        "bos_bullish": bos_bullish,
        "bos_bearish": bos_bearish,
        "fvg_bullish": fvg_bullish,
        "fvg_bearish": fvg_bearish,
        "ob_bullish": ob_bullish,
        "ob_bearish": ob_bearish,
        "sweep_high": sweep_high,
        "sweep_low": sweep_low,
        "displacement_up": displacement_up,
        "displacement_down": displacement_down,
        "strong_volume": strong_volume,
        "near_weekly_high": near_weekly_high,
        "near_weekly_low": near_weekly_low,
        "atr": atr,
        "recent_high": recent_high,
        "recent_low": recent_low,
    }


def get_session(hour):
    for name, (start, end) in KILLZONES.items():
        if start <= hour < end:
            return name
    return None


def analyze_pair(pair, ind, session, time_utc):
    """تحليل كامل بناءً على الاستراتيجية ICT"""
    if not ind:
        return None

    price = ind["current"]
    atr = ind["atr"]

    # تحديد الاتجاه
    if ind["bias"] == "Bullish" and ind["bos_bullish"]:
        direction = "LONG"
        confidence = 0
        reasons = []

        if ind["sweep_low"]: confidence += 25; reasons.append("✅ Liquidity Sweep")
        if ind["displacement_up"]: confidence += 20; reasons.append("✅ Displacement صاعد")
        if ind["fvg_bullish"]: confidence += 20; reasons.append("✅ FVG صاعد")
        if ind["ob_bullish"]: confidence += 15; reasons.append("✅ OB صاعد")
        if ind["strong_volume"]: confidence += 10; reasons.append("✅ حجم قوي")
        if not ind["near_weekly_high"]: confidence += 10; reasons.append("✅ بعيد عن Weekly High")

        entry = price
        sl = price - (atr * 1.5)
        tp1 = price + (atr * 2)
        tp2 = price + (atr * 4)

    elif ind["bias"] == "Bearish" and ind["bos_bearish"]:
        direction = "SHORT"
        confidence = 0
        reasons = []

        if ind["sweep_high"]: confidence += 25; reasons.append("✅ Liquidity Sweep")
        if ind["displacement_down"]: confidence += 20; reasons.append("✅ Displacement هابط")
        if ind["fvg_bearish"]: confidence += 20; reasons.append("✅ FVG هابط")
        if ind["ob_bearish"]: confidence += 15; reasons.append("✅ OB هابط")
        if ind["strong_volume"]: confidence += 10; reasons.append("✅ حجم قوي")
        if not ind["near_weekly_low"]: confidence += 10; reasons.append("✅ بعيد عن Weekly Low")

        entry = price
        sl = price + (atr * 1.5)
        tp1 = price - (atr * 2)
        tp2 = price - (atr * 4)

    else:
        return None  # لا يوجد setup واضح

    # فلتر الثقة — لا ترسل إذا أقل من 60%
    if confidence < 60:
        return None

    rr = round((atr * 2) / (atr * 1.5), 2)

    # تنسيق الرسالة
    emoji = "🟢" if direction == "LONG" else "🔴"
    pair_display = pair.replace("/", "")

    msg = f"""
{emoji} <b>إشارة {direction} — {pair_display}</b>
📍 {session} Killzone | 🕐 {time_utc} UTC

💰 السعر: <b>{round(price, 5)}</b>

📊 <b>التحليل ICT:</b>
• Bias: {ind['bias']}
• BOS: {'✅' if ind['bos_bullish'] or ind['bos_bearish'] else '❌'}
• FVG: {'✅' if ind['fvg_bullish'] or ind['fvg_bearish'] else '❌'}
• OB: {'✅' if ind['ob_bullish'] or ind['ob_bearish'] else '❌'}
• Liquidity Sweep: {'✅' if ind['sweep_low'] or ind['sweep_high'] else '❌'}
• Displacement: {'✅' if ind['displacement_up'] or ind['displacement_down'] else '❌'}

🎯 <b>نقاط التداول:</b>
• Entry: <b>{round(entry, 5)}</b>
• SL: <b>{round(sl, 5)}</b>
• TP1 (1:2): <b>{round(tp1, 5)}</b>
• TP2 (1:4): <b>{round(tp2, 5)}</b>
• R:R: 1:{rr}

✅ <b>الفلاتر:</b>
{chr(10).join(reasons)}

🔥 نسبة الثقة: <b>{confidence}%</b>

⚠️ مخاطرة 1% فقط — انتظر تأكيد الشمعة
"""
    return msg


def main():
    send_message(
        "🤖 <b>بوت الفوريكس AI — يعمل الآن</b>\n\n"
        "📋 الاستراتيجية: ICT / Smart Money\n"
        "📡 البيانات: Twelve Data (OHLC حقيقية)\n"
        "🎯 الأزواج: 10 أزواج فوريكس + ذهب\n"
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

        for pair in PAIRS:
            pair_key = f"{pair}_{session_key}"
            if pair_key in sent_sessions:
                continue

            # جلب بيانات H1 وH4
            candles_h1 = get_candles(pair, "1h", 50)
            if not candles_h1:
                log.warning(f"لا بيانات لـ {pair}")
                time.sleep(5)
                continue

            ind = calculate_indicators(candles_h1)
            msg = analyze_pair(pair, ind, session, time_utc)

            if msg:
                send_message(msg)
                sent_sessions[pair_key] = True
            else:
                log.info(f"لا setup لـ {pair}")

            time.sleep(3)

        time.sleep(300)  # فحص كل 5 دقائق


if __name__ == "__main__":
    main()
