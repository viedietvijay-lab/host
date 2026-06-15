import os
import subprocess
import re
import time
import json
import threading
import hashlib
import sys
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import shutil
from pathlib import Path

# ============================================
# CONFIGURATION
# ============================================
BOT_TOKEN = "8832181426:AAHslqQXqbyZatMUHSfL9d6qeNo5mrUUWHk"
DATA_FILE = "user_data.json"
CHANNELS_FILE = "force_channels.json"
ADMIN_IDS = [8139558808,1364476174]  # Sirf yeh admin
BOT_NAME = "𝐕𝐢𝐞𝐝𝐢𝐞𝐭 𝐇𝐨𝐬𝐭"
MAX_FILES_PER_USER = 1  # Normal user ke liye sirf 1 file

bot = telebot.TeleBot(BOT_TOKEN)
os.makedirs("user_scripts", exist_ok=True)
os.makedirs("backups", exist_ok=True)

# Track running scripts
running = {}
user_cooldown = {}

# BOT ON/OFF STATUS (Admin isko toggle kar sakta hai)
BOT_STATUS_FILE = "bot_status.json"

def get_bot_status():
    """Check if bot is ON or OFF"""
    if os.path.exists(BOT_STATUS_FILE):
        try:
            with open(BOT_STATUS_FILE, 'r') as f:
                data = json.load(f)
                return data.get("status", "on"), data.get("reason", "")
        except:
            return "on", ""
    return "on", ""

def set_bot_status(status, reason=""):
    """Set bot ON/OFF status (Admin only)"""
    with open(BOT_STATUS_FILE, 'w') as f:
        json.dump({"status": status, "reason": reason, "updated": time.time()}, f, indent=2)

# ============================================
# FORCE CHANNELS MANAGEMENT
# ============================================

def load_force_channels():
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_force_channels(channels):
    with open(CHANNELS_FILE, 'w') as f:
        json.dump(channels, f, indent=2)

def check_all_channels(user_id):
    channels = load_force_channels()
    if not channels:
        return True
    
    for channel in channels:
        try:
            member = bot.get_chat_member(f"@{channel['username']}", user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except:
            return False
    return True

def get_join_keyboard():
    channels = load_force_channels()
    kb = InlineKeyboardMarkup(row_width=1)
    for channel in channels:
        kb.add(InlineKeyboardButton(f"📢 Join {channel['name']}", url=f"https://t.me/{channel['username']}"))
    kb.add(InlineKeyboardButton("✅ Check Membership", callback_data="check_channels"))
    return kb

# ============================================
# DATA MANAGEMENT
# ============================================

def load():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"users": {}, "devices": {}, "banned": []}

def save(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ============================================
# HELPERS
# ============================================

def is_admin(uid):
    return uid in ADMIN_IDS

def is_banned(uid):
    data = load()
    return str(uid) in data.get("banned", [])

def get_files(uid):
    data = load()
    return data["users"].get(str(uid), {}).get("files", [])

def get_max_files(uid):
    """Admin ke liye unlimited, normal user ke liye 1"""
    if is_admin(uid):
        return 999999  # Unlimited for admin
    return MAX_FILES_PER_USER  # 1 for normal users

def can_upload(uid):
    if is_admin(uid):
        return True, "ok"
    
    # Cooldown check (10 seconds)
    if uid in user_cooldown:
        if time.time() - user_cooldown[uid] < 10:
            return False, f"Wait {int(10 - (time.time() - user_cooldown[uid]))}s between uploads"
    
    # File limit check - Sirf 1 file for normal users
    files = get_files(uid)
    if len(files) >= MAX_FILES_PER_USER:
        return False, f"❌ You can only upload {MAX_FILES_PER_USER} file! Contact admin for more slots."
    
    return True, "ok"

# ============================================
# SCRIPT RUNNER
# ============================================

BUILTIN = {'os','sys','re','time','json','random','shutil','glob','math',
           'datetime','threading','subprocess','asyncio','pathlib','hashlib',
           'typing','collections','itertools','functools','string','logging'}

def get_imports(path):
    imps = set()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            c = f.read()
        
        patterns = [
            r'^\s*import\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            r'^\s*from\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+import'
        ]
        
        for pattern in patterns:
            for m in re.findall(pattern, c, re.MULTILINE):
                if m not in BUILTIN and not m.startswith('_'):
                    imps.add(m)
    except Exception as e:
        print(f"Import scan error: {e}")
    return list(imps)

def install_packages(packages, chat_id, msg_id):
    results = []
    for pkg in packages:
        try:
            bot.edit_message_text(f"📦 Installing: {pkg}...", chat_id, msg_id)
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
                capture_output=True,
                timeout=60
            )
            if result.returncode == 0:
                results.append(f"✅ {pkg}")
            else:
                results.append(f"❌ {pkg}")
        except Exception as e:
            results.append(f"⚠️ {pkg}: {str(e)[:50]}")
        time.sleep(0.5)
    return results

def run_script(path, uid, name, chat_id):
    try:
        process = subprocess.Popen(
            [sys.executable, path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.path.dirname(path)
        )
        
        stdout, stderr = process.communicate()
        out = stdout if stdout else stderr
        out = out[:3500] + ("..." if len(out) > 3500 else "")
        
        if uid in running:
            del running[uid]
        
        data = load()
        if str(uid) in data["users"]:
            for f in data["users"][str(uid)]["files"]:
                if f["name"] == name:
                    f["status"] = "stop"
                    break
            save(data)
        
        status_emoji = "✅" if process.returncode == 0 else "❌"
        result_msg = f"{status_emoji} *{name}*\n"
        if out.strip():
            result_msg += f"```\n{out}\n```"
        else:
            result_msg += "_No output_"
        
        bot.send_message(chat_id, result_msg, parse_mode="Markdown")
        
    except Exception as e:
        if uid in running:
            del running[uid]
        bot.send_message(chat_id, f"❌ *Error*: {str(e)[:200]}", parse_mode="Markdown")

# ============================================
# BEAUTIFUL KEYBOARDS
# ============================================

def main_kb(uid=None):
    kb = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("📁 𝙼𝚢 𝙵𝚒𝚕𝚎𝚜", callback_data="files"),
        InlineKeyboardButton("📊 𝚂𝚝𝚊𝚝𝚜", callback_data="stats"),
        InlineKeyboardButton("❓ 𝙷𝚎𝚕𝚙", callback_data="help"),
        InlineKeyboardButton("👥 𝚂𝚞𝚙𝚙𝚘𝚛𝚝", url="https://t.me/viedietlooterschat")
    ]
    kb.add(*buttons)
    
    if uid and is_admin(uid):
        kb.add(InlineKeyboardButton("👑 𝙰𝚍𝚖𝚒𝚗 𝙿𝚊𝚗𝚎𝚕", callback_data="admin_panel"))
    
    return kb

