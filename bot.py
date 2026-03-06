import os
import random
import asyncio
import logging
import pytz
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
    Application
)

# ================= LOGGING SETUP =================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= CONFIGURATION =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MONGO_URI = os.getenv("MONGO_URI", "")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1002686058050"))
PORT = int(os.getenv("PORT", "8080"))

ADMINS_STR = os.getenv("ADMIN_IDS", "5298223577")
ADMINS = [int(x.strip()) for x in ADMINS_STR.split(",") if x.strip().isdigit()]

OWNER_USERNAME = os.getenv("OWNER_USERNAME", "cinewood_flix") 
UPI_ID = os.getenv("UPI_ID", "your-upi@paytm") 
PLAN_IMG_URL = "https://graph.org/file/56b5deb73f3b132e2bb73.jpg" 

# ================= CHANNEL SETUP =================
FORCE_SUB_CHANNELS = [-1003627956964]
CATEGORY_CHANNELS = {
    "🎬 All ": -1002726601987,
}
DEFAULT_CHANNEL = -1002726601987

# ================= BOT SETTINGS =================
IST = pytz.timezone('Asia/Kolkata')
TRIAL_HOURS = 24
REFERRAL_REQUIREMENT = 3 
MAX_DAILY_VIDEOS_FREE = 5 
MAX_DAILY_VIDEOS_PREMIUM = 100

CAPTION_TEXT = (
    "ⓘ 𝙏𝙝𝙞𝙨 𝙢𝙚𝙙𝙞𝙖 𝙬𝙞𝙡𝙡 𝙗𝙚 𝙖𝙪𝙩𝙤𝙢𝙖𝙩𝙞𝙘𝙖𝙡𝙡𝙮 𝙙𝙚𝙡𝙚𝙩𝙚𝙙 𝙖𝙛𝙩𝙚𝙧 10 𝙢𝙞𝙣𝙪𝙩𝙚𝙨.\n"
    "𝙋𝙡𝙚𝙖𝙨𝙚 𝙗𝙤𝙤𝙠𝙢𝙖𝙧𝙠 𝙤𝙧 𝙙𝙤𝙬𝙣𝙡𝙤𝙖𝙙 𝙞𝙛 𝙮𝙤𝙪 𝙬𝙖𝙣𝙩 𝙩𝙤 𝙬𝙖𝙩𝙘𝙝 𝙡𝙖𝙩𝙚𝙧.\n\n\n"
    "━━━━━━━━━━━━━━━\n"
    "🤖 𝙈𝙤𝙫𝙞𝙚 𝘽𝙤𝙤𝙩 : @ChaudharyAutoFilterbot\n"
    "📢 𝘽𝙖𝙘𝙠𝙪𝙥 𝘾𝙝𝙖𝙣𝙣𝙚𝙡 : @cinewood_flix\n"
    "🔒 𝙋𝙧𝙞𝙫𝙖𝙩𝙚 𝘾𝙝𝙖𝙣𝙣𝙚𝙡 : https://t.me/+IKEPBquEvmc0ODhl\n"
    "━━━━━━━━━━━━━━━"
)

# ================= DATABASE SETUP =================
client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=True)
db = client["telegram_bot_db"]
users_col = db["users"]
media_col = db["media"]

# ================= UTILITY FUNCTIONS =================

def get_ist_now():
    return datetime.now(IST)

def format_datetime(dt_str):
    if isinstance(dt_str, str):
        try: dt = datetime.fromisoformat(dt_str)
        except ValueError: dt = datetime.now()
    else: dt = dt_str
    if dt.tzinfo is None: dt = dt.replace(tzinfo=IST)
    return dt.strftime("%d/%m/%Y, %I:%M %p")

async def send_log(bot, log_type, user, additional_text=""):
    text = f"#{log_type}\n\nID: <code>{user.id}</code>\nName: {user.full_name}\n{additional_text}"
    try: await bot.send_message(LOG_CHANNEL_ID, text, parse_mode="HTML")
    except: pass

async def check_user_membership(bot, user_id, channels):
    if not channels: return True
    for channel_id in channels:
        try:
            member = await bot.get_chat_member(channel_id, user_id)
            if member.status not in ["member", "administrator", "creator"]: return False
        except: continue
    return True

# ================= KEYBOARDS =================

