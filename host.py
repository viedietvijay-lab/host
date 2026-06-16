#!/usr/bin/env python3
"""
👑 VIEDIET HOST BOT - FIXED VERSION
Telegram Python Hosting Bot with safe editing
"""

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
ADMIN_IDS = [8139558808, 1364476174]
BOT_NAME = "𝐕𝐢𝐞𝐝𝐢𝐞𝐭 𝐇𝐨𝐬𝐭"
MAX_FILES_PER_USER = 1

bot = telebot.TeleBot(BOT_TOKEN)
os.makedirs("user_scripts", exist_ok=True)
os.makedirs("backups", exist_ok=True)

running = {}
user_cooldown = {}

BOT_STATUS_FILE = "bot_status.json"

def get_bot_status():
    if os.path.exists(BOT_STATUS_FILE):
        try:
            with open(BOT_STATUS_FILE, 'r') as f:
                data = json.load(f)
                return data.get("status", "on"), data.get("reason", "")
        except:
            return "on", ""
    return "on", ""

def set_bot_status(status, reason=""):
    with open(BOT_STATUS_FILE, 'w') as f:
        json.dump({"status": status, "reason": reason, "updated": time.time()}, f, indent=2)

# ============================================
# SAFE EDIT FUNCTION - FIXES THE ERROR
# ============================================

