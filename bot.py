import logging
import os
import json
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- IMPORTANT CONFIGURATION CONSTANTS ---
# !!! REPLACE THESE WITH YOUR ACTUAL VALUES !!!

# Bot token from BotFather
TOKEN = "7766320056:AAG3ZVx2nX9KUfCqweon4EJJLOJCcNravHk" # <--- REPLACE THIS WITH YOUR BOT'S TOKEN

# Your Telegram Channel ID.
# To get your channel ID:
# 1. Add @RawDataBot to your channel as an administrator.
# 2. Forward any message from your channel to @RawDataBot.
# 3. Look for the "chat" object in the JSON response; the "id" field is your channel ID.
#    It usually starts with -100. Example: -1001234567890
CHANNEL_ID = -1002716521964 # <--- REPLACE THIS WITH YOUR CHANNEL'S ID

# List of Telegram User IDs who will be administrators.
# To get your user ID: Send /id to @userinfobot or @RawDataBot.
# Example: ADMIN_IDS = [123456789, 987654321]
ADMIN_IDS = [7619535371] # <--- REPLACE WITH YOUR ADMIN USER IDs (as integers)

MIN_WITHDRAWAL_AMOUNT = 50 # Minimum balance required for withdrawal
REFERRAL_BONUS = 5         # Amount earned per successful referral

# --- Global Data Stores ---
# Dictionary to store user data (in a real application, consider a database like PostgreSQL, MongoDB, etc.)
user_data = {}
# Dictionary to track daily bonus claims (persisted to file)
daily_bonus_claims = {}

# --- File Paths for Persistence ---
USER_DATA_FILE = 'user_data.json'
DAILY_BONUS_CLAIMS_FILE = 'daily_bonus_claims.json'

# --- File Operations ---
def save_user_data():
    """Saves the user_data dictionary to a JSON file."""
    try:
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(user_data, f, indent=4)
        logger.info("User data saved successfully.")
    except IOError as e:
        logger.error(f"Error saving user data: {e}")

def load_user_data():
    """Loads user data from a JSON file into the user_data dictionary."""
    global user_data
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, 'r') as f:
                user_data = json.load(f)
            logger.info("User data loaded successfully.")
        else:
            user_data = {}
            logger.info("No user data file found. Initializing empty user_data.")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Error loading user data or file corrupted: {e}. Initializing empty user_data.")
        user_data = {}

def save_daily_bonus_claims():
    """Saves the daily_bonus_claims dictionary to a JSON file."""
    try:
        with open(DAILY_BONUS_CLAIMS_FILE, 'w') as f:
            json.dump(daily_bonus_claims, f, indent=4)
        logger.info("Daily bonus claims saved successfully.")
    except IOError as e:
        logger.error(f"Error saving daily bonus claims: {e}")

def load_daily_bonus_claims():
    """Loads daily bonus claims from a JSON file into the daily_bonus_claims dictionary."""
    global daily_bonus_claims
    try:
        if os.path.exists(DAILY_BONUS_CLAIMS_FILE):
            with open(DAILY_BONUS_CLAIMS_FILE, 'r') as f:
                daily_bonus_claims = json.load(f)
            logger.info("Daily bonus claims loaded successfully.")
        else:
            daily_bonus_claims = {}
            logger.info("No daily bonus claims file found. Initializing empty daily_bonus_claims.")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Error loading daily bonus claims or file corrupted: {e}. Initializing empty daily_bonus_claims.")
        daily_bonus_claims = {}

# --- Helper Functions ---