def get_main_keyboard(is_admin=False):
    buttons = [
        [InlineKeyboardButton("▶ Start Browsing", callback_data="send_media")],
        [InlineKeyboardButton("📊 My Status", callback_data="status")],
        [InlineKeyboardButton("💎 Plans", callback_data="plans")],
        [InlineKeyboardButton("🔄 Change Category", callback_data="change_category")]
    ]
    if is_admin: buttons.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

def get_media_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👍 Like", callback_data="like"), InlineKeyboardButton("👎 Dislike", callback_data="dislike")],
        [InlineKeyboardButton("⏮ Previous", callback_data="previous"), InlineKeyboardButton("⏭ Next", callback_data="next")],
        [InlineKeyboardButton("🔄 Category", callback_data="change_category"), InlineKeyboardButton("❌ Close", callback_data="close")]
    ])

def get_plans_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 Month - ₹50", callback_data="pay_1"), InlineKeyboardButton("2 Months - ₹90", callback_data="pay_2")],
        [InlineKeyboardButton("3 Months - ₹130", callback_data="pay_3")],
        [InlineKeyboardButton("🎁 Free 1 Day Premium (Referral)", callback_data="plan_referral")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu_del")] 
    ])

def get_payment_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Send Payment Proof", callback_data="submit_proof")],
        [InlineKeyboardButton("🔙 Back", callback_data="plans")]
    ])

def get_category_keyboard():
    buttons = [[InlineKeyboardButton(f"{cat}", callback_data=f"set_category_{cat}")] for cat in CATEGORY_CHANNELS.keys()]
    buttons.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)

def get_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Premium", callback_data="admin_add_premium"), InlineKeyboardButton("📤 Index Channel", callback_data="admin_index")],
        [InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats"), InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_menu")]
    ])

# ================= MANAGERS =================

class UserManager:
    async def get_user(self, user_id):
        return await users_col.find_one({"_id": str(user_id)})

    async def create_user(self, user_id, name):
        expiry = get_ist_now()
        default_cat = list(CATEGORY_CHANNELS.keys())[0] if CATEGORY_CHANNELS else "🎬 All "
        user_data = {
            "_id": str(user_id), "name": name, "plan": "free", "expires": expiry.isoformat(),
            "referrals": 0, "daily_videos": 0, "last_reset_date": get_ist_now().strftime("%Y-%m-%d"),
            "current_category": default_cat, "last_sent_media": [], "last_activity": get_ist_now().isoformat()
        }
        await users_col.update_one({"_id": str(user_id)}, {"$set": user_data}, upsert=True)
        return user_data

    async def update_user(self, user_id, updates):
        updates["last_activity"] = get_ist_now().isoformat()
        await users_col.update_one({"_id": str(user_id)}, {"$set": updates})

    async def check_reset_daily(self, user_id, user_data):
        today_str = get_ist_now().strftime("%Y-%m-%d")
        if user_data.get("last_reset_date") != today_str:
            await users_col.update_one({"_id": str(user_id)}, {"$set": {"daily_videos": 0, "last_reset_date": today_str}})
            return True
        return False

    async def add_referral(self, referrer_id):
        referrer = await self.get_user(referrer_id)
        if referrer:
            new_refs = referrer.get("referrals", 0) + 1
            upd = {"referrals": new_refs}
            if new_refs % REFERRAL_REQUIREMENT == 0:
                try:
                    current_exp = datetime.fromisoformat(referrer["expires"])
                    if current_exp < get_ist_now().replace(tzinfo=None): current_exp = get_ist_now().replace(tzinfo=None)
                    new_exp = current_exp + timedelta(days=1)
                    upd.update({"expires": new_exp.isoformat(), "plan": "premium"})
                except: pass
            await self.update_user(referrer_id, upd)

    async def is_premium(self, user_id):
        user = await self.get_user(user_id)
        if not user: return False
        try:
            exp = datetime.fromisoformat(user["expires"])
            if exp.tzinfo is None: exp = exp.replace(tzinfo=IST)
            return exp > get_ist_now()
        except: return False

    async def set_premium(self, user_id, days):
        user = await self.get_user(user_id)
        start_date = get_ist_now().replace(tzinfo=None)
        if user:
            try:
                current_exp = datetime.fromisoformat(user["expires"])
                if current_exp > start_date: start_date = current_exp
            except: pass
        new_exp = start_date + timedelta(days=days)
        await users_col.update_one({"_id": str(user_id)}, {"$set": {"expires": new_exp.isoformat(), "plan": "premium", "daily_videos": 0}}, upsert=True)
        return new_exp