def safe_edit_message(chat_id, msg_id, text, parse_mode="Markdown", reply_markup=None):
    """Safe edit - handles 'message not modified' error"""
    try:
        bot.edit_message_text(text, chat_id, msg_id, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        if "message is not modified" in str(e):
            pass  # Ignore - same content
        else:
            raise e

def safe_answer_callback(call_id, text, show_alert=False):
    """Safe callback answer"""
    try:
        bot.answer_callback_query(call_id, text, show_alert=show_alert)
    except Exception as e:
        pass  # Ignore callback errors

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
    if is_admin(uid):
        return 999999
    data = load()
    extra = data["users"].get(str(uid), {}).get("extra_slots", 0)
    return MAX_FILES_PER_USER + extra

def can_upload(uid):
    if is_admin(uid):
        return True, "ok"
    
    if uid in user_cooldown:
        if time.time() - user_cooldown[uid] < 10:
            return False, f"Wait {int(10 - (time.time() - user_cooldown[uid]))}s between uploads"
    
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
            safe_edit_message(chat_id, msg_id, f"📦 Installing: {pkg}...")
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
# KEYBOARDS
# ============================================

def main_kb(uid=None):
    kb = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("📁 My Files", callback_data="files"),
        InlineKeyboardButton("📊 Stats", callback_data="stats"),
        InlineKeyboardButton("❓ Help", callback_data="help"),
        InlineKeyboardButton("👥 Support", url="https://t.me/viedietlooterschat")
    ]
    kb.add(*buttons)
    
    if uid and is_admin(uid):
        kb.add(InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel"))
    
    return kb

def admin_panel_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    
    bot_status, bot_reason = get_bot_status()
    status_btn = "🔴 BOT OFF" if bot_status == "off" else "🟢 BOT ON"
    status_cmd = "bot_off" if bot_status == "on" else "bot_on"
    
    buttons = [
        InlineKeyboardButton("📊 Server Stats", callback_data="adm_stats"),
        InlineKeyboardButton("👥 All Users", callback_data="adm_users"),
        InlineKeyboardButton("📱 Device Tracker", callback_data="adm_devices"),
        InlineKeyboardButton("🔗 Force Channels", callback_data="adm_channels"),
        InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast"),
        InlineKeyboardButton("🚫 Ban/Unban", callback_data="adm_ban"),
        InlineKeyboardButton("➕ Give Extra Slot", callback_data="adm_give_slot"),
        InlineKeyboardButton(status_btn, callback_data=status_cmd),
        InlineKeyboardButton("💾 Backup", callback_data="adm_backup"),
        InlineKeyboardButton("🗑️ Clear All", callback_data="adm_clear"),
        InlineKeyboardButton("🔙 Back", callback_data="back")
    ]
    kb.add(*buttons)
    return kb

def files_kb(uid):
    kb = InlineKeyboardMarkup(row_width=1)
    files = get_files(uid)
    for f in files:
        icon = "🔄" if f["status"] == "run" else "⏸️"
        kb.add(InlineKeyboardButton(f"{icon} {f['name'][:30]}", callback_data=f"file_{f['name']}"))
    kb.add(InlineKeyboardButton("🔙 Main Menu", callback_data="back"))
    return kb

def action_kb(name, status):
    kb = InlineKeyboardMarkup(row_width=2)
    if status == "run":
        kb.add(InlineKeyboardButton("🛑 Stop", callback_data=f"stop_{name}"))
    else:
        kb.add(InlineKeyboardButton("▶️ Start", callback_data=f"start_{name}"))
    kb.add(InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{name}"))
    kb.add(InlineKeyboardButton("📋 View Code", callback_data=f"view_{name}"))
    kb.add(InlineKeyboardButton("🔙 Back to Files", callback_data="files"))
    return kb

def channels_management_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    channels = load_force_channels()
    for ch in channels:
        kb.add(InlineKeyboardButton(f"❌ Remove @{ch['username']}", callback_data=f"remove_ch_{ch['username']}"))
    kb.add(InlineKeyboardButton("➕ Add Channel", callback_data="add_channel"))
    kb.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel"))
    return kb

# ============================================
# COMMAND HANDLERS
# ============================================

@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    
    bot_status, bot_reason = get_bot_status()
    if bot_status == "off":
        bot.reply_to(m, f"🔴 *Bot is OFF*\n\nReason: {bot_reason if bot_reason else 'Maintenance'}\n\nPlease try again later.", parse_mode="Markdown")
        return
    
    if is_banned(uid):
        bot.reply_to(m, "🚫 You are banned from using this bot!")
        return
    
    if not check_all_channels(uid):
        bot.reply_to(m, f"🔒 *Join required channels first!*", 
                    parse_mode="Markdown", reply_markup=get_join_keyboard())
        return
    
    chat_id = m.chat.id
    
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
        f"🚀 *Powerful Python Hosting Bot*\n\n"
        f"📁 Send `.py` files to host\n"
        f"✅ No time limit on scripts\n"
        f"📦 Auto-install packages\n"
        f"📊 Max {MAX_FILES_PER_USER} file(s) per user\n\n"
        f"👑 *Admin has unlimited slots*"
    )
    
    bot.reply_to(m, welcome_msg, parse_mode="Markdown", reply_markup=main_kb(uid))

@bot.message_handler(commands=['admin'])
def admin_cmd(m):
    uid = m.from_user.id
    if is_admin(uid):
        bot.reply_to(m, "👑 *Admin Control Panel*", parse_mode="Markdown", reply_markup=admin_panel_kb())
    else:
        bot.reply_to(m, "❌ Access denied!")

@bot.message_handler(commands=['myfiles'])
def myfiles_cmd(m):
    uid = m.from_user.id
    
    bot_status, _ = get_bot_status()
    if bot_status == "off" and not is_admin(uid):
        bot.reply_to(m, "🔴 Bot is currently OFF. Try again later.")
        return
    
    if is_banned(uid):
        bot.reply_to(m, "🚫 You are banned!")
        return
    
    if not check_all_channels(uid):
        bot.reply_to(m, "🔒 Join required channels!", reply_markup=get_join_keyboard())
        return
    
    files = get_files(uid)
    if not files:
        bot.reply_to(m, "📁 *No files uploaded yet*\n\nSend a `.py` file to get started!",
                    parse_mode="Markdown", reply_markup=main_kb(uid))
    else:
        bot.reply_to(m, "📁 *Your Files:*", parse_mode="Markdown", reply_markup=files_kb(uid))

@bot.message_handler(content_types=['document'])
def handle_doc(m):
    uid = m.from_user.id
    
    bot_status, bot_reason = get_bot_status()
    if bot_status == "off" and not is_admin(uid):
        bot.reply_to(m, f"🔴 *Bot is OFF*\n\nReason: {bot_reason if bot_reason else 'Maintenance'}\n\nOnly admin can upload right now.", parse_mode="Markdown")
        return
    
    if is_banned(uid):
        bot.reply_to(m, "🚫 You are banned!")
        return
    
    if not check_all_channels(uid):
        bot.reply_to(m, "🔒 Join required channels first!", reply_markup=get_join_keyboard())
        return
    
    if uid in running:
        bot.reply_to(m, f"⚠️ Already running a script: `{running[uid]}`\nStop it first!", parse_mode="Markdown")
        return
    
    can_up, msg = can_upload(uid)
    if not can_up:
        bot.reply_to(m, f"⚠️ {msg}")
        return
    
    doc = m.document
    if not doc.file_name.endswith('.py'):
        bot.reply_to(m, "❌ *Only `.py` files are allowed!*", parse_mode="Markdown")
        return
    
    if doc.file_size > 10 * 1024 * 1024:
        bot.reply_to(m, "❌ *File too big!* Max 10MB", parse_mode="Markdown")
        return
    
    if not is_admin(uid):
        user_cooldown[uid] = time.time()
    
    status_msg = bot.reply_to(m, "📥 *Downloading file...*", parse_mode="Markdown")
    
    try:
        file_info = bot.get_file(doc.file_id)
        name = re.sub(r'[^\w\-.]', '_', doc.file_name)
        safe_name = f"{int(time.time())}_{name}"
        path = f"user_scripts/{uid}_{safe_name}"
        
        downloaded = bot.download_file(file_info.file_path)
        with open(path, 'wb') as w:
            w.write(downloaded)
        
        safe_edit_message(m.chat.id, status_msg.message_id, "🔍 *Scanning dependencies...*")
        imports = get_imports(path)
        
        if imports:
            safe_edit_message(m.chat.id, status_msg.message_id, f"📦 *Found {len(imports)} package(s)*\nInstalling...")
            results = install_packages(imports, m.chat.id, status_msg.message_id)
            result_text = "\n".join(results)
            safe_edit_message(m.chat.id, status_msg.message_id, f"📦 *Installation Results:*\n{result_text}")
        else:
            safe_edit_message(m.chat.id, status_msg.message_id, "✅ *No external dependencies found*")
        
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
        
        safe_edit_message(
            m.chat.id, status_msg.message_id,
            f"✅ *File Added Successfully!*\n\n"
            f"📄 Name: `{name}`\n"
            f"📦 Size: {doc.file_size/1024:.1f}KB\n"
            f"📊 Usage: {len(get_files(uid))}/{get_max_files(uid)} files\n\n"
            f"Use /myfiles to run your script",
            reply_markup=main_kb(uid)
        )
        
    except Exception as e:
        safe_edit_message(m.chat.id, status_msg.message_id, f"❌ *Error:* {str(e)[:200]}")

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(m):
    uid = m.from_user.id
    if not is_admin(uid):
        return
    
    bot.reply_to(m, "📢 *Send the message to broadcast*", parse_mode="Markdown")
    bot.register_next_step_handler(m, process_broadcast)

def process_broadcast(m):
    uid = m.from_user.id
    if not is_admin(uid):
        return
    
    msg = m.text
    data = load()
    users = list(data["users"].keys())
    
    status_msg = bot.reply_to(m, f"📢 *Broadcasting to {len(users)} users...*", parse_mode="Markdown")
    
    success = 0
    fail = 0
    
    for user_id in users:
        try:
            bot.send_message(int(user_id), f"📢 *Announcement*\n\n{msg}", parse_mode="Markdown")
            success += 1
        except:
            fail += 1
        time.sleep(0.05)
    
    safe_edit_message(
        m.chat.id, status_msg.message_id,
        f"✅ *Broadcast Complete*\n\n"
        f"✅ Sent: {success}\n"
        f"❌ Failed: {fail}"
    )

# ============================================
# CALLBACK HANDLERS
# ============================================

@bot.callback_query_handler(func=lambda c: True)
def handle_callback(c):
    uid = c.from_user.id
    cmd = c.data
    
    admin_commands = ['adm_', 'add_channel', 'remove_ch_', 'bot_on', 'bot_off', 'give_slot_']
    if any(cmd.startswith(x) for x in admin_commands):
        if not is_admin(uid):
            safe_answer_callback(c.id, "Admin access required!", show_alert=True)
            return
    
    if is_banned(uid) and not is_admin(uid):
        safe_answer_callback(c.id, "You are banned!", show_alert=True)
        return
    
    # ========== BOT ON/OFF CONTROL ==========
    if cmd == "bot_on" and is_admin(uid):
        set_bot_status("on", "")
        safe_answer_callback(c.id, "✅ Bot is ON NOW!")
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         "👑 *Admin Panel*", reply_markup=admin_panel_kb())
        return
    
    if cmd == "bot_off" and is_admin(uid):
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         "🔴 *TURN BOT OFF*\n\nSend reason (optional):\n/cancel to abort")
        bot.register_next_step_handler(c.message, lambda m: set_bot_off_with_reason(m, c.message.chat.id, c.message.message_id))
        return
    
    # ========== GIVE EXTRA SLOT ==========
    if cmd == "adm_give_slot" and is_admin(uid):
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         "➕ *Give Extra Slot*\n\nSend the user ID to give an extra file slot.")
        bot.register_next_step_handler(c.message, give_extra_slot_process)
        return
    
    # ========== CHANNEL CHECK ==========
    if cmd == "check_channels":
        if check_all_channels(uid):
            safe_edit_message(c.message.chat.id, c.message.message_id,
                             "✅ *All channels verified!*", reply_markup=main_kb(uid))
        else:
            safe_answer_callback(c.id, "Please join all channels first!", show_alert=True)
    
    # ========== ADMIN PANEL ==========
    elif cmd == "admin_panel" and is_admin(uid):
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         "👑 *Admin Panel*", reply_markup=admin_panel_kb())
    
    elif cmd == "adm_stats" and is_admin(uid):
        data = load()
        total_files = sum(len(u.get('files', [])) for u in data['users'].values())
        running_count = len(running)
        bot_status, _ = get_bot_status()
        
        stats = (
            f"📊 *Server Statistics*\n\n"
            f"🤖 Bot Status: `{'🟢 ON' if bot_status == 'on' else '🔴 OFF'}`\n"
            f"👥 *Users:* `{len(data['users'])}`\n"
            f"📁 *Files:* `{total_files}`\n"
            f"🏃 *Running:* `{running_count}`\n"
            f"📱 *Devices:* `{len(data.get('devices', {}))}`\n"
            f"🚫 *Banned:* `{len(data.get('banned', []))}`"
        )
        safe_edit_message(c.message.chat.id, c.message.message_id, stats, reply_markup=admin_panel_kb())
    
    elif cmd == "adm_users" and is_admin(uid):
        data = load()
        users_text = "👥 *User List*\n\n"
        for i, (uid_str, info) in enumerate(list(data['users'].items())[:20], 1):
            file_count = len(info.get('files', []))
            max_files = get_max_files(int(uid_str))
            users_text += f"{i}. `{uid_str[:15]}...` | {file_count}/{max_files} files\n"
        
        if len(data['users']) > 20:
            users_text += f"\n... and {len(data['users']) - 20} more"
        
        safe_edit_message(c.message.chat.id, c.message.message_id, users_text, reply_markup=admin_panel_kb())
    
    elif cmd == "adm_devices" and is_admin(uid):
        data = load()
        devices = data.get('devices', {})
        if not devices:
            text = "📱 *No devices recorded*"
        else:
            text = "📱 *Device Tracker*\n\n"
            for device_id, info in list(devices.items())[:15]:
                users = info.get('users', [])
                last_active = datetime.fromtimestamp(info.get('last_active', time.time())).strftime('%Y-%m-%d %H:%M')
                text += f"🆔 `{device_id[:12]}...`\n"
                text += f"   👥 {len(users)} account(s)\n"
                text += f"   ⏱️ Last: {last_active}\n\n"
        safe_edit_message(c.message.chat.id, c.message.message_id, text, reply_markup=admin_panel_kb())
    
    elif cmd == "adm_channels" and is_admin(uid):
        channels = load_force_channels()
        if not channels:
            text = "🔗 *Force Channels*\n\nNo channels configured."
        else:
            text = "🔗 *Force Channels*\n\n"
            for ch in channels:
                text += f"📢 @{ch['username']} - {ch['name']}\n"
        safe_edit_message(c.message.chat.id, c.message.message_id, text, reply_markup=channels_management_kb())
    
    elif cmd == "add_channel" and is_admin(uid):
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         "➕ *Add Force Channel*\n\nSend channel username (without @):")
        bot.register_next_step_handler(c.message, add_channel_process)
    
    elif cmd.startswith("remove_ch_") and is_admin(uid):
        username = cmd[10:]
        channels = load_force_channels()
        channels = [ch for ch in channels if ch['username'] != username]
        save_force_channels(channels)
        safe_answer_callback(c.id, f"Removed @{username}", show_alert=True)
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         "✅ *Channel removed*", reply_markup=admin_panel_kb())
    
    elif cmd == "adm_broadcast" and is_admin(uid):
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         "📢 *Broadcast*\n\nUse /broadcast command.", reply_markup=admin_panel_kb())
    
    elif cmd == "adm_ban" and is_admin(uid):
        data = load()
        banned = data.get('banned', [])
        if banned:
            text = "🚫 *Banned Users*\n\n"
            for uid_str in banned[:20]:
                text += f"• `{uid_str[:15]}...`\n"
            text += "\nSend user ID to unban."
        else:
            text = "🚫 *No banned users*\n\nSend user ID to ban."
        
        safe_edit_message(c.message.chat.id, c.message.message_id, text)
        bot.register_next_step_handler(c.message, ban_user_process)
    
    elif cmd == "adm_backup" and is_admin(uid):
        backup_name = f"backup_{int(time.time())}.json"
        shutil.copy(DATA_FILE, f"backups/{backup_name}")
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         f"✅ *Backup created*\n`backups/{backup_name}`", reply_markup=admin_panel_kb())
    
    elif cmd == "adm_clear" and is_admin(uid):
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("✅ Yes, Clear All", callback_data="confirm_clear"))
        kb.add(InlineKeyboardButton("❌ Cancel", callback_data="admin_panel"))
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         "⚠️ *DANGER*\n\nThis will delete ALL user data!\nAre you sure?", reply_markup=kb)
    
    elif cmd == "confirm_clear" and is_admin(uid):
        for f in os.listdir("user_scripts"):
            try:
                os.remove(f"user_scripts/{f}")
            except:
                pass
        save({"users": {}, "devices": {}, "banned": []})
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         "✅ *All data cleared!*", reply_markup=admin_panel_kb())
    
    # ========== USER COMMANDS ==========
    elif cmd == "back":
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         "✨ *Main Menu*", reply_markup=main_kb(uid))
    
    elif cmd == "files":
        files = get_files(uid)
        if not files:
            safe_edit_message(c.message.chat.id, c.message.message_id,
                             "📁 *No files*", reply_markup=main_kb(uid))
        else:
            safe_edit_message(c.message.chat.id, c.message.message_id,
                             "📁 *Your Files*", reply_markup=files_kb(uid))
    
    elif cmd == "stats":
        files = get_files(uid)
        max_files = get_max_files(uid)
        text = (
            f"📊 *Your Stats*\n\n"
            f"📁 Files: `{len(files)}/{max_files}`\n"
            f"🏃 Running: `{'Yes' if uid in running else 'No'}`\n"
            f"👑 Admin: `{'Yes' if is_admin(uid) else 'No'}`\n"
            f"💾 Storage: `{sum(f.get('size', 0) for f in files)/1024/1024:.2f}MB`"
        )
        safe_edit_message(c.message.chat.id, c.message.message_id, text, reply_markup=main_kb(uid))
    
    elif cmd == "help":
        help_text = (
            f"❓ *Help Guide*\n\n"
            f"📤 *Upload File*\n"
            f"Send any `.py` file to the bot\n\n"
            f"▶️ *Run Script*\n"
            f"Use /myfiles → Select file → Start\n\n"
            f"🛑 *Stop Script*\n"
            f"Same menu → Stop\n\n"
            f"📦 *Dependencies*\n"
            f"Bot auto-installs required packages\n\n"
            f"⚠️ *Limits*\n"
            f"• Max 1 file per user\n"
            f"• Admin can give extra slots\n"
            f"• Max 10MB per file\n"
            f"• No time limit"
        )
        safe_edit_message(c.message.chat.id, c.message.message_id, help_text, reply_markup=main_kb(uid))
    
    # ========== FILE ACTIONS ==========
    elif cmd.startswith("file_"):
        name = cmd[5:]
        for f in get_files(uid):
            if f["name"] == name:
                status = "🔄 Running" if f["status"] == "run" else "⏸️ Stopped"
                uploaded = datetime.fromtimestamp(f.get('uploaded', time.time())).strftime('%Y-%m-%d')
                text = f"📄 *{name}*\n\nStatus: {status}\nUploaded: {uploaded}\nSize: {f.get('size', 0)/1024:.1f}KB"
                safe_edit_message(c.message.chat.id, c.message.message_id, text, reply_markup=action_kb(name, f["status"]))
                return
    
    elif cmd.startswith("view_"):
        name = cmd[5:]
        for f in get_files(uid):
            if f["name"] == name and os.path.exists(f["path"]):
                try:
                    with open(f["path"], 'r', encoding='utf-8') as code_file:
                        code = code_file.read(3000)
                    code_preview = code[:2000] + ("..." if len(code) > 2000 else "")
                    safe_edit_message(c.message.chat.id, c.message.message_id,
                                     f"📄 *{name}*\n```python\n{code_preview}\n```",
                                     reply_markup=action_kb(name, f["status"]))
                except:
                    safe_answer_callback(c.id, "Cannot read file", show_alert=True)
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
        
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         f"🗑️ *Deleted:* `{name}`", reply_markup=main_kb(uid))
    
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
        
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         f"🛑 *Stopped:* `{name}`", reply_markup=main_kb(uid))
    
    elif cmd.startswith("start_"):
        name = cmd[6:]
        
        bot_status, _ = get_bot_status()
        if bot_status == "off" and not is_admin(uid):
            safe_answer_callback(c.id, "Bot is OFF! Only admin can run scripts.", show_alert=True)
            return
        
        if uid in running:
            safe_answer_callback(c.id, f"Already running: {running[uid]}", show_alert=True)
            return
        
        data = load()
        for f in data["users"].get(str(uid), {}).get("files", []):
            if f["name"] == name and os.path.exists(f["path"]):
                running[uid] = name
                f["status"] = "run"
                save(data)
                safe_edit_message(c.message.chat.id, c.message.message_id,
                                 f"▶️ *Started:* `{name}`\n⏱️ No time limit\n\nScript is running...",
                                 reply_markup=main_kb(uid))
                threading.Thread(target=run_script, args=(f["path"], uid, name, c.message.chat.id), daemon=True).start()
                return

# ========== HELPER FUNCTIONS ==========

def set_bot_off_with_reason(m, chat_id, msg_id):
    uid = m.from_user.id
    if not is_admin(uid):
        return
    
    if m.text == "/cancel":
        safe_edit_message(chat_id, msg_id, "✅ Cancelled.", reply_markup=admin_panel_kb())
        return
    
    reason = m.text.strip()
    set_bot_status("off", reason)
    safe_edit_message(chat_id, msg_id,
                     f"🔴 *Bot is OFF*\n\nReason: {reason}", reply_markup=admin_panel_kb())

def add_channel_process(m):
    uid = m.from_user.id
    if not is_admin(uid):
        return
    
    username = m.text.strip().replace('@', '')
    channels = load_force_channels()
    
    if username in [ch['username'] for ch in channels]:
        bot.reply_to(m, "❌ Channel already added!")
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
        bot.reply_to(m, f"✅ Added @{username} to force channels!", reply_markup=admin_panel_kb())
    except Exception as e:
        bot.reply_to(m, f"❌ Error: {str(e)[:100]}\nMake sure bot is admin!")

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
            action = "unbanned"
        else:
            data["banned"].append(target_uid)
            action = "banned"
        
        save(data)
        bot.reply_to(m, f"✅ User `{target_uid}` {action}!", parse_mode="Markdown", reply_markup=admin_panel_kb())
    except:
        bot.reply_to(m, "❌ Invalid user ID!")