def admin_panel_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    
    # Check bot status for button display
    bot_status, bot_reason = get_bot_status()
    status_btn = "🔴 𝙱𝙾𝚃 𝙾𝙵𝙵" if bot_status == "off" else "🟢 𝙱𝙾𝚃 𝙾𝙽"
    status_cmd = "bot_off" if bot_status == "on" else "bot_on"
    
    buttons = [
        InlineKeyboardButton("📊 𝚂𝚎𝚛𝚟𝚎𝚛 𝚂𝚝𝚊𝚝𝚜", callback_data="adm_stats"),
        InlineKeyboardButton("👥 𝙰𝚕𝚕 𝚄𝚜𝚎𝚛𝚜", callback_data="adm_users"),
        InlineKeyboardButton("📱 𝙳𝚎𝚟𝚒𝚌𝚎 𝚃𝚛𝚊𝚌𝚔𝚎𝚛", callback_data="adm_devices"),
        InlineKeyboardButton("🔗 𝙵𝚘𝚛𝚌𝚎 𝙲𝚑𝚊𝚗𝚗𝚎𝚕𝚜", callback_data="adm_channels"),
        InlineKeyboardButton("📢 𝙱𝚛𝚘𝚊𝚍𝚌𝚊𝚜𝚝", callback_data="adm_broadcast"),
        InlineKeyboardButton("🚫 𝙱𝚊𝚗/𝚄𝚗𝚋𝚊𝚗", callback_data="adm_ban"),
        InlineKeyboardButton("➕ 𝙶𝚒𝚟𝚎 𝙴𝚡𝚝𝚛𝚊 𝚂𝚕𝚘𝚝", callback_data="adm_give_slot"),
        InlineKeyboardButton(status_btn, callback_data=status_cmd),
        InlineKeyboardButton("💾 𝙱𝚊𝚌𝚔𝚞𝚙", callback_data="adm_backup"),
        InlineKeyboardButton("🗑️ 𝙲𝚕𝚎𝚊𝚛 𝙰𝚕𝚕", callback_data="adm_clear"),
        InlineKeyboardButton("🔙 𝙱𝚊𝚌𝚔", callback_data="back")
    ]
    kb.add(*buttons)
    return kb

def files_kb(uid):
    kb = InlineKeyboardMarkup(row_width=1)
    files = get_files(uid)
    for f in files:
        icon = "🔄" if f["status"] == "run" else "⏸️"
        kb.add(InlineKeyboardButton(f"{icon} {f['name'][:30]}", callback_data=f"file_{f['name']}"))
    kb.add(InlineKeyboardButton("🔙 𝙼𝚊𝚒𝚗 𝙼𝚎𝚗𝚞", callback_data="back"))
    return kb

def action_kb(name, status):
    kb = InlineKeyboardMarkup(row_width=2)
    if status == "run":
        kb.add(InlineKeyboardButton("🛑 𝚂𝚝𝚘𝚙", callback_data=f"stop_{name}"))
    else:
        kb.add(InlineKeyboardButton("▶️ 𝚂𝚝𝚊𝚛𝚝", callback_data=f"start_{name}"))
    kb.add(InlineKeyboardButton("🗑️ 𝙳𝚎𝚕𝚎𝚝𝚎", callback_data=f"del_{name}"))
    kb.add(InlineKeyboardButton("📋 𝚅𝚒𝚎𝚠 𝙲𝚘𝚍𝚎", callback_data=f"view_{name}"))
    kb.add(InlineKeyboardButton("🔙 𝙱𝚊𝚌𝚔 𝚝𝚘 𝙵𝚒𝚕𝚎𝚜", callback_data="files"))
    return kb

def channels_management_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    channels = load_force_channels()
    for ch in channels:
        kb.add(InlineKeyboardButton(f"❌ 𝚁𝚎𝚖𝚘𝚟𝚎 @{ch['username']}", callback_data=f"remove_ch_{ch['username']}"))
    kb.add(InlineKeyboardButton("➕ 𝙰𝚍𝚍 𝙲𝚑𝚊𝚗𝚗𝚎𝚕", callback_data="add_channel"))
    kb.add(InlineKeyboardButton("🔙 𝙱𝚊𝚌𝚔 𝚝𝚘 𝙰𝚍𝚖𝚒𝚗", callback_data="admin_panel"))
    return kb

# ============================================
# COMMAND HANDLERS
# ============================================

@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    
    # Check if bot is OFF
    bot_status, bot_reason = get_bot_status()
    if bot_status == "off":
        bot.reply_to(m, f"🔴 *𝙱𝚘𝚝 𝚒𝚜 𝙾𝙵𝙵*\n\n𝚁𝚎𝚊𝚜𝚘𝚗: {bot_reason if bot_reason else '𝙼𝚊𝚒𝚗𝚝𝚎𝚗𝚊𝚗𝚌𝚎'}\n\n𝙿𝚕𝚎𝚊𝚜𝚎 𝚝𝚛𝚢 𝚊𝚐𝚊𝚒𝚗 𝚕𝚊𝚝𝚎𝚛.", parse_mode="Markdown")
        return
    
    if is_banned(uid):
        bot.reply_to(m, "🚫 𝚈𝚘𝚞 𝚊𝚛𝚎 𝚋𝚊𝚗𝚗𝚎𝚍 𝚏𝚛𝚘𝚖 𝚞𝚜𝚒𝚗𝚐 𝚝𝚑𝚒𝚜 𝚋𝚘𝚝!")
        return
    
    if not check_all_channels(uid):
        bot.reply_to(m, f"🔒 *𝙹𝚘𝚒𝚗 𝚛𝚎𝚚𝚞𝚒𝚛𝚎𝚍 𝚌𝚑𝚊𝚗𝚗𝚎𝚕𝚜 𝚏𝚒𝚛𝚜𝚝!*", 
                    parse_mode="Markdown", reply_markup=get_join_keyboard())
        return
    
    chat_id = m.chat.id
    
    # Track device
    data = load()
    device_id = hashlib.sha256(f"{uid}_{chat_id}_{time.time()}".encode()).hexdigest()[:16]
    
    if "devices" not in data:
        data["devices"] = {}
    
    if device_id not in data["devices"]:
        data["devices"][device_id] = {
            "users": [uid],
            "first_seen": time.time(),
            "last_active": time.time()
        }
    else:
        if uid not in data["devices"][device_id]["users"]:
            data["devices"][device_id]["users"].append(uid)
        data["devices"][device_id]["last_active"] = time.time()
    save(data)
    
    welcome_msg = (
        f"✨ *{BOT_NAME}*\n\n"
        f"🚀 *𝙿𝚘𝚠𝚎𝚛𝚏𝚞𝚕 𝙿𝚢𝚝𝚑𝚘𝚗 𝙷𝚘𝚜𝚝𝚒𝚗𝚐 𝙱𝚘𝚝*\n\n"
        f"📁 𝚂𝚎𝚗𝚍 `.𝚙𝚢` 𝚏𝚒𝚕𝚎𝚜 𝚝𝚘 𝚑𝚘𝚜𝚝\n"
        f"✅ 𝙽𝚘 𝚝𝚒𝚖𝚎 𝚕𝚒𝚖𝚒𝚝 𝚘𝚗 𝚜𝚌𝚛𝚒𝚙𝚝𝚜\n"
        f"📦 𝙰𝚞𝚝𝚘-𝚒𝚗𝚜𝚝𝚊𝚕𝚕 𝚙𝚊𝚌𝚔𝚊𝚐𝚎𝚜\n"
        f"📊 𝙼𝚊𝚡 {MAX_FILES_PER_USER} 𝚏𝚒𝚕𝚎(𝚜) 𝚙𝚎𝚛 𝚞𝚜𝚎𝚛\n\n"
        f"👑 *𝙰𝚍𝚖𝚒𝚗 𝚑𝚊𝚜 𝚞𝚗𝚕𝚒𝚖𝚒𝚝𝚎𝚍 𝚜𝚕𝚘𝚝𝚜*"
    )
    
    bot.reply_to(m, welcome_msg, parse_mode="Markdown", reply_markup=main_kb(uid))

