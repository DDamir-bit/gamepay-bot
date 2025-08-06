import asyncio
import json
import os
import time
import logging
import re
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# 🔑 Конфиг
CLIENT_TOKEN = os.getenv("CLIENT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

MENU_PHOTO = "https://i.ibb.co/5g1VNg9P/menu.jpg"
GAME_PHOTOS = {
    "Roblox": "https://th.bing.com/th/id/R.076d146437ffc79cebc36bf2ded91196?rik=C%2f9D3lpgvSBUiw&pid=ImgRaw&r=0",
    "Free Fire": "https://dl.dir.freefiremobile.com/common/web_event/official2.ff.garena.all/20236/5393e837d1d7a223f0e3d024054de618.jpg",
    "Brawl Stars": "https://supercell.com/images/1a5b69311180a4a1c374e10556941f05/hero_bg_brawlstars.a385872a.jpg",
    "Clash Royale": "https://th.bing.com/th/id/R.32edca680f22f3a9af3a1c337a3e815d?rik=9FhK2PEi8c4psQ&pid=ImgRaw&r=0"
}

ORDERS_FILE = "orders.json"
orders = {}
archive = []

PRICE_PER_ROBUX_RUB = 0.85
PRICE_PER_ROBUX_KZT = 5.7

FREE_FIRE_PACKS = {100: 90, 310: 270, 520: 450, 1060: 900, 2180: 1800, 5600: 4600}
BRAWL_PACKS = {30: 360, 80: 800, 170: 1600, 360: 3000, 950: 5000, 2000: 10000}
CLASH_PACKS = {80: 100, 500: 500, 1200: 1000, 2500: 2000, 6500: 5000}

ORDER_LIFETIME = 600
ROBLOX_STOCK = 20000

GAMES = {
    "Roblox": ["Log+Pass", "GamePass"],
    "Free Fire": ["Player ID"],
    "Brawl Stars": ["Player Tag"],
    "Clash Royale": ["Player Tag"]
}

bot = Bot(token=CLIENT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)

# === FSM ===
class OrderStates(StatesGroup):
    game = State()
    method = State()
    nickname = State()
    password = State()
    robux = State()
    package = State()
    currency = State()
    payment = State()

# === Сохранение/загрузка заказов ===
def save_orders():
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump({"orders": orders, "archive": archive}, f, ensure_ascii=False, indent=4)

def load_orders():
    global orders, archive
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            orders.update(data.get("orders", {}))
            archive.extend(data.get("archive", []))

def cleanup_orders():
    now = time.time()
    expired = [oid for oid, o in orders.items() if now - o['timestamp'] > ORDER_LIFETIME and o['status'] != 'На подтверждении']
    for oid in expired:
        archive.append(orders.pop(oid))
    save_orders()

# === Валидация ника ===
def validate_nickname(game, value):
    value = value.strip()
    if game == "Free Fire":
        digits = re.sub(r"\s", "", value)
        return digits.isdigit() and len(digits) == 10
    elif game in ["Brawl Stars", "Clash Royale"]:
        return value.startswith("#") and 4 <= len(value) <= 15
    elif game == "Roblox":
        return re.fullmatch(r"^[A-Za-z0-9_]{3,20}$", value) is not None
    return False

# === Главное меню ===
def main_menu(user_id):
    buttons = [
        [InlineKeyboardButton(text="🛒 Сделать заказ", callback_data="order")],
        [InlineKeyboardButton(text="📦 Мои заказы", callback_data="my_orders")],
        [InlineKeyboardButton(text="📢 Отзывы", web_app=WebAppInfo(url="https://ddamir-bit.github.io/GamePayreview/"))],
        [InlineKeyboardButton(text="📞 Поддержка", url="https://t.me/gpadmin4_bot")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# === Команда /start ===
@dp.message(Command("start"))
async def start_client(msg: types.Message):
    await msg.answer_photo(MENU_PHOTO,
        caption="🎮 <b>Добро пожаловать в GamePay!</b>\n💸 Быстрый и безопасный донат.\n👇 Выберите действие:",
        reply_markup=main_menu(msg.from_user.id))

# === Выбор игры ===
@dp.callback_query(lambda c: c.data == "order")
async def choose_game(cb: types.CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=g, callback_data=f"game_{g}")] for g in GAMES])
    await state.set_state(OrderStates.game)
    await cb.message.answer_photo(MENU_PHOTO, caption="🎮 <b>Выберите игру:</b>", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("game_"))
