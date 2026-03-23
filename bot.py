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
from telegram.error import TelegramError

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
UPI_ID = os.getenv("UPI_ID", "Amit0000@fam") 
PLAN_IMG_URL = "QR.jpg" 

# ================= CHANNEL SETUP =================
FORCE_SUB_CHANNELS = [-1003627956964]
CATEGORY_CHANNELS = {
    "🎬 All ": -1003776098672,
}
DEFAULT_CHANNEL = -1003776098672

# ================= BOT SETTINGS =================
IST = pytz.timezone('Asia/Kolkata')
REFERRAL_REQUIREMENT = 1  # Users needed for 1 Day Free Premium
MAX_DAILY_VIDEOS_FREE = 6 
MAX_DAILY_VIDEOS_PREMIUM = 100
AUTO_DELETE_SECONDS = 600 # 10 Minutes

CAPTION_TEXT = (
    "ⓘ 𝙏𝙝𝙞𝙨 𝙢𝙚𝙙𝙞𝙖 𝙬𝙞𝙡𝙡 𝙗𝙚 𝙖𝙪𝙩𝙤𝙢𝙖𝙩𝙞𝙘𝙖𝙡𝙡𝙮 𝙙𝙚𝙡𝙚𝙩𝙚𝙙 𝙖𝙛𝙩𝙚𝙧 10 𝙢𝙞𝙣𝙪𝙩𝙚𝙨.\n"
    "𝙋𝙡𝙚𝙖𝙨𝙚 𝙗𝙤𝙤𝙠𝙢𝙖𝙧𝙠 𝙤𝙧 𝙙𝙤𝙬𝙣𝙡𝙤𝙖𝙙 𝙞𝙛 𝙮𝙤𝙪 𝙬𝙖𝙣𝙩 𝙩𝙤 𝙬𝙖𝙩𝙘𝙝 𝙡𝙖𝙩𝙚𝙧.\n\n\n"
    "━━━━━━━━━━━━━━━\n"
    "🤖 𝙈𝙤𝙫𝙞𝙚 𝘽𝙤𝙩 : @ChaudharyAutoFilterbot\n"
    "📢 𝘽𝙖𝙘𝙠𝙪𝙥 𝘾𝙝𝙖𝙣𝙣𝙚𝙡 : @cinewood_flix\n"
    "🔒 𝙋𝙧𝙞𝙫𝙖𝙩𝙚 𝘾𝙝𝙖𝙣𝙣𝙚𝙡 : https://t.me/+IKEPBquEvmc0ODhl\n"
    "━━━━━━━━━━━━━━━"
)

# ================= DATABASE SETUP =================
client = AsyncIOMotorClient(
    MONGO_URI,
    tls=True,
    tlsAllowInvalidCertificates=False
)

db = client["telegram_bot_db"]
users_col = db["users"]
media_col = db["media"]
proofs_col = db["pending_proofs"]

# ================= UTILITY FUNCTIONS =================

def get_ist_now():
    return datetime.now(IST)

def format_datetime(dt_str):
    if isinstance(dt_str, str):
        try:
            dt = datetime.fromisoformat(dt_str)
        except ValueError:
            dt = datetime.now()
    else:
        dt = dt_str
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.strftime("%d/%m/%Y, %I:%M %p")

async def send_log(bot, log_type, user, additional_text=""):
    if log_type == "NEW_USER":
        text = (
            "#NewUser\n\n"
            f"Iᴅ - <code>{user.id}</code>\n"
            f"Nᴀᴍᴇ - {user.full_name}\n"
            f"Dᴀᴛᴇ - {get_ist_now().strftime('%d/%m/%Y')}"
        )
        try:
            await bot.send_message(LOG_CHANNEL_ID, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Log error: {e}")

async def check_user_membership(bot, user_id, channels):
    if not channels: return True
    for channel_id in channels:
        try:
            member = await bot.get_chat_member(channel_id, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
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
    if is_admin:
        buttons.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

def get_media_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👍 Like", callback_data="like"), 
         InlineKeyboardButton("👎 Dislike", callback_data="dislike")],
        [InlineKeyboardButton("⏮ Previous", callback_data="previous"), 
         InlineKeyboardButton("⏭ Next", callback_data="next")],
        [InlineKeyboardButton("🔄 Category", callback_data="change_category"), 
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])