@bot.message_handler(commands=['admin'])
def admin_cmd(m):
    uid = m.from_user.id
    if is_admin(uid):
        bot.reply_to(m, "👑 *𝙰𝚍𝚖𝚒𝚗 𝙲𝚘𝚗𝚝𝚛𝚘𝚕 𝙿𝚊𝚗𝚎𝚕*", parse_mode="Markdown", reply_markup=admin_panel_kb())
    else:
        bot.reply_to(m, "❌ 𝙰𝚌𝚌𝚎𝚜𝚜 𝚍𝚎𝚗𝚒𝚎𝚍!")

@bot.message_handler(commands=['myfiles'])
def myfiles_cmd(m):
    uid = m.from_user.id
    
    bot_status, _ = get_bot_status()
    if bot_status == "off" and not is_admin(uid):
        bot.reply_to(m, "🔴 𝙱𝚘𝚝 𝚒𝚜 𝚌𝚞𝚛𝚛𝚎𝚗𝚝𝚕𝚢 𝙾𝙵𝙵. 𝚃𝚛𝚢 𝚊𝚐𝚊𝚒𝚗 𝚕𝚊𝚝𝚎𝚛.")
        return
    
    if is_banned(uid):
        bot.reply_to(m, "🚫 𝚈𝚘𝚞 𝚊𝚛𝚎 𝚋𝚊𝚗𝚗𝚎𝚍!")
        return
    
    if not check_all_channels(uid):
        bot.reply_to(m, "🔒 𝙹𝚘𝚒𝚗 𝚛𝚎𝚚𝚞𝚒𝚛𝚎𝚍 𝚌𝚑𝚊𝚗𝚗𝚎𝚕𝚜!", reply_markup=get_join_keyboard())
        return
    
    files = get_files(uid)
    if not files:
        bot.reply_to(m, "📁 *𝙽𝚘 𝚏𝚒𝚕𝚎𝚜 𝚞𝚙𝚕𝚘𝚊𝚍𝚎𝚍 𝚢𝚎𝚝*\n\n𝚂𝚎𝚗𝚍 𝚊 `.𝚙𝚢` 𝚏𝚒𝚕𝚎 𝚝𝚘 𝚐𝚎𝚝 𝚜𝚝𝚊𝚛𝚝𝚎𝚍!",
                    parse_mode="Markdown", reply_markup=main_kb(uid))
    else:
        bot.reply_to(m, "📁 *𝚈𝚘𝚞𝚛 𝙵𝚒𝚕𝚎𝚜:*", parse_mode="Markdown", reply_markup=files_kb(uid))

