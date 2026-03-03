import telebot
from telebot import types
import sqlite3
import json
import os

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = '8766592998:AAE-sXbokn0pzoi1CIVhL8ODq4QFSNx9a1o'
WEB_APP_URL = 'https://chmonya-inc.github.io/shuriken/'
ADMIN_IDS = [5136561232, 7124786200]
MAIN_ADMIN = 7124786200

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0,
            username TEXT,
            first_name TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            status TEXT DEFAULT 'pending',
            receipt_message_id INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def get_or_create_user(user_id, username='', first_name=''):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute('INSERT INTO users (user_id, balance, username, first_name) VALUES (?, 0, ?, ?)', 
                      (user_id, username, first_name))
        conn.commit()
        user = (user_id, 0, username, first_name)
    conn.close()
    return user

def update_balance(user_id, amount):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    if result:
        new_balance = result[0] + amount
        cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?', (new_balance, user_id))
        conn.commit()
        conn.close()
        return new_balance
    conn.close()
    return None

def get_balance(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def get_treasury():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(balance) FROM users')
    result = cursor.fetchone()[0]
    conn.close()
    return result if result else 0

def save_deposit_request(user_id, amount):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO deposits (user_id, amount, status) VALUES (?, ?, "pending")', (user_id, amount))
    deposit_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return deposit_id

init_db()
bot = telebot.TeleBot(BOT_TOKEN)

# --- ХРАНИЛИЩЕ СОСТОЯНИЙ ---
user_states = {}
deposit_requests = {}

# --- КЛАВИАТУРЫ ---
def admin_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("💰 Изменить баланс", callback_data="admin_change_balance"))
    markup.add(types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"))
    markup.add(types.InlineKeyboardButton("⚙️ Установить множитель", callback_data="admin_multiplier"))
    return markup

def main_menu_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🚀 Запустить Mini App", web_app=types.WebAppInfo(url=WEB_APP_URL)))
    return markup

def deposit_cancel_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_deposit"))
    return markup

# --- ОБРАБОТЧИКИ ---
@bot.message_handler(commands=['start'])
def start_message(message):
    user_id = message.from_user.id
    username = message.from_user.username or ''
    first_name = message.from_user.first_name or ''
    get_or_create_user(user_id, username, first_name)
    
    text = f"Привет, {message.from_user.first_name}!\n"
    text += "Нажми кнопку ниже, чтобы открыть приложение."
    
    bot.send_message(message.chat.id, text, reply_markup=main_menu_keyboard())

@bot.message_handler(commands=['ap'])
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Доступ запрещён")
        return
    bot.send_message(message.chat.id, "🛠 Админ панель:", reply_markup=admin_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "admin_change_balance")
def admin_change_balance(call):
    if call.from_user.id not in ADMIN_IDS:
        return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📝 Введите ID пользователя:")
    user_states[call.from_user.id] = {'state': 'wait_admin_user_id'}

@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def admin_stats(call):
    if call.from_user.id not in ADMIN_IDS:
        return
    bot.answer_callback_query(call.id)
    treasury = get_treasury()
    bot.send_message(call.message.chat.id, f"📊 Казна бота: {treasury} TON")

@bot.callback_query_handler(func=lambda call: call.data == "admin_multiplier")
def admin_multiplier(call):
    if call.from_user.id not in ADMIN_IDS:
        return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "⚙️ Функция в разработке")

@bot.callback_query_handler(func=lambda call: call.data == "cancel_deposit")
def cancel_deposit(call):
    bot.answer_callback_query(call.id, "Отменено")
    user_id = call.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    if user_id in deposit_requests:
        del deposit_requests[user_id]
    bot.send_message(call.message.chat.id, "❌ Пополнение отменено")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    
    if user_id in user_states and user_states[user_id].get('state') == 'wait_admin_user_id':
        try:
            target_id = int(message.text)
            user_states[user_id]['state'] = 'wait_admin_amount'
            user_states[user_id]['target_id'] = target_id
            bot.send_message(message.chat.id, "💰 Введите сумму для зачисления (TON):")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Неверный ID. Введите число.")
        return
    
    if user_id in user_states and user_states[user_id].get('state') == 'wait_admin_amount':
        try:
            amount = float(message.text)
            target_id = user_states[user_id]['target_id']
            new_balance = update_balance(target_id, amount)
            
            if new_balance is not None:
                bot.send_message(message.chat.id, f"✅ Баланс пользователя {target_id} изменен на {amount} TON\nНовый баланс: {new_balance} TON")
                try:
                    bot.send_message(target_id, f"💰 На ваш баланс поступило {amount} TON")
                except:
                    pass
            else:
                bot.send_message(message.chat.id, "❌ Ошибка обновления")
            
            del user_states[user_id]
        except ValueError:
            bot.send_message(message.chat.id, "❌ Неверная сумма. Введите число.")
        return

@bot.message_handler(content_types=['photo', 'document'])
def handle_receipt(message):
    user_id = message.from_user.id
    
    if user_id in deposit_requests:
        amount = deposit_requests[user_id]
        save_deposit_request(user_id, amount)
        
        bot.send_message(message.chat.id, "✅ Спасибо, мы постараемся как можно скорее рассмотреть заявку на пополнение!")
        
        username = message.from_user.username or str(user_id)
        admin_text = f"📥 Заявка на пополнение на сумму {amount} TON от @{username}"
        bot.send_message(MAIN_ADMIN, admin_text)
        
        bot.forward_message(MAIN_ADMIN, message.chat.id, message.message_id)
        
        del deposit_requests[user_id]
        return

# --- ОБРАБОТКА ДАННЫХ ОТ MINI APP ---
@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    user_id = message.from_user.id
    username = message.from_user.username or ''
    first_name = message.from_user.first_name or ''
    
    print(f"📩 ПОЛУЧЕНЫ ДАННЫЕ ОТ MINI APP от пользователя {user_id}")
    print(f"📦 Данные: {message.web_app_data.data}")
    
    get_or_create_user(user_id, username, first_name)
    
    try:
        data = json.loads(message.web_app_data.data)
        action = data.get('action')
        
        print(f"✅ Действие: {action}")
        
        if action == 'get_balance':
            balance = get_balance(user_id)
            bot.send_message(user_id, f"💰 Ваш баланс: {balance} TON")
            
        elif action == 'deposit_request':
            amount = data.get('amount', 0)
            print(f"💰 Запрос на пополнение: {amount} TON")
            
            deposit_requests[user_id] = amount
            
            bot.send_message(
                user_id, 
                f"📎 Пришлите чек на сумму {amount} TON в тонах, мы вскоре рассмотрим заявку на пополнение",
                reply_markup=deposit_cancel_keyboard()
            )
            print(f"✅ Сообщение отправлено пользователю {user_id}")
            
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка JSON: {e}")
        bot.send_message(user_id, "❌ Ошибка обработки данных")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        bot.send_message(user_id, f"❌ Произошла ошибка: {e}")

@bot.message_handler(commands=['balance'])
def send_balance(message):
    balance = get_balance(message.from_user.id)
    bot.send_message(message.chat.id, f"💰 Ваш баланс: {balance} TON")

@bot.message_handler(commands=['test'])
def test_message(message):
    bot.send_message(message.chat.id, "✅ Бот работает!")

if __name__ == '__main__':
    print("🤖 Бот запущен...")
    print(f"📡 Web App URL: {WEB_APP_URL}")
    bot.infinity_polling()