def get_plans_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("2 Days - ₹9", callback_data="pay_1"),
         InlineKeyboardButton("7 Days - ₹29", callback_data="pay_2")],
        [InlineKeyboardButton("1 Months - ₹99", callback_data="pay_3")],
        [InlineKeyboardButton(f"🎁 Free 1 Day ({REFERRAL_REQUIREMENT} Refers)", callback_data="plan_referral")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu_del")] 
    ])

def get_payment_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Send Payment Proof", callback_data="submit_proof")],
        [InlineKeyboardButton("🔙 Back", callback_data="plans")]
    ])

def get_category_keyboard():
    buttons = []
    for category in CATEGORY_CHANNELS.keys():
        buttons.append([InlineKeyboardButton(f"{category}", callback_data=f"set_category_{category}")])
    buttons.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)

async def get_admin_keyboard():
    count = await proofs_col.count_documents({})
    proof_text = f"🔔 Pending Proofs ({count})" if count > 0 else "🔔 No Pending Proofs"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(proof_text, callback_data="admin_check_proofs")],
        [InlineKeyboardButton("➕ Add Premium (Manual)", callback_data="admin_add_premium")],
        [InlineKeyboardButton("📤 Index Channel", callback_data="admin_index")],
        [InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_menu")]
    ])

# ================= USER MANAGER =================