@bot.message_handler(content_types=['document'])
def handle_doc(m):
    uid = m.from_user.id
    
    # Check bot status first
    bot_status, bot_reason = get_bot_status()
    if bot_status == "off" and not is_admin(uid):
        bot.reply_to(m, f"🔴 *𝙱𝚘𝚝 𝚒𝚜 𝙾𝙵𝙵*\n\n𝚁𝚎𝚊𝚜𝚘𝚗: {bot_reason if bot_reason else '𝙼𝚊𝚒𝚗𝚝𝚎𝚗𝚊𝚗𝚌𝚎'}\n\n𝙾𝚗𝚕𝚢 𝚊𝚍𝚖𝚒𝚗 𝚌𝚊𝚗 𝚞𝚙𝚕𝚘𝚊𝚍 𝚛𝚒𝚐𝚑𝚝 𝚗𝚘𝚠.", parse_mode="Markdown")
        return
    
    if is_banned(uid):
        bot.reply_to(m, "🚫 𝚈𝚘𝚞 𝚊𝚛𝚎 𝚋𝚊𝚗𝚗𝚎𝚍!")
        return
    
    if not check_all_channels(uid):
        bot.reply_to(m, "🔒 𝙹𝚘𝚒𝚗 𝚛𝚎𝚚𝚞𝚒𝚛𝚎𝚍 𝚌𝚑𝚊𝚗𝚗𝚎𝚕𝚜 𝚏𝚒𝚛𝚜𝚝!", reply_markup=get_join_keyboard())
        return
    
    if uid in running:
        bot.reply_to(m, f"⚠️ 𝙰𝚕𝚛𝚎𝚊𝚍𝚢 𝚛𝚞𝚗𝚗𝚒𝚗𝚐 𝚊 𝚜𝚌𝚛𝚒𝚙𝚝: `{running[uid]}`\n𝚂𝚝𝚘𝚙 𝚒𝚝 𝚏𝚒𝚛𝚜𝚝!", parse_mode="Markdown")
        return
    
    can_up, msg = can_upload(uid)
    if not can_up:
        bot.reply_to(m, f"⚠️ {msg}")
        return
    
    doc = m.document
    if not doc.file_name.endswith('.py'):
        bot.reply_to(m, "❌ *𝙾𝚗𝚕𝚢 `.𝚙𝚢` 𝚏𝚒𝚕𝚎𝚜 𝚊𝚛𝚎 𝚊𝚕𝚕𝚘𝚠𝚎𝚍!*", parse_mode="Markdown")
        return
    
    if doc.file_size > 10 * 1024 * 1024:
        bot.reply_to(m, "❌ *𝙵𝚒𝚕𝚎 𝚝𝚘𝚘 𝚋𝚒𝚐!* 𝙼𝚊𝚡 10𝙼𝙱", parse_mode="Markdown")
        return
    
    # Apply cooldown for normal users
    if not is_admin(uid):
        user_cooldown[uid] = time.time()
    
    status_msg = bot.reply_to(m, "📥 *𝙳𝚘𝚠𝚗𝚕𝚘𝚊𝚍𝚒𝚗𝚐 𝚏𝚒𝚕𝚎...*", parse_mode="Markdown")
    
    try:
        file_info = bot.get_file(doc.file_id)
        name = re.sub(r'[^\w\-.]', '_', doc.file_name)
        safe_name = f"{int(time.time())}_{name}"
        path = f"user_scripts/{uid}_{safe_name}"
        
        downloaded = bot.download_file(file_info.file_path)
        with open(path, 'wb') as w:
            w.write(downloaded)
        
        bot.edit_message_text("🔍 *𝚂𝚌𝚊𝚗𝚗𝚒𝚗𝚐 𝚍𝚎𝚙𝚎𝚗𝚍𝚎𝚗𝚌𝚒𝚎𝚜...*", m.chat.id, status_msg.message_id, parse_mode="Markdown")
        imports = get_imports(path)
        
        if imports:
            bot.edit_message_text(f"📦 *𝙵𝚘𝚞𝚗𝚍 {len(imports)} 𝚙𝚊𝚌𝚔𝚊𝚐𝚎(𝚜)*\n𝙸𝚗𝚜𝚝𝚊𝚕𝚕𝚒𝚗𝚐...", 
                                 m.chat.id, status_msg.message_id, parse_mode="Markdown")
            results = install_packages(imports, m.chat.id, status_msg.message_id)
            result_text = "\n".join(results)
            bot.edit_message_text(f"📦 *𝙸𝚗𝚜𝚝𝚊𝚕𝚕𝚊𝚝𝚒𝚘𝚗 𝚁𝚎𝚜𝚞𝚕𝚝𝚜:*\n{result_text}", 
                                 m.chat.id, status_msg.message_id, parse_mode="Markdown")
        else:
            bot.edit_message_text("✅ *𝙽𝚘 𝚎𝚡𝚝𝚎𝚛𝚗𝚊𝚕 𝚍𝚎𝚙𝚎𝚗𝚍𝚎𝚗𝚌𝚒𝚎𝚜 𝚏𝚘𝚞𝚗𝚍*", 
                                 m.chat.id, status_msg.message_id, parse_mode="Markdown")
        
        data = load()
        if str(uid) not in data["users"]:
            data["users"][str(uid)] = {"files": [], "joined": time.time()}
        
        data["users"][str(uid)]["files"].append({
            "name": name,
            "path": path,
            "status": "stop",
            "uploaded": time.time(),
            "size": doc.file_size
        })
        save(data)
        
        bot.edit_message_text(
            f"✅ *𝙵𝚒𝚕𝚎 𝙰𝚍𝚍𝚎𝚍 𝚂𝚞𝚌𝚌𝚎𝚜𝚜𝚏𝚞𝚕𝚕𝚢!*\n\n"
            f"📄 𝙽𝚊𝚖𝚎: `{name}`\n"
            f"📦 𝚂𝚒𝚣𝚎: {doc.file_size/1024:.1f}𝙺𝙱\n"
            f"📊 𝚄𝚜𝚊𝚐𝚎: {len(get_files(uid))}/{get_max_files(uid)} 𝚏𝚒𝚕𝚎𝚜\n\n"
            f"𝚄𝚜𝚎 /𝚖𝚢𝚏𝚒𝚕𝚎𝚜 𝚝𝚘 𝚛𝚞𝚗 𝚢𝚘𝚞𝚛 𝚜𝚌𝚛𝚒𝚙𝚝",
            m.chat.id, status_msg.message_id, parse_mode="Markdown", reply_markup=main_kb(uid)
        )
        
    except Exception as e:
        bot.edit_message_text(f"❌ *𝙴𝚛𝚛𝚘𝚛:* {str(e)[:200]}", m.chat.id, status_msg.message_id, parse_mode="Markdown")

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(m):
    uid = m.from_user.id
    if not is_admin(uid):
        return
    
    bot.reply_to(m, "📢 *𝚂𝚎𝚗𝚍 𝚝𝚑𝚎 𝚖𝚎𝚜𝚜𝚊𝚐𝚎 𝚝𝚘 𝚋𝚛𝚘𝚊𝚍𝚌𝚊𝚜𝚝*", parse_mode="Markdown")
    bot.register_next_step_handler(m, process_broadcast)

def process_broadcast(m):
    uid = m.from_user.id
    if not is_admin(uid):
        return
    
    msg = m.text
    data = load()
    users = list(data["users"].keys())
    
    status_msg = bot.reply_to(m, f"📢 *𝙱𝚛𝚘𝚊𝚍𝚌𝚊𝚜𝚝𝚒𝚗𝚐 𝚝𝚘 {len(users)} 𝚞𝚜𝚎𝚛𝚜...*", parse_mode="Markdown")
    
    success = 0
    fail = 0
    
    for user_id in users:
        try:
            bot.send_message(int(user_id), f"📢 *𝙰𝚗𝚗𝚘𝚞𝚗𝚌𝚎𝚖𝚎𝚗𝚝*\n\n{msg}", parse_mode="Markdown")
            success += 1
        except:
            fail += 1
        time.sleep(0.05)
    
    bot.edit_message_text(
        f"✅ *𝙱𝚛𝚘𝚊𝚍𝚌𝚊𝚜𝚝 𝙲𝚘𝚖𝚙𝚕𝚎𝚝𝚎*\n\n"
        f"✅ 𝚂𝚎𝚗𝚝: {success}\n"
        f"❌ 𝙵𝚊𝚒𝚕𝚎𝚍: {fail}",
        m.chat.id, status_msg.message_id, parse_mode="Markdown"
    )

# ============================================
# CALLBACK HANDLERS
# ============================================

@bot.callback_query_handler(func=lambda c: True)
def handle_callback(c):
    uid = c.from_user.id
    cmd = c.data
    
    # Admin commands check
    admin_commands = ['adm_', 'add_channel', 'remove_ch_', 'bot_on', 'bot_off', 'give_slot_']
    if any(cmd.startswith(x) for x in admin_commands):
        if not is_admin(uid):
            bot.answer_callback_query(c.id, "𝙰𝚍𝚖𝚒𝚗 𝚊𝚌𝚌𝚎𝚜𝚜 𝚛𝚎𝚚𝚞𝚒𝚛𝚎𝚍!", show_alert=True)
            return
    
    # Banned check for non-admin
    if is_banned(uid) and not is_admin(uid):
        bot.answer_callback_query(c.id, "𝚈𝚘𝚞 𝚊𝚛𝚎 𝚋𝚊𝚗𝚗𝚎𝚍!", show_alert=True)
        return
    
    # ========== BOT ON/OFF CONTROL ==========
    if cmd == "bot_on" and is_admin(uid):
        set_bot_status("on", "")
        bot.answer_callback_query(c.id, "✅ 𝙱𝚘𝚝 𝚒𝚜 𝙾𝙽 𝙽𝙾𝚆!")
        bot.edit_message_text("👑 *𝙰𝚍𝚖𝚒𝚗 𝙿𝚊𝚗𝚎𝚕*", c.message.chat.id, c.message.message_id,
                             parse_mode="Markdown", reply_markup=admin_panel_kb())
        return
    
    if cmd == "bot_off" and is_admin(uid):
        bot.edit_message_text("🔴 *𝚃𝚄𝚁𝙽 𝙱𝙾𝚃 𝙾𝙵𝙵*\n\n𝚂𝚎𝚗𝚍 𝚛𝚎𝚊𝚜𝚘𝚗 (𝚘𝚙𝚝𝚒𝚘𝚗𝚊𝚕):\n/𝚌𝚊𝚗𝚌𝚎𝚕 𝚝𝚘 𝚊𝚋𝚘𝚛𝚝",
                             c.message.chat.id, c.message.message_id, parse_mode="Markdown")
        bot.register_next_step_handler(c.message, lambda m: set_bot_off_with_reason(m, c.message.chat.id, c.message.message_id))
        return
    
    # ========== GIVE EXTRA SLOT TO USER ==========
    if cmd == "adm_give_slot" and is_admin(uid):
        bot.edit_message_text("➕ *𝙶𝚒𝚟𝚎 𝙴𝚡𝚝𝚛𝚊 𝚂𝚕𝚘𝚝*\n\n𝚂𝚎𝚗𝚍 𝚝𝚑𝚎 𝚞𝚜𝚎𝚛 𝙸𝙳 𝚝𝚘 𝚐𝚒𝚟𝚎 𝚊𝚗 𝚎𝚡𝚝𝚛𝚊 𝚏𝚒𝚕𝚎 𝚜𝚕𝚘𝚝.",
                             c.message.chat.id, c.message.message_id, parse_mode="Markdown")
        bot.register_next_step_handler(c.message, give_extra_slot_process)
        return
    
    # ========== CHANNEL CHECK ==========
    if cmd == "check_channels":
        if check_all_channels(uid):
            bot.edit_message_text("✅ *𝙰𝚕𝚕 𝚌𝚑𝚊𝚗𝚗𝚎𝚕𝚜 𝚟𝚎𝚛𝚒𝚏𝚒𝚎𝚍!*", c.message.chat.id, c.message.message_id,
                                 parse_mode="Markdown", reply_markup=main_kb(uid))
        else:
            bot.answer_callback_query(c.id, "𝙿𝚕𝚎𝚊𝚜𝚎 𝚓𝚘𝚒𝚗 𝚊𝚕𝚕 𝚌𝚑𝚊𝚗𝚗𝚎𝚕𝚜 𝚏𝚒𝚛𝚜𝚝!", show_alert=True)
    
    # ========== ADMIN PANEL ==========
    elif cmd == "admin_panel" and is_admin(uid):
        bot.edit_message_text("👑 *𝙰𝚍𝚖𝚒𝚗 𝙿𝚊𝚗𝚎𝚕*", c.message.chat.id, c.message.message_id,
                             parse_mode="Markdown", reply_markup=admin_panel_kb())
    
    elif cmd == "adm_stats" and is_admin(uid):
        data = load()
        total_files = sum(len(u.get('files', [])) for u in data['users'].values())
        running_count = len(running)
        bot_status, _ = get_bot_status()
        
        stats = (
            f"📊 *𝚂𝚎𝚛𝚟𝚎𝚛 𝚂𝚝𝚊𝚝𝚒𝚜𝚝𝚒𝚌𝚜*\n\n"
            f"🤖 𝙱𝚘𝚝 𝚂𝚝𝚊𝚝𝚞𝚜: `{'🟢 𝙾𝙽' if bot_status == 'on' else '🔴 𝙾𝙵𝙵'}`\n"
            f"👥 *𝚄𝚜𝚎𝚛𝚜:* `{len(data['users'])}`\n"
            f"📁 *𝙵𝚒𝚕𝚎𝚜:* `{total_files}`\n"
            f"🏃 *𝚁𝚞𝚗𝚗𝚒𝚗𝚐:* `{running_count}`\n"
            f"📱 *𝙳𝚎𝚟𝚒𝚌𝚎𝚜:* `{len(data.get('devices', {}))}`\n"
            f"🚫 *𝙱𝚊𝚗𝚗𝚎𝚍:* `{len(data.get('banned', []))}`"
        )
        bot.edit_message_text(stats, c.message.chat.id, c.message.message_id,
                             parse_mode="Markdown", reply_markup=admin_panel_kb())
    
    elif cmd == "adm_users" and is_admin(uid):
        data = load()
        users_text = "👥 *𝚄𝚜𝚎𝚛 𝙻𝚒𝚜𝚝*\n\n"
        for i, (uid_str, info) in enumerate(list(data['users'].items())[:20], 1):
            file_count = len(info.get('files', []))
            max_files = get_max_files(int(uid_str))
            users_text += f"{i}. `{uid_str[:15]}...` | {file_count}/{max_files} 𝚏𝚒𝚕𝚎𝚜\n"
        
        if len(data['users']) > 20:
            users_text += f"\n... 𝚊𝚗𝚍 {len(data['users']) - 20} 𝚖𝚘𝚛𝚎"
        
        bot.edit_message_text(users_text, c.message.chat.id, c.message.message_id,
                             parse_mode="Markdown", reply_markup=admin_panel_kb())
    
    elif cmd == "adm_devices" and is_admin(uid):
        data = load()
        devices = data.get('devices', {})
        if not devices:
            text = "📱 *𝙽𝚘 𝚍𝚎𝚟𝚒𝚌𝚎𝚜 𝚛𝚎𝚌𝚘𝚛𝚍𝚎𝚍*"
        else:
            text = "📱 *𝙳𝚎𝚟𝚒𝚌𝚎 𝚃𝚛𝚊𝚌𝚔𝚎𝚛*\n\n"
            for device_id, info in list(devices.items())[:15]:
                users = info.get('users', [])
                last_active = datetime.fromtimestamp(info.get('last_active', time.time())).strftime('%Y-%m-%d %H:%M')
                text += f"🆔 `{device_id[:12]}...`\n"
                text += f"   👥 {len(users)} 𝚊𝚌𝚌𝚘𝚞𝚗𝚝(𝚜)\n"
                text += f"   ⏱️ 𝙻𝚊𝚜𝚝: {last_active}\n\n"
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id,
                             parse_mode="Markdown", reply_markup=admin_panel_kb())
    
    elif cmd == "adm_channels" and is_admin(uid):
        channels = load_force_channels()
        if not channels:
            text = "🔗 *𝙵𝚘𝚛𝚌𝚎 𝙲𝚑𝚊𝚗𝚗𝚎𝚕𝚜*\n\n𝙽𝚘 𝚌𝚑𝚊𝚗𝚗𝚎𝚕𝚜 𝚌𝚘𝚗𝚏𝚒𝚐𝚞𝚛𝚎𝚍."
        else:
            text = "🔗 *𝙵𝚘𝚛𝚌𝚎 𝙲𝚑𝚊𝚗𝚗𝚎𝚕𝚜*\n\n"
            for ch in channels:
                text += f"📢 @{ch['username']} - {ch['name']}\n"
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id,
                             parse_mode="Markdown", reply_markup=channels_management_kb())
    
    elif cmd == "add_channel" and is_admin(uid):
        bot.edit_message_text("➕ *𝙰𝚍𝚍 𝙵𝚘𝚛𝚌𝚎 𝙲𝚑𝚊𝚗𝚗𝚎𝚕*\n\n𝚂𝚎𝚗𝚍 𝚌𝚑𝚊𝚗𝚗𝚎𝚕 𝚞𝚜𝚎𝚛𝚗𝚊𝚖𝚎 (𝚠𝚒𝚝𝚑𝚘𝚞𝚝 @):",
                             c.message.chat.id, c.message.message_id, parse_mode="Markdown")
        bot.register_next_step_handler(c.message, add_channel_process)
    
    elif cmd.startswith("remove_ch_") and is_admin(uid):
        username = cmd[10:]
        channels = load_force_channels()
        channels = [ch for ch in channels if ch['username'] != username]
        save_force_channels(channels)
        bot.answer_callback_query(c.id, f"𝚁𝚎𝚖𝚘𝚟𝚎𝚍 @{username}", show_alert=True)
        bot.edit_message_text("✅ *𝙲𝚑𝚊𝚗𝚗𝚎𝚕 𝚛𝚎𝚖𝚘𝚟𝚎𝚍*", c.message.chat.id, c.message.message_id,
                             parse_mode="Markdown", reply_markup=admin_panel_kb())
    
    elif cmd == "adm_broadcast" and is_admin(uid):
        bot.edit_message_text("📢 *𝙱𝚛𝚘𝚊𝚍𝚌𝚊𝚜𝚝*\n\n𝚄𝚜𝚎 /𝚋𝚛𝚘𝚊𝚍𝚌𝚊𝚜𝚝 𝚌𝚘𝚖𝚖𝚊𝚗𝚍.",
                             c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=admin_panel_kb())
    
    elif cmd == "adm_ban" and is_admin(uid):
        data = load()
        banned = data.get('banned', [])
        if banned:
            text = "🚫 *𝙱𝚊𝚗𝚗𝚎𝚍 𝚄𝚜𝚎𝚛𝚜*\n\n"
            for uid_str in banned[:20]:
                text += f"• `{uid_str[:15]}...`\n"
            text += "\n𝚂𝚎𝚗𝚍 𝚞𝚜𝚎𝚛 𝙸𝙳 𝚝𝚘 𝚞𝚗𝚋𝚊𝚗."
        else:
            text = "🚫 *𝙽𝚘 𝚋𝚊𝚗𝚗𝚎𝚍 𝚞𝚜𝚎𝚛𝚜*\n\n𝚂𝚎𝚗𝚍 𝚞𝚜𝚎𝚛 𝙸𝙳 𝚝𝚘 𝚋𝚊𝚗."
        
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id,
                             parse_mode="Markdown")
        bot.register_next_step_handler(c.message, ban_user_process)
    
    elif cmd == "adm_backup" and is_admin(uid):
        backup_name = f"backup_{int(time.time())}.json"
        shutil.copy(DATA_FILE, f"backups/{backup_name}")
        bot.edit_message_text(f"✅ *𝙱𝚊𝚌𝚔𝚞𝚙 𝚌𝚛𝚎𝚊𝚝𝚎𝚍*\n`𝚋𝚊𝚌𝚔𝚞𝚙𝚜/{backup_name}`",
                             c.message.chat.id, c.message.message_id, parse_mode="Markdown",
                             reply_markup=admin_panel_kb())
    
    elif cmd == "adm_clear" and is_admin(uid):
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("✅ 𝚈𝚎𝚜, 𝙲𝚕𝚎𝚊𝚛 𝙰𝚕𝚕", callback_data="confirm_clear"))
        kb.add(InlineKeyboardButton("❌ 𝙲𝚊𝚗𝚌𝚎𝚕", callback_data="admin_panel"))
        bot.edit_message_text("⚠️ *𝙳𝙰𝙽𝙶𝙴𝚁*\n\n𝚃𝚑𝚒𝚜 𝚠𝚒𝚕𝚕 𝚍𝚎𝚕𝚎𝚝𝚎 𝙰𝙻𝙻 𝚞𝚜𝚎𝚛 𝚍𝚊𝚝𝚊!\n𝙰𝚛𝚎 𝚢𝚘𝚞 𝚜𝚞𝚛𝚎?",
                             c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=kb)
    
    elif cmd == "confirm_clear" and is_admin(uid):
        for f in os.listdir("user_scripts"):
            try:
                os.remove(f"user_scripts/{f}")
            except:
                pass
        save({"users": {}, "devices": {}, "banned": []})
        bot.edit_message_text("✅ *𝙰𝚕𝚕 𝚍𝚊𝚝𝚊 𝚌𝚕𝚎𝚊𝚛𝚎𝚍!*", c.message.chat.id, c.message.message_id,
                             parse_mode="Markdown", reply_markup=admin_panel_kb())
    
    # ========== USER COMMANDS ==========
    elif cmd == "back":
        bot.edit_message_text("✨ *𝙼𝚊𝚒𝚗 𝙼𝚎𝚗𝚞*", c.message.chat.id, c.message.message_id,
                             parse_mode="Markdown", reply_markup=main_kb(uid))
    
    elif cmd == "files":
        files = get_files(uid)
        if not files:
            bot.edit_message_text("📁 *𝙽𝚘 𝚏𝚒𝚕𝚎𝚜*", c.message.chat.id, c.message.message_id,
                                 parse_mode="Markdown", reply_markup=main_kb(uid))
        else:
            bot.edit_message_text("📁 *𝚈𝚘𝚞𝚛 𝙵𝚒𝚕𝚎𝚜*", c.message.chat.id, c.message.message_id,
                                 parse_mode="Markdown", reply_markup=files_kb(uid))
    
    elif cmd == "stats":
        files = get_files(uid)
        max_files = get_max_files(uid)
        text = (
            f"📊 *𝚈𝚘𝚞𝚛 𝚂𝚝𝚊𝚝𝚜*\n\n"
            f"📁 𝙵𝚒𝚕𝚎𝚜: `{len(files)}/{max_files}`\n"
            f"🏃 𝚁𝚞𝚗𝚗𝚒𝚗𝚐: `{'𝚈𝚎𝚜' if uid in running else '𝙽𝚘'}`\n"
            f"👑 𝙰𝚍𝚖𝚒𝚗: `{'𝚈𝚎𝚜' if is_admin(uid) else '𝙽𝚘'}`\n"
            f"💾 𝚂𝚝𝚘𝚛𝚊𝚐𝚎: `{sum(f.get('size', 0) for f in files)/1024/1024:.2f}𝙼𝙱`"
        )
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id,
                             parse_mode="Markdown", reply_markup=main_kb(uid))
    
    elif cmd == "help":
        help_text = (
            f"❓ *𝙷𝚎𝚕𝚙 𝙶𝚞𝚒𝚍𝚎*\n\n"
            f"📤 *𝚄𝚙𝚕𝚘𝚊𝚍 𝙵𝚒𝚕𝚎*\n"
            f"𝚂𝚎𝚗𝚍 𝚊𝚗𝚢 `.𝚙𝚢` 𝚏𝚒𝚕𝚎 𝚝𝚘 𝚝𝚑𝚎 𝚋𝚘𝚝\n\n"
            f"▶️ *𝚁𝚞𝚗 𝚂𝚌𝚛𝚒𝚙𝚝*\n"
            f"𝚄𝚜𝚎 /𝚖𝚢𝚏𝚒𝚕𝚎𝚜 → 𝚂𝚎𝚕𝚎𝚌𝚝 𝚏𝚒𝚕𝚎 → 𝚂𝚝𝚊𝚛𝚝\n\n"
            f"🛑 *𝚂𝚝𝚘𝚙 𝚂𝚌𝚛𝚒𝚙𝚝*\n"
            f"𝚂𝚊𝚖𝚎 𝚖𝚎𝚗𝚞 → 𝚂𝚝𝚘𝚙\n\n"
            f"📦 *𝙳𝚎𝚙𝚎𝚗𝚍𝚎𝚗𝚌𝚒𝚎𝚜*\n"
            f"𝙱𝚘𝚝 𝚊𝚞𝚝𝚘-𝚒𝚗𝚜𝚝𝚊𝚕𝚕𝚜 𝚛𝚎𝚚𝚞𝚒𝚛𝚎𝚍 𝚙𝚊𝚌𝚔𝚊𝚐𝚎𝚜\n\n"
            f"⚠️ *𝙻𝚒𝚖𝚒𝚝𝚜*\n"
            f"• 𝙼𝚊𝚡 1 𝚏𝚒𝚕𝚎 𝚙𝚎𝚛 𝚞𝚜𝚎𝚛\n"
            f"• 𝙰𝚍𝚖𝚒𝚗 𝚌𝚊𝚗 𝚐𝚒𝚟𝚎 𝚎𝚡𝚝𝚛𝚊 𝚜𝚕𝚘𝚝𝚜\n"
            f"• 𝙼𝚊𝚡 10𝙼𝙱 𝚙𝚎𝚛 𝚏𝚒𝚕𝚎\n"
            f"• 𝙽𝚘 𝚝𝚒𝚖𝚎 𝚕𝚒𝚖𝚒𝚝"
        )
        bot.edit_message_text(help_text, c.message.chat.id, c.message.message_id,
                             parse_mode="Markdown", reply_markup=main_kb(uid))
    
    # ========== FILE ACTIONS ==========
    elif cmd.startswith("file_"):
        name = cmd[5:]
        for f in get_files(uid):
            if f["name"] == name:
                status = "🔄 𝚁𝚞𝚗𝚗𝚒𝚗𝚐" if f["status"] == "run" else "⏸️ 𝚂𝚝𝚘𝚙𝚙𝚎𝚍"
                uploaded = datetime.fromtimestamp(f.get('uploaded', time.time())).strftime('%Y-%m-%d')
                text = f"📄 *{name}*\n\n𝚂𝚝𝚊𝚝𝚞𝚜: {status}\n𝚄𝚙𝚕𝚘𝚊𝚍𝚎𝚍: {uploaded}\n𝚂𝚒𝚣𝚎: {f.get('size', 0)/1024:.1f}𝙺𝙱"
                bot.edit_message_text(text, c.message.chat.id, c.message.message_id,
                                     parse_mode="Markdown", reply_markup=action_kb(name, f["status"]))
                return
    
    elif cmd.startswith("view_"):
        name = cmd[5:]
        for f in get_files(uid):
            if f["name"] == name and os.path.exists(f["path"]):
                try:
                    with open(f["path"], 'r', encoding='utf-8') as code_file:
                        code = code_file.read(3000)
                    code_preview = code[:2000] + ("..." if len(code) > 2000 else "")
                    bot.edit_message_text(f"📄 *{name}*\n```python\n{code_preview}\n```",
                                         c.message.chat.id, c.message.message_id,
                                         parse_mode="Markdown", reply_markup=action_kb(name, f["status"]))
                except:
                    bot.answer_callback_query(c.id, "𝙲𝚊𝚗𝚗𝚘𝚝 𝚛𝚎𝚊𝚍 𝚏𝚒𝚕𝚎", show_alert=True)
                return
    
    elif cmd.startswith("del_"):
        name = cmd[4:]
        if uid in running and running.get(uid) == name:
            del running[uid]
        
        data = load()
        if str(uid) in data["users"]:
            for f in data["users"][str(uid)]["files"]:
                if f["name"] == name:
                    if os.path.exists(f["path"]):
                        os.remove(f["path"])
                    break
            data["users"][str(uid)]["files"] = [f for f in data["users"][str(uid)]["files"] if f["name"] != name]
            save(data)
        
        bot.edit_message_text(f"🗑️ *𝙳𝚎𝚕𝚎𝚝𝚎𝚍:* `{name}`", c.message.chat.id, c.message.message_id,
                             parse_mode="Markdown", reply_markup=main_kb(uid))
    
    elif cmd.startswith("stop_"):
        name = cmd[5:]
        if uid in running and running.get(uid) == name:
            del running[uid]
        
        data = load()
        if str(uid) in data["users"]:
            for f in data["users"][str(uid)]["files"]:
                if f["name"] == name:
                    f["status"] = "stop"
                    break
            save(data)
        
        bot.edit_message_text(f"🛑 *𝚂𝚝𝚘𝚙𝚙𝚎𝚍:* `{name}`", c.message.chat.id, c.message.message_id,
                             parse_mode="Markdown", reply_markup=main_kb(uid))
    
    elif cmd.startswith("start_"):
        name = cmd[6:]
        
        # Check if bot is OFF (only admin can start scripts when bot is off)
        bot_status, _ = get_bot_status()
        if bot_status == "off" and not is_admin(uid):
            bot.answer_callback_query(c.id, "𝙱𝚘𝚝 𝚒𝚜 𝙾𝙵𝙵! 𝙾𝚗𝚕𝚢 𝚊𝚍𝚖𝚒𝚗 𝚌𝚊𝚗 𝚛𝚞𝚗 𝚜𝚌𝚛𝚒𝚙𝚝𝚜.", show_alert=True)
            return
        
        if uid in running:
            bot.answer_callback_query(c.id, f"𝙰𝚕𝚛𝚎𝚊𝚍𝚢 𝚛𝚞𝚗𝚗𝚒𝚗𝚐: {running[uid]}", show_alert=True)
            return
        
        data = load()
        for f in data["users"].get(str(uid), {}).get("files", []):
            if f["name"] == name and os.path.exists(f["path"]):
                running[uid] = name
                f["status"] = "run"
                save(data)
                bot.edit_message_text(f"▶️ *𝚂𝚝𝚊𝚛𝚝𝚎𝚍:* `{name}`\n⏱️ 𝙽𝚘 𝚝𝚒𝚖𝚎 𝚕𝚒𝚖𝚒𝚝\n\n𝚂𝚌𝚛𝚒𝚙𝚝 𝚒𝚜 𝚛𝚞𝚗𝚗𝚒𝚗𝚐...",
                                     c.message.chat.id, c.message.message_id,
                                     parse_mode="Markdown", reply_markup=main_kb(uid))
                threading.Thread(target=run_script, args=(f["path"], uid, name, c.message.chat.id), daemon=True).start()
                return