async def choose_method(cb: types.CallbackQuery, state: FSMContext):
    game = cb.data.split("_", 1)[1]
    await state.update_data(game=game)
    methods = GAMES[game]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=m, callback_data=f"method_{m}")] for m in methods])
    stock = f"\n📦 Наличие: {ROBLOX_STOCK} робуксов" if game == "Roblox" else ""
    await state.set_state(OrderStates.method)
    await cb.message.answer_photo(GAME_PHOTOS[game], caption=f"🎯 {game}{stock}\nВыберите метод:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("method_"))
async def input_nickname(cb: types.CallbackQuery, state: FSMContext):
    method = cb.data.split("_", 1)[1]
    data = await state.get_data()
    oid = str(int(time.time()))
    orders[oid] = {
        "id": oid,
        "user_id": cb.from_user.id,
        "username": cb.from_user.username,
        "game": data["game"],
        "method": method,
        "status": "Ожидает данных",
        "timestamp": time.time()
    }
    save_orders()
    await state.update_data(order_id=oid)
    await state.set_state(OrderStates.nickname)
    await cb.message.answer(f"📝 Введите ник/ID ({'c #' if data['game'] in ['Brawl Stars','Clash Royale'] else ''}):")

# === Никнейм ===
@dp.message(OrderStates.nickname)
async def process_nickname(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    oid = data["order_id"]
    order = orders[oid]
    if not validate_nickname(order["game"], msg.text):
        return await msg.answer("❌ Неверный формат. Попробуйте снова.")
    order["nickname"] = msg.text.strip()

    if order["method"] == "Log+Pass":
        await state.set_state(OrderStates.password)
        await msg.answer("🔑 Введите пароль от аккаунта Roblox:")
    elif order["game"] == "Roblox":
        await state.set_state(OrderStates.robux)
        await msg.answer(f"💰 Введите количество робуксов (доступно: {ROBLOX_STOCK})")
    else:
        packs = FREE_FIRE_PACKS if order["game"]=="Free Fire" else BRAWL_PACKS if order["game"]=="Brawl Stars" else CLASH_PACKS
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{k} за {v}₽", callback_data=f"pack_{oid}_{k}_{v}")] for k,v in packs.items()
        ])
        await state.set_state(OrderStates.package)
        await msg.answer("💎 Выберите пакет:", reply_markup=kb)
    save_orders()

# === Пароль Roblox ===
@dp.message(OrderStates.password)
async def process_password(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    order = orders[data["order_id"]]
    order["password"] = msg.text.strip()
    await state.set_state(OrderStates.robux)
    await msg.answer(f"💰 Введите количество робуксов (доступно: {ROBLOX_STOCK})")
    save_orders()

# === Робуксы ===
@dp.message(OrderStates.robux)
async def process_robux(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit():
        return await msg.answer("❌ Введите число!")
    robux = int(msg.text)
    data = await state.get_data()
    order = orders[data["order_id"]]
    if robux > ROBLOX_STOCK:
        return await msg.answer(f"❌ Превышает наличие ({ROBLOX_STOCK})")
    order["robux"] = robux
    await state.set_state(OrderStates.currency)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 ЮMoney (₽)", callback_data="pay_rub")],
        [InlineKeyboardButton(text="🇰🇿 Kaspi (₸)", callback_data="pay_kzt")]
    ])
    await msg.answer("💳 Выберите валюту оплаты:", reply_markup=kb)
    save_orders()

# === Пакеты ===
@dp.callback_query(lambda c: c.data.startswith("pack_"))
async def select_pack(cb: types.CallbackQuery, state: FSMContext):
    _, oid, amount, price = cb.data.split("_")
    order = orders[oid]
    order["robux"] = int(amount)
    order["price"] = int(price)
    await state.set_state(OrderStates.currency)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 ЮMoney (₽)", callback_data="pay_rub")],
        [InlineKeyboardButton(text="🇰🇿 Kaspi (₸)", callback_data="pay_kzt")]
    ])
    await cb.message.answer("💳 Выберите валюту оплаты:", reply_markup=kb)

# === Выбор валюты ===
        # === Выбор валюты ===
            # === Выбор валюты ===
