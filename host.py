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

# ============================================
# CONFIG
# ============================================
BOT_TOKEN = "8832181426:AAHslqQXqbyZatMUHSfL9d6qeNo5mrUUWHk"
DATA_FILE = "user_data.json"
MAX_FILES_PER_USER = 1
ADMIN_IDS = [8139558808]
FORCE_CHANNEL = "viedietlooterschat"
BOT_NAME = "𝐕𝐢𝐞𝐝𝐢𝐞𝐭 𝐇𝐨𝐬𝐭"

bot = telebot.TeleBot(BOT_TOKEN)
os.makedirs("user_scripts", exist_ok=True)

# Track running scripts
running = {}

# ============================================
# DEVICE FINGERPRINT (ADMIN ONLY)
# ============================================

def get_device_id(user_id, chat_id, first_seen=None):
    """Generate unique device ID - visible only to admin"""
    if first_seen is None:
        first_seen = str(int(time.time()))
    
    # Create fingerprint using multiple factors
    data_string = f"{user_id}_{chat_id}_{first_seen}"
    device_id = hashlib.sha256(data_string.encode()).hexdigest()[:16]
    
    # Also create a device group (same device might have multiple accounts)
    device_group = hashlib.md5(f"{device_id}_group".encode()).hexdigest()[:12]
    
    return device_id, device_group

# ============================================
# DATA
# ============================================

def load():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"users": {}, "used_ref": [], "devices": {}}

def save(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ============================================
# HELPERS
# ============================================

def is_admin(uid):
    return uid in ADMIN_IDS

def is_member(uid):
    try:
        m = bot.get_chat_member(f"@{FORCE_CHANNEL}", uid)
        return m.status in ['member', 'administrator', 'creator']
    except:
        return False

def get_files(uid):
    data = load()
    return data["users"].get(str(uid), {}).get("files", [])

def get_max(uid):
    if is_admin(uid):
        return 999
    data = load()
    return data["users"].get(str(uid), {}).get("max", MAX_FILES_PER_USER)

# ============================================
# SCRIPT RUNNER
# ============================================

def run_script(path, uid, name, chat_id):
    try:
        p = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=None)
        out = p.stdout if p.stdout else p.stderr
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
        
        bot.send_message(chat_id, f"{'✅' if p.returncode==0 else '❌'} *{name}*\n```\n{out}\n```", parse_mode="Markdown")
    except Exception as e:
        if uid in running:
            del running[uid]
        bot.send_message(chat_id, f"❌ *Error*: {str(e)[:200]}")

# ============================================
# INSTALL DEPS
# ============================================

BUILTIN = {'os','sys','re','time','json','random','shutil','glob','math',
           'datetime','threading','subprocess','asyncio','pathlib','hashlib'}

def get_imports(path):
    imps = set()
    try:
        with open(path, 'r') as f:
            c = f.read()
        for m in re.findall(r'^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)', c, re.MULTILINE):
            if m not in BUILTIN:
                imps.add(m)
    except:
        pass
    return list(imps)

def install(pkg):
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", pkg, "--quiet"], capture_output=True)
        return r.returncode == 0
    except:
        return False

# ============================================
# KEYBOARDS
# ============================================

def main_kb():
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("📁 My Files", callback_data="files"),
           InlineKeyboardButton("➕ Refer", callback_data="ref"))
    kb.row(InlineKeyboardButton("📊 Stats", callback_data="stats"),
           InlineKeyboardButton("❓ Help", callback_data="help"))
    kb.row(InlineKeyboardButton("👥 Support", url="https://t.me/viedietlooterschat"))
    return kb

def files_kb(uid):
    kb = InlineKeyboardMarkup()
    for f in get_files(uid):
        icon = "🔄" if f["status"] == "run" else "⏸️"
        kb.add(InlineKeyboardButton(f"{icon} {f['name'][:25]}", callback_data=f"file_{f['name']}"))
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="back"))
    return kb

def action_kb(name, status):
    kb = InlineKeyboardMarkup()
    if status == "run":
        kb.add(InlineKeyboardButton("🛑 Stop", callback_data=f"stop_{name}"))
    else:
        kb.add(InlineKeyboardButton("▶️ Start", callback_data=f"start_{name}"))
    kb.add(InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{name}"))
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="files"))
    return kb

def admin_kb():
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("📊 Stats", callback_data="adm_stats"),
           InlineKeyboardButton("👥 Users", callback_data="adm_users"))
    kb.row(InlineKeyboardButton("📱 Devices", callback_data="adm_devices"),
           InlineKeyboardButton("🗑️ Clear", callback_data="adm_clear"))
    kb.row(InlineKeyboardButton("🔙 Back", callback_data="back"))
    return kb

# ============================================
# COMMANDS
# ============================================