class UserManager:
    async def get_user(self, user_id):
        return await users_col.find_one({"_id": str(user_id)})

    async def create_user(self, user_id, name):
        expiry = get_ist_now()
        default_cat = list(CATEGORY_CHANNELS.keys())[0] if CATEGORY_CHANNELS else "🎬 All "
        user_data = {
            "_id": str(user_id),
            "name": name,
            "plan": "free",
            "expires": expiry.isoformat(),
            "referrals": 0,
            "daily_videos": 0,
            "last_reset_date": get_ist_now().strftime("%Y-%m-%d"),
            "current_category": default_cat,
            "last_sent_media": [],
            "last_activity": get_ist_now().isoformat()
        }
        await users_col.update_one({"_id": str(user_id)}, {"$set": user_data}, upsert=True)
        return user_data

    async def update_user(self, user_id, updates):
        updates["last_activity"] = get_ist_now().isoformat()
        await users_col.update_one({"_id": str(user_id)}, {"$set": updates})

    async def check_reset_daily(self, user_id, user_data):
        today_str = get_ist_now().strftime("%Y-%m-%d")
        if user_data.get("last_reset_date") != today_str:
            await users_col.update_one(
                {"_id": str(user_id)}, 
                {"$set": {"daily_videos": 0, "last_reset_date": today_str}}
            )
            return True
        return False

    async def add_referral(self, referrer_id, context):
        referrer = await self.get_user(referrer_id)
        if not referrer: return

        new_refs = referrer.get("referrals", 0) + 1
        await self.update_user(referrer_id, {"referrals": new_refs})

        if new_refs % REFERRAL_REQUIREMENT == 0:
            new_exp = await self.set_premium(referrer_id, 1)
            try:
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=(
                        f"🎉 <b>Congratulations!</b>\n\n"
                        f"You have referred {new_refs} users in total.\n"
                        f"✅ <b>1 Day Free Premium</b> has been activated!\n\n"
                        f"⏳ <b>New Expiry:</b> {format_datetime(new_exp)}\n\n"
                        f"<i>Refer {REFERRAL_REQUIREMENT} more new users to get another day!</i>"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to notify referrer {referrer_id}: {e}")

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
        
        await users_col.update_one(
            {"_id": str(user_id)},
            {"$set": {
                "expires": new_exp.isoformat(), 
                "plan": "premium", 
                "daily_videos": 0
            }},
            upsert=True
        )
        return new_exp

# ================= MEDIA MANAGER =================

class MediaManager:
    async def add_media(self, channel_id, message_id):
        await media_col.update_one(
            {"channel_id": str(channel_id)},
            {"$addToSet": {"message_ids": message_id}},
            upsert=True
        )

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
        async for doc in media_col.find():
            total += len(doc.get("message_ids", []))
        return total

    async def index_single_message(self, bot, channel_id, message_id):
        try:
            existing = await media_col.find_one({"channel_id": str(channel_id), "message_ids": message_id})
            if existing: return False
            msg = await bot.get_message(channel_id, message_id)
            if msg.photo or msg.video or msg.document:
                await media_col.update_one({"channel_id": str(channel_id)}, {"$addToSet": {"message_ids": message_id}}, upsert=True)
                return True
            return False
        except: return False

user_manager = UserManager()
media_manager = MediaManager()

# ================= BROADCAST FEATURE =================

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMINS: return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠ <b>Please reply to a message to broadcast it.</b>", parse_mode="HTML")
        return

    target_msg = update.message.reply_to_message
    status_msg = await update.message.reply_text("🚀 <b>Broadcast Started...</b>", parse_mode="HTML")
    
    all_users = users_col.find({})
    total_users = await users_col.count_documents({})
    
    success = 0
    blocked = 0
    deleted = 0
    
    async for u in all_users:
        try:
            await context.bot.copy_message(
                chat_id=int(u['_id']),
                from_chat_id=target_msg.chat_id,
                message_id=target_msg.message_id
            )
            success += 1
            await asyncio.sleep(0.05) 
        except TelegramError as e:
            if "blocked" in str(e).lower(): blocked += 1
            elif "user is deactivated" in str(e).lower(): deleted += 1
            else: pass
    
    text = (
        f"✅ <b>Broadcast Completed!</b>\n\n"
        f"👥 Total Users: {total_users}\n"
        f"📩 Sent: {success}\n"
        f"🚫 Blocked: {blocked}\n"
        f"🗑 Deleted: {deleted}"
    )
    await status_msg.edit_text(text, parse_mode="HTML")

# ================= MAIN FEATURES =================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    
    existing_user = await user_manager.get_user(user.id)
    
    if not existing_user:
        user_data = await user_manager.create_user(user.id, user.full_name)
        await send_log(context.bot, "NEW_USER", user)
        
        if args and args[0].startswith("ref_"):
            try:
                ref_id = args[0].split("ref_")[1]
                if ref_id != str(user.id): 
                    await user_manager.add_referral(ref_id, context)
            except Exception as e:
                logger.error(f"Referral error: {e}")
    else:
        user_data = existing_user

    if not await check_user_membership(context.bot, user.id, FORCE_SUB_CHANNELS):
        buttons = []
        for cid in FORCE_SUB_CHANNELS:
            try:
                chat = await context.bot.get_chat(cid)
                link = chat.invite_link or await chat.export_invite_link()
                buttons.append([InlineKeyboardButton(f"🔔 Join {chat.title}", url=link)])
            except: pass
        buttons.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_join")])
        await update.message.reply_text("❗ Join channels to use bot:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    is_premium = await user_manager.is_premium(user.id)
    plan_name = "Premium" if is_premium else "Free (Limited)"
    
    text = (
        f"✨ Welcome {user.full_name}!\n\n"
        f"📁 Category: {user_data.get('current_category', 'All')}\n"
        f"🎁 Plan: {plan_name}\n"
        f"⏳ Expires: {format_datetime(user_data['expires'])}"
    )
    await update.message.reply_text(text, reply_markup=get_main_keyboard(user.id in ADMINS))

async def send_media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, specific_mid=None):
    if update.callback_query:
        query = update.callback_query
        user_id = query.from_user.id
        message = query.message
    else:
        user_id = update.effective_user.id
        message = update.message

    user_data = await user_manager.get_user(user_id)
    
    if await user_manager.check_reset_daily(user_id, user_data):
        user_data = await user_manager.get_user(user_id) 

    is_premium = await user_manager.is_premium(user_id)
    limit = MAX_DAILY_VIDEOS_PREMIUM if is_premium else MAX_DAILY_VIDEOS_FREE
    
    if user_data.get("daily_videos", 0) >= limit:
        msg = f"📊 <b>Daily Limit Reached!</b>\n\nFree User Limit: {MAX_DAILY_VIDEOS_FREE} videos/day.\nResets at 12:00 AM IST.\n\n👇 Buy Premium for 100 videos/day!"
        markup = get_plans_keyboard()
        if update.callback_query: 
            await query.message.reply_text(msg, reply_markup=markup, parse_mode="HTML")
            await query.answer()
        else: await message.reply_text(msg, reply_markup=markup, parse_mode="HTML")
        return

    cid = CATEGORY_CHANNELS.get(user_data.get("current_category"), DEFAULT_CHANNEL)
    
    if specific_mid:
        mid = specific_mid
    else:
        mid = await media_manager.get_intelligent_media(cid, user_data.get("last_sent_media", []))

    if not mid:
        if update.callback_query: await query.answer("No media found.", show_alert=True)
        return

    try:
        # PROTECT_CONTENT = TRUE added here
        sent = await context.bot.copy_message(
            chat_id=user_id, 
            from_chat_id=cid, 
            message_id=mid, 
            caption=CAPTION_TEXT, 
            reply_markup=get_media_keyboard(),
            protect_content=True # <--- Prevents Forwarding and Saving
        )
        
        if not specific_mid:
            new_history = (user_data.get("last_sent_media", []) + [mid])[-100:]
            await user_manager.update_user(user_id, {
                "daily_videos": user_data.get("daily_videos", 0) + 1,
                "last_sent_media": new_history
            })
        
        if update.callback_query: await query.answer()
        asyncio.create_task(auto_delete(context, user_id, sent.message_id))
    except Exception as e:
        logger.error(f"Send failed: {e}")
        if update.callback_query: await query.answer("Media unavailable.", show_alert=True)

async def auto_delete(context, chat_id, mid):
    await asyncio.sleep(AUTO_DELETE_SECONDS)
    try: await context.bot.delete_message(chat_id, mid)
    except: pass

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_data = await user_manager.get_user(user.id)
    
    if await user_manager.check_reset_daily(user.id, user_data):
        user_data = await user_manager.get_user(user.id)

    is_premium = await user_manager.is_premium(user.id)
    plan_name = "Premium" if is_premium else "Free (Limited)"
    total_media = await media_manager.get_media_count()
    watched = user_data.get("daily_videos", 0)
    refs = user_data.get("referrals", 0)
    
    text = (
        f"📊 <b>My Status</b>\n\n"
        f"👤 {user.full_name}\n"
        f"🎁 Plan: {plan_name}\n"
        f"⏳ Expires: {format_datetime(user_data['expires'])}\n"
        f"🎬 Category: {user_data.get('current_category', 'All')}\n"
        f"✅ Watched Today: {watched}\n"
        f"📥 Downloads Today: {watched}\n"
        f"🔗 Total Referrals: {refs}\n"
        f"🎯 Next Reward At: {(refs // REFERRAL_REQUIREMENT + 1) * REFERRAL_REQUIREMENT} Referrals\n"
        f"📁 Total Media in Bot: {total_media}"
    )
    
    await query.message.edit_text(text, reply_markup=get_main_keyboard(user.id in ADMINS), parse_mode="HTML")

# ================= PLAN & PAYMENT HANDLERS =================

async def plans_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    caption = (
        "💎 <b>Premium Plans Benefits:</b>\n\n"
        "• 🎥 100 videos/day\n"
        "• ⚡ Unlimited downloads\n"
        "• 🚫 Ad-free experience\n"
        "• 🔓 Early access to new videos\n\n"
        "👇 <b>Select a plan:</b>"
    )
    
    if query.message.photo:
        await query.message.edit_caption(caption=caption, reply_markup=get_plans_keyboard(), parse_mode="HTML")
    else:
        await query.message.delete()
        await context.bot.send_photo(
            chat_id=query.from_user.id,
            photo=PLAN_IMG_URL,
            caption=caption,
            reply_markup=get_plans_keyboard(),
            parse_mode="HTML"
        )

async def handle_payment_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    plan_map = {
        "pay_1": ("2 Days", "9"),
        "pay_2": ("7 Days", "29"),
        "pay_3": ("1 Months", "99")
    }
    
    name, price = plan_map[data]
    user_id = query.from_user.id
    
    caption = (
        "🧾 <b>Payment Details:</b>\n\n"
        f"Plan: <b>{name}</b>\n"
        f"Amount: <b>{price} Ruppee</b>\n"
        f"UPI ID: <code>{UPI_ID}</code>\n\n"
        f"🆔 <b>Your User Id:</b> <code>{user_id}</code>\n\n"
        "<i>Scan QR or Pay through UPI ID and send Payment proof.</i>"
    )
    
    await query.message.edit_caption(caption=caption, reply_markup=get_payment_keyboard(), parse_mode="HTML")

# ================= PROOF SUBMISSION & STORAGE =================

async def proof_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("📸 <b>Send screenshot here</b>:", parse_mode="HTML")
    return "WAITING_PROOF"

async def proof_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo = update.message.photo[-1].file_id
    
    proof_data = {
        "user_id": user.id,
        "name": user.full_name,
        "file_id": photo,
        "date": get_ist_now(),
        "status": "pending"
    }
    
    await proofs_col.insert_one(proof_data)

    await update.message.reply_text(
        "✅ <b>Proof Sent Successfully!</b>\n\n"
        "Please wait for admin approval. You will be notified.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(user.id in ADMINS)
    )
    return ConversationHandler.END

async def proof_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END

# ================= ADMIN PROOF PROCESSING (QUEUE) =================

async def admin_check_proofs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMINS:
        return
        
    proof = await proofs_col.find_one({"status": "pending"}, sort=[("date", 1)])
    
    if not proof:
        await query.message.edit_text(
            "✅ <b>No Pending Proofs!</b>", 
            reply_markup=await get_admin_keyboard(),
            parse_mode="HTML"
        )
        return

    caption = (
        f"🔔 <b>Pending Proof</b>\n\n"
        f"👤 Name: {proof['name']}\n"
        f"🆔 ID: <code>{proof['user_id']}</code>\n"
        f"📅 Date: {proof['date'].strftime('%d/%m/%Y %I:%M %p')}\n\n"
        "👇 <b>Select Action:</b>"
    )
    
    admin_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"verify_acc_{proof['user_id']}_{str(proof['_id'])}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"verify_rej_{proof['user_id']}_{str(proof['_id'])}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]
    ])
    
    try:
        if query.message.photo:
             await query.message.edit_media(
                media=InputMediaPhoto(media=proof['file_id'], caption=caption, parse_mode="HTML"),
                reply_markup=admin_markup
            )
        else:
            await query.message.delete()
            await context.bot.send_photo(
                chat_id=query.from_user.id,
                photo=proof['file_id'],
                caption=caption,
                reply_markup=admin_markup,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Error showing proof: {e}")
        await proofs_col.delete_one({"_id": proof["_id"]})
        await query.message.reply_text("❌ Error loading proof. Removed from queue.")

async def admin_verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("_")
    action = data[1]
    user_id = int(data[2])
    proof_oid = data[3]
    
    context.user_data['target_user_id'] = user_id
    context.user_data['proof_oid'] = proof_oid
    
    if action == "acc":
        await query.message.reply_text(
            f"✅ <b>Approving User:</b> <code>{user_id}</code>\n\n"
            "🔢 <b>Enter number of days:</b>",
            parse_mode="HTML"
        )
        return "ADMIN_WAIT_DAYS"
        
    elif action == "rej":
        await query.message.reply_text(
            f"❌ <b>Rejecting User:</b> <code>{user_id}</code>\n\n"
            "📝 <b>Enter reason:</b>",
            parse_mode="HTML"
        )
        return "ADMIN_WAIT_REASON"

async def admin_process_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = context.user_data.get('target_user_id')
    proof_oid = context.user_data.get('proof_oid')
    
    if not text.isdigit():
        await update.message.reply_text("❌ Please enter a valid number.")
        return "ADMIN_WAIT_DAYS"
    
    days = int(text)
    new_exp = await user_manager.set_premium(user_id, days)
    
    try:
        await context.bot.send_message(
            user_id,
            f"🎉 <b>Payment Approved!</b>\n\n"
            f"💎 Plan activated for {days} days.\n"
            f"📅 Expires: {format_datetime(new_exp)}\n\n"
            "Enjoy premium features!",
            parse_mode="HTML"
        )
    except: pass
    
    from bson.objectid import ObjectId
    try: await proofs_col.delete_one({"_id": ObjectId(proof_oid)})
    except: pass

    await update.message.reply_text("✅ Approved.")
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔔 Check Next Proof", callback_data="admin_check_proofs")]])
    await update.message.reply_text("🔽 Continue?", reply_markup=kb)
    return ConversationHandler.END

async def admin_process_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text
    user_id = context.user_data.get('target_user_id')
    proof_oid = context.user_data.get('proof_oid')
    
    try:
        await context.bot.send_message(
            user_id,
            f"❌ <b>Payment Rejected</b>\n\n"
            f"📝 Reason: {reason}",
            parse_mode="HTML"
        )
    except: pass
    
    from bson.objectid import ObjectId
    try: await proofs_col.delete_one({"_id": ObjectId(proof_oid)})
    except: pass

    await update.message.reply_text("✅ Rejected.")
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔔 Check Next Proof", callback_data="admin_check_proofs")]])
    await update.message.reply_text("🔽 Continue?", reply_markup=kb)
    return ConversationHandler.END

# ================= ADMIN HANDLERS (General) =================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMINS:
        await query.answer("❌ Admins Only!", show_alert=True)
        return
    
    markup = await get_admin_keyboard()
    
    if query.message.photo:
        await query.message.delete()
        await context.bot.send_message(query.from_user.id, "⚙️ <b>Admin Panel</b>", reply_markup=markup, parse_mode="HTML")
    else:
        await query.message.edit_text("⚙️ <b>Admin Panel</b>", reply_markup=markup, parse_mode="HTML")

async def admin_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMINS: return ConversationHandler.END
    if query.message.text: await query.message.edit_text("👤 <b>Send User ID</b>:", parse_mode="HTML")
    else: await query.message.reply_text("👤 <b>Send User ID</b>:", parse_mode="HTML")
    return "GET_USER_ID"

async def admin_premium_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['premium_user_id'] = int(update.message.text.strip())
        await update.message.reply_text("📅 <b>Enter Days:</b> (e.g., 30)", parse_mode="HTML")
        return "GET_DAYS"
    except:
        await update.message.reply_text("❌ Invalid ID.")
        return "GET_USER_ID"

async def admin_premium_get_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        days = int(update.message.text.strip())
        user_id = context.user_data['premium_user_id']
        new_exp = await user_manager.set_premium(user_id, days)
        await update.message.reply_text(f"✅ User {user_id} Updated!\nExpires: {format_datetime(new_exp)}")
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Invalid days.")
        return "GET_DAYS"

async def admin_index_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMINS: return ConversationHandler.END
    await query.message.reply_text("📤 Send Channel Link/ID:", parse_mode="HTML")
    return "GET_CHANNEL"

async def admin_index_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        chat = await context.bot.get_chat(text if text.startswith("-") or text.startswith("@") else f"@{text.split('/')[-1]}")
        context.user_data['index_channel'] = chat.id
        await update.message.reply_text(f"✅ Found: {chat.title}\n🔢 Enter range `1-100` or `latest`:", parse_mode="HTML")
        return "GET_RANGE"
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return ConversationHandler.END

async def admin_index_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    channel_id = context.user_data['index_channel']
    start_id, end_id = 0, 0
    if text.lower() == "latest":
        try:
            msg = await context.bot.send_message(channel_id, ".")
            end_id = msg.message_id
            await context.bot.delete_message(channel_id, end_id)
            start_id = max(1, end_id - 100)
        except: 
            await update.message.reply_text("❌ Bot needs admin rights to check latest.")
            return ConversationHandler.END
    elif "-" in text:
        s, e = text.split("-")
        start_id, end_id = int(s), int(e)
    
    await update.message.reply_text("🚀 Indexing started...")
    asyncio.create_task(run_indexing(context.bot, update.effective_user.id, channel_id, start_id, end_id))
    return ConversationHandler.END

async def run_indexing(bot, admin_id, channel_id, start, end):
    indexed = 0
    for i in range(start, end + 1):
        if await media_manager.index_single_message(bot, channel_id, i): indexed += 1
        if i % 50 == 0: await asyncio.sleep(1)
    await bot.send_message(admin_id, f"✅ Indexing Done! Added {indexed} files.")

async def cancel_op(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Cancelled.")
    return ConversationHandler.END

# ================= DISPATCHER =================

async def callback_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    user_id = update.callback_query.from_user.id
    
    if data == "status":
        if update.callback_query.message.photo: 
            await update.callback_query.message.delete()
            await status_command(update, context) 
        else:
            await status_command(update, context)
            
    elif data == "send_media" or data == "next":
        await send_media_handler(update, context)
        
    elif data == "previous":
        user_data = await user_manager.get_user(user_id)
        history = user_data.get("last_sent_media", [])
        if len(history) >= 2:
            prev_id = history[-2] 
            await send_media_handler(update, context, specific_mid=prev_id)
        else:
            await update.callback_query.answer("⚠️ No history.", show_alert=True)

    elif data == "change_category":
        await update.callback_query.message.edit_text("Select Category:", reply_markup=get_category_keyboard())
    
    elif data.startswith("set_category_"):
        cat = data.replace("set_category_", "")
        await user_manager.update_user(user_id, {"current_category": cat})
        await update.callback_query.message.edit_text(f"✅ Category set to: {cat}", reply_markup=get_main_keyboard(user_id in ADMINS))
        
    elif data == "plans":
        await plans_menu(update, context)
        
    elif data.startswith("pay_"):
        await handle_payment_selection(update, context)
            
    elif data == "plan_referral":
        link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
        user = await user_manager.get_user(user_id)
        count = user.get('referrals', 0)
        needed = REFERRAL_REQUIREMENT - (count % REFERRAL_REQUIREMENT)
        
        caption = (
            f"🔗 <b>Referral Program</b>\n\n"
            f"Link: `{link}`\n\n"
            f"Invite {REFERRAL_REQUIREMENT} New Friends = 1 Day Premium!\n\n"
            f"📊 Your Total Invites: <b>{count}</b>\n"
            f"🚀 Invites needed for next reward: <b>{needed}</b>"
        )
        if update.callback_query.message.photo:
            await update.callback_query.message.edit_caption(caption=caption, reply_markup=get_plans_keyboard(), parse_mode="HTML")
        else:
            await plans_menu(update, context)

    elif data == "admin_panel":
        await admin_panel(update, context)
        
    elif data == "admin_check_proofs":
        await admin_check_proofs(update, context)
        
    elif data == "back_to_menu":
        await update.callback_query.message.edit_text(f"✨ Welcome!", reply_markup=get_main_keyboard(user_id in ADMINS))
    
    elif data == "back_to_menu_del":
        await update.callback_query.message.delete()
        await start_command(update, context)

    elif data == "like": await update.callback_query.answer("👍 Liked!")
    elif data == "dislike": await update.callback_query.answer("👎 Disliked!")
    elif data == "close": await update.callback_query.message.delete()
    
    elif data == "admin_stats":
        cnt = await users_col.count_documents({})
        med = await media_manager.get_media_count()
        await update.callback_query.message.edit_text(f"📊 Users: {cnt}\n📁 Media: {med}", reply_markup=await get_admin_keyboard())

async def save_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if msg and (msg.video or msg.document or msg.photo):
        await media_manager.add_media(msg.chat_id, msg.message_id)

# ================= SERVER & MAIN =================

async def web_start():
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text="Bot Alive"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()

async def post_init(app: Application):
    await web_start()
    try: 
        await client.admin.command('ping')
        await app.bot.send_message(LOG_CHANNEL_ID, "🟢 <b>Bot Restarted & Online</b>", parse_mode="HTML")
    except Exception as e: logger.error(e)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Conversations
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(proof_start, pattern="^submit_proof$")],
        states={"WAITING_PROOF": [MessageHandler(filters.PHOTO, proof_receive)]},
        fallbacks=[CommandHandler("cancel", proof_cancel)]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_verify_callback, pattern=r"^verify_")],
        states={
            "ADMIN_WAIT_DAYS": [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_approve)],
            "ADMIN_WAIT_REASON": [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_reject)],
        },
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

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    
    # Handlers
    app.add_handler(CallbackQueryHandler(callback_dispatcher))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, save_media))
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