# ========== HELPER FUNCTIONS ==========

def set_bot_off_with_reason(m, chat_id, msg_id):
    uid = m.from_user.id
    if not is_admin(uid):
        return
    
    if m.text == "/cancel":
        bot.edit_message_text("✅ 𝙲𝚊𝚗𝚌𝚎𝚕𝚕𝚎𝚍.", chat_id, msg_id, reply_markup=admin_panel_kb())
        return
    
    reason = m.text.strip()
    set_bot_status("off", reason)
    bot.edit_message_text(f"🔴 *𝙱𝚘𝚝 𝚒𝚜 𝙾𝙵𝙵*\n\n𝚁𝚎𝚊𝚜𝚘𝚗: {reason}", chat_id, msg_id,
                         parse_mode="Markdown", reply_markup=admin_panel_kb())

def add_channel_process(m):
    uid = m.from_user.id
    if not is_admin(uid):
        return
    
    username = m.text.strip().replace('@', '')
    channels = load_force_channels()
    
    if username in [ch['username'] for ch in channels]:
        bot.reply_to(m, "❌ 𝙲𝚑𝚊𝚗𝚗𝚎𝚕 𝚊𝚕𝚛𝚎𝚊𝚍𝚢 𝚊𝚍𝚍𝚎𝚍!")
        return
    
    try:
        chat = bot.get_chat(f"@{username}")
        channels.append({
            "username": username,
            "name": chat.title,
            "added_by": uid,
            "added_at": time.time()
        })
        save_force_channels(channels)
        bot.reply_to(m, f"✅ 𝙰𝚍𝚍𝚎𝚍 @{username} 𝚝𝚘 𝚏𝚘𝚛𝚌𝚎 𝚌𝚑𝚊𝚗𝚗𝚎𝚕𝚜!", reply_markup=admin_panel_kb())
    except Exception as e:
        bot.reply_to(m, f"❌ 𝙴𝚛𝚛𝚘𝚛: {str(e)[:100]}\n𝙼𝚊𝚔𝚎 𝚜𝚞𝚛𝚎 𝚋𝚘𝚝 𝚒𝚜 𝚊𝚍𝚖𝚒𝚗!")

