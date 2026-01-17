import json
import telebot
import logging
import sys
from datetime import datetime
from report_generator import generate_report

# --- LOGGING SETUP ---
# This configures the bot to write logs to both 'bot_activity.log' and the console.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler("bot_activity.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# --- LOAD CONFIGURATION ---
def load_config():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            token = config.get('bot_token')
            if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
                raise ValueError("Invalid Bot Token in config.json")
            return token
    except FileNotFoundError:
        logger.critical("config.json not found. Exiting.")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Error loading config: {e}")
        sys.exit(1)

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

BOT_TOKEN = load_config()
EVENTS_MAP = load_events()

# Initialize Bot
bot = telebot.TeleBot(BOT_TOKEN)
logger.info("--- Polymarket Bot Initialized ---")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    chat_id = message.chat.id
    
    logger.info(f"User {username} ({user_id}) started the bot in chat {chat_id}")
    
    commands_list = "\n".join([f"/{cmd}" for cmd in EVENTS_MAP.keys()])
    welcome_text = (
        "Welcome! I track Polymarket odds.\n\n"
        "**Available Commands:**\n"
        f"{commands_list}"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

# Dynamic Handler: Catches any command that exists in our events.json
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
    
    bot.send_message(chat_id, "Fetching latest odds from Polymarket... ⏳")
    
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

# Catch-all for unknown commands
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    logger.info(f"Unknown message from {message.from_user.username}: {message.text}")
    # Optional: bot.reply_to(message, "I don't recognize that command.")

if __name__ == "__main__":
    try:
        logger.info("Starting polling loop...")
        bot.infinity_polling()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.critical(f"Bot crashed: {e}")