@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    chat_id = m.chat.id
    
    if not is_member(uid):
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("📢 JOIN", url=f"https://t.me/{FORCE_CHANNEL}"))
        kb.add(InlineKeyboardButton("✅ Joined", callback_data="check"))
        bot.reply_to(m, f"🔒 Join @{FORCE_CHANNEL} first!", reply_markup=kb)
        return
    
    # Track device
    data = load()
    device_id, device_group = get_device_id(uid, chat_id)
    
    if "devices" not in data:
        data["devices"] = {}
    
    if device_group not in data["devices"]:
        data["devices"][device_group] = {
            "users": [uid],
            "first_seen": time.time(),
            "device_id": device_id
        }
    else:
        if uid not in data["devices"][device_group]["users"]:
            data["devices"][device_group]["users"].append(uid)
    save(data)
    
    # Check referral
    if m.text and "ref_" in m.text:
        ref = m.text.split("ref_")[-1]
        if str(uid) not in data.get("used_ref", []):
            if ref != str(uid):
                data["used_ref"] = data.get("used_ref", []) + [str(uid)]
                if ref not in data["users"]:
                    data["users"][ref] = {"files": [], "max": MAX_FILES_PER_USER}
                data["users"][ref]["max"] = data["users"][ref].get("max", MAX_FILES_PER_USER) + 2
                save(data)
                bot.reply_to(m, f"✅ Referral success! +2 slots for @{ref}", reply_markup=main_kb())
                return
    
    bot.reply_to(m, f"✨ *{BOT_NAME}*\n\nSend `.py` files to host!\n✅ No time limit\n📁 Max {MAX_FILES_PER_USER} files\n\n🔗 `https://t.me/Viediet_host_bot?start=ref_{uid}`", parse_mode="Markdown", reply_markup=main_kb())

@bot.message_handler(commands=['admin'])
def admin(m):
    if is_admin(m.from_user.id):
        bot.reply_to(m, "👑 Admin Panel", reply_markup=admin_kb())
    else:
        bot.reply_to(m, "❌ No")

@bot.message_handler(commands=['myfiles'])
def myfiles(m):
    uid = m.from_user.id
    if not is_member(uid):
        bot.reply_to(m, "❌ Join channel first!")
        return
    
    files = get_files(uid)
    if not files:
        bot.reply_to(m, "📁 No files. Send a `.py` file!", reply_markup=main_kb())
    else:
        bot.reply_to(m, "📁 Your files:", reply_markup=files_kb(uid))

@bot.message_handler(content_types=['document'])
def handle_doc(m):
    uid = m.from_user.id
    
    if not is_member(uid):
        bot.reply_to(m, "❌ Join channel first!")
        return
    
    if uid in running:
        bot.reply_to(m, f"⚠️ Already running: {running[uid]}")
        return
    
    doc = m.document
    if not doc.file_name.endswith('.py'):
        bot.reply_to(m, "❌ Send .py only!")
        return
    
    if doc.file_size > 10*1024*1024:
        bot.reply_to(m, "❌ Max 10MB")
        return
    
    files = get_files(uid)
    if len(files) >= get_max(uid):
        bot.reply_to(m, f"❌ Limit {get_max(uid)} files! Refer for +2 slots")
        return
    
    # Download
    f = bot.get_file(doc.file_id)
    name = re.sub(r'[^\w\-.]', '_', doc.file_name)
    path = f"user_scripts/{uid}_{int(time.time())}_{name}"
    downloaded = bot.download_file(f.file_path)
    with open(path, 'wb') as w:
        w.write(downloaded)
    
    # Install deps
    imps = get_imports(path)
    if imps:
        bot.reply_to(m, f"📦 Installing: {', '.join(imps)}")
        for pkg in imps:
            install(pkg)
    
    # Save
    data = load()
    if str(uid) not in data["users"]:
        data["users"][str(uid)] = {"files": [], "max": MAX_FILES_PER_USER}
    data["users"][str(uid)]["files"].append({"name": name, "path": path, "status": "stop"})
    save(data)
    
    bot.reply_to(m, f"✅ *Added:* {name}\n\nUse /myfiles to run", parse_mode="Markdown", reply_markup=main_kb())

