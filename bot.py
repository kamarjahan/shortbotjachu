import os
import asyncio
import logging
import requests
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
JACHU_API_KEY = os.environ.get("JACHU_API_KEY", "")

user_states = {}

# --- Pyrogram Client ---
app = Client(
    "jachu_shortener_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# --- Dummy Web Server (HuggingFace needs this) ---
async def health_check(request):
    return web.Response(text="Bot is alive!")

# --- URL Shortening Function (Using requests) ---
def shorten_url(url: str, slug: str = None) -> dict:
    api_url = "https://jachu.xyz/api/create"
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": JACHU_API_KEY
    }

    payload = {"url": url}
    if slug:
        payload["slug"] = slug

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- Start Command ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_states.pop(message.from_user.id, None)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Read Legal Docs 📜", url="https://jachu.xyz/legal")],
        [InlineKeyboardButton("Help ❓", callback_data="help_info")]
    ])

    await message.reply_text(
        "👋 Send me a link starting with http:// or https:// and I'll shorten it.",
        reply_markup=keyboard
    )

# --- Handle URL ---
@app.on_message(filters.regex(r"^https?://") & filters.private)
async def handle_url(client: Client, message: Message):
    user_id = message.from_user.id

    user_states[user_id] = {
        "url": message.text.strip(),
        "step": "CHOOSE_MODE"
    }

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔀 Random Alias", callback_data="mode_random")],
        [InlineKeyboardButton("✍️ Custom Alias", callback_data="mode_custom")]
    ])

    await message.reply_text("How would you like to shorten it?", reply_markup=keyboard)

# --- Handle Button Clicks ---
@app.on_callback_query(filters.regex(r"^mode_"))
async def handle_mode(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    mode = callback_query.data

    if user_id not in user_states:
        return await callback_query.answer("Session expired. Send link again.", show_alert=True)

    url = user_states[user_id]["url"]

    if mode == "mode_random":
        await callback_query.message.edit_text("⏳ Shortening...")

        # Run blocking requests in thread
        result = await asyncio.to_thread(shorten_url, url)

        if result.get("status") == "success":
            await callback_query.message.edit_text(f"✅ **Success!**\n{result.get('short_url')}")
        else:
            await callback_query.message.edit_text(f"❌ **Error:** {result.get('message')}")

        user_states.pop(user_id, None)

    elif mode == "mode_custom":
        user_states[user_id]["step"] = "WAITING_FOR_ALIAS"
        await callback_query.message.edit_text("Type your custom alias (example: `my-link`).")

# --- Handle Custom Alias ---
@app.on_message(filters.text & filters.private & ~filters.command(["start"]))
async def handle_alias(client: Client, message: Message):
    user_id = message.from_user.id

    if user_id in user_states and user_states[user_id].get("step") == "WAITING_FOR_ALIAS":
        alias = message.text.strip()
        url = user_states[user_id]["url"]

        processing = await message.reply_text(f"⏳ Claiming alias `{alias}`...")

        result = await asyncio.to_thread(shorten_url, url, alias)

        if result.get("status") == "success":
            await processing.edit_text(f"✅ **Success!**\n{result.get('short_url')}")
            user_states.pop(user_id, None)
        else:
            await processing.edit_text(
                f"❌ **Failed:** {result.get('message')}\n\nAlias likely taken. Try another."
            )

# --- Help Button ---
@app.on_callback_query(filters.regex("help_info"))
async def help_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.answer(
        "Send any valid URL starting with http:// or https://",
        show_alert=True
    )

# --- Main Function ---
async def main():
    server = web.Application()
    server.router.add_get('/', health_check)

    runner = web.AppRunner(server)
    await runner.setup()

    port = int(os.environ.get("PORT", 7860))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    logger.info(f"Web server running on port {port}")

    # Start bot in polling mode
    await app.start()

    me = await app.get_me()
    logger.info(f"Bot started as @{me.username}")

    await idle()


if __name__ == "__main__":
    asyncio.run(main())