async def check_channel_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if a user is a member of the configured Telegram channel."""
    try:
        chat_member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        # Status can be 'member', 'administrator', 'creator' for members
        return chat_member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Error checking channel membership for user {user_id}: {e}")
        # If an error occurs (e.g., bot not admin in channel, channel ID wrong), assume not a member
        return False

async def get_channel_info(context: ContextTypes.DEFAULT_TYPE):
    """Retrieves channel information."""
    try:
        channel_info = await context.bot.get_chat(chat_id=CHANNEL_ID)
        channel_name = channel_info.title
        channel_link = channel_info.invite_link
        if not channel_link and channel_info.username: # Fallback for public channels
            channel_link = f"https://t.me/{channel_info.username}"
        return channel_name, channel_link
    except Exception as e:
        logger.error(f"Error getting channel info for {CHANNEL_ID}: {e}")
        return "our Telegram Channel", "Please contact admin for link" # Generic fallback

async def prompt_channel_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message prompting the user to join the channel."""
    channel_name, channel_link = await get_channel_info(context)
    
    keyboard = [[InlineKeyboardButton(f"👉 Join {channel_name} 👈", url=channel_link)],
                [InlineKeyboardButton("✅ I've Joined", callback_data="check_joined_channel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        "🛑 To use this bot, you must first join our Telegram Channel.\n\n"
        f"Please join *{channel_name}* to continue:"
    )
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Could not edit message for channel join prompt, sending new message: {e}")
            await update.effective_chat.send_message(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends or edits the message to display the main menu."""
    user = update.effective_user
    user_id = str(user.id)
    
    # Ensure user data is initialized, though start command should handle this.
    if user_id not in user_data:
        # This shouldn't happen if /start is called first, but good for robustness.
        user_data[user_id] = {
            'balance': 0,
            'total_earned': 0,
            'referrals': [],
            'withdrawals': [],
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name
        }
        save_user_data()

    welcome_text = (
        f"👋 Welcome to the Referral Earning Bot, {user.first_name}!\n\n"
        f"Earn ₹{REFERRAL_BONUS} for each friend you refer to this bot.\n"
        f"You can withdraw your earnings once you reach ₹{MIN_WITHDRAWAL_AMOUNT}.\n\n"
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
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup)
        except Exception as e:
            logger.warning(f"Could not edit message for main menu for user {user_id}, sending new message: {e}")
            await update.effective_chat.send_message(welcome_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = str(user.id)
    
    # Always update user's last known name/username
    if user_id not in user_data: # If new user, initialize fully
        user_data[user_id] = {
            'balance': 0,
            'total_earned': 0,
            'referrals': [],
            'withdrawals': [],
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name
        }
    else: # If existing user, just update name/username fields
        user_data[user_id]['username'] = user.username
        user_data[user_id]['first_name'] = user.first_name
        user_data[user_id]['last_name'] = user.last_name

    # Check channel membership first
    if not await check_channel_membership(user.id, context):
        await prompt_channel_join(update, context)
        return # Stop execution until user joins and clicks "I've Joined"

    # Proceed only if user is a channel member
    
    # Check if this user was referred by someone (only if new user)
    if len(context.args) > 0: # context.args contains parameters from start link (e.g., /start <referrer_id>)
        referrer_id = context.args[0]
        
        # If this is a truly new user who just got initialized and they were referred by a valid user
        if not user_data[user_id]['referrals'] and referrer_id in user_data and referrer_id != user_id:
            # Add bonus to referrer
            user_data[referrer_id]['balance'] += REFERRAL_BONUS
            user_data[referrer_id]['total_earned'] += REFERRAL_BONUS
            user_data[referrer_id]['referrals'].append(user_id)
            
            # Notify referrer
            try:
                await context.bot.send_message(
                    chat_id=int(referrer_id),
                    text=f"🎉 Congratulations! {user.first_name} joined using your referral link. You earned ₹{REFERRAL_BONUS}!"
                )
            except Exception as e:
                logger.error(f"Failed to notify referrer {referrer_id}: {e}")
        
    await send_main_menu(update, context)
    save_user_data()

# --- User Callback Query Handlers ---

async def user_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    await query.answer() # Acknowledge the callback query immediately

    # Ensure user exists in our data
    if user_id not in user_data:
        await query.edit_message_text("❌ Your session expired or data not found. Please type /start to restart the bot.")
        return

    # Channel membership check for all main menu interactions
    if not await check_channel_membership(query.from_user.id, context):
        await prompt_channel_join(update, context)
        return

    # --- Main Menu Callbacks ---
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
            f"You'll earn ₹{REFERRAL_BONUS} for each friend who joins using your link!"
        )
        
        keyboard = [[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=referral_text, reply_markup=reply_markup)
    
    elif query.data == "withdraw":
        balance = user_data[user_id]['balance']
        
        if balance >= MIN_WITHDRAWAL_AMOUNT:
            withdraw_text = (
                f"💸 You can withdraw ₹{balance}.\n\n"
                f"Please provide your payment details by sending a message in this format:\n"
                f"`Withdraw: [Payment Method] [Account Details]`\n\n"
                f"Example: `Withdraw: UPI yourUPIid@bank` or `Withdraw: Paytm 9876543210`"
            )
        else:
            withdraw_text = (
                f"❌ Your current balance (₹{balance}) is less than the minimum withdrawal amount (₹{MIN_WITHDRAWAL_AMOUNT}).\n\n"
                f"Refer more friends to increase your balance!"
            )
        
        keyboard = [[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=withdraw_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "daily_bonus":
        today = datetime.now().strftime("%Y-%m-%d")
        
        if user_id in daily_bonus_claims and daily_bonus_claims[user_id] == today:
            bonus_text = "⏰ You've already claimed your daily bonus today. Come back tomorrow!"
        else:
            bonus_amount = random.randint(1, 10)  # Random bonus between ₹1 and ₹10
            user_data[user_id]['balance'] += bonus_amount
            user_data[user_id]['total_earned'] += bonus_amount
            daily_bonus_claims[user_id] = today
            save_user_data()
            save_daily_bonus_claims() # Save bonus claims state
            
            bonus_text = f"🎁 Congratulations! You've received your daily bonus of ₹{bonus_amount}!"
        
        keyboard = [[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=bonus_text, reply_markup=reply_markup)
    
    elif query.data == "how_to_earn":
        earn_text = (
            "💡 How to earn with our bot:\n\n"
            f"1️⃣ Share your referral link with friends\n"
            f"2️⃣ Earn ₹{REFERRAL_BONUS} for each friend who joins\n"
            f"3️⃣ Claim a daily bonus up to ₹10\n"
            f"4️⃣ Withdraw your earnings once you reach ₹{MIN_WITHDRAWAL_AMOUNT}\n\n"
            f"The more friends you refer, the more you earn! 🚀"
        )
        
        keyboard = [[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=earn_text, reply_markup=reply_markup)
    
    elif query.data == "back_to_menu":
        await send_main_menu(update, context)
    
    # --- Channel Join Check Callback ---
    elif query.data == "check_joined_channel":
        if await check_channel_membership(query.from_user.id, context):
            await query.edit_message_text("✅ You have successfully joined the channel! Redirecting to main menu...")
            # Re-run start to process referral and show main menu properly
            await start(update, context) 
        else:
            channel_name, channel_link = await get_channel_info(context)
            keyboard = [[InlineKeyboardButton(f"👉 Join {channel_name} 👈", url=channel_link)],
                        [InlineKeyboardButton("✅ I've Joined", callback_data="check_joined_channel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"❌ It seems you haven't joined the channel yet. Please join *{channel_name}* and try again:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

# --- Admin Panel Handlers ---

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /admin command, showing the admin panel menu."""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🚫 Access Denied. You are not an administrator.")
        return
    
    keyboard = [
        [InlineKeyboardButton("👥 View Users", callback_data="admin_view_users")],
        [InlineKeyboardButton("💸 Pending Withdrawals", callback_data="admin_pending_withdrawals")],
        [InlineKeyboardButton("📣 Broadcast Message", callback_data="admin_broadcast_start")],
        [InlineKeyboardButton("💰 Manage User Balance", callback_data="admin_manage_balance_start")],
        [InlineKeyboardButton("✉️ Send Message to User", callback_data="admin_send_message_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚙️ Welcome to the Admin Panel!", reply_markup=reply_markup)

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles callback queries from the admin panel."""
    query = update.callback_query
    admin_user_id = query.from_user.id
    
    if admin_user_id not in ADMIN_IDS:
        await query.answer("🚫 Access Denied.")
        await query.edit_message_text("🚫 Access Denied. You are not an administrator.")
        return
    
    await query.answer() # Acknowledge the callback query

    data = query.data
    
    # --- Admin Main Menu Navigation ---
    if data == "admin_menu":
        # Clear any ongoing admin operation state when returning to main menu
        if admin_user_id in context.user_data:
            if 'admin_state' in context.user_data[admin_user_id]:
                del context.user_data[admin_user_id]['admin_state']
            if 'target_user_id' in context.user_data[admin_user_id]:
                del context.user_data[admin_user_id]['target_user_id']
            if 'action' in context.user_data[admin_user_id]:
                del context.user_data[admin_user_id]['action']
        await admin_command(update, context) # Reuse admin command to send menu

    # --- View Users ---
    elif data == "admin_view_users":
        total_users = len(user_data)
        users_list = "Registered Users:\n\n"
        
        # Display first 10 for brevity, can be expanded with pagination or search
        count = 0
        for uid, data in user_data.items():
            if count >= 10: 
                users_list += f"\n...and {total_users - count} more users. Use Manage Balance to view specific users."
                break
            users_list += f"🆔 {uid}\n"
            users_list += f"  Name: {data.get('first_name', 'N/A')} {data.get('last_name', '')} (@{data.get('username', 'N/A')})\n"
            users_list += f"  Balance: ₹{data['balance']}, Referrals: {len(data['referrals'])}\n"
            users_list += "---\n"
            count += 1
            
        users_list += f"\nTotal users: {total_users}"
        
        keyboard = [[InlineKeyboardButton("◀️ Back to Admin Menu", callback_data="admin_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(users_list, reply_markup=reply_markup)

    # --- Pending Withdrawals ---
    elif data == "admin_pending_withdrawals":
        pending_withdrawals_messages = []
        has_pending = False
        
        for uid, u_data in user_data.items():
            for i, withdrawal in enumerate(u_data['withdrawals']):
                if withdrawal['status'] == 'pending':
                    has_pending = True
                    withdrawal_text = (
                        f"💸 *Pending Withdrawal Request*\n"
                        f"User ID: `{uid}` ({u_data.get('first_name', 'N/A')} {u_data.get('last_name', '')} @{u_data.get('username', 'N/A')})\n"
                        f"Amount: ₹{withdrawal['amount']}\n"
                        f"Details: `{withdrawal['payment_details']}`\n"
                        f"Date: {withdrawal['date']}\n"
                    )
                    
                    keyboard = [[InlineKeyboardButton(f"✅ Mark Paid (User {uid})", callback_data=f"admin_mark_paid_{uid}_{i}")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    # Store message and markup to send separately
                    pending_withdrawals_messages.append({"text": withdrawal_text, "reply_markup": reply_markup})
        
        if not has_pending:
            await query.edit_message_text("No pending withdrawals.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Admin Menu", callback_data="admin_menu")]]))
        else:
            await query.edit_message_text("Listing all pending withdrawals:")
            for msg_data in pending_withdrawals_messages:
                try:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id, 
                        text=msg_data["text"], 
                        reply_markup=msg_data["reply_markup"],
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Failed to send pending withdrawal message: {e}")
            
            # Send a final 'Back to Admin Menu' button
            await context.bot.send_message(
                chat_id=query.message.chat_id, 
                text="End of pending withdrawals list.", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Admin Menu", callback_data="admin_menu")]])
            )

    elif data.startswith("admin_mark_paid_"):
        parts = data.split('_')
        target_user_id = parts[3]
        withdrawal_index = int(parts[4])
        
        if target_user_id in user_data and len(user_data[target_user_id]['withdrawals']) > withdrawal_index:
            withdrawal = user_data[target_user_id]['withdrawals'][withdrawal_index]
            if withdrawal['status'] == 'pending':
                withdrawal['status'] = 'completed'
                withdrawal['completion_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                save_user_data()
                
                await query.edit_message_text(f"✅ Withdrawal for User ID {target_user_id}, Amount ₹{withdrawal['amount']} marked as paid.")
                
                # Notify user
                try:
                    await context.bot.send_message(
                        chat_id=int(target_user_id),
                        text=f"🥳 Your withdrawal request for ₹{withdrawal['amount']} has been processed and paid!\n"
                             f"Payment details: {withdrawal['payment_details']}"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user {target_user_id} about paid withdrawal: {e}")
            else:
                await query.edit_message_text("This withdrawal is already processed or has an invalid status.")
        else:
            await query.edit_message_text("Withdrawal not found or invalid.")
        
        # Add back to admin menu button
        keyboard = [[InlineKeyboardButton("◀️ Back to Admin Menu", callback_data="admin_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=query.message.chat_id, text=".", reply_markup=reply_markup) 

    # --- Broadcast Message ---
    elif data == "admin_broadcast_start":
        context.user_data[admin_user_id] = {'admin_state': 'waiting_for_broadcast_message'}
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel_operation")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Please send the message you want to broadcast to all users.", reply_markup=reply_markup)

    # --- Manage User Balance ---
    elif data == "admin_manage_balance_start":
        context.user_data[admin_user_id] = {'admin_state': 'waiting_for_balance_user_id'}
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel_operation")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Please send the User ID (numeric) of the user whose balance you want to manage.", reply_markup=reply_markup)

    # --- Send Message to User ---
    elif data == "admin_send_message_start":
        context.user_data[admin_user_id] = {'admin_state': 'waiting_for_target_user_id'}
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel_operation")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Please send the User ID (numeric) of the user you want to send a message to.", reply_markup=reply_markup)

    # --- Balance action selection (Add/Subtract) ---
    elif data.startswith("admin_balance_action_"):
        target_user_id = context.user_data[admin_user_id].get('target_user_id')
        if not target_user_id or target_user_id not in user_data:
            await query.edit_message_text("Error: Target user not set or invalid. Please restart operation.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Admin Menu", callback_data="admin_menu")]]))
            del context.user_data[admin_user_id]['admin_state']
            return
        
        context.user_data[admin_user_id]['action'] = data.split('_')[-1] # 'add' or 'subtract'
        context.user_data[admin_user_id]['admin_state'] = 'waiting_for_balance_amount_value'
        
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel_operation")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(f"Please send the amount (numeric) to {context.user_data[admin_user_id]['action']} to user {target_user_id}'s balance.", reply_markup=reply_markup)

    # --- Cancel Operation ---
    elif data == "admin_cancel_operation":
        if admin_user_id in context.user_data and 'admin_state' in context.user_data[admin_user_id]:
            del context.user_data[admin_user_id]['admin_state']
            if 'target_user_id' in context.user_data[admin_user_id]:
                del context.user_data[admin_user_id]['target_user_id']
            if 'action' in context.user_data[admin_user_id]:
                del context.user_data[admin_user_id]['action']
        await query.edit_message_text("Operation cancelled.")
        await admin_command(update, context)


# --- Universal Message Handler (for both users and admin text inputs) ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message_text = update.message.text
    user_id = str(update.effective_user.id)
    admin_id_int = update.effective_user.id # Use int for ADMIN_IDS comparison
    
    # --- ADMIN Panel Message Input Handling ---
    if admin_id_int in ADMIN_IDS and admin_id_int in context.user_data and 'admin_state' in context.user_data[admin_id_int]:
        current_admin_state = context.user_data[admin_id_int]['admin_state']
        
        # Admin Broadcast Message
        if current_admin_state == 'waiting_for_broadcast_message':
            broadcast_message = message_text
            success_count = 0
            fail_count = 0
            
            await update.message.reply_text("Sending broadcast message to all users...")
            
            for target_uid in list(user_data.keys()): # Iterate over a copy as user_data might change
                try:
                    await context.bot.send_message(chat_id=int(target_uid), text=broadcast_message)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send broadcast to user {target_uid}: {e}")
                    fail_count += 1
            
            await update.message.reply_text(f"Broadcast complete!\nSuccessful: {success_count}\nFailed: {fail_count}")
            del context.user_data[admin_id_int]['admin_state'] # Clear admin state
            await admin_command(update, context) # Show admin menu again
            return

        # Admin Manage User Balance - Step 1: Get User ID
        elif current_admin_state == 'waiting_for_balance_user_id':
            try:
                target_user_id = message_text # User ID is still a string in user_data keys
                if target_user_id not in user_data:
                    await update.message.reply_text("User ID not found. Please enter a valid User ID or /admin to cancel.")
                    return
                
                context.user_data[admin_id_int]['target_user_id'] = target_user_id
                context.user_data[admin_id_int]['admin_state'] = 'waiting_for_balance_action_selection' # New state for action selection
                
                target_user = user_data[target_user_id]
                
                keyboard = [
                    [InlineKeyboardButton("➕ Add Balance", callback_data="admin_balance_action_add")],
                    [InlineKeyboardButton("➖ Subtract Balance", callback_data="admin_balance_action_subtract")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel_operation")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"Selected user: {target_user.get('first_name', '')} {target_user.get('last_name', '')} (@{target_user.get('username', 'N/A')})\n"
                    f"Current Balance: ₹{target_user['balance']}\n\n"
                    f"Choose an action:",
                    reply_markup=reply_markup
                )
                return
        
        # Admin Manage User Balance - Step 3: Get Amount Value
        elif current_admin_state == 'waiting_for_balance_amount_value':
            target_user_id = context.user_data[admin_id_int].get('target_user_id')
            action = context.user_data[admin_id_int].get('action')

            if not target_user_id or not action or target_user_id not in user_data:
                await update.message.reply_text("Error: Balance management session invalid. Please restart with /admin.")
                # Clear all related admin state
                del context.user_data[admin_id_int]['admin_state']
                if 'target_user_id' in context.user_data[admin_id_int]: del context.user_data[admin_id_int]['target_user_id']
                if 'action' in context.user_data[admin_id_int]: del context.user_data[admin_id_int]['action']
                return

            try:
                amount = float(message_text)
                if amount < 0:
                    await update.message.reply_text("Amount cannot be negative. Please enter a positive number or /admin to cancel.")
                    return

                current_balance = user_data[target_user_id]['balance']
                
                if action == 'add':
                    user_data[target_user_id]['balance'] += amount
                    user_data[target_user_id]['total_earned'] += amount # Assuming admin additions also count as earned
                    response_text = f"Successfully added ₹{amount} to user {target_user_id}'s balance."
                elif action == 'subtract':
                    if current_balance < amount:
                        await update.message.reply_text(f"Cannot subtract ₹{amount}. User's current balance is only ₹{current_balance}.")
                        return
                    user_data[target_user_id]['balance'] -= amount
                    # No change to total_earned on subtraction for now
                    response_text = f"Successfully subtracted ₹{amount} from user {target_user_id}'s balance."
                
                save_user_data()
                
                await update.message.reply_text(f"{response_text}\nNew balance for {target_user_id}: ₹{user_data[target_user_id]['balance']}")
                
                # Notify the target user
                try:
                    await context.bot.send_message(
                        chat_id=int(target_user_id),
                        text=f"📊 Your balance has been updated by an administrator.\n"
                             f"Amount {action}ed: ₹{amount}\n"
                             f"New balance: ₹{user_data[target_user_id]['balance']}"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user {target_user_id} about balance update: {e}")

            except ValueError:
                await update.message.reply_text("Invalid amount. Please enter a numeric value or /admin to cancel.")
                return
            except Exception as e:
                await update.message.reply_text(f"An error occurred: {e}. Please try again or /admin to cancel.")
                return
            finally:
                # Clear admin state
                del context.user_data[admin_id_int]['admin_state']
                if 'target_user_id' in context.user_data[admin_id_int]: del context.user_data[admin_id_int]['target_user_id']
                if 'action' in context.user_data[admin_id_int]: del context.user_data[admin_id_int]['action']
                await admin_command(update, context) # Show admin menu again
            return

        # Admin Send Message to User - Step 1: Get User ID
        elif current_admin_state == 'waiting_for_target_user_id':
            try:
                target_user_id = message_text
                if target_user_id not in user_data:
                    await update.message.reply_text("User ID not found. Please enter a valid User ID or /admin to cancel.")
                    return
                
                context.user_data[admin_id_int]['target_user_id'] = target_user_id
                context.user_data[admin_id_int]['admin_state'] = 'waiting_for_message_content'
                
                target_user = user_data[target_user_id]
                
                keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel_operation")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"Selected user: {target_user.get('first_name', '')} {target_user.get('last_name', '')} (@{target_user.get('username', 'N/A')})\n"
                    f"Please send the message you want to send to this user:",
                    reply_markup=reply_markup
                )
                return

        # Admin Send Message to User - Step 2: Get Message Content
        elif current_admin_state == 'waiting_for_message_content':
            target_user_id = context.user_data[admin_id_int].get('target_user_id')
            if not target_user_id or target_user_id not in user_data:
                await update.message.reply_text("Error: Target user not set. Please restart the operation with /admin.")
                del context.user_data[admin_id_int]['admin_state']
                return
            
            message_to_send = message_text
            try:
                await context.bot.send_message(chat_id=int(target_user_id), text=message_to_send)
                await update.message.reply_text(f"Message successfully sent to User ID: {target_user_id}")
            except Exception as e:
                await update.message.reply_text(f"Failed to send message to User ID: {target_user_id}. Error: {e}")
            finally:
                del context.user_data[admin_id_int]['admin_state']
                if 'target_user_id' in context.user_data[admin_id_int]:
                    del context.user_data[admin_id_int]['target_user_id']
                await admin_command(update, context) # Show admin menu again
                return
    
    # --- USER Withdrawal Request Handling ---
    elif message_text.lower().startswith("withdraw:"):
        # Check channel membership before processing withdrawal request
        if not await check_channel_membership(update.effective_user.id, context):
            await prompt_channel_join(update, context)
            return

        if user_id in user_data and user_data[user_id]['balance'] >= MIN_WITHDRAWAL_AMOUNT:
            amount_to_withdraw = user_data[user_id]['balance']
            payment_details = message_text[len("withdraw:"):].strip()  # Remove "Withdraw: " prefix
            
            if not payment_details:
                await update.message.reply_text("Please provide your payment details after 'Withdraw:'. Example: `Withdraw: UPI yourUPIid@bank`", parse_mode='Markdown')
                return

            # Record withdrawal
            withdrawal = {
                'amount': amount_to_withdraw,
                'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'payment_details': payment_details,
                'status': 'pending'
            }
            
            user_data[user_id]['withdrawals'].append(withdrawal)
            user_data[user_id]['balance'] = 0 # Reset balance after withdrawal request
            save_user_data()
            
            await update.message.reply_text(
                f"✅ Withdrawal request for ₹{amount_to_withdraw} has been submitted!\n\n"
                f"Payment details: {payment_details}\n\n"
                f"Your request is being processed and will be completed within 24 hours. Your balance has been reset to ₹0."
            )
            # Notify admins about new withdrawal request
            for admin_id in ADMIN_IDS:
                try:
                    user_info = user_data.get(user_id, {})
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"🚨 *New withdrawal request from User ID:* `{user_id}`\n"
                             f"Name: {user_info.get('first_name', 'N/A')} {user_info.get('last_name', '')} (@{user_info.get('username', 'N/A')})\n"
                             f"Amount: ₹{amount_to_withdraw}\n"
                             f"Details: `{payment_details}`\n"
                             f"Date: {withdrawal['date']}\n\n"
                             f"Use /admin to manage.",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id} about new withdrawal: {e}")

        else:
            await update.message.reply_text(
                f"❌ You don't have enough balance to withdraw. Minimum withdrawal amount is ₹{MIN_WITHDRAWAL_AMOUNT}. Your current balance is ₹{user_data[user_id]['balance'] if user_id in user_data else 0}."
            )
        return # Exit here, as this was a specific withdrawal command
    
    # --- General Message Handling (not withdrawal and not admin-specific state) ---
    else:
        # For any other message from a regular user, or an admin not in a specific state, show the main menu.
        # But first, check channel membership.
        if not await check_channel_membership(update.effective_user.id, context):
            await prompt_channel_join(update, context)
            return
        
        await send_main_menu(update, context)


# --- Main function to set up the bot ---
def main() -> None:
    # Load existing user data and daily bonus claims
    load_user_data()
    load_daily_bonus_claims()
    
    # Create the Application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command)) # Admin command
    
    # Callback Query Handlers
    # User callbacks (all except those starting with 'admin_')
    application.add_handler(CallbackQueryHandler(user_button_callback, pattern="^(?!admin_)")) 
    # Admin callbacks (all starting with 'admin_')
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_")) 

    # Message Handler (needs to be carefully ordered for admin states)
    # This single handler will manage all text messages (not commands).
    # It first checks if it's an admin in a multi-step conversation.
    # Then it checks if it's a user withdrawal request.
    # Finally, it defaults to showing the main menu.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the Bot
    logger.info("Bot starting...")
    application.run_polling(poll_interval=1.0) # Added poll_interval for slightly more responsive polling

if __name__ == "__main__":
    main()
