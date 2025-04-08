import logging
import os
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from BotFather
TOKEN = "BOT_TOKEN_ID"

# Dictionary to store user data (in a real application, use a database)
user_data = {}

# Dictionary to track daily bonus claims
daily_bonus_claims = {}

# Function to save user data to a file
def save_user_data():
    with open('user_data.json', 'w') as f:
        json.dump(user_data, f)

# Function to load user data from a file
def load_user_data():
    global user_data
    try:
        with open('user_data.json', 'r') as f:
            user_data = json.load(f)
    except FileNotFoundError:
        user_data = {}

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = str(user.id)
    
    # Check if this user was referred by someone
    if context.args and len(context.args) > 0:
        referrer_id = context.args[0]
        
        # If this is a new user and they were referred
        if user_id not in user_data and referrer_id in user_data and referrer_id != user_id:
            # Add bonus to referrer
            user_data[referrer_id]['balance'] += 5
            user_data[referrer_id]['total_earned'] += 5
            user_data[referrer_id]['referrals'].append(user_id)
            
            # Notify referrer
            try:
                await context.bot.send_message(
                    chat_id=int(referrer_id),
                    text=f"🎉 Congratulations! {user.first_name} joined using your referral link. You earned ₹5!"
                )
            except Exception as e:
                logger.error(f"Failed to notify referrer: {e}")
    
    # Initialize user data if not exists
    if user_id not in user_data:
        user_data[user_id] = {
            'balance': 0,
            'total_earned': 0,
            'referrals': [],
            'withdrawals': []
        }
    
    # Create referral link
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_id}"
    
    # Welcome message with main menu
    welcome_text = (
        f"👋 Welcome to the Referral Earning Bot, {user.first_name}!\n\n"
        f"Earn ₹5 for each friend you refer to this bot.\n"
        f"You can withdraw your earnings once you reach ₹50.\n\n"
        f"Use the buttons below to navigate:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("💰 Balance", callback_data="balance"),
            InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")
        ],
        [
            InlineKeyboardButton("💸 Withdraw", callback_data="withdraw"),
            InlineKeyboardButton("🎁 Daily Bonus", callback_data="daily_bonus")
        ],
        [
            InlineKeyboardButton("ℹ️ How to Earn", callback_data="how_to_earn")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    # Save user data
    save_user_data()

# Callback query handler
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    # Ensure user exists in our data
    if user_id not in user_data:
        user_data[user_id] = {
            'balance': 0,
            'total_earned': 0,
            'referrals': [],
            'withdrawals': []
        }
    
    await query.answer()
    
    if query.data == "balance":
        balance_text = (
            f"💰 Your current balance: ₹{user_data[user_id]['balance']}\n"
            f"💵 Total earned: ₹{user_data[user_id]['total_earned']}\n"
            f"👥 Total referrals: {len(user_data[user_id]['referrals'])}"
        )
        
        keyboard = [[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text=balance_text, reply_markup=reply_markup)
    
    elif query.data == "referral_link":
        bot_username = (await context.bot.get_me()).username
        referral_link = f"https://t.me/{bot_username}?start={user_id}"
        
        referral_text = (
            f"🔗 Share this link with your friends:\n\n"
            f"{referral_link}\n\n"
            f"You'll earn ₹5 for each friend who joins using your link!"
        )
        
        keyboard = [[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text=referral_text, reply_markup=reply_markup)
    
    elif query.data == "withdraw":
        balance = user_data[user_id]['balance']
        
        if balance >= 50:
            withdraw_text = (
                f"💸 You can withdraw ₹{balance}.\n\n"
                f"Please provide your payment details by sending a message in this format:\n"
                f"Withdraw: [Payment Method] [Account Details]"
            )
        else:
            withdraw_text = (
                f"❌ Your current balance (₹{balance}) is less than the minimum withdrawal amount (₹50).\n\n"
                f"Refer more friends to increase your balance!"
            )
        
        keyboard = [[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text=withdraw_text, reply_markup=reply_markup)
    
    elif query.data == "daily_bonus":
        today = datetime.now().strftime("%Y-%m-%d")
        
        if user_id in daily_bonus_claims and daily_bonus_claims[user_id] == today:
            bonus_text = "⏰ You've already claimed your daily bonus today. Come back tomorrow!"
        else:
            # Add random bonus between 1 and 10
            import random
            bonus_amount = random.randint(1, 10)  # Random bonus between ₹1 and ₹10
            user_data[user_id]['balance'] += bonus_amount
            user_data[user_id]['total_earned'] += bonus_amount
            daily_bonus_claims[user_id] = today
            save_user_data()
            
            bonus_text = f"🎁 Congratulations! You've received your daily bonus of ₹{bonus_amount}!"
        
        keyboard = [[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text=bonus_text, reply_markup=reply_markup)
    
    elif query.data == "how_to_earn":
        earn_text = (
            "💡 How to earn with our bot:\n\n"
            "1️⃣ Share your referral link with friends\n"
            "2️⃣ Earn ₹5 for each friend who joins\n"
            "3️⃣ Claim a daily bonus up to ₹10\n"
            "4️⃣ Withdraw your earnings once you reach ₹50\n\n"
            "The more friends you refer, the more you earn! 🚀"
        )
        
        keyboard = [[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text=earn_text, reply_markup=reply_markup)
    
    elif query.data == "back_to_menu":
        # Return to main menu
        welcome_text = (
            f"👋 Welcome to the Referral Earning Bot!\n\n"
            f"Earn ₹5 for each friend you refer to this bot.\n"
            f"You can withdraw your earnings once you reach ₹50.\n\n"
            f"Use the buttons below to navigate:"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("💰 Balance", callback_data="balance"),
                InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")
            ],
            [
                InlineKeyboardButton("💸 Withdraw", callback_data="withdraw"),
                InlineKeyboardButton("🎁 Daily Bonus", callback_data="daily_bonus")
            ],
            [
                InlineKeyboardButton("ℹ️ How to Earn", callback_data="how_to_earn")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=welcome_text, reply_markup=reply_markup)

# Handle withdrawal requests
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message_text = update.message.text
    user_id = str(update.effective_user.id)
    
    if message_text.startswith("Withdraw:"):
        if user_id in user_data and user_data[user_id]['balance'] >= 50:
            # Process withdrawal
            amount = user_data[user_id]['balance']
            payment_details = message_text[9:].strip()  # Remove "Withdraw: " prefix
            
            # Record withdrawal
            withdrawal = {
                'amount': amount,
                'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'payment_details': payment_details,
                'status': 'pending'
            }
            
            user_data[user_id]['withdrawals'].append(withdrawal)
            user_data[user_id]['balance'] = 0
            save_user_data()
            
            await update.message.reply_text(
                f"✅ Withdrawal request for ₹{amount} has been submitted!\n\n"
                f"Payment details: {payment_details}\n\n"
                f"Your request is being processed and will be completed within 24 hours."
            )
        else:
            await update.message.reply_text(
                "❌ You don't have enough balance to withdraw. Minimum withdrawal amount is ₹50."
            )
    else:
        # For any other message, show the main menu
        await start(update, context)

# Main function
def main() -> None:
    # Load existing user data
    load_user_data()
    
    # Create the Application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()