class MediaManager:
    async def add_media(self, channel_id, message_id):
        await media_col.update_one({"channel_id": str(channel_id)}, {"$addToSet": {"message_ids": message_id}}, upsert=True)

    async def get_intelligent_media(self, channel_id, user_last_seen_ids=None):
        doc = await media_col.find_one({"channel_id": str(channel_id)})
        if not doc or not doc.get("message_ids"): return None
        all_ids = doc["message_ids"]
        if not user_last_seen_ids: return random.choice(all_ids)
        seen_set = set(user_last_seen_ids[-50:])
        unseen = [m for m in all_ids if m not in seen_set]
        return random.choice(unseen) if unseen else random.choice(all_ids)

    async def get_media_count(self):
        total = 0
        async for doc in media_col.find(): total += len(doc.get("message_ids", []))
        return total

    async def index_single_message(self, bot, channel_id, message_id):
        try:
            # Check if already in DB to avoid double entry
            existing = await media_col.find_one({"channel_id": str(channel_id), "message_ids": message_id})
            if existing: return False
            
            # Fetch message with correct parameters
            msg = await bot.get_message(chat_id=channel_id, message_id=message_id)
            
            # Filter for any media type
            if any([msg.video, msg.document, msg.photo, msg.audio, msg.animation, msg.video_note]):
                await media_col.update_one(
                    {"channel_id": str(channel_id)}, 
                    {"$addToSet": {"message_ids": message_id}}, 
                    upsert=True
                )
                return True
            return False
        except Exception as e:
            logger.debug(f"Skip ID {message_id}: {e}")
            return False

user_manager = UserManager()
media_manager = MediaManager()

# ================= HANDLERS =================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    if args and args[0].startswith("ref_"):
        ref_id = args[0].split("ref_")[1]
        if ref_id != str(user.id): await user_manager.add_referral(ref_id)

    user_data = await user_manager.get_user(user.id)
    if not user_data:
        user_data = await user_manager.create_user(user.id, user.full_name)
        await send_log(context.bot, "NEW_USER", user)

    if not await check_user_membership(context.bot, user.id, FORCE_SUB_CHANNELS):
        buttons = []
        for cid in FORCE_SUB_CHANNELS:
            try:
                chat = await context.bot.get_chat(cid)
                buttons.append([InlineKeyboardButton(f"🔔 Join {chat.title}", url=chat.invite_link or await chat.export_invite_link())])
            except: pass
        buttons.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_join")])
        await update.message.reply_text("❗ Join channels to use bot:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    is_prem = await user_manager.is_premium(user.id)
    text = f"✨ Welcome {user.full_name}!\n\n📁 Category: {user_data.get('current_category', 'All')}\n🎁 Plan: {'Premium' if is_prem else 'Free'}\n⏳ Expires: {format_datetime(user_data['expires'])}"
    await update.message.reply_text(text, reply_markup=get_main_keyboard(user.id in ADMINS))

async def send_media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, specific_mid=None):
    user_id = update.effective_user.id
    user_data = await user_manager.get_user(user_id)
    await user_manager.check_reset_daily(user_id, user_data)
    user_data = await user_manager.get_user(user_id)

    is_prem = await user_manager.is_premium(user_id)
    limit = MAX_DAILY_VIDEOS_PREMIUM if is_prem else MAX_DAILY_VIDEOS_FREE
    if user_data.get("daily_videos", 0) >= limit:
        msg = update.callback_query.message if update.callback_query else update.message
        await msg.reply_text("📊 <b>Limit Reached!</b>\nBuy Premium for more.", reply_markup=get_plans_keyboard(), parse_mode="HTML")
        return

    cid = CATEGORY_CHANNELS.get(user_data.get("current_category"), DEFAULT_CHANNEL)
    mid = specific_mid or await media_manager.get_intelligent_media(cid, user_data.get("last_sent_media", []))
    
    if not mid:
        if update.callback_query: await update.callback_query.answer("No media found.", show_alert=True)
        return

    try:
        sent = await context.bot.copy_message(user_id, cid, mid, caption=CAPTION_TEXT, reply_markup=get_media_keyboard())
        if not specific_mid:
            new_h = (user_data.get("last_sent_media", []) + [mid])[-100:]
            await user_manager.update_user(user_id, {"daily_videos": user_data.get("daily_videos", 0) + 1, "last_sent_media": new_h})
        asyncio.create_task(auto_delete(context, user_id, sent.message_id))
    except Exception as e:
        logger.error(e)

async def auto_delete(context, chat_id, mid):
    await asyncio.sleep(600)
    try: await context.bot.delete_message(chat_id, mid)
    except: pass

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_data = await user_manager.get_user(query.from_user.id)
    is_prem = await user_manager.is_premium(query.from_user.id)
    text = (f"📊 <b>My Status</b>\n\n👤 {query.from_user.full_name}\n🎁 Plan: {'Premium' if is_prem else 'Free'}\n"
            f"⏳ Expires: {format_datetime(user_data['expires'])}\n✅ Watched: {user_data.get('daily_videos', 0)}\n"
            f"🔗 Referrals: {user_data.get('referrals', 0)}\n📁 Total Media: {await media_manager.get_media_count()}")
    await query.message.edit_text(text, reply_markup=get_main_keyboard(query.from_user.id in ADMINS), parse_mode="HTML")

# ================= ADMIN / INDEXING =================

async def admin_index_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.message.reply_text("📤 <b>Indexing:</b>\n\nSend Channel ID (e.g. -100...) or Link:", parse_mode="HTML")
    return "GET_CHANNEL"

async def admin_index_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        target = text if text.startswith("-") or text.startswith("@") else f"@{text.split('/')[-1]}"
        chat = await context.bot.get_chat(target)
        context.user_data['index_channel'] = chat.id
        await update.message.reply_text(f"✅ Found: {chat.title}\n\n🔢 Enter Range (e.g., `1-1000`) or send `latest` for last 100:", parse_mode="HTML")
        return "GET_RANGE"
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return ConversationHandler.END

async def admin_index_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    channel_id = context.user_data.get('index_channel')
    if not channel_id: return ConversationHandler.END

    start_id, end_id = 0, 0
    if text.lower() == "latest":
        try:
            temp = await context.bot.send_message(channel_id, "Checking latest ID...")
            end_id = temp.message_id
            await context.bot.delete_message(channel_id, end_id)
            start_id = max(1, end_id - 100)
        except Exception as e:
            await update.message.reply_text(f"❌ Error fetching latest: {e}")
            return ConversationHandler.END
    elif "-" in text:
        try:
            s, e = text.split("-")
            start_id, end_id = int(s), int(e)
        except:
            await update.message.reply_text("❌ Format: 1-100")
            return ConversationHandler.END
    else:
        return ConversationHandler.END

    asyncio.create_task(run_indexing_ui(context.bot, update.effective_user.id, channel_id, start_id, end_id))
    await update.message.reply_text(f"🚀 Started indexing {start_id} to {end_id}...")
    return ConversationHandler.END

async def run_indexing_ui(bot, admin_id, channel_id, start, end):
    total = end - start + 1
    indexed = 0
    status_msg = await bot.send_message(admin_id, "⌛ <b>Preparing Indexing...</b>", parse_mode="HTML")
    last_update = 0

    for i in range(start, end + 1):
        if await media_manager.index_single_message(bot, channel_id, i):
            indexed += 1
        
        curr_time = asyncio.get_event_loop().time()
        if curr_time - last_update > 8:
            processed = i - start + 1
            percent = (processed / total) * 100
            bar = "▓" * int(percent / 10) + "░" * (10 - int(percent / 10))
            text = (f"🚀 <b>Indexing Progress</b>\n\n"
                    f"📂 Range: <code>{start}-{end}</code>\n"
                    f"✅ Indexed: <code>{indexed}</code>\n"
                    f"🔄 Processed: <code>{processed}/{total}</code>\n"
                    f"📊 Status: <code>{percent:.2f}%</code>\n\n"
                    f"<code>[{bar}]</code>")
            try: await status_msg.edit_text(text, parse_mode="HTML")
            except: pass
            last_update = curr_time
        await asyncio.sleep(0.05)

    await bot.send_message(admin_id, f"✅ <b>Indexing Finished!</b>\n\nTotal Files Added: {indexed}\nChannel: <code>{channel_id}</code>", parse_mode="HTML")

# ================= ADMIN PANEL & OTHER HANDLERS =================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMINS: return
    try: await query.message.delete()
    except: pass
    await context.bot.send_message(query.from_user.id, "⚙️ <b>Admin Panel</b>", reply_markup=get_admin_keyboard(), parse_mode="HTML")

async def admin_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text("👤 <b>Send User ID:</b>", parse_mode="HTML")
    return "GET_USER_ID"

async def admin_premium_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['premium_user_id'] = update.message.text.strip()
    await update.message.reply_text("📅 <b>Days:</b>", parse_mode="HTML")
    return "GET_DAYS"

async def admin_premium_get_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        days = int(update.message.text)
        exp = await user_manager.set_premium(context.user_data['premium_user_id'], days)
        await update.message.reply_text(f"✅ Success! New Expiry: {format_datetime(exp)}")
    except: await update.message.reply_text("❌ Error.")
    return ConversationHandler.END

async def proof_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text("📸 <b>Send Screenshot:</b>", parse_mode="HTML")
    return "WAITING_PROOF"

async def proof_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_photo(LOG_CHANNEL_ID, update.message.photo[-1].file_id, caption=f"#Proof\nID: {update.effective_user.id}")
    await update.message.reply_text("✅ Proof Sent to Admins.", reply_markup=get_main_keyboard(update.effective_user.id in ADMINS))
    return ConversationHandler.END

async def cancel_op(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Cancelled.")
    return ConversationHandler.END

async def plans_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cap = "💎 <b>Premium Plans:</b>\n\n• 100 videos/day\n• No Ads\n• Direct Links"
    await context.bot.send_photo(update.effective_user.id, PLAN_IMG_URL, caption=cap, reply_markup=get_plans_keyboard(), parse_mode="HTML")

async def callback_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data, user_id = query.data, query.from_user.id
    
    if data == "status": await status_command(update, context)
    elif data in ["send_media", "next"]: await send_media_handler(update, context)
    elif data == "previous":
        ud = await user_manager.get_user(user_id)
        h = ud.get("last_sent_media", [])
        if len(h) > 1: await send_media_handler(update, context, h[-2])
        else: await query.answer("No History.", show_alert=True)
    elif data == "change_category": await query.message.edit_text("Select Category:", reply_markup=get_category_keyboard())
    elif data.startswith("set_category_"):
        await user_manager.update_user(user_id, {"current_category": data.replace("set_category_", "")})
        await query.message.edit_text("✅ Category Updated!", reply_markup=get_main_keyboard(user_id in ADMINS))
    elif data == "plans": await plans_menu(update, context)
    elif data == "admin_panel": await admin_panel(update, context)
    elif data == "admin_stats":
        u_cnt = await users_col.count_documents({})
        m_cnt = await media_manager.get_media_count()
        await query.message.edit_text(f"📊 Stats:\nUsers: {u_cnt}\nMedia: {m_cnt}", reply_markup=get_admin_keyboard())
    elif data == "back_to_menu_del": 
        try: await query.message.delete()
        except: pass
        await start_command(update, context)
    elif data == "back_to_menu": await query.message.edit_text("✨ Welcome!", reply_markup=get_main_keyboard(user_id in ADMINS))
    elif data == "close": await query.message.delete()
    elif data == "check_join": await start_command(update, context)
    
    try: await query.answer()
    except: pass

async def save_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = update.channel_post
    if p and any([p.video, p.document, p.photo, p.audio, p.animation]):
        await media_manager.add_media(p.chat_id, p.message_id)

async def web_start():
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text="Bot Alive"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()

async def post_init(app: Application):
    await web_start()
    try: await app.bot.send_message(LOG_CHANNEL_ID, "🟢 <b>Bot Online & Web Server Started</b>", parse_mode="HTML")
    except: pass

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(proof_start, pattern="^submit_proof$")],
        states={"WAITING_PROOF": [MessageHandler(filters.PHOTO, proof_receive)]},
        fallbacks=[CommandHandler("cancel", cancel_op)]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_premium_start, pattern="^admin_add_premium$")],
        states={"GET_USER_ID": [MessageHandler(filters.TEXT, admin_premium_get_id)], "GET_DAYS": [MessageHandler(filters.TEXT, admin_premium_get_days)]},
        fallbacks=[CommandHandler("cancel", cancel_op)]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_index_start, pattern="^admin_index$")],
        states={"GET_CHANNEL": [MessageHandler(filters.TEXT, admin_index_channel)], "GET_RANGE": [MessageHandler(filters.TEXT, admin_index_run)]},
        fallbacks=[CommandHandler("cancel", cancel_op)]
    ))

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(callback_dispatcher))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, save_media))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
