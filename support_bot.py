import asyncio
import os
import logging
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

support_bot = Bot(token=ADMIN_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

client_cache = {}
dialogues = {}        # {user_id: {"username": str, "last_msg": str, "messages": int, "last_time": int}}
last_active = {}      # {user_id: timestamp}
all_clients = set()   # Список всех клиентов для уведомлений
operator_online = False

auto_replies = [
    "Пожалуйста, уточните ваш вопрос подробнее.",
    "Ваш запрос принят, ожидайте ответа оператора.",
    "Мы проверяем информацию по вашему запросу.",
    "Для завершения запроса укажите дополнительные данные."
]

# Главное меню
def support_menu(user_id):
    if user_id == ADMIN_ID:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📂 Диалоги", callback_data="admin_dialogs")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="⚡ Автоответы", callback_data="admin_auto_replies")],
            [InlineKeyboardButton(text="📶 Онлайн/Оффлайн", callback_data="admin_toggle_status")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_admin")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🆘 Помощь", callback_data="client_help")],
            [InlineKeyboardButton(text="👥 Операторы онлайн", callback_data="client_operators")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_client")]
        ])

# Уведомления всем клиентам
async def notify_all_clients(message: str):
    tasks = []
    for uid in all_clients:
        try:
            tasks.append(support_bot.send_message(uid, message))
        except Exception:
            pass
    if tasks:
        await asyncio.gather(*tasks)

# Старт
@dp.message(Command("start"))
async def start_support(msg: types.Message):
    all_clients.add(msg.from_user.id)
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("👑 <b>Режим администратора поддержки.</b>", reply_markup=support_menu(msg.from_user.id))
    else:
        await msg.answer("📞 <b>Вы подключены к поддержке.</b>\nНажмите «Помощь» для обращения.",
                         reply_markup=support_menu(msg.from_user.id))

# Назад
@dp.callback_query(lambda c: c.data.startswith("back_"))
async def go_back(cb: types.CallbackQuery):
    await cb.message.answer("⬅ Главное меню:", reply_markup=support_menu(cb.from_user.id))

# Помощь для клиента
@dp.callback_query(lambda c: c.data == "client_help")
async def client_help(cb: types.CallbackQuery):
    if not operator_online:
        return await cb.message.answer("⚠ Все операторы оффлайн. Попробуйте позже.",
                                       reply_markup=support_menu(cb.from_user.id))
    await cb.message.answer("✍ Напишите свой вопрос, и оператор ответит вам.", reply_markup=support_menu(cb.from_user.id))

# Онлайн/Оффлайн операторов
@dp.callback_query(lambda c: c.data == "client_operators")
async def client_operators(cb: types.CallbackQuery):
    status = "🟢 Онлайн" if operator_online else "🔴 Оффлайн"
    await cb.message.answer(f"👥 <b>Статус операторов:</b> {status}", reply_markup=support_menu(cb.from_user.id))

# Переключение статуса операторов
@dp.callback_query(lambda c: c.data == "admin_toggle_status")
async def toggle_status(cb: types.CallbackQuery):
    global operator_online
    operator_online = not operator_online
    status = "🟢 Онлайн" if operator_online else "🔴 Оффлайн"
    await cb.message.answer(f"✅ Статус изменён: {status}", reply_markup=support_menu(cb.from_user.id))
    await notify_all_clients(f"📢 Операторы теперь {status.lower()}.")

# Сообщение клиента
@dp.message(lambda m: m.from_user.id != ADMIN_ID)
async def forward_to_admin(msg: types.Message):
    global operator_online
    if not operator_online:
        return await msg.answer("⚠ Все операторы оффлайн. Попробуйте позже.")

    uid = msg.from_user.id
    username = msg.from_user.username or "Без ника"
    text = msg.text
    all_clients.add(uid)

    if uid not in dialogues:
        dialogues[uid] = {"username": username, "last_msg": text, "messages": 1, "last_time": time.time()}
    else:
        dialogues[uid]["last_msg"] = text
        dialogues[uid]["messages"] += 1
        dialogues[uid]["last_time"] = time.time()

    last_active[uid] = time.time()
    sent = await support_bot.send_message(
        ADMIN_ID,
        f"📩 <b>Сообщение от @{username}</b> (ID: {uid}):\n\n{text}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Закрыть диалог", callback_data=f"close_dialog_{uid}")]
        ])
    )
    client_cache[sent.message_id] = uid
    await msg.answer("✅ Ваш запрос принят. Оператор ответит в ближайшее время.")