@dp.callback_query(lambda c: c.data.startswith("pay_"), OrderStates.currency)
async def choose_currency(cb: types.CallbackQuery, state: FSMContext):
                currency = "₽" if cb.data.endswith("rub") else "₸"
                data = await state.get_data()
                order = orders[data["order_id"]]
                order["currency"] = currency

                # 💵 Цена
                if order["game"] == "Roblox":
                    price = order["robux"] * (PRICE_PER_ROBUX_RUB if currency == "₽" else PRICE_PER_ROBUX_KZT)
                else:
                    price = order["price"]
                    if currency == "₸":  # Конвертация для других игр
                        price *= 6

                order["price"] = price
                order["status"] = "Ожидает оплаты"
                save_orders()

                await state.set_state(OrderStates.payment)
                await cb.message.answer_photo(
                    GAME_PHOTOS[order["game"]],
                    caption=(f"🛒 <b>Заказ #{order['id']}</b>\n🎮 {order['game']}\n👤 Ник: {order['nickname']}\n"
                             f"💎 Сумма: {price} {currency}\n\n🚨 Оплатите в течение 10 минут!\n\n"
                             "💳 Реквизиты:\n• ЮMoney: 5599 0020 8114 9975\n• Kaspi: +4400 4303 8120 7254\n\n"
                             "📤 После оплаты отправьте чек (скриншот) сюда."),
                )




# === Приём чека ===
@dp.message(OrderStates.payment)
async def receive_check(msg: types.Message, state: FSMContext):
    if not msg.photo:
        return await msg.answer("❌ Пришлите фото чека!")
    data = await state.get_data()
    order = orders[data["order_id"]]
    order["check"] = msg.photo[-1].file_id
    order["status"] = "На подтверждении"
    save_orders()

    kb_admin = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{order['id']}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_{order['id']}")]
    ])
    await msg.answer("✅ Чек получен, ждите подтверждения!")
    await bot.send_photo(
        ADMIN_ID, msg.photo[-1].file_id,
        caption=(f"🚨 Новый заказ #{order['id']}\n🎮 {order['game']}\n👤 {order['nickname']}\n"
                 f"{'🔑 Пароль: '+order.get('password','') if order['method']=='Log+Pass' else ''}\n"
                 f"💎 Сумма: {order['price']} {order['currency']}"),
        reply_markup=kb_admin
    )
    await state.clear()

# === Принятие или отклонение заказа админом ===
@dp.callback_query(lambda c: c.data.startswith("accept_") or c.data.startswith("decline_"))
async def handle_admin_decision(cb: types.CallbackQuery):
    oid = cb.data.split("_")[1]
    order = orders.get(oid)
    if not order:
        return await cb.answer("❌ Заказ не найден.")

    if cb.data.startswith("accept_"):
        order["status"] = "✅ Подтверждён"
        await bot.send_message(order["user_id"], f"✅ Ваш заказ #{oid} подтверждён и будет выполнен!")
        await cb.message.edit_caption(cb.message.caption + "\n\n✅ Заказ подтверждён!", reply_markup=None)
    else:
        order["status"] = "❌ Отклонён"
        await bot.send_message(order["user_id"], f"❌ Ваш заказ #{oid} отклонён. Свяжитесь с поддержкой.")
        await cb.message.edit_caption(cb.message.caption + "\n\n❌ Заказ отклонён.", reply_markup=None)

    save_orders()
    await cb.answer("Готово!")

# === Просмотр заказов пользователя ===
@dp.callback_query(lambda c: c.data == "my_orders")
async def show_orders(cb: types.CallbackQuery):
    user_orders = [o for o in orders.values() if o["user_id"] == cb.from_user.id]
    if not user_orders:
        return await cb.message.answer("📦 У вас пока нет активных заказов.")
    text = "📦 <b>Ваши заказы:</b>\n\n"
    for o in user_orders:
        text += f"🆔 #{o['id']} | 🎮 {o['game']} | 💎 {o.get('robux','')} | Статус: {o['status']}\n"
    await cb.message.answer(text)

# === Запуск ===
async def main():
    load_orders()
    asyncio.create_task(order_cleanup_loop())
    await dp.start_polling(bot)

async def order_cleanup_loop():
    while True:
        cleanup_orders()
        await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(main())