def ban_user_process(m):
    uid = m.from_user.id
    if not is_admin(uid):
        return
    
    try:
        target_uid = int(m.text.strip())
        data = load()
        
        if "banned" not in data:
            data["banned"] = []
        
        if target_uid in data["banned"]:
            data["banned"].remove(target_uid)
            action = "𝚞𝚗𝚋𝚊𝚗𝚗𝚎𝚍"
        else:
            data["banned"].append(target_uid)
            action = "𝚋𝚊𝚗𝚗𝚎𝚍"
        
        save(data)
        bot.reply_to(m, f"✅ 𝚄𝚜𝚎𝚛 `{target_uid}` {action}!", parse_mode="Markdown", reply_markup=admin_panel_kb())
    except:
        bot.reply_to(m, "❌ 𝙸𝚗𝚟𝚊𝚕𝚒𝚍 𝚞𝚜𝚎𝚛 𝙸𝙳!")

def give_extra_slot_process(m):
    uid = m.from_user.id
    if not is_admin(uid):
        return
    
    try:
        target_uid = int(m.text.strip())
        data = load()
        
        if str(target_uid) not in data["users"]:
            data["users"][str(target_uid)] = {"files": [], "joined": time.time()}
        
        # Give extra slot by increasing max (stored in user data)
        # For normal users we track extra slots separately
        if "extra_slots" not in data["users"][str(target_uid)]:
            data["users"][str(target_uid)]["extra_slots"] = 0
        
        data["users"][str(target_uid)]["extra_slots"] += 1
        save(data)
        
        bot.reply_to(m, f"✅ 𝙶𝚊𝚟𝚎 +1 𝚎𝚡𝚝𝚛𝚊 𝚏𝚒𝚕𝚎 𝚜𝚕𝚘𝚝 𝚝𝚘 `{target_uid}`!\n\n𝙽𝚘𝚠 𝚝𝚑𝚎𝚢 𝚌𝚊𝚗 𝚞𝚙𝚕𝚘𝚊𝚍 {MAX_FILES_PER_USER + data['users'][str(target_uid)]['extra_slots']} 𝚏𝚒𝚕𝚎𝚜.", 
                    parse_mode="Markdown", reply_markup=admin_panel_kb())
        
        # Notify user
        try:
            bot.send_message(target_uid, f"🎉 *𝙶𝚘𝚘𝚍 𝙽𝚎𝚠𝚜!*\n\n𝙰𝚍𝚖𝚒𝚗 𝚑𝚊𝚜 𝚐𝚒𝚟𝚎𝚗 𝚢𝚘𝚞 +1 𝚎𝚡𝚝𝚛𝚊 𝚏𝚒𝚕𝚎 𝚜𝚕𝚘𝚝!\n\n𝙽𝚘𝚠 𝚢𝚘𝚞 𝚌𝚊𝚗 𝚞𝚙𝚕𝚘𝚊𝚍 {MAX_FILES_PER_USER + data['users'][str(target_uid)]['extra_slots']} 𝚏𝚒𝚕𝚎𝚜.", parse_mode="Markdown")
        except:
            pass
            
    except:
        bot.reply_to(m, "❌ 𝙸𝚗𝚟𝚊𝚕𝚒𝚍 𝚞𝚜𝚎𝚛 𝙸𝙳!")