# Ответ админа
@dp.message(lambda m: m.from_user.id == ADMIN_ID)
async def reply_to_client(msg: types.Message):
    if msg.reply_to_message and msg.reply_to_message.message_id in client_cache:
        uid = client_cache[msg.reply_to_message.message_id]
        await support_bot.send_message(uid, f"💬 <b>Ответ от поддержки:</b>\n\n{msg.text}")
        await msg.answer("✅ Ответ отправлен клиенту.")
    else:
        await msg.answer("⚠ Ответьте реплаем на сообщение клиента.")

# Закрыть диалог
@dp.callback_query(lambda c: c.data.startswith("close_dialog_"))
async def close_dialog(cb: types.CallbackQuery):
    uid = int(cb.data.split("_")[2])
    if uid in dialogues:
        await support_bot.send_message(uid, "🔒 Ваш диалог с поддержкой был закрыт.")
        del dialogues[uid]
        await cb.message.answer(f"✅ Диалог с пользователем ID {uid} закрыт.", reply_markup=support_menu(cb.from_user.id))
    else:
        await cb.answer("❌ Диалог уже закрыт.")

# Диалоги
@dp.callback_query(lambda c: c.data == "admin_dialogs")
async def admin_dialogs(cb: types.CallbackQuery):
    if not dialogues:
        return await cb.message.answer("📂 <b>Диалоги пусты.</b>", reply_markup=support_menu(cb.from_user.id))
    text = "📂 <b>Активные диалоги:</b>\n\n"
    for uid, data in dialogues.items():
        time_str = datetime.fromtimestamp(data['last_time']).strftime("%d.%m %H:%M")
        text += f"👤 @{data['username']} (ID: {uid})\n💬 {data['last_msg']}\n🕒 {time_str}\n\n"
    await cb.message.answer(text, reply_markup=support_menu(cb.from_user.id))

# Статистика
@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(cb: types.CallbackQuery):
    if not dialogues:
        return await cb.message.answer("📊 <b>Нет данных для статистики.</b>", reply_markup=support_menu(cb.from_user.id))
    text = "📊 <b>Статистика:</b>\n\n"
    for uid, data in dialogues.items():
        time_str = datetime.fromtimestamp(data['last_time']).strftime("%d.%m %H:%M")
        text += f"👤 @{data['username']} | Сообщений: {data['messages']} | Последнее: {time_str}\n"
    await cb.message.answer(text, reply_markup=support_menu(cb.from_user.id))

# Автоответы
@dp.callback_query(lambda c: c.data == "admin_auto_replies")
async def admin_auto_replies(cb: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=txt[:30] + "..." if len(txt) > 30 else txt, callback_data=f"send_auto_{i}")]
        for i, txt in enumerate(auto_replies)
    ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_admin")])
    await cb.message.answer("⚡ <b>Выберите автоответ:</b>", reply_markup=kb)

# Отправка автоответа
@dp.callback_query(lambda c: c.data.startswith("send_auto_"))
async def send_auto_reply(cb: types.CallbackQuery):
    idx = int(cb.data.split("_")[2])
    if not dialogues:
        return await cb.message.answer("❌ Нет активных диалогов для ответа.", reply_markup=support_menu(cb.from_user.id))
    last_uid = list(dialogues.keys())[-1]
    await support_bot.send_message(last_uid, f"💬 <b>Ответ от поддержки:</b>\n\n{auto_replies[idx]}")
    await cb.message.answer(f"✅ Автоответ отправлен @{dialogues[last_uid]['username']}", reply_markup=support_menu(cb.from_user.id))

# 🚀 Запуск
async def main():
    await dp.start_polling(support_bot)

if __name__ == "__main__":
    asyncio.run(main())
