import asyncio
import os
import json

from aiogram import Bot, Dispatcher, types
from aiogram.types import BotCommand
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# ======== CONFIG ========
API_TOKEN = '8008249494:AAF3BM3RVpMbm-whf0Vvc8lwGyrKd8z1DTA'
API_ID = 26585593
API_HASH = '0c4742a519fe33ea6b63c2473fb71429'
ADMIN_ID = 7753090895

SESSIONS_DIR = 'sessions'
DATA_FILE = 'data.json'

os.makedirs(SESSIONS_DIR, exist_ok=True)
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'w') as f:
        json.dump({}, f)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ======== SESSION DATA UTILS ========
def load_data():
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def add_session_data(name, info):
    data = load_data()
    data[name] = info
    save_data(data)

def get_all_sessions():
    return load_data()

def remove_session_data(name):
    data = load_data()
    if name in data:
        del data[name]
        save_data(data)
    path = os.path.join(SESSIONS_DIR, f"{name}.session")
    if os.path.exists(path):
        os.remove(path)

# ======== FSM STATES ========
class NewSession(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()

# ======== ADMIN GUARD ========
async def admin_only(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⛔ Bu buyruq faqat admin uchun.")
        return False
    return True

# ======== /start ========
@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    await message.answer(
        "🤖 Avto Guruh Bot\n\n"
        "✅ /newsession - Yangi session qo'shish (ochiq)\n"
        "✅ /sessions - Sessionlar ro'yxatini ko'rish (faqat admin)\n"
        "✅ /remove - Sessionni o'chirish (faqat admin)"
    )

# ======== /newsession ========
@dp.message(Command('newsession'))
async def cmd_newsession(message: types.Message, state: FSMContext):
    await message.answer("📌 Yangi session uchun ism kiriting (masalan: user1):")
    await state.set_state(NewSession.waiting_for_name)

@dp.message(NewSession.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("📱 Telefon raqamingizni kiriting (masalan: +998901234567):")
    await state.set_state(NewSession.waiting_for_phone)

@dp.message(NewSession.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    data = await state.get_data()

    name = data['name']
    phone = data['phone']
    session_file = os.path.join(SESSIONS_DIR, f"{name}.session")
    client = TelegramClient(session_file, API_ID, API_HASH)
    await client.connect()

    try:
        sent = await client.send_code_request(phone)
        await state.update_data(sent=sent)
        await message.answer("✅ Kod yuborildi. Uni kiriting:")
        await client.disconnect()
        await state.set_state(NewSession.waiting_for_code)
    except Exception as e:
        await client.disconnect()
        await message.answer(f"❌ Xato: {e}")
        await state.clear()

@dp.message(NewSession.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data['name']
    phone = data['phone']
    code = message.text.strip()

    session_file = os.path.join(SESSIONS_DIR, f"{name}.session")
    client = TelegramClient(session_file, API_ID, API_HASH)
    await client.connect()

    try:
        await client.sign_in(phone, code)
        await client.disconnect()
        add_session_data(name, {
            'phone_number': phone,
            'status': 'stopped'
        })
        await message.answer(f"✅ Session '{name}' muvaffaqiyatli yaratildi!")
        await state.clear()
    except SessionPasswordNeededError:
        await state.update_data(code=code)
        await client.disconnect()
        await message.answer("🔐 2FA parol kerak. Uni yuboring:")
        await state.set_state(NewSession.waiting_for_password)
    except Exception as e:
        await client.disconnect()
        await message.answer(f"❌ Kod xato yoki boshqa xato: {e}")
        await state.clear()

@dp.message(NewSession.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data['name']
    phone = data['phone']
    code = data['code']
    password = message.text.strip()

    session_file = os.path.join(SESSIONS_DIR, f"{name}.session")
    client = TelegramClient(session_file, API_ID, API_HASH)
    await client.connect()

    try:
        await client.sign_in(phone, code, password=password)
        await client.disconnect()
        add_session_data(name, {
            'phone_number': phone,
            'status': 'stopped'
        })
        await message.answer(f"✅ Session '{name}' muvaffaqiyatli yaratildi!")
    except Exception as e:
        await client.disconnect()
        await message.answer(f"❌ Parol xato yoki boshqa xato: {e}")
    await state.clear()

# ======== /sessions (admin) ========
@dp.message(Command('sessions'))
async def cmd_sessions(message: types.Message):
    if not await admin_only(message): return
    data = get_all_sessions()
    if not data:
        return await message.answer("📭 Sessionlar yo'q.")
    text = "📋 Sessionlar:\n"
    for k, v in data.items():
        text += f"✅ {k}: {v['phone_number']} | Status: {v['status']}\n"
    await message.answer(text)

# ======== /remove (admin) ========
@dp.message(Command('remove'))
async def cmd_remove(message: types.Message):
    if not await admin_only(message): return
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("⚠️ /remove <session_name>")
    name = parts[1]
    remove_session_data(name)
    await message.answer(f"🗑️ Session '{name}' o'chirildi.")

# ======== COMMANDS LIST ========
async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Botni boshlash"),
        BotCommand(command="newsession", description="Yangi session qo'shish (ochiq)"),
        BotCommand(command="sessions", description="Sessionlar ro'yxatini ko'rish (faqat admin)"),
        BotCommand(command="remove", description="Sessionni o'chirish (faqat admin)"),
    ])

# ======== MAIN ========
async def main():
    await set_commands()
    print("✅ Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
