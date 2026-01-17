import json
import os
import telebot
import logging
import sys
from datetime import datetime
from report_generator import generate_report

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler("bot_activity.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_events():
    try:
        with open('events.json', 'r') as f:
            events = json.load(f)
            logger.info(f"Events loaded successfully: {list(events.keys())}")
            return events
    except FileNotFoundError:
        logger.warning("events.json not found. No dynamic commands loaded.")
        return {}
    except Exception as e:
        logger.error(f"Error loading events.json: {e}")
        return {}

BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
EVENTS_MAP = load_events()

# Initialize Bot
bot = telebot.TeleBot(BOT_TOKEN)
logger.info("--- Polymarket Bot Initialized ---")

# --- WELCOME HANDLER (/start) ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    chat_id = message.chat.id
    
    logger.info(f"User {username} ({user_id}) started the bot in chat {chat_id}")
    
    welcome_text = (
        "👋 **Welcome to PolyBot!** 🔮\n\n"
        "I am your personal analyst for **Polymarket** prediction markets. "
        "I track real-time odds for major geopolitical and economic events.\n\n"
        "📉 **What I do:**\n"
        "• Fetch live probability charts (Last 24h)\n"
        "• Compare odds: Today vs Next Week vs Month End\n"
        "• Generate instant analysis tables\n\n"
        "🚀 **Get Started:**\n"
        "Type /help to see the list of tracked markets and generate your first report!"
    )
    # Using Markdown for bolding
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

# --- HELP HANDLER (/help) ---
@bot.message_handler(commands=['help'])
def send_help(message):
    logger.info(f"User {message.from_user.username} requested help.")
    
    if not EVENTS_MAP:
        bot.reply_to(message, "⚠️ No events configured. Check `events.json`.")
        return

    # Build the list of commands dynamically
    events_list_text = ""
    for command, url in EVENTS_MAP.items():
        # Escape underscores for Markdown so the command doesn't turn italic
        clean_cmd = command.replace("_", "\\_")
        events_list_text += f"🔹 /{clean_cmd}\n   🔗 [View Market Source]({url})\n\n"

    help_text = (
        "📊 **Available Markets**\n"
        "Select a command below to generate a real-time odds report:\n\n"
        f"{events_list_text}"
        "───────────────────\n"
        "💡 To add a new tracker, commit a request to update `events.json` in [Github](https://github.com/sadraheydari/polymarket_telegram_bot)."
    )
    
    # disable_web_page_preview=True keeps the chat clean from URL previews
    bot.reply_to(message, help_text, parse_mode="Markdown", disable_web_page_preview=True)

# --- DYNAMIC COMMAND HANDLER ---
@bot.message_handler(func=lambda message: message.text.startswith('/') and message.text.split()[0][1:] in EVENTS_MAP)
def handle_dynamic_command(message):
    # Extract command (remove '/' and take first word)
    command = message.text.split()[0][1:]
    event_url = EVENTS_MAP.get(command)
    
    # Log the Request
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    chat_id = message.chat.id
    logger.info(f"COMMAND: /{command} | USER: {username} ({user_id}) | URL: {event_url}")
    
    bot.send_message(chat_id, "🔍 **Fetching latest odds from Polymarket...**\nPlease wait while I generate the chart.", parse_mode="Markdown")
    
    try:
        # Generate Report
        photo, table_text = generate_report(event_url)
        
        if photo:
            logger.info(f"Report generated successfully for {username}. Sending...")
            
            # Send the plot
            bot.send_photo(chat_id, photo)
            # Send the text table
            bot.send_message(chat_id, table_text, parse_mode='Markdown')
            
            logger.info(f"Sent successfully to chat {chat_id}")
        else:
            error_msg = f"⚠️ Error: {table_text}"
            logger.error(f"Failed to generate report: {table_text}")
            bot.send_message(chat_id, error_msg)
            
    except Exception as e:
        error_msg = f"An unexpected error occurred: {e}"
        logger.exception(f"CRITICAL ERROR handling /{command}: {e}")
        bot.send_message(chat_id, error_msg)

# --- CATCH-ALL HANDLER ---
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    # Just log unknown messages, don't reply to avoid spamming groups
    logger.info(f"Ignored message from {message.from_user.username}: {message.text}")

if __name__ == "__main__":
    try:
        logger.info("Starting polling loop...")
        bot.infinity_polling()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.critical(f"Bot crashed: {e}")