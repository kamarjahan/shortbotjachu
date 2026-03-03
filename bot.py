import os
import asyncio
import aiohttp
import logging
import urllib.request
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery


# Force logs to show up immediately
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
API_ID_STR = os.environ.get("API_ID", "0")
API_ID = int(API_ID_STR) if API_ID_STR.strip().isdigit() else 0
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
JACHU_API_KEY = os.environ.get("JACHU_API_KEY", "")

# --- 1. FORCE CLEAR GHOST WEBHOOKS & STUCK UPDATES ---
try:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
    urllib.request.urlopen(url)
    logger.info("🧹 Cleared old webhooks and pending updates from Telegram.")
except Exception as e:
    logger.warning(f"Could not clear webhooks (this is usually fine): {e}")

user_states = {}

# --- 2. INSTANTIATE WITH in_memory=True ---
# This forces the bot to ignore old .session files and strictly use your Bot Token
app = Client("jachu_shortener_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Dummy Web Server ---
async def health_check(request):
    return web.Response(text="Bot is alive and running!")

# --- 3. THE RADAR LOGGER ---
# This runs BEFORE any other command and logs every single interaction to your Hugging Face console.
@app.on_message(filters.all, group=-1)
async def catch_all_logger(client: Client, message: Message):
    sender = message.from_user.first_name if message.from_user else "Unknown"
    text = message.text or "Non-text message"
    logger.info(f"📥 RADAR DETECTED MESSAGE from {sender}: {text}")

# --- API Helper Function ---
async def shorten_url(url: str, slug: str = None) -> dict:
    api_url = "https://jachu.xyz/api/create"
    headers = {"Content-Type": "application/json", "X-API-Key": JACHU_API_KEY}
    payload = {"url": url}
    if slug: payload["slug"] = slug

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(api_url, headers=headers, json=payload) as response:
                return await response.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

# --- Bot Commands ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_states.pop(message.from_user.id, None)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Read Legal Docs 📜", url="https://jachu.xyz/legal")],
        [InlineKeyboardButton("Help❓", callback_data="help_info")]
    ])
    await message.reply_text("👋 Welcome! Send me a link starting with http:// or https:// and I'll shorten it.", reply_markup=keyboard)

@app.on_message(filters.regex(r"^https?://") & filters.private)
async def handle_url(client: Client, message: Message):
    user_id = message.from_user.id
    user_states[user_id] = {"url": message.text.strip(), "step": "CHOOSE_MODE"}
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔀 Random Alias", callback_data="mode_random")],
        [InlineKeyboardButton("✍️ Custom Alias", callback_data="mode_custom")]
    ])
    await message.reply_text("How would you like to shorten it?", reply_markup=keyboard)

@app.on_callback_query(filters.regex(r"^mode_"))
async def handle_callback_query(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    mode = callback_query.data
    
    if user_id not in user_states:
        return await callback_query.answer("Session expired. Send link again.", show_alert=True)

    if mode == "mode_random":
        await callback_query.message.edit_text("⏳ Shortening...")
        result = await shorten_url(user_states[user_id]["url"])
        if result.get("status") == "success":
            await callback_query.message.edit_text(f"✅ **Success!**\n{result.get('short_url')}")
        else:
            await callback_query.message.edit_text(f"❌ **Error:** {result.get('message')}")
        user_states.pop(user_id, None)

    elif mode == "mode_custom":
        user_states[user_id]["step"] = "WAITING_FOR_ALIAS"
        await callback_query.message.edit_text("Please type your custom alias (e.g., `my-link`).")

@app.on_message(filters.text & filters.private & ~filters.command(["start"]))
async def handle_custom_alias(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in user_states and user_states[user_id].get("step") == "WAITING_FOR_ALIAS":
        alias = message.text.strip()
        processing_msg = await message.reply_text(f"⏳ Claiming alias `{alias}`...")
        result = await shorten_url(user_states[user_id]["url"], slug=alias)
        
        if result.get("status") == "success":
            await processing_msg.edit_text(f"✅ **Success!**\n{result.get('short_url')}")
            user_states.pop(user_id, None)
        else:
            await processing_msg.edit_text(f"❌ **Failed:** {result.get('message')}\n\nAlias likely taken. Reply with a **different alias**.")

@app.on_callback_query(filters.regex("help_info"))
async def help_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.answer("Send any valid URL starting with http:// or https:// to start!", show_alert=True)

# --- Main Loop ---
async def main():
    server = web.Application()
    server.router.add_get('/', health_check)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 7860))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"✅ Web server started on port {port}.")

    if not API_ID or not API_HASH or not BOT_TOKEN:
        logger.error("❌ CRITICAL: Missing API_ID, API_HASH, or BOT_TOKEN in Secrets!")
        while True:
            await asyncio.sleep(3600)

    logger.info("⏳ Starting Pyrogram bot...")
    try:
        await app.start()
        
        # --- ADD THESE TWO LINES ---
        me = await app.get_me()
        logger.info(f"🎯 I AM ALIVE AS: @{me.username}")
        # ---------------------------
        
        logger.info("🤖 Bot is successfully online and ready to answer commands!")    
        logger.info("🤖 Bot is successfully online and ready to answer commands!")
        await idle()
    except Exception as e:
        logger.error(f"❌ CRITICAL: Pyrogram crashed while starting. Error: {e}")
    finally:
        while True:
             await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