# ============================================
# CALLBACKS
# ============================================

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    uid = c.from_user.id
    
    if not is_member(uid):
        bot.edit_message_text("❌ Join channel!", c.message.chat.id, c.message.message_id)
        return
    
    cmd = c.data
    
    # Admin
    if cmd == "adm_stats" and is_admin(uid):
        d = load()
        stats = f"📊 *Server Stats*\n\n"
        stats += f"👥 Users: `{len(d['users'])}`\n"
        stats += f"📁 Files: `{sum(len(u.get('files',[])) for u in d['users'].values())}`\n"
        stats += f"📱 Devices: `{len(d.get('devices', {}))}`\n"
        stats += f"🏃 Running: `{len(running)}`\n"
        bot.edit_message_text(stats, c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=admin_kb())
        return
    
    if cmd == "adm_users" and is_admin(uid):
        d = load()
        txt = "👥 *Users*\n\n"
        for u, info in list(d['users'].items())[:15]:
            txt += f"🆔 `{u[:8]}...` | {len(info.get('files',[]))}/{info.get('max',3)} files\n"
        bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=admin_kb())
        return
    
    if cmd == "adm_devices" and is_admin(uid):
        d = load()
        devices = d.get("devices", {})
        if not devices:
            txt = "📱 No devices recorded."
        else:
            txt = "📱 *Devices*\n\n"
            for device_group, info in list(devices.items())[:15]:
                users = info.get("users", [])
                txt += f"🆔 `{device_group[:10]}...` | {len(users)} account(s)\n"
                for u in users[:3]:
                    txt += f"   └ User `{str(u)[:8]}...`\n"
                txt += "\n"
        bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=admin_kb())
        return
    
    if cmd == "adm_clear" and is_admin(uid):
        for f in os.listdir("user_scripts"):
            try:
                os.remove(f"user_scripts/{f}")
            except:
                pass
        save({"users": {}, "used_ref": [], "devices": {}})
        bot.edit_message_text("✅ Cleared!", c.message.chat.id, c.message.message_id, reply_markup=admin_kb())
        return
    
    # User
    if cmd == "check":
        if is_member(uid):
            bot.edit_message_text("✅ Verified!", c.message.chat.id, c.message.message_id, reply_markup=main_kb())
        else:
            bot.edit_message_text("❌ Not joined!", c.message.chat.id, c.message.message_id)
        return
    
    if cmd == "back":
        bot.edit_message_text("✨ Menu", c.message.chat.id, c.message.message_id, reply_markup=main_kb())
        return
    
    if cmd == "files":
        files = get_files(uid)
        if not files:
            bot.edit_message_text("📁 No files", c.message.chat.id, c.message.message_id, reply_markup=main_kb())
        else:
            bot.edit_message_text("📁 Your files:", c.message.chat.id, c.message.message_id, reply_markup=files_kb(uid))
        return
    
    if cmd == "ref":
        bot.edit_message_text(f"🔗 `https://t.me/Viediet_host_bot?start=ref_{uid}`\n\n+2 slots per refer!", c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=main_kb())
        return
    
    if cmd == "stats":
        files = get_files(uid)
        bot.edit_message_text(f"📁 {len(files)}/{get_max(uid)} files\n🏃 Running: {'Yes' if uid in running else 'No'}", c.message.chat.id, c.message.message_id, reply_markup=main_kb())
        return
    
    if cmd == "help":
        bot.edit_message_text("Send .py file → Auto install deps → Run /myfiles → Start", c.message.chat.id, c.message.message_id, reply_markup=main_kb())
        return
    
    # File actions
    if cmd.startswith("file_"):
        name = cmd[5:]
        for f in get_files(uid):
            if f["name"] == name:
                status = "🔄 Running" if f["status"] == "run" else "⏸️ Stopped"
                bot.edit_message_text(f"📄 {name}\nStatus: {status}", c.message.chat.id, c.message.message_id, reply_markup=action_kb(name, f["status"]))
                return
    
    if cmd.startswith("del_"):
        name = cmd[4:]
        if uid in running and running[uid] == name:
            del running[uid]
        d = load()
        if str(uid) in d["users"]:
            for f in d["users"][str(uid)]["files"]:
                if f["name"] == name:
                    if os.path.exists(f["path"]):
                        os.remove(f["path"])
                    break
            d["users"][str(uid)]["files"] = [f for f in d["users"][str(uid)]["files"] if f["name"] != name]
            save(d)
        bot.edit_message_text(f"🗑️ Deleted: {name}", c.message.chat.id, c.message.message_id, reply_markup=main_kb())
        return
    
    if cmd.startswith("stop_"):
        name = cmd[5:]
        if uid in running and running[uid] == name:
            del running[uid]
        d = load()
        if str(uid) in d["users"]:
            for f in d["users"][str(uid)]["files"]:
                if f["name"] == name:
                    f["status"] = "stop"
                    break
            save(d)
        bot.edit_message_text(f"🛑 Stopped: {name}", c.message.chat.id, c.message.message_id, reply_markup=main_kb())
        return
    
    if cmd.startswith("start_"):
        name = cmd[6:]
        if uid in running:
            bot.answer_callback_query(c.id, f"Already running: {running[uid]}", show_alert=True)
            return
        
        d = load()
        for f in d["users"].get(str(uid), {}).get("files", []):
            if f["name"] == name and os.path.exists(f["path"]):
                running[uid] = name
                f["status"] = "run"
                save(d)
                bot.edit_message_text(f"▶️ Started: {name}\n⏱️ No time limit", c.message.chat.id, c.message.message_id, reply_markup=main_kb())
                threading.Thread(target=run_script, args=(f["path"], uid, name, c.message.chat.id)).start()
                return

# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    print("=" * 50)
    print(f"✨ {BOT_NAME} running!")
    print("✅ /start - Menu")
    print("✅ /myfiles - Manage files")
    print("✅ /admin - Admin panel (See devices)")
    print("=" * 50)
    bot.infinity_polling(timeout=30)