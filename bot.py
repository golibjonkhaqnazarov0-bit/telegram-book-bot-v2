import os
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
import sqlite3

# ============ KONFIGURATSIYA ============
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
REQUIRED_CHANNEL = "@kitoblarim_77_7"

# Botni ishga tushirish
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
logging.basicConfig(level=logging.INFO)

# ============ MA'LUMOTLAR BAZASI ============
conn = sqlite3.connect('kitob_platforma.db', check_same_thread=False)
c = conn.cursor()

# Barcha jadvallar
c.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    balance INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    exp INTEGER DEFAULT 0,
    referrer_id INTEGER,
    created_at TIMESTAMP,
    last_active TIMESTAMP,
    is_blocked INTEGER DEFAULT 0,
    is_admin INTEGER DEFAULT 0
)''')

c.execute('''CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    author TEXT,
    category TEXT,
    description TEXT,
    file_id TEXT,
    rating REAL DEFAULT 0,
    downloads INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    is_premium INTEGER DEFAULT 0,
    created_at TIMESTAMP
)''')

c.execute('''CREATE TABLE IF NOT EXISTS user_books (
    user_id INTEGER,
    book_id INTEGER,
    downloaded_at TIMESTAMP,
    rating INTEGER DEFAULT 0
)''')

c.execute('''CREATE TABLE IF NOT EXISTS premium_users (
    user_id INTEGER PRIMARY KEY,
    expire_date TIMESTAMP
)''')

c.execute('''CREATE TABLE IF NOT EXISTS referrals (
    user_id INTEGER,
    referred_id INTEGER,
    created_at TIMESTAMP
)''')

c.execute('''CREATE TABLE IF NOT EXISTS user_activity (
    user_id INTEGER,
    activity_date DATE,
    points INTEGER DEFAULT 0
)''')

c.execute('''CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    user_name TEXT,
    message TEXT,
    created_at TIMESTAMP,
    is_answered INTEGER DEFAULT 0,
    answer TEXT,
    answered_at TIMESTAMP
)''')

c.execute('''CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    content TEXT,
    created_at TIMESTAMP
)''')

c.execute('''CREATE TABLE IF NOT EXISTS leaderboard (
    user_id INTEGER PRIMARY KEY,
    total_points INTEGER DEFAULT 0
)''')

# Admin sozlamalari
c.execute("INSERT OR IGNORE INTO users (id, username, full_name, is_admin, created_at) VALUES (?, ?, ?, ?, ?)",
          (ADMIN_ID, "admin", "Administrator", 1, datetime.now()))
conn.commit()

# ============ HOLATLAR ============
class AddBookState(StatesGroup):
    title = State()
    author = State()
    category = State()
    description = State()
    file = State()
    is_premium = State()

# ============ YORDAMCHI FUNKSIYALAR ============
async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def add_points(user_id, points):
    c.execute("UPDATE users SET balance = balance + ? WHERE id=?", (points, user_id))
    c.execute("UPDATE leaderboard SET total_points = total_points + ? WHERE user_id=?", (points, user_id))
    if c.rowcount == 0:
        c.execute("INSERT INTO leaderboard (user_id, total_points) VALUES (?, ?)", (user_id, points))
    conn.commit()
    
    c.execute("SELECT balance FROM users WHERE id=?", (user_id,))
    res = c.fetchone()
    if res:
        balance = res[0]
        new_level = balance // 500 + 1
        c.execute("UPDATE users SET level = ? WHERE id=?", (new_level, user_id))
        conn.commit()

async def check_premium(user_id):
    c.execute("SELECT expire_date FROM premium_users WHERE user_id=? AND expire_date > datetime('now')", (user_id,))
    return c.fetchone() is not None

async def give_premium(user_id, days=30):
    expire_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("INSERT OR REPLACE INTO premium_users (user_id, expire_date) VALUES (?, ?)", (user_id, expire_date))
    conn.commit()

def log_activity(user_id):
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute("INSERT OR REPLACE INTO user_activity (user_id, activity_date, points) VALUES (?, ?, COALESCE((SELECT points FROM user_activity WHERE user_id=? AND activity_date=?), 0) + 1)",
              (user_id, today, user_id, today))
    conn.commit()

def format_datetime(dt_str):
    if not dt_str:
        return "Noma'lum"
    try:
        if isinstance(dt_str, str):
            if '.' in dt_str:
                dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S.%f')
            else:
                dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
        else:
            dt = dt_str
        return dt.strftime('%d.%m.%Y %H:%M')
    except:
        return str(dt_str)[:16]

# ============ ASOSIY MENYU KNOPKALARI ============
def get_main_keyboard(user_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📚 KITOBLAR", callback_data="show_books"),
        InlineKeyboardButton("🔍 QIDIRISH", callback_data="search_menu"),
        InlineKeyboardButton("⭐ TAVSIYALAR", callback_data="recommend_books"),
        InlineKeyboardButton("🏆 TOP USERS", callback_data="leaderboard_menu"),
        InlineKeyboardButton("🎮 DARAJAM", callback_data="my_level"),
        InlineKeyboardButton("💎 PREMIUM", callback_data="premium_menu"),
        InlineKeyboardButton("👥 DO'ST TAKLIF", callback_data="referral_menu"),
        InlineKeyboardButton("⚡ KUNLIK BONUS", callback_data="daily_bonus")
    )
    
    if user_id == ADMIN_ID:
        keyboard.add(InlineKeyboardButton("🛠 ADMIN PANEL", callback_data="admin_panel"))
    else:
        keyboard.add(InlineKeyboardButton("📞 ADMINGA MUROJAAT", callback_data="contact_admin"))
    
    keyboard.add(
        InlineKeyboardButton("💬 YORDAM", callback_data="help_menu"),
        InlineKeyboardButton("👤 PROFILIM", callback_data="my_profile")
    )
    return keyboard

def get_admin_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📊 STATISTIKA", callback_data="admin_stats"),
        InlineKeyboardButton("👥 FOYDALANUVCHILAR", callback_data="admin_users_list"),
        InlineKeyboardButton("💬 XABARLAR", callback_data="admin_messages_list"),
        InlineKeyboardButton("➕ KITOB QO'SHISH", callback_data="admin_add_book"),
        InlineKeyboardButton("📚 KITOBLAR RO'YXATI", callback_data="admin_books_list"),
        InlineKeyboardButton("🚫 BLOKLANGANLAR", callback_data="admin_blocked_list"),
        InlineKeyboardButton("💎 PREMIUM BERISH", callback_data="admin_give_premium"),
        InlineKeyboardButton("📢 E'LON YUBORISH", callback_data="admin_announcement"),
        InlineKeyboardButton("📤 XABAR YOZISH", callback_data="admin_send_message"),
        InlineKeyboardButton("◀️ ORQAGA", callback_data="admin_panel_back")
    )
    return keyboard

# ============ START BUYRUG'I ============
@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    user_id = message.from_user.id
    
    c.execute("SELECT is_blocked FROM users WHERE id=?", (user_id,))
    blocked = c.fetchone()
    if blocked and blocked[0] == 1:
        await message.answer("❌ Siz botdan bloklangansiz!\nAdmin bilan bog'lanishingiz mumkin.")
        return
    
    referrer_id = None
    if len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
            if referrer_id == user_id:
                referrer_id = None
        except:
            pass
    
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    if not c.fetchone():
        c.execute("INSERT INTO users (id, username, full_name, referrer_id, created_at, last_active) VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, message.from_user.username, message.from_user.full_name, referrer_id, 
                   datetime.now(), datetime.now()))
        conn.commit()
        
        if referrer_id:
            c.execute("INSERT INTO referrals (user_id, referred_id, created_at) VALUES (?, ?, ?)", 
                      (referrer_id, user_id, datetime.now()))
            conn.commit()
            
            c.execute("SELECT COUNT(*) FROM referrals WHERE user_id=?", (referrer_id,))
            referral_count = c.fetchone()[0]
            
            if referral_count >= 10:
                await give_premium(referrer_id, 30)
                await bot.send_message(referrer_id, "🎉 TABRIKLAYMIZ! 10 ta do'st taklif qildingiz va PREMIUM a'zolikni QO'LGA KIRITDINGIZ! 🎉")
            
            add_points(referrer_id, 100)
            await bot.send_message(referrer_id, f"👤 Do'stingiz {message.from_user.full_name} botga qo'shildi! Sizga 100 ball berildi.")
    
    c.execute("SELECT last_active FROM users WHERE id=?", (user_id,))
    last_active = c.fetchone()
    if last_active and last_active[0]:
        try:
            last_date = datetime.strptime(str(last_active[0]), '%Y-%m-%d %H:%M:%S.%f').date()
        except:
            try:
                last_date = datetime.strptime(str(last_active[0]), '%Y-%m-%d %H:%M:%S').date()
            except:
                last_date = datetime.now().date()
        today = datetime.now().date()
        if last_date < today:
            add_points(user_id, 5)
            await message.answer("✨ Kunlik faollik bonusi: +5 ball! ✨")
    
    c.execute("UPDATE users SET last_active = ? WHERE id=?", (datetime.now(), user_id))
    conn.commit()
    log_activity(user_id)
    
    if await check_subscription(user_id):
        c.execute("SELECT balance FROM users WHERE id=?", (user_id,))
        balance = c.fetchone()[0]
        
        await message.answer(
            f"📚 *{message.from_user.full_name}*, Kitob platformasiga XUSH KELIBSIZ!\n\n"
            f"🎯 1000+ kitoblar, aqlli tavsiyalar va darajalar!\n"
            f"💰 Balansingiz: {balance} ball\n\n"
            f"👇 Quyidagi knopkalar orqali botdan foydalaning:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard(user_id)
        )
    else:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("📢 KANALGA A'ZO BO'LISH", url="https://t.me/kitoblarim_77_7"))
        keyboard.add(InlineKeyboardButton("✅ TEKSHIRISH", callback_data="check_sub"))
        await message.answer(
            "🔐 Botdan foydalanish uchun avval kanalga a'zo bo'ling!",
            reply_markup=keyboard
        )

@dp.callback_query_handler(lambda c: c.data == 'check_sub')
async def check_sub(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.edit_text(
            "✅ A'zoligingiz tasdiqlandi!\n\n👇 Quyidagi knopkalar orqali davom eting:",
            reply_markup=get_main_keyboard(callback.from_user.id)
        )
    else:
        await callback.answer("❌ Hali kanalga a'zo bo'lmagansiz!", show_alert=True)
    await callback.answer()

# ============ ADMINGA MUROJAAT ============
@dp.callback_query_handler(lambda c: c.data == 'contact_admin')
async def contact_admin(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📞 *ADMINGA MUROJAAT*\n\nXabaringizni yozing. Admin tez orada javob beradi.\n\n⚠️ Iltimos, faqat muhim masalalarda murojaat qiling!",
        parse_mode=ParseMode.MARKDOWN
    )
    await dp.current_state(user=callback.from_user.id).set_state("waiting_admin_message")
    await callback.answer()

@dp.message_handler(state="waiting_admin_message")
async def process_contact_admin(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    
    c.execute("INSERT INTO messages (user_id, user_name, message, created_at, is_answered) VALUES (?, ?, ?, ?, 0)",
              (user_id, user_name, message.text, datetime.now()))
    conn.commit()
    msg_id = c.lastrowid
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("💬 JAVOB BERISH", callback_data=f"admin_reply_{msg_id}"))
    keyboard.add(InlineKeyboardButton("👤 FOYDALANUVCHI", callback_data=f"admin_view_user_{user_id}"))
    
    await bot.send_message(
        ADMIN_ID,
        f"📩 *YANGI XABAR!*\n\n👤 Foydalanuvchi: {user_name}\n🆔 ID: {user_id}\n🕐 Vaqt: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n💬 Xabar: {message.text}\n\n📝 Xabar ID: #{msg_id}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    
    await message.answer(
        "✅ Xabaringiz adminga yuborildi!\nTez orada javob olasiz.\n\n🏠 Bosh menyu: /start",
        reply_markup=get_main_keyboard(user_id)
    )
    await state.finish()

# ============ ADMIN PANEL ============
@dp.callback_query_handler(lambda c: c.data == 'admin_panel')
async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Bu bo'lim faqat admin uchun!", show_alert=True)
        return
    
    c.execute("SELECT COUNT(*) FROM messages WHERE is_answered = 0")
    unread = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1")
    blocked = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM users WHERE is_admin = 0")
    total_users = c.fetchone()[0]
    
    await callback.message.edit_text(
        f"🛠 *ADMIN PANEL* 🛠\n\n📊 Statistika:\n👥 Jami foydalanuvchilar: {total_users}\n💬 O'qilmagan xabarlar: {unread}\n🚫 Bloklanganlar: {blocked}\n\nQuyidagi knopkalar orqali boshqaring:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'admin_stats')
async def admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT COUNT(*) FROM users WHERE is_admin = 0")
    users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM books")
    books = c.fetchone()[0]
    
    c.execute("SELECT SUM(downloads) FROM books")
    downloads = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM premium_users WHERE expire_date > datetime('now')")
    premium = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM user_books")
    total_downloads = c.fetchone()[0]
    
    c.execute("SELECT AVG(rating) FROM books WHERE rating > 0")
    avg_rating = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM messages WHERE is_answered = 0")
    unread = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM messages")
    total_messages = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM referrals")
    total_referrals = c.fetchone()[0]
    
    c.execute("SELECT SUM(balance) FROM users")
    total_balance = c.fetchone()[0] or 0
    
    text = f"📊 *BOT STATISTIKASI*\n\n"
    text += f"👤 Foydalanuvchilar: {users}\n"
    text += f"📚 Kitoblar: {books}\n"
    text += f"📥 Yuklamalar: {downloads}\n"
    text += f"📊 Umumiy yuklamalar: {total_downloads}\n"
    text += f"⭐ O'rtacha reyting: {avg_rating:.1f}\n"
    text += f"💎 Premium a'zolar: {premium}\n"
    text += f"💰 Umumiy ballar: {total_balance}\n"
    text += f"👥 Referallar: {total_referrals}\n"
    text += f"💬 Jami xabarlar: {total_messages}\n"
    text += f"💬 O'qilmagan xabarlar: {unread}\n"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔄 YANGILASH", callback_data="admin_stats"))
    keyboard.add(InlineKeyboardButton("◀️ ORQAGA", callback_data="admin_panel"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

# ============ FOYDALANUVCHILAR RO'YXATI ============
@dp.callback_query_handler(lambda c: c.data == 'admin_users_list')
async def admin_users_list(callback: types.CallbackQuery, page=0):
    if callback.from_user.id != ADMIN_ID:
        return
    
    offset = page * 10
    c.execute("SELECT id, username, full_name, balance, level, is_blocked, created_at FROM users WHERE is_admin = 0 ORDER BY created_at DESC LIMIT 10 OFFSET ?", (offset,))
    users = c.fetchall()
    
    if not users:
        await callback.answer("Foydalanuvchilar topilmadi!")
        return
    
    text = f"👥 *FOYDALANUVCHILAR RO'YXATI* (Sahifa {page+1})\n\n"
    for user in users:
        status = "🚫" if user[5] == 1 else "✅"
        username_display = f"@{user[1]}" if user[1] else "Yo'q"
        text += f"{status} *{user[2]}*\n"
        text += f"   🆔 {user[0]} | 👤 {username_display} | 💰 {user[3]} | 📊 {user[4]}\n"
        text += f"   📅 Qo'shilgan: {format_datetime(user[6])}\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=3)
    c.execute("SELECT COUNT(*) FROM users WHERE is_admin = 0")
    total = c.fetchone()[0]
    pages = (total + 9) // 10
    
    if pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"users_page_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="none"))
        if page < pages - 1:
            nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"users_page_{page+1}"))
        keyboard.row(*nav_buttons)
    
    keyboard.add(InlineKeyboardButton("◀️ ORQAGA", callback_data="admin_panel"))
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('users_page_'))
async def users_page(callback: types.CallbackQuery):
    page = int(callback.data.split('_')[2])
    await admin_users_list(callback, page)

@dp.callback_query_handler(lambda c: c.data.startswith('admin_view_user_'))
async def admin_view_user(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    user_id = int(callback.data.split('_')[3])
    
    c.execute("SELECT username, full_name, balance, level, is_blocked, created_at, last_active FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    
    if not user:
        await callback.answer("Foydalanuvchi topilmadi!")
        return
    
    c.execute("SELECT COUNT(*) FROM user_books WHERE user_id=?", (user_id,))
    books_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM referrals WHERE user_id=?", (user_id,))
    referrals_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM referrals WHERE referred_id=?", (user_id,))
    referred_by = c.fetchone()[0]
    
    username_display = f"@{user[0]}" if user[0] else "Yo'q"
    
    text = f"👤 *FOYDALANUVCHI MA'LUMOTLARI*\n\n"
    text += f"*Ismi:* {user[1]}\n"
    text += f"*Username:* {username_display}\n"
    text += f"*ID:* {user_id}\n"
    text += f"*Balans:* {user[2]} ball\n"
    text += f"*Daraja:* {user[3]}\n"
    text += f"*Holat:* {'🚫 Bloklangan' if user[4] == 1 else '✅ Faol'}\n\n"
    text += f"📚 *Statistika:*\n"
    text += f"• Yuklagan kitoblar: {books_count}\n"
    text += f"• Taklif qilganlar: {referrals_count}\n"
    text += f"• Kim taklif qilgan: {'✅ Ha (' + str(referred_by) + ' ta)' if referred_by > 0 else '❌ Yo\\'q'}\n\n"
    text += f"📅 Qo'shilgan: {format_datetime(user[5])}\n"
    text += f"🕐 Oxirgi faollik: {format_datetime(user[6])}"
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📊 STATISTIKA", callback_data=f"user_stats_{user_id}"),
        InlineKeyboardButton("📚 YUKLAGAN KITOBLAR", callback_data=f"user_books_{user_id}"),
        InlineKeyboardButton("👥 REFERALLAR", callback_data=f"user_referrals_{user_id}"),
        InlineKeyboardButton("💬 XABAR YOZISH", callback_data=f"user_message_{user_id}")
    )
    
    if user[4] == 0:
        keyboard.add(InlineKeyboardButton("🚫 BLOKLASH", callback_data=f"user_block_{user_id}"))
    else:
        keyboard.add(InlineKeyboardButton("🔓 BLOKNI OCHISH", callback_data=f"user_unblock_{user_id}"))
    
    keyboard.add(InlineKeyboardButton("◀️ ORQAGA", callback_data="admin_users_list"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('user_stats_'))
async def user_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    user_id = int(callback.data.split('_')[2])
    
    c.execute("SELECT COUNT(*) FROM user_books WHERE user_id=?", (user_id,))
    downloads = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (user_id,))
    messages = c.fetchone()[0]
    
    c.execute("SELECT SUM(points) FROM user_activity WHERE user_id=?", (user_id,))
    activity = c.fetchone()[0] or 0
    
    c.execute("SELECT created_at FROM users WHERE id=?", (user_id,))
    joined = c.fetchone()[0]
    days = (datetime.now() - datetime.strptime(str(joined), '%Y-%m-%d %H:%M:%S.%f')).days if '.' in str(joined) else (datetime.now() - datetime.strptime(str(joined), '%Y-%m-%d %H:%M:%S')).days
    
    text = f"📊 *FOYDALANUVCHI STATISTIKASI*\n\n"
    text += f"📚 Yuklagan kitoblar: {downloads}\n"
    text += f"💬 Yozgan xabarlar: {messages}\n"
    text += f"⭐ Faollik ballari: {activity}\n"
    text += f"📅 Botda: {days} kun\n"
    text += f"📈 O'rtacha kunlik faollik: {activity // max(days, 1)} ball"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("◀️ ORQAGA", callback_data=f"admin_view_user_{user_id}"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('user_books_'))
async def user_books(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    user_id = int(callback.data.split('_')[2])
    
    c.execute("""SELECT b.title, b.author, ub.downloaded_at FROM user_books ub 
                 JOIN books b ON ub.book_id = b.id 
                 WHERE ub.user_id=? ORDER BY ub.downloaded_at DESC LIMIT 10""", (user_id,))
    books = c.fetchall()
    
    if not books:
        await callback.answer("Foydalanuvchi hech qanday kitob yuklamagan!")
        return
    
    text = f"📚 *FOYDALANUVCHI YUKLAGAN KITOBLAR*\n\n"
    for i, book in enumerate(books, 1):
        text += f"{i}. *{book[0]}* - {book[1]}\n"
        text += f"   📅 {format_datetime(book[2])}\n\n"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("◀️ ORQAGA", callback_data=f"admin_view_user_{user_id}"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('user_referrals_'))
async def user_referrals(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    user_id = int(callback.data.split('_')[2])
    
    c.execute("""SELECT u.full_name, u.created_at FROM referrals r 
                 JOIN users u ON r.referred_id = u.id 
                 WHERE r.user_id=? ORDER BY r.created_at DESC LIMIT 10""", (user_id,))
    referrals = c.fetchall()
    
    if not referrals:
        await callback.answer("Foydalanuvchi hech kimni taklif qilmagan!")
        return
    
    text = f"👥 *TAKLIF QILGANLAR RO'YXATI*\n\n"
    for i, ref in enumerate(referrals, 1):
        text += f"{i}. {ref[0]}\n"
        text += f"   📅 {format_datetime(ref[1])}\n\n"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("◀️ ORQAGA", callback_data=f"admin_view_user_{user_id}"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('user_block_'))
async def user_block(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    user_id = int(callback.data.split('_')[2])
    
    c.execute("UPDATE users SET is_blocked = 1 WHERE id=?", (user_id,))
    conn.commit()
    
    try:
        await bot.send_message(user_id, "❌ Siz botdan bloklandingiz!")
    except:
        pass
    await callback.answer("✅ Foydalanuvchi bloklandi!", show_alert=True)
    await admin_view_user(callback)

@dp.callback_query_handler(lambda c: c.data.startswith('user_unblock_'))
async def user_unblock(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    user_id = int(callback.data.split('_')[2])
    
    c.execute("UPDATE users SET is_blocked = 0 WHERE id=?", (user_id,))
    conn.commit()
    
    try:
        await bot.send_message(user_id, "✅ Sizning blokingiz ochildi!")
    except:
        pass
    await callback.answer("✅ Blok ochildi!", show_alert=True)
    await admin_view_user(callback)

@dp.callback_query_handler(lambda c: c.data.startswith('user_message_'))
async def user_message_start(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    user_id = int(callback.data.split('_')[2])
    
    c.execute("SELECT full_name FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    
    await callback.message.edit_text(
        f"📤 *XABAR YOZISH*\n\n👤 Foydalanuvchi: {user[0]}\n🆔 ID: {user_id}\n\nYubormoqchi bo'lgan xabaringizni yozing:",
        parse_mode=ParseMode.MARKDOWN
    )
    await dp.current_state(user=callback.from_user.id).set_state(f"waiting_personal_msg_{user_id}")
    await callback.answer()

@dp.message_handler(state_startswith="waiting_personal_msg_")
async def send_personal_message(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    state_name = await state.get_state()
    user_id = int(state_name.split('_')[3])
    
    try:
        await bot.send_message(user_id, f"📩 *Admin xabari:*\n\n{message.text}", parse_mode=ParseMode.MARKDOWN)
        await message.answer("✅ Xabar yuborildi!", reply_markup=get_admin_keyboard())
    except:
        await message.answer("❌ Xabar yuborishda xatolik yuz berdi!")
    await state.finish()

# ============ XABARLAR BO'LIMI ============
@dp.callback_query_handler(lambda c: c.data == 'admin_messages_list')
async def admin_messages_list(callback: types.CallbackQuery, page=0):
    if callback.from_user.id != ADMIN_ID:
        return
    
    offset = page * 10
    c.execute("SELECT id, user_id, user_name, message, created_at FROM messages WHERE is_answered = 0 ORDER BY created_at DESC LIMIT 10 OFFSET ?", (offset,))
    messages = c.fetchall()
    
    if not messages:
        await callback.message.edit_text("💬 *KUTILAYOTGAN XABARLAR YO'Q*\n\nBarcha xabarlarga javob berilgan.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
        return
    
    text = f"💬 *KUTILAYOTGAN XABARLAR* (Sahifa {page+1})\n\n"
    for msg in messages:
        text += f"📝 #{msg[0]}\n👤 {msg[2]} (ID: {msg[1]})\n🕐 {format_datetime(msg[4])}\n💬 {msg[3][:100]}{'...' if len(msg[3]) > 100 else ''}\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    for msg in messages[:5]:
        keyboard.add(InlineKeyboardButton(f"📝 #{msg[0]} - JAVOB BERISH", callback_data=f"admin_reply_{msg[0]}"))
    keyboard.add(InlineKeyboardButton("◀️ ORQAGA", callback_data="admin_panel"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('admin_reply_'))
async def admin_reply_message(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    msg_id = int(callback.data.split('_')[2])
    
    c.execute("SELECT user_id, user_name, message, created_at FROM messages WHERE id=?", (msg_id,))
    msg = c.fetchone()
    
    text = f"💬 *XABARGA JAVOB BERISH*\n\n👤 Foydalanuvchi: {msg[1]}\n🆔 ID: {msg[0]}\n🕐 Yuborilgan: {format_datetime(msg[3])}\n\n📝 *Xabar matni:*\n{msg[2]}\n\n✍️ Javobingizni yozing:"
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    await dp.current_state(user=callback.from_user.id).set_state(f"waiting_reply_{msg_id}")
    await callback.answer()

@dp.message_handler(state_startswith="waiting_reply_")
async def process_admin_reply(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    state_name = await state.get_state()
    msg_id = int(state_name.split('_')[2])
    
    c.execute("SELECT user_id FROM messages WHERE id=?", (msg_id,))
    res = c.fetchone()
    if not res:
        await message.answer("❌ Xabar topilmadi!")
        await state.finish()
        return
    user_id = res[0]
    
    try:
        await bot.send_message(user_id, f"📩 *Admin javobi:*\n\n{message.text}\n\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}", parse_mode=ParseMode.MARKDOWN)
        c.execute("UPDATE messages SET is_answered = 1, answer = ?, answered_at = ? WHERE id=?", (message.text, datetime.now(), msg_id))
        conn.commit()
        await message.answer("✅ Javob yuborildi!", reply_markup=get_admin_keyboard())
    except:
        await message.answer("❌ Javob yuborishda xatolik yuz berdi!")
    await state.finish()

# ============ BLOKLANGANLAR ============
@dp.callback_query_handler(lambda c: c.data == 'admin_blocked_list')
async def admin_blocked_list(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT id, username, full_name, balance, created_at FROM users WHERE is_blocked = 1 AND is_admin = 0")
    users = c.fetchall()
    
    if not users:
        await callback.answer("Bloklangan foydalanuvchilar yo'q!")
        return
    
    text = "🚫 *BLOKLANGAN FOYDALANUVCHILAR*\n\n"
    for user in users:
        username_display = f"@{user[1]}" if user[1] else "Yo'q"
        text += f"👤 {user[2]}\n🆔 {user[0]} | 👤 {username_display}\n💰 Balans: {user[3]}\n📅 Qo'shilgan: {format_datetime(user[4])}\n\n"
    
    keyboard = InlineKeyboardMarkup()
    for user in users[:5]:
        keyboard.add(InlineKeyboardButton(f"🔓 {user[2]} - BLOKNI OCHISH", callback_data=f"user_unblock_{user[0]}"))
    keyboard.add(InlineKeyboardButton("◀️ ORQAGA", callback_data="admin_panel"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

# ============ KITOBLAR BOSHQARUVI ============
@dp.callback_query_handler(lambda c: c.data == 'admin_books_list')
async def admin_books_list(callback: types.CallbackQuery, page=0):
    if callback.from_user.id != ADMIN_ID:
        return
    
    offset = page * 10
    c.execute("SELECT id, title, author, downloads, views, is_premium FROM books ORDER BY created_at DESC LIMIT 10 OFFSET ?", (offset,))
    books = c.fetchall()
    
    if not books:
        await callback.message.edit_text("📚 Hozircha kitoblar mavjud emas.", reply_markup=get_admin_keyboard())
        return
    
    text = f"📚 *KITOBLAR RO'YXATI* (Sahifa {page+1})\n\n"
    for book in books:
        premium = "💎 " if book[5] == 1 else ""
        text += f"{premium}📖 *{book[1]}* - {book[2]}\n"
        text += f"   📥 {book[3]} | 👁 {book[4]} | ID: {book[0]}\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    for book in books[:5]:
        keyboard.add(InlineKeyboardButton(f"📖 {book[1][:20]}", callback_data=f"admin_view_book_{book[0]}"))
    
    c.execute("SELECT COUNT(*) FROM books")
    total = c.fetchone()[0]
    pages = (total + 9) // 10
    
    if pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"admin_books_page_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="none"))
        if page < pages - 1:
            nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"admin_books_page_{page+1}"))
        keyboard.row(*nav_buttons)
    
    keyboard.add(InlineKeyboardButton("◀️ ORQAGA", callback_data="admin_panel"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('admin_books_page_'))
async def admin_books_page(callback: types.CallbackQuery):
    page = int(callback.data.split('_')[3])
    await admin_books_list(callback, page)

@dp.callback_query_handler(lambda c: c.data.startswith('admin_view_book_'))
async def admin_view_book(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    book_id = int(callback.data.split('_')[3])
    
    c.execute("SELECT * FROM books WHERE id=?", (book_id,))
    book = c.fetchone()
    
    if not book:
        await callback.answer("Kitob topilmadi!")
        return

    text = f"📖 *KITOB MA'LUMOTLARI*\n\n"
    text += f"*Nomi:* {book[1]}\n"
    text += f"*Muallif:* {book[2]}\n"
    text += f"*Kategoriya:* {book[3]}\n"
    text += f"*Tavsif:* {book[4]}\n\n"
    text += f"*Reyting:* {book[6]}\n"
    text += f"*Yuklamalar:* {book[7]}\n"
    text += f"*Ko'rishlar:* {book[8]}\n"
    text += f"*Premium:* {'✅ Ha' if book[9] == 1 else '❌ Yo\\'q'}\n"
    text += f"*Qo'shilgan:* {format_datetime(book[10])}\n"
    text += f"*File ID:* `{book[5]}`"
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🗑 O'CHIRISH", callback_data=f"admin_delete_book_{book_id}"),
        InlineKeyboardButton("◀️ ORQAGA", callback_data="admin_books_list")
    )
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('admin_delete_book_'))
async def admin_delete_book(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    book_id = int(callback.data.split('_')[3])
    
    c.execute("SELECT title FROM books WHERE id=?", (book_id,))
    res = c.fetchone()
    if not res:
        await callback.answer("Kitob topilmadi!")
        return
    title = res[0]
    
    c.execute("DELETE FROM books WHERE id=?", (book_id,))
    c.execute("DELETE FROM user_books WHERE book_id=?", (book_id,))
    conn.commit()
    
    await callback.answer(f"✅ {title} kitobi o'chirildi!", show_alert=True)
    await admin_books_list(callback)

# ============ KITOB QO'SHISH ============
@dp.callback_query_handler(lambda c: c.data == 'admin_add_book')
async def admin_add_book_start(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    await AddBookState.title.set()
    await callback.message.edit_text("➕ *KITOB QO'SHISH*\n\n1/6 - Kitob nomini kiriting:", parse_mode=ParseMode.MARKDOWN)
    await callback.answer()

@dp.message_handler(state=AddBookState.title)
async def add_book_title(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['title'] = message.text
    await AddBookState.next()
    await message.answer("2/6 - Muallifni kiriting:")

@dp.message_handler(state=AddBookState.author)
async def add_book_author(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['author'] = message.text
    await AddBookState.next()
    await message.answer("3/6 - Kategoriyani kiriting:\n(Masalan: Motivatsion, Badiiy, Ilmiy, Biznes)")

@dp.message_handler(state=AddBookState.category)
async def add_book_category(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['category'] = message.text
    await AddBookState.next()
    await message.answer("4/6 - Kitob haqida qisqacha tavsif yozing:")

@dp.message_handler(state=AddBookState.description)
async def add_book_description(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['description'] = message.text
    await AddBookState.next()
    await message.answer("5/6 - Kitob faylini (PDF yoki EPUB) yuboring:")

@dp.message_handler(state=AddBookState.file, content_types=types.ContentTypes.DOCUMENT)
async def add_book_file(message: types.Message, state: FSMContext):
    file_id = message.document.file_id
    async with state.proxy() as data:
        data['file_id'] = file_id
    await AddBookState.next()
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ HA", callback_data="book_premium_yes"),
        InlineKeyboardButton("❌ YO'Q", callback_data="book_premium_no")
    )
    await message.answer("6/6 - Bu kitob PREMIUM bo'ladimi?", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith('book_premium_'), state=AddBookState.is_premium)
async def add_book_premium(callback: types.CallbackQuery, state: FSMContext):
    is_premium = 1 if callback.data == 'book_premium_yes' else 0
    
    async with state.proxy() as data:
        c.execute("INSERT INTO books (title, author, category, description, file_id, is_premium, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (data['title'], data['author'], data['category'], data['description'], data['file_id'], is_premium, datetime.now()))
        conn.commit()
        book_id = c.lastrowid
    
    await state.finish()
    
    text = f"✅ *KITOB QO'SHILDI!*\n\n📖 Nomi: {data['title']}\n✍️ Muallif: {data['author']}\n📚 Kategoriya: {data['category']}\n💎 Premium: {'✅ Ha' if is_premium else '❌ Yo\\'q'}\n🆔 Kitob ID: {book_id}"
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
    await callback.answer()

# ============ PREMIUM BERISH ============
@dp.callback_query_handler(lambda c: c.data == 'admin_give_premium')
async def admin_give_premium_start(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    await callback.message.edit_text("💎 *PREMIUM BERISH*\n\nPremium beriladigan foydalanuvchi ID sini yuboring:", parse_mode=ParseMode.MARKDOWN)
    await dp.current_state(user=callback.from_user.id).set_state("waiting_premium_user")
    await callback.answer()

@dp.message_handler(state="waiting_premium_user")
async def admin_give_premium_handler(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        user_id = int(message.text)
        c.execute("SELECT full_name FROM users WHERE id=?", (user_id,))
        user = c.fetchone()
        
        if not user:
            await message.answer("❌ Foydalanuvchi topilmadi!")
            await state.finish()
            return
        
        await give_premium(user_id, 30)
        await message.answer(f"✅ {user[0]} ga 30 kunlik premium berildi!", reply_markup=get_admin_keyboard())
        try:
            await bot.send_message(user_id, "🎉 *TABRIKLAYMIZ!* Sizga 30 kunlik PREMIUM a'zolik berildi! 🎉", parse_mode=ParseMode.MARKDOWN)
        except:
            pass
    except:
        await message.answer("❌ Xato ID! Iltimos, to'g'ri ID yuboring.")
    
    await state.finish()

# ============ E'LON YUBORISH ============
@dp.callback_query_handler(lambda c: c.data == 'admin_announcement')
async def admin_announcement_handler(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    await callback.message.edit_text("📢 *E'LON YUBORISH*\n\nBarcha foydalanuvchilarga yuboriladigan e'lon matnini yozing:", parse_mode=ParseMode.MARKDOWN)
    await dp.current_state(user=callback.from_user.id).set_state("waiting_announcement")
    await callback.answer()

@dp.message_handler(state="waiting_announcement")
async def process_announcement_handler(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT id FROM users WHERE is_blocked = 0")
    users = c.fetchall()
    
    sent = 0
    failed = 0
    
    msg = await message.answer("📢 E'lon yuborilmoqda...")
    
    for user in users:
        try:
            await bot.send_message(user[0], f"📢 *BOT E'LONI*\n\n{message.text}\n\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}", parse_mode=ParseMode.MARKDOWN)
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    
    await msg.edit_text(f"✅ E'lon yuborildi!\n\n📤 Yuborilgan: {sent}\n❌ Xatolik: {failed}", reply_markup=get_admin_keyboard())
    await state.finish()

# ============ XABAR YOZISH ============
@dp.callback_query_handler(lambda c: c.data == 'admin_send_message')
async def admin_send_message_start(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT id, full_name FROM users WHERE is_admin = 0 ORDER BY created_at DESC LIMIT 20")
    users = c.fetchall()
    
    text = "📤 *XABAR YOZISH*\n\nXabar yubormoqchi bo'lgan foydalanuvchini tanlang:\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for user in users:
        keyboard.add(InlineKeyboardButton(f"👤 {user[1]} (ID: {user[0]})", callback_data=f"admin_msg_user_{user[0]}"))
    keyboard.add(InlineKeyboardButton("◀️ ORQAGA", callback_data="admin_panel"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('admin_msg_user_'))
async def admin_msg_user_handler(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    user_id = int(callback.data.split('_')[3])
    
    c.execute("SELECT full_name FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    
    await callback.message.edit_text(f"📤 *XABAR YOZISH*\n\n👤 Qabul qiluvchi: {user[0]}\n🆔 ID: {user_id}\n\nXabar matnini yozing:", parse_mode=ParseMode.MARKDOWN)
    await dp.current_state(user=callback.from_user.id).set_state(f"admin_send_msg_{user_id}")
    await callback.answer()

@dp.message_handler(state_startswith="admin_send_msg_")
async def admin_send_message_process_handler(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    state_name = await state.get_state()
    user_id = int(state_name.split('_')[3])
    
    try:
        await bot.send_message(user_id, f"📩 *Admin xabari:*\n\n{message.text}\n\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}", parse_mode=ParseMode.MARKDOWN)
        await message.answer("✅ Xabar yuborildi!", reply_markup=get_admin_keyboard())
    except:
        await message.answer("❌ Xabar yuborishda xatolik yuz berdi!")
    await state.finish()

# ============ ORQAGA ============
@dp.callback_query_handler(lambda c: c.data == 'admin_panel_back')
async def admin_panel_back_handler(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await admin_panel(callback)

# ============ YORDAM ============
@dp.callback_query_handler(lambda c: c.data == 'help_menu')
async def help_menu_handler(callback: types.CallbackQuery):
    text = "💬 *YORDAM MARKAZI*\n\n📚 Kitoblar - barcha kitoblarni ko'rish\n🔍 Qidirish - nom, muallif bo'yicha qidirish\n⭐ Tavsiyalar - sizga mos kitoblar\n👥 Do'st taklif - do'stlaringizni chaqirib ball yig'ish\n💰 Ballar - har yuklab olish uchun ball\n🎮 Darajalar - ball yig'ib darajangizni oshiring\n💎 Premium - 10 ta do'st taklif qiling va 30 kun PREMIUM"
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🏠 BOSH MENYU", callback_data="main_menu"))
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

# ============ ASOSIY FUNKSIYALAR (QISQA) ============
@dp.callback_query_handler(lambda c: c.data == 'main_menu')
async def main_menu_handler(callback: types.CallbackQuery):
    await callback.message.edit_text("📚 *ASOSIY MENYU*\n\nQuyidagi knopkalar orqali botdan foydalaning:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(callback.from_user.id))
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'show_books')
async def show_books_handler(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Avval kanalga a'zo bo'ling!", show_alert=True)
        return
    
    c.execute("SELECT id, title, author, rating, downloads, is_premium FROM books ORDER BY downloads DESC LIMIT 10")
    books = c.fetchall()
    
    if not books:
        await callback.message.edit_text("📚 Hozircha kitoblar mavjud emas.", reply_markup=get_main_keyboard(callback.from_user.id))
        return
    
    text = "📚 *ENG KO'P O'QILGAN KITOBLAR*\n\n"
    for book in books:
        premium_icon = "💎 " if book[5] == 1 else ""
        text += f"{premium_icon}📖 *{book[1]}* - {book[2]}\n   ⭐ {book[3]} | 📥 {book[4]}\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for book in books[:5]:
        keyboard.add(InlineKeyboardButton(f"📖 {book[1]}", callback_data=f"view_book_{book[0]}"))
    keyboard.add(InlineKeyboardButton("🏠 BOSH MENYU", callback_data="main_menu"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

# ============ QO'SHIMCHA HANDLERLAR ============
@dp.callback_query_handler(lambda c: c.data.startswith('view_book_'))
async def view_book_handler(callback: types.CallbackQuery):
    book_id = int(callback.data.split('_')[2])
    c.execute("SELECT * FROM books WHERE id=?", (book_id,))
    book = c.fetchone()
    if not book:
        await callback.answer("Kitob topilmadi!")
        return
    
    c.execute("UPDATE books SET views = views + 1 WHERE id=?", (book_id,))
    conn.commit()
    
    text = f"📖 *{book[1]}*\n\n✍️ Muallif: {book[2]}\n📚 Kategoriya: {book[3]}\n📝 Tavsif: {book[4]}\n⭐ Reyting: {book[6]}\n📥 Yuklamalar: {book[7]}\n💎 Premium: {'✅ Ha' if book[9] == 1 else '❌ Yo\\'q'}"
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(InlineKeyboardButton("📥 YUKLAB OLISH", callback_data=f"download_book_{book_id}"))
    keyboard.add(InlineKeyboardButton("🏠 BOSH MENYU", callback_data="main_menu"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('download_book_'))
async def download_book_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    book_id = int(callback.data.split('_')[2])
    
    c.execute("SELECT * FROM books WHERE id=?", (book_id,))
    book = c.fetchone()
    
    if book[9] == 1 and not await check_premium(user_id):
        await callback.answer("💎 Bu kitob faqat PREMIUM a'zolar uchun!", show_alert=True)
        return
    
    try:
        await bot.send_document(user_id, book[5], caption=f"📖 {book[1]} - {book[2]}\n\nBot: @{ (await bot.get_me()).username }")
        c.execute("UPDATE books SET downloads = downloads + 1 WHERE id=?", (book_id,))
        c.execute("INSERT INTO user_books (user_id, book_id, downloaded_at) VALUES (?, ?, ?)", (user_id, book_id, datetime.now()))
        conn.commit()
        await callback.answer("✅ Kitob yuborildi!")
    except:
        await callback.answer("❌ Faylni yuborishda xatolik!")

@dp.callback_query_handler(lambda c: c.data == 'search_menu')
async def search_menu_handler(callback: types.CallbackQuery):
    await callback.message.edit_text("🔍 *QIDIRISH*\n\nKitob nomi yoki muallifini yozing:", parse_mode=ParseMode.MARKDOWN)
    await dp.current_state(user=callback.from_user.id).set_state("waiting_search")
    await callback.answer()

@dp.message_handler(state="waiting_search")
async def process_search_handler(message: types.Message, state: FSMContext):
    query = f"%{message.text}%"
    c.execute("SELECT id, title, author FROM books WHERE title LIKE ? OR author LIKE ? LIMIT 10", (query, query))
    books = c.fetchall()
    
    if not books:
        await message.answer("❌ Hech narsa topilmadi!")
    else:
        text = "🔍 *QIDIRUV NATIJALARI:*\n\n"
        keyboard = InlineKeyboardMarkup(row_width=1)
        for book in books:
            text += f"📖 {book[1]} - {book[2]}\n"
            keyboard.add(InlineKeyboardButton(f"📖 {book[1]}", callback_data=f"view_book_{book[0]}"))
        keyboard.add(InlineKeyboardButton("🏠 BOSH MENYU", callback_data="main_menu"))
        await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'recommend_books')
async def recommend_books_handler(callback: types.CallbackQuery):
    c.execute("SELECT id, title, author FROM books ORDER BY RANDOM() LIMIT 5")
    books = c.fetchall()
    text = "⭐ *SIZ UCHUN TAVSIYALAR:*\n\n"
    keyboard = InlineKeyboardMarkup(row_width=1)
    for book in books:
        text += f"📖 {book[1]} - {book[2]}\n"
        keyboard.add(InlineKeyboardButton(f"📖 {book[1]}", callback_data=f"view_book_{book[0]}"))
    keyboard.add(InlineKeyboardButton("🏠 BOSH MENYU", callback_data="main_menu"))
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'leaderboard_menu')
async def leaderboard_menu_handler(callback: types.CallbackQuery):
    c.execute("SELECT u.full_name, l.total_points FROM leaderboard l JOIN users u ON l.user_id = u.id ORDER BY l.total_points DESC LIMIT 10")
    users = c.fetchall()
    text = "🏆 *TOP FOYDALANUVCHILAR:*\n\n"
    for i, user in enumerate(users, 1):
        text += f"{i}. {user[0]} - {user[1]} ball\n"
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🏠 BOSH MENYU", callback_data="main_menu"))
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'my_level')
async def my_level_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    c.execute("SELECT balance, level FROM users WHERE id=?", (user_id,))
    res = c.fetchone()
    text = f"📊 *SIZNING DARAJANGIZ*\n\n💰 Balans: {res[0]} ball\n📊 Daraja: {res[1]}\n\n💡 Keyingi daraja uchun: {500 - (res[0] % 500)} ball kerak."
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🏠 BOSH MENYU", callback_data="main_menu"))
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'premium_menu')
async def premium_menu_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_prem = await check_premium(user_id)
    if is_prem:
        c.execute("SELECT expire_date FROM premium_users WHERE user_id=?", (user_id,))
        exp = c.fetchone()[0]
        text = f"💎 *SIZ PREMIUM A'ZOSIZ!*\n\n📅 Tugash muddati: {format_datetime(exp)}"
    else:
        text = "💎 *PREMIUM A'ZOLIK*\n\nPremium afzalliklari:\n1. Barcha kitoblarni yuklab olish\n2. Reklamasiz foydalanish\n3. Maxsus belgilar\n\n💡 Premium olish uchun 10 ta do'st taklif qiling!"
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🏠 BOSH MENYU", callback_data="main_menu"))
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'referral_menu')
async def referral_menu_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    c.execute("SELECT COUNT(*) FROM referrals WHERE user_id=?", (user_id,))
    count = c.fetchone()[0]
    text = f"👥 *DO'ST TAKLIF QILISH*\n\nSizning taklif havolangiz:\n`{ref_link}`\n\nTaklif qilingan do'stlar: {count} ta\n\n🎁 Har bir do'st uchun 100 ball!"
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🏠 BOSH MENYU", callback_data="main_menu"))
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'daily_bonus')
async def daily_bonus_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute("SELECT * FROM user_activity WHERE user_id=? AND activity_date=?", (user_id, today))
    if c.fetchone():
        await callback.answer("❌ Siz bugun bonus olgansiz!", show_alert=True)
    else:
        add_points(user_id, 10)
        log_activity(user_id)
        await callback.answer("✅ Kunlik bonus: +10 ball!", show_alert=True)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'my_profile')
async def my_profile_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    c.execute("SELECT full_name, balance, level, created_at FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    is_prem = await check_premium(user_id)
    text = f"👤 *PROFILIM*\n\nIsm: {user[0]}\nID: {user_id}\nBalans: {user[1]} ball\nDaraja: {user[2]}\nPremium: {'✅ Ha' if is_prem else '❌ Yo\\'q'}\nQo'shilgan vaqt: {format_datetime(user[3])}"
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🏠 BOSH MENYU", callback_data="main_menu"))
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

# ============ BOTNI ISHGA TUSHIRISH ============
async def on_startup(dp):
    print("🤖 Kitob platformasi boti ishga tushdi!")
    print(f"👤 Admin ID: {ADMIN_ID}")
    print(f"📢 Kanal: {REQUIRED_CHANNEL}")

if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