def give_extra_slot_process(m):
    uid = m.from_user.id
    if not is_admin(uid):
        return
    
    try:
        target_uid = int(m.text.strip())
        data = load()
        
        if str(target_uid) not in data["users"]:
            data["users"][str(target_uid)] = {"files": [], "joined": time.time()}
        
        if "extra_slots" not in data["users"][str(target_uid)]:
            data["users"][str(target_uid)]["extra_slots"] = 0
        
        data["users"][str(target_uid)]["extra_slots"] += 1
        save(data)
        
        bot.reply_to(m, f"✅ Gave +1 extra file slot to `{target_uid}`!\n\nNow they can upload {MAX_FILES_PER_USER + data['users'][str(target_uid)]['extra_slots']} files.", 
                    parse_mode="Markdown", reply_markup=admin_panel_kb())
        
        try:
            bot.send_message(target_uid, f"🎉 *Good News!*\n\nAdmin has given you +1 extra file slot!\n\nNow you can upload {MAX_FILES_PER_USER + data['users'][str(target_uid)]['extra_slots']} files.", parse_mode="Markdown")
        except:
            pass
            
    except:
        bot.reply_to(m, "❌ Invalid user ID!")

# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print(f"✨ {BOT_NAME}")
    print("=" * 60)
    print("✅ Bot Started!")
    print(f"📊 Admin ID: {ADMIN_IDS[0]}")
    print("📁 Commands:")
    print("   /start - Main menu")
    print("   /myfiles - Manage files")
    print("   /admin - Admin panel")
    print("   /broadcast - Send broadcast")
    print("=" * 60)
    
    try:
        bot.infinity_polling(timeout=30, interval=1)
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)