# Update get_max_files function to include extra slots
def get_max_files(uid):
    if is_admin(uid):
        return 999999
    data = load()
    extra = data["users"].get(str(uid), {}).get("extra_slots", 0)
    return MAX_FILES_PER_USER + extra

# Override the function
import builtins
builtins.get_max_files = get_max_files

# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print(f"✨ {BOT_NAME}")
    print("=" * 60)
    print("✅ 𝙱𝚘𝚝 𝚂𝚝𝚊𝚛𝚝𝚎𝚍!")
    print(f"📊 𝙰𝚍𝚖𝚒𝚗 𝙸𝙳: {ADMIN_IDS[0]}")
    print("📁 𝙲𝚘𝚖𝚖𝚊𝚗𝚍𝚜:")
    print("   /𝚜𝚝𝚊𝚛𝚝 - 𝙼𝚊𝚒𝚗 𝚖𝚎𝚗𝚞")
    print("   /𝚖𝚢𝚏𝚒𝚕𝚎𝚜 - 𝙼𝚊𝚗𝚊𝚐𝚎 𝚏𝚒𝚕𝚎𝚜")
    print("   /𝚊𝚍𝚖𝚒𝚗 - 𝙰𝚍𝚖𝚒𝚗 𝚙𝚊𝚗𝚎𝚕")
    print("   /𝚋𝚛𝚘𝚊𝚍𝚌𝚊𝚜𝚝 - 𝚂𝚎𝚗𝚍 𝚋𝚛𝚘𝚊𝚍𝚌𝚊𝚜𝚝")
    print("=" * 60)
    
    try:
        bot.infinity_polling(timeout=30, interval=1)
    except Exception as e:
        print(f"𝙴𝚛𝚛𝚘𝚛: {e}")
        time.sleep(5)
