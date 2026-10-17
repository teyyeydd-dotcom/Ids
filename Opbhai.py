import asyncio
import logging
import re
import sys
import datetime
import time
import random
import secrets
import os
import json
from typing import List, Dict, Optional, Tuple

from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    FloodWaitError,
    UserAlreadyParticipantError,
    InviteRequestSentError,
    MessageNotModifiedError
)
from telethon.tl.functions.messages import (
    ImportChatInviteRequest, 
    SendReactionRequest, 
    GetMessagesViewsRequest, 
    CheckChatInviteRequest
)
from telethon.tl.functions.channels import (
    JoinChannelRequest, 
    LeaveChannelRequest, 
    GetFullChannelRequest
)
from telethon.tl.functions.account import UpdateStatusRequest, SetPrivacyRequest
from telethon.tl.functions.phone import JoinGroupCallRequest, LeaveGroupCallRequest
from telethon.tl.types import (
    PeerChannel, 
    ReactionEmoji, 
    InputPrivacyKeyStatusTimestamp, 
    InputPrivacyValueAllowAll, 
    InputPrivacyValueDisallowAll,
    DataJSON,
    ChannelParticipantAdmin,
    ChannelParticipantCreator
)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ======================= CONFIGURATION =======================
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_IDS = [7795080978, 5498096445]  # ✅ FIXED: Updated owner IDs

KEEP_ALIVE_INTERVAL = 12
START_TIME = datetime.datetime.now()
DATA_FILE = "bot_data.json"

active_clients: Dict[str, TelegramClient] = {}
task_states = {}
VC_MONITORS: Dict[str, asyncio.Task] = {}
SHUTDOWN = False

account_modes = {}
temp_online_until = {}
next_random_toggle = {}

# ======================= JSON DATA MANAGER =======================
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            return {"sessions": {}, "approved_users": [], "history": []}
    return {"sessions": {}, "approved_users": [], "history": []}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ======================= SESSION MANAGEMENT =======================
async def get_all_sessions():
    data = load_data()
    return data.get("sessions", {})

async def add_session(phone, session_str):
    data = load_data()
    data["sessions"][phone] = session_str
    save_data(data)

async def remove_session(phone):
    data = load_data()
    if phone in data["sessions"]:
        del data["sessions"][phone]
        save_data(data)
        return True
    return False

# ======================= APPROVAL SYSTEM =======================
async def approve_user(user_id: int, approved_by: int, username: str = "", title: str = "") -> bool:
    try:
        data = load_data()
        data["approved_users"] = [u for u in data["approved_users"] if u["user_id"] != user_id]
        data["approved_users"].append({
            "user_id": user_id,
            "username": username,
            "title": title,
            "approved_by": approved_by,
            "approved_at": datetime.datetime.utcnow().isoformat(),
            "is_approved": True
        })
        save_data(data)
        return True
    except Exception as e:
        logger.error(f"Approve error: {e}")
        return False

async def unapprove_user(user_id: int) -> bool:
    try:
        data = load_data()
        original_len = len(data["approved_users"])
        data["approved_users"] = [u for u in data["approved_users"] if u["user_id"] != user_id]
        if len(data["approved_users"]) < original_len:
            save_data(data)
            return True
        return False
    except Exception as e:
        logger.error(f"Unapprove error: {e}")
        return False

async def is_user_approved(user_id: int) -> bool:
    if user_id in OWNER_IDS:
        return True
    data = load_data()
    for user in data["approved_users"]:
        if user["user_id"] == user_id and user.get("is_approved", True):
            return True
    return False

async def get_approved_users() -> List[dict]:
    data = load_data()
    return [u for u in data["approved_users"] if u.get("is_approved", True)]

# ======================= HISTORY LOGGING =======================
async def log_activity(phone, action, target, status):
    try:
        data = load_data()
        data["history"].append({
            "phone": phone,
            "action": action,
            "target": target,
            "status": status,
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
        if len(data["history"]) > 1000:
            data["history"] = data["history"][-1000:]
        save_data(data)
    except Exception as e:
        logger.error(f"Log activity error: {e}")

async def get_today_joins():
    today = datetime.datetime.now().date().isoformat()
    data = load_data()
    count = 0
    for log in data["history"]:
        if log["action"] == "JOIN" and log["timestamp"].startswith(today):
            count += 1
    return count

# ======================= STYLE FUNCTION =======================
def style_text(text: str) -> str:
    bold_caps = {
        'A':'𝗔','B':'𝗕','C':'𝗖','D':'𝗗','E':'𝗘','F':'𝗙','G':'𝗚','H':'𝗛','I':'𝗜',
        'J':'𝗝','K':'𝗞','L':'𝗟','M':'𝗠','N':'𝗡','O':'𝗢','P':'𝗣','Q':'𝗤','R':'𝗥',
        'S':'𝗦','T':'𝗧','U':'𝗨','V':'𝗩','W':'𝗪','X':'𝗫','Y':'𝗬','Z':'𝗭'
    }
    small_caps = {
        'A':'ᴀ','B':'ʙ','C':'ᴄ','D':'ᴅ','E':'ᴇ','F':'ғ','G':'ɢ','H':'ʜ','I':'ɪ',
        'J':'ᴊ','K':'ᴋ','L':'ʟ','M':'ᴍ','N':'ɴ','O':'ᴏ','P':'ᴘ','Q':'ǫ','R':'ʀ',
        'S':'ꜱ','T':'ᴛ','U':'ᴜ','V':'ᴠ','W':'ᴡ','X':'x','Y':'ʏ','Z':'ᴢ'
    }
    def style_word(word):
        if not word:
            return ''
        first = word[0].upper()
        first_styled = bold_caps.get(first, first)
        rest = word[1:].upper()
        rest_styled = ''.join(small_caps.get(ch, ch.lower()) for ch in rest)
        return first_styled + rest_styled
    return re.sub(r'[A-Za-z]+', lambda m: style_word(m.group(0)), text)

def get_uptime():
    diff = datetime.datetime.now() - START_TIME
    minutes = int(diff.total_seconds() / 60)
    if minutes < 60:
        return f"{minutes}M"
    elif minutes < 1440:
        return f"{minutes // 60}𝗛 {minutes % 60}𝗠"
    else:
        return f"{minutes // 1440}𝗗 {minutes % 1440 // 60}𝗛"

async def set_account_status(client, phone: str, is_online: bool):
    try:
        if is_online:
            await client(SetPrivacyRequest(
                key=InputPrivacyKeyStatusTimestamp(),
                rules=[InputPrivacyValueAllowAll()]
            ))
            await client(UpdateStatusRequest(offline=False))
        else:
            await client(SetPrivacyRequest(
                key=InputPrivacyKeyStatusTimestamp(),
                rules=[InputPrivacyValueDisallowAll()]
            ))
            await client(UpdateStatusRequest(offline=True))
    except Exception as e:
        logger.error(f"Status update error for {phone}: {e}")

def trigger_temp_online(phone: str, duration_seconds: int = 90):
    random_duration = duration_seconds + random.randint(0, 30)
    temp_online_until[phone] = time.time() + random_duration
    logger.info(f"⚡ {phone} mixed status set to ONLINE for {random_duration}s")

async def keep_alive(client, phone: str):
    last_applied_status = None
    while not SHUTDOWN:
        try:
            now = time.time()
            should_be_online = False
            if phone in temp_online_until and now < temp_online_until[phone]:
                should_be_online = True
            else:
                if next_random_toggle.get(phone, 0) < now:
                    if random.random() < 0.35:
                        should_be_online = True
                        temp_online_until[phone] = now + random.randint(60, 120)
                    next_random_toggle[phone] = now + random.randint(300, 900)
            if last_applied_status != should_be_online:
                await set_account_status(client, phone, is_online=should_be_online)
                last_applied_status = should_be_online
            else:
                if should_be_online:
                    await client(UpdateStatusRequest(offline=False))
                else:
                    await client(UpdateStatusRequest(offline=True))
            await client.get_me()
        except Exception as e:
            logger.warning(f"Keep-alive loop warning for {phone}: {e}")
        await asyncio.sleep(KEEP_ALIVE_INTERVAL)

async def start_saved_clients():
    sessions = await get_all_sessions()
    logger.info(f"Loading {len(sessions)} sessions...")
    loaded_phones = []
    for phone, session_str in sessions.items():
        try:
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            if await client.is_user_authorized():
                active_clients[phone] = client
                loaded_phones.append(phone)
                logger.info(f"Connected: {phone}")
        except Exception as e:
            logger.error(f"Failed to connect {phone}: {e}")
    for phone in loaded_phones:
        client = active_clients[phone]
        account_modes[phone] = "SMART_MIXED"
        next_random_toggle[phone] = time.time() + random.randint(10, 300)
        asyncio.create_task(keep_alive(client, phone))
    logger.info(f"Loaded {len(loaded_phones)} accounts with SMART MIXED Status Engine")

# ======================= HELPER FUNCTIONS =======================
def parse_target(link: str):
    link = link.strip()
    username_match = re.search(r"(?:t\.me/|@)([a-zA-Z0-9_]{5,32})", link)
    if username_match and "joinchat" not in link and "/c/" not in link:
        return ("public", username_match.group(1))
    invite_match = re.search(r"t\.me/(?:\+|joinchat/)([a-zA-Z0-9_-]+)", link)
    if invite_match:
        return ("private", invite_match.group(1))
    return (None, None)

def parse_vc_link(link: str):
    link = link.strip().replace(" ", "")
    for prefix in ["https://", "http://", "www.", "t.me/", "telegram.me/"]:
        link = link.replace(prefix, "")
    if "?" in link:
        link = link.split("?")[0]
    is_private = False
    identifier = link
    if "joinchat/" in link:
        is_private = True
        identifier = link.split("joinchat/")[1].replace("/", "")
    elif link.startswith("+"):
        is_private = True
        identifier = link[1:].replace("/", "")
    else:
        is_private = False
        identifier = link.replace("@", "").replace("/", "")
    return is_private, identifier

async def resolve_user(bot_client, input_text: str):
    input_text = input_text.strip()
    try:
        if input_text.isdigit():
            entity = await bot_client.get_entity(int(input_text))
        else:
            username = input_text.replace("@", "")
            entity = await bot_client.get_entity(username)
        
        user_id = entity.id
        username_str = f"@{entity.username}" if getattr(entity, 'username', None) else ""
        first_name = getattr(entity, 'first_name', '') or ''
        last_name = getattr(entity, 'last_name', '') or ''
        full_name = f"{first_name} {last_name}".strip() or "User"
        
        display_text = f"{full_name} ({username_str})" if username_str else full_name
        return user_id, username_str, display_text
    except Exception as e:
        logger.error(f"Error resolving user {input_text}: {e}")
        if input_text.isdigit():
            return int(input_text), "", f"ID: {input_text}"
        return None, None, None

async def is_client_admin(client: TelegramClient, entity) -> bool:
    try:
        permissions = await client.get_permissions(entity)
        if permissions and (permissions.is_admin or permissions.is_creator):
            return True
    except Exception:
        try:
            participant = await client.get_permissions(entity, 'me')
            if isinstance(participant, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                return True
        except Exception:
            pass
    return False

async def send_reaction_normal(client, peer, msg_id, emoji):
    try:
        await client(SendReactionRequest(
            peer=peer,
            msg_id=msg_id,
            reaction=[ReactionEmoji(emoticon=emoji)]
        ))
        return True, None
    except Exception as e:
        return False, str(e)

async def view_post(client, peer, msg_id):
    try:
        await client(GetMessagesViewsRequest(
            peer=peer,
            id=[msg_id],
            increment=True
        ))
        return True, None
    except Exception as e:
        return False, str(e)

async def send_multiple_reactions(client, peer, msg_id, emojis):
    results = []
    for emoji in emojis:
        ok, err = await send_reaction_normal(client, peer, msg_id, emoji)
        results.append((emoji, ok, err))
        await asyncio.sleep(0.1 + random.uniform(0.05, 0.15))
    return results

async def resolve_post_peer(link, link_type, target):
    try:
        clean = link.replace('https://', '').replace('http://', '').strip()
        if 't.me/c/' in clean:
            parts = clean.split('t.me/c/')[1].split('/')
            entity = int(parts[0])
            msg_id = int(parts[1].split('?')[0])
            return PeerChannel(abs(entity)), msg_id
        else:
            parts = clean.split('t.me/')[1].split('/')
            entity = parts[0]
            msg_id = int(parts[1].split('?')[0])
            return entity, msg_id
    except Exception:
        return None, None

def get_stop_button():
    return [[Button.inline(style_text("⛔ FORCE STOP"), b"force_stop")]]

def get_cancel():
    return [[Button.inline(style_text("🔙 BACK"), b"back")]]

def get_qty_buttons():
    return [
        [Button.inline("10", b"qty_10"), Button.inline("50", b"qty_50")],
        [Button.inline("100", b"qty_100"), Button.inline(style_text("ALL"), b"qty_all")],
        [Button.inline(style_text("CUSTOM"), b"qty_custom")],
        [Button.inline(style_text("🔙 BACK"), b"back")]
    ]

def get_views_qty_buttons():
    return [
        [Button.inline("10", b"views_qty_10"), Button.inline("50", b"views_qty_50")],
        [Button.inline("100", b"views_qty_100"), Button.inline(style_text("ALL"), b"views_qty_all")],
        [Button.inline(style_text("CUSTOM"), b"views_qty_custom")],
        [Button.inline(style_text("🔙 BACK"), b"back")]
    ]

def get_vc_qty_buttons():
    return [
        [Button.inline("10", b"vc_qty_10"), Button.inline("50", b"vc_qty_50")],
        [Button.inline("100", b"vc_qty_100"), Button.inline(style_text("ALL"), b"vc_qty_all")],
        [Button.inline(style_text("CUSTOM"), b"vc_qty_custom")],
        [Button.inline(style_text("🔙 BACK"), b"back")]
    ]

async def interruptible_sleep(seconds: float, chat_id: int) -> bool:
    step = 0.2
    elapsed = 0.0
    while elapsed < seconds:
        if task_states.get(chat_id, {}).get('cancel'):
            return True
        await asyncio.sleep(step)
        elapsed += step
    return False

# ======================= VC FUNCTIONS =======================
async def monitor_vc(client, entity, phone, identifier):
    while phone in VC_MONITORS and not SHUTDOWN:
        try:
            full_chat = await client(GetFullChannelRequest(entity))
            call_obj = full_chat.full_chat.call
            if not call_obj:
                logger.info(f"[{phone}] VC ended, stopping monitor")
                if phone in VC_MONITORS:
                    del VC_MONITORS[phone]
                break
            try:
                my_ssrc = random.randint(10000, 99999999)
                params = DataJSON(data=json.dumps({"min_version": 2, "ssrc": my_ssrc, "muted": True}))
                await client(JoinGroupCallRequest(call=call_obj, join_as=await client.get_input_entity('me'), params=params, muted=True))
            except UserAlreadyParticipantError:
                pass
            except Exception as e:
                logger.error(f"[{phone}] VC monitor join error: {e}")
        except Exception as e:
            logger.error(f"[{phone}] VC monitor error: {e}")
        await asyncio.sleep(15)

async def _worker_vc_join_persistent(client, phone, identifier, is_private):
    try:
        trigger_temp_online(phone, duration_seconds=180)
        entity = None
        if is_private:
            try:
                updates = await client(ImportChatInviteRequest(identifier))
                if updates.chats:
                    entity = updates.chats[0]
            except UserAlreadyParticipantError:
                try:
                    invite_info = await client(CheckChatInviteRequest(identifier))
                    if hasattr(invite_info, 'chat'):
                        entity = invite_info.chat
                    elif hasattr(invite_info, 'title'):
                        target_title = invite_info.title
                        async for dialog in client.iter_dialogs(limit=None):
                            if dialog.title == target_title:
                                entity = dialog.entity
                                break
                except Exception as e:
                    return 0, f"Already in but resolve failed: {str(e)[:50]}"
            except InviteRequestSentError:
                return 0, "Join request sent to admin (pending approval)"
            except FloodWaitError as e:
                return 0, f"Flood wait {e.seconds}s on channel join"
            except Exception as e:
                return 0, f"Failed to join private channel: {str(e)[:50]}"
        else:
            try:
                await client(JoinChannelRequest(identifier))
            except UserAlreadyParticipantError:
                pass
            except Exception as e:
                return 0, f"Failed to join public channel: {str(e)[:50]}"
            try:
                entity = await client.get_entity(identifier)
            except Exception as e:
                return 0, f"Failed to resolve public entity: {str(e)[:50]}"
        if not entity:
            return 0, "Could not obtain channel/group entity"
        full_chat = await client(GetFullChannelRequest(entity))
        if not full_chat.full_chat.call:
            return 0, "No active voice chat in this channel"
        call_obj = full_chat.full_chat.call
        my_ssrc = random.randint(10000, 99999999)
        params = DataJSON(data=json.dumps({"min_version": 2, "ssrc": my_ssrc, "muted": True}))
        await client(JoinGroupCallRequest(call=call_obj, join_as=await client.get_input_entity('me'), params=params, muted=True))
        if phone in VC_MONITORS:
            VC_MONITORS[phone].cancel()
        VC_MONITORS[phone] = asyncio.create_task(monitor_vc(client, entity, phone, identifier))
        return 1, "Joined VC with persistent monitor"
    except Exception as e:
        return 0, f"Error: {str(e)[:50]}"

async def execute_vc_join(event, raw_link: str, count_limit: int):
    chat_id = event.chat_id
    task_states[chat_id] = {'running': True, 'cancel': False}
    is_private, identifier = parse_vc_link(raw_link)
    if not identifier:
        if chat_id in task_states:
            del task_states[chat_id]
        return await event.respond(style_text("❌ INVALID VOICE CHAT LINK!"))
    all_phones = list(active_clients.keys())
    random.shuffle(all_phones)
    selected_phones = all_phones[:count_limit] if count_limit > 0 else all_phones
    msg = await event.respond(
        style_text(f"🎙️ JOINING VC WITH {len(selected_phones)} ACCOUNTS..."),
        buttons=get_stop_button()
    )
    success_count = 0
    fail_count = 0
    was_cancelled = False
    for idx, phone in enumerate(selected_phones, 1):
        if task_states.get(chat_id, {}).get('cancel'):
            was_cancelled = True
            break
        client = active_clients.get(phone)
        if not client:
            fail_count += 1
            continue
        status, reason = await _worker_vc_join_persistent(client, phone, identifier, is_private)
        if status == 1:
            success_count += 1
            await log_activity(phone, "VC_JOIN", raw_link, "Success")
        else:
            fail_count += 1
            await log_activity(phone, "VC_JOIN", raw_link, reason)
        percent = int((idx / len(selected_phones)) * 100)
        bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
        status_msg = style_text(f"""🎙️ VC JOIN PROGRESS
[{bar}] {percent}%
👤 Account {idx}/{len(selected_phones)}: {phone}
✅ Success: {success_count} | ❌ Failed: {fail_count}""")
        try:
            await msg.edit(status_msg, buttons=get_stop_button())
        except Exception:
            pass
        if await interruptible_sleep(random.uniform(0.1, 0.4), chat_id):
            was_cancelled = True
            break
    if chat_id in task_states:
        del task_states[chat_id]
    title = "⛔ VC JOIN FORCE STOPPED!" if was_cancelled else "✅ VC JOIN TASK COMPLETE!"
    final_text = style_text(f"""{title}
━━━━━━━━━━━━━━━━━━━━━━
📊 VC JOIN RESULTS:
━━━━━━━━━━━━━━━━━━━━━━
✅ Joined VC: {success_count}
❌ Failed: {fail_count}
👥 Total Accounts: {len(selected_phones)}
━━━━━━━━━━━━━━━━━━━━━━""")
    await msg.edit(final_text, buttons=None)
    await asyncio.sleep(1)
    await show_menu(event, event.sender_id)

async def execute_vc_leave(event):
    chat_id = event.chat_id
    task_states[chat_id] = {'running': True, 'cancel': False}
    msg = await event.respond(style_text("🎙️ LEAVING ALL VOICE CHATS..."), buttons=get_stop_button())
    for phone, task in list(VC_MONITORS.items()):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if phone in VC_MONITORS:
            del VC_MONITORS[phone]
    left_count = 0
    was_cancelled = False
    for phone, client in list(active_clients.items()):
        if task_states.get(chat_id, {}).get('cancel'):
            was_cancelled = True
            break
        trigger_temp_online(phone, duration_seconds=90)
        try:
            dialogs = await client.get_dialogs(limit=30)
            for dialog in dialogs:
                if task_states.get(chat_id, {}).get('cancel'):
                    was_cancelled = True
                    break
                try:
                    entity = dialog.entity
                    full_chat = await client(GetFullChannelRequest(entity))
                    if full_chat.full_chat.call:
                        await client(LeaveGroupCallRequest(full_chat.full_chat.call))
                        left_count += 1
                        try:
                            await msg.edit(style_text(f"🎙️ LEAVING VC...\n✅ Left VC instances: {left_count}"), buttons=get_stop_button())
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass
        if await interruptible_sleep(0.2, chat_id):
            was_cancelled = True
            break
    if chat_id in task_states:
        del task_states[chat_id]
    status = "⛔ VC LEAVE FORCE STOPPED!" if was_cancelled else "✅ LEFT ALL VOICE CHATS!"
    await msg.edit(style_text(f"{status}\nTotal Left Calls: {left_count}"), buttons=None)
    await asyncio.sleep(1)
    await show_menu(event, event.sender_id)

# ======================= AUTO VIEWS =======================
async def send_auto_views(chat_id, msg_id, channel_username=None):
    if not active_clients:
        return
    phones = list(active_clients.keys())
    random.shuffle(phones)
    success = 0
    for phone in phones:
        client = active_clients[phone]
        trigger_temp_online(phone, duration_seconds=90)
        try:
            target_peer = channel_username if channel_username else chat_id
            try:
                await client(GetMessagesViewsRequest(
                    peer=target_peer,
                    id=[msg_id],
                    increment=True
                ))
                success += 1
            except Exception:
                await client.get_messages(target_peer, ids=msg_id)
                success += 1
            await log_activity(phone, "AUTO_VIEW", f"msg_id:{msg_id}", "Success")
        except Exception as e:
            if channel_username and ("not found" in str(e).lower() or "channel" in str(e).lower()):
                try:
                    await client(JoinChannelRequest(channel_username))
                    await asyncio.sleep(1)
                    await client.get_messages(channel_username, ids=msg_id)
                    success += 1
                    await log_activity(phone, "AUTO_VIEW", f"msg_id:{msg_id}", "Success after join")
                except Exception:
                    await log_activity(phone, "AUTO_VIEW", f"msg_id:{msg_id}", "Failed join")
            else:
                await log_activity(phone, "AUTO_VIEW", f"msg_id:{msg_id}", str(e)[:30])
        await asyncio.sleep(0.3 + random.uniform(0.1, 0.4))

# ======================= EXECUTION FUNCTIONS =======================
async def execute_join(event, task_data, count_limit):
    chat_id = event.chat_id
    task_states[chat_id] = {'running': True, 'cancel': False}
    links_data = task_data['links_data']
    delay = task_data['delay']
    all_phones = list(active_clients.keys())
    random.shuffle(all_phones)
    selected = all_phones[:count_limit]
    msg = await event.respond(
        style_text(f"🚀 JOINING {len(links_data)} LINKS WITH {len(selected)} ACCOUNTS..."),
        buttons=get_stop_button()
    )
    success = 0
    failed = 0
    already = 0
    was_cancelled = False
    total_ops = len(links_data) * len(selected)
    current_op = 0
    link_idx = 0
    for link_idx, link_info in enumerate(links_data, 1):
        if task_states.get(chat_id, {}).get('cancel'):
            was_cancelled = True
            break
        link_type = link_info['type']
        target = link_info['target']
        original_link = link_info['link']
        for acc_idx, phone in enumerate(selected):
            if task_states.get(chat_id, {}).get('cancel'):
                was_cancelled = True
                break
            trigger_temp_online(phone, duration_seconds=90)
            current_op += 1
            client = active_clients.get(phone)
            if not client:
                failed += 1
                continue
            try:
                if link_type == 'public':
                    await client(JoinChannelRequest(target))
                else:
                    await client(ImportChatInviteRequest(target))
                success += 1
                await log_activity(phone, "JOIN", original_link, "Success")
            except UserAlreadyParticipantError:
                already += 1
                success += 1
                await log_activity(phone, "JOIN", original_link, "Already member")
            except InviteRequestSentError:
                success += 1
                await log_activity(phone, "JOIN", original_link, "Request sent")
            except FloodWaitError as e:
                wait_time = e.seconds if e.seconds < 30 else 30
                await log_activity(phone, "JOIN", original_link, f"Flood wait {wait_time}s")
                if await interruptible_sleep(wait_time, chat_id):
                    was_cancelled = True
                    break
                try:
                    if link_type == 'public':
                        await client(JoinChannelRequest(target))
                    else:
                        await client(ImportChatInviteRequest(target))
                    success += 1
                    await log_activity(phone, "JOIN", original_link, "Success after retry")
                except Exception:
                    failed += 1
            except Exception as e:
                failed += 1
                await log_activity(phone, "JOIN", original_link, str(e)[:30])
            percent = int((current_op / total_ops) * 100) if total_ops > 0 else 0
            filled = percent // 10
            bar = "█" * filled + "░" * (10 - filled)
            status_text = style_text(f"""⟪ JOIN PROGRESS ⟫
[{bar}] {percent}%

📌 Link {link_idx}/{len(links_data)}: {original_link[:35]}
👤 Account {acc_idx + 1}/{len(selected)}: {phone}

📊 STATS:
✅ Success: {success}
⚠️ Already: {already}
❌ Failed: {failed}""")
            try:
                await msg.edit(status_text, buttons=get_stop_button())
            except Exception:
                pass
            actual_delay = delay + random.uniform(0.1, 0.5)
            if await interruptible_sleep(actual_delay, chat_id):
                was_cancelled = True
                break
    title = "⛔ JOIN TASK FORCE STOPPED!" if was_cancelled else "✅ JOIN TASK COMPLETE!"
    final_text = style_text(f"""{title}
━━━━━━━━━━━━━━━━━━━━━━
📊 FINAL STATISTICS:
━━━━━━━━━━━━━━━━━━━━━━
✅ Joined: {success - already}
⚠️ Already: {already}
❌ Failed: {failed}
━━━━━━━━━━━━━━━━━━━━━━
📌 Links Processed: {link_idx if was_cancelled else len(links_data)}
👥 Accounts Used: {len(selected)}
📈 Rate: {int((success/(success+failed))*100) if (success+failed)>0 else 0}%
━━━━━━━━━━━━━━━━━━━━━━""")
    if chat_id in task_states:
        del task_states[chat_id]
    await msg.edit(final_text, buttons=None)
    await asyncio.sleep(1)
    await show_menu(event, event.sender_id)

async def execute_leave_specific(event, link):
    chat_id = event.chat_id
    task_states[chat_id] = {'running': True, 'cancel': False}
    link_type, target = parse_target(link)
    if not link_type and "t.me/" not in link:
        return await event.respond(style_text("INVALID LINK!"), buttons=[[Button.inline(style_text("BACK"), b"back")]])
    msg = await event.respond(style_text(f"📤 LEAVING: {link}"), buttons=get_stop_button())
    count = 0
    skipped_admin = 0
    was_cancelled = False
    for phone, client in list(active_clients.items()):
        if task_states.get(chat_id, {}).get('cancel'):
            was_cancelled = True
            break
        trigger_temp_online(phone, duration_seconds=90)
        try:
            entity = None
            if link_type == 'public':
                entity = await client.get_entity(target)
            else:
                entity = await client.get_entity(link)
            if entity:
                if await is_client_admin(client, entity):
                    skipped_admin += 1
                    logger.info(f"Skipping leave for {phone} in {link} because account is Admin")
                    continue
                if link_type == 'public':
                    await client(LeaveChannelRequest(target))
                else:
                    await client.delete_dialog(entity)
                count += 1
                try:
                    await msg.edit(style_text(f"📤 LEAVING: {link}\n✅ Left: {count}\n🛡️ Protected Admins: {skipped_admin}"), buttons=get_stop_button())
                except Exception:
                    pass
        except Exception:
            pass
        if await interruptible_sleep(1.0 + random.uniform(0.1, 0.3), chat_id):
            was_cancelled = True
            break
    if chat_id in task_states:
        del task_states[chat_id]
    status = "⛔ LEAVE FORCE STOPPED" if was_cancelled else "✅ LEFT FROM"
    await msg.edit(style_text(f"{status} {count} ACCOUNTS\n🛡️ Protected Admins: {skipped_admin}"), buttons=None)
    await asyncio.sleep(1)
    await show_menu(event, event.sender_id)

async def execute_leave_all(event):
    chat_id = event.chat_id
    task_states[chat_id] = {'running': True, 'cancel': False}
    msg = await event.respond(style_text("⚠️ LEAVING ALL CHANNELS..."), buttons=get_stop_button())
    total = 0
    skipped_admin = 0
    was_cancelled = False
    for phone, client in list(active_clients.items()):
        if task_states.get(chat_id, {}).get('cancel'):
            was_cancelled = True
            break
        trigger_temp_online(phone, duration_seconds=90)
        try:
            async for dialog in client.iter_dialogs():
                if task_states.get(chat_id, {}).get('cancel'):
                    was_cancelled = True
                    break
                if dialog.is_channel or dialog.is_group:
                    try:
                        if await is_client_admin(client, dialog.entity):
                            skipped_admin += 1
                            logger.info(f"Skipping leave for {phone} in channel {dialog.title} (Admin Protection)")
                            continue
                        await client.delete_dialog(dialog.entity)
                        total += 1
                        try:
                            await msg.edit(style_text(f"⚠️ LEAVING...\n✅ Left: {total}\n🛡️ Protected Admins: {skipped_admin}"), buttons=get_stop_button())
                        except Exception:
                            pass
                        if await interruptible_sleep(0.5 + random.uniform(0.1, 0.3), chat_id):
                            was_cancelled = True
                            break
                    except Exception:
                        pass
        except Exception:
            pass
    if chat_id in task_states:
        del task_states[chat_id]
    status = "⛔ LEAVE ALL FORCE STOPPED" if was_cancelled else "✅ LEFT FROM"
    await msg.edit(style_text(f"{status} {total} CHATS\n🛡️ Protected Admins: {skipped_admin}"), buttons=None)
    await asyncio.sleep(1)
    await show_menu(event, event.sender_id)

async def execute_react_view(event, task_data, count_limit):
    chat_id = event.chat_id
    task_states[chat_id] = {'running': True, 'cancel': False}
    links_data = task_data['links_data']
    emoji = task_data['emoji']
    speed = task_data['speed']
    accounts = list(active_clients.keys())[:count_limit]
    random.shuffle(accounts)
    msg = await event.respond(
        style_text(f"⚡ REACT & VIEW on {len(links_data)} posts with {len(accounts)} accounts..."),
        buttons=get_stop_button()
    )
    total_ops = len(links_data) * len(accounts)
    current = 0
    success = 0
    failed = 0
    react_ok = 0
    view_ok = 0
    was_cancelled = False
    for link_info in links_data:
        if task_states.get(chat_id, {}).get('cancel'):
            was_cancelled = True
            break
        peer, msg_id = await resolve_post_peer(link_info['link'], link_info['type'], link_info['target'])
        if not peer:
            failed += len(accounts)
            continue
        for phone in accounts:
            if task_states.get(chat_id, {}).get('cancel'):
                was_cancelled = True
                break
            trigger_temp_online(phone, duration_seconds=90)
            current += 1
            client = active_clients.get(phone)
            if not client:
                failed += 1
                continue
            r_ok, _ = await send_reaction_normal(client, peer, msg_id, emoji)
            if r_ok:
                react_ok += 1
            v_ok, _ = await view_post(client, peer, msg_id)
            if v_ok:
                view_ok += 1
            if r_ok and v_ok:
                success += 1
            else:
                failed += 1
            percent = int((current / total_ops) * 100) if total_ops > 0 else 0
            bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
            status = style_text(f"⟪ REACT & VIEW ⟫\n[{bar}] {percent}%\n"
                                 f"✅ Success: {success}  ❌ Failed: {failed}\n"
                                 f"👍 Reactions: {react_ok}  👁 Views: {view_ok}")
            try:
                await msg.edit(status, buttons=get_stop_button())
            except Exception:
                pass
            if await interruptible_sleep(speed + random.uniform(0.05, 0.2), chat_id):
                was_cancelled = True
                break
    if chat_id in task_states:
        del task_states[chat_id]
    title = "⛔ REACT & VIEW FORCE STOPPED!" if was_cancelled else "✅ REACT & VIEW COMPLETE!"
    final = style_text(f"{title}\n"
                       f"━━━━━━━━━━━━━━━━━━━━━━\n"
                       f"✅ Both actions: {success}\n"
                       f"❌ Failed: {failed}\n"
                       f"👍 Reactions sent: {react_ok}\n"
                       f"👁 Views incremented: {view_ok}")
    await msg.edit(final, buttons=None)
    await asyncio.sleep(1)
    await show_menu(event, event.sender_id)

async def execute_multi_react_view(event, task_data, count_limit):
    chat_id = event.chat_id
    task_states[chat_id] = {'running': True, 'cancel': False}
    links_data = task_data['links_data']
    emojis = task_data['emojis']
    speed = task_data['speed']
    accounts = list(active_clients.keys())[:count_limit]
    random.shuffle(accounts)
    msg = await event.respond(
        style_text(f"🔄 MULTI‑REACT & VIEW on {len(links_data)} posts with {len(accounts)} accounts..."),
        buttons=get_stop_button()
    )
    total_ops = len(links_data) * len(accounts)
    current = 0
    success = 0
    failed = 0
    reactions_sent = 0
    was_cancelled = False
    for link_info in links_data:
        if task_states.get(chat_id, {}).get('cancel'):
            was_cancelled = True
            break
        peer, msg_id = await resolve_post_peer(link_info['link'], link_info['type'], link_info['target'])
        if not peer:
            failed += len(accounts)
            continue
        for phone in accounts:
            if task_states.get(chat_id, {}).get('cancel'):
                was_cancelled = True
                break
            trigger_temp_online(phone, duration_seconds=90)
            current += 1
            client = active_clients.get(phone)
            if not client:
                failed += 1
                continue
            res = await send_multiple_reactions(client, peer, msg_id, emojis)
            reactions_sent += len([r for r in res if r[1]])
            v_ok, _ = await view_post(client, peer, msg_id)
            if v_ok:
                success += 1
            else:
                failed += 1
            percent = int((current / total_ops) * 100) if total_ops > 0 else 0
            bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
            status = style_text(f"⟪ MULTI‑REACT ⟫\n[{bar}] {percent}%\n"
                                 f"✅ Viewed: {success}  ❌ Failed: {failed}\n"
                                 f"🔥 Reactions sent: {reactions_sent}")
            try:
                await msg.edit(status, buttons=get_stop_button())
            except Exception:
                pass
            if await interruptible_sleep(speed + random.uniform(0.05, 0.2), chat_id):
                was_cancelled = True
                break
    if chat_id in task_states:
        del task_states[chat_id]
    title = "⛔ MULTI‑REACT FORCE STOPPED!" if was_cancelled else "✅ MULTI‑REACT & VIEW COMPLETE!"
    final = style_text(f"{title}\n"
                       f"━━━━━━━━━━━━━━━━━━━━━━\n"
                       f"✅ Views: {success}\n"
                       f"❌ Failed: {failed}\n"
                       f"🔥 Reactions sent: {reactions_sent}")
    await msg.edit(final, buttons=None)
    await asyncio.sleep(1)
    await show_menu(event, event.sender_id)

async def execute_views(event, post_link, count_limit):
    chat_id_task = event.chat_id
    task_states[chat_id_task] = {'running': True, 'cancel': False}
    channel_username = None
    message_id = None
    chat_id = None
    public_match = re.search(r"t\.me/([a-zA-Z0-9_]+)/(\d+)", post_link)
    if public_match:
        channel_username = public_match.group(1)
        message_id = int(public_match.group(2))
    private_match = re.search(r"t\.me/c/(\d+)/(\d+)", post_link)
    if private_match:
        channel_id = int(private_match.group(1))
        message_id = int(private_match.group(2))
        chat_id = int(f"-100{channel_id}")
    if not channel_username and not chat_id:
        if chat_id_task in task_states:
            del task_states[chat_id_task]
        return await event.respond(style_text("❌ Invalid post link!\n\n✅ Valid formats:\n• https://t.me/username/123\n• https://t.me/c/123456789/123"))
    all_phones = list(active_clients.keys())
    random.shuffle(all_phones)
    selected = all_phones[:count_limit] if count_limit > 0 else all_phones
    if not selected:
        if chat_id_task in task_states:
            del task_states[chat_id_task]
        return await event.respond(style_text("❌ No active accounts!"))
    msg = await event.respond(
        style_text(f"👁️ SENDING REAL VIEWS...\n📌 {post_link[:50]}...\n👥 Accounts: {len(selected)}\n⏳ Processing..."),
        buttons=get_stop_button()
    )
    success = 0
    failed = 0
    not_member = 0
    was_cancelled = False
    total_ops = len(selected)
    current_op = 0
    for acc_idx, phone in enumerate(selected):
        if task_states.get(chat_id_task, {}).get('cancel'):
            was_cancelled = True
            break
        trigger_temp_online(phone, duration_seconds=90)
        current_op += 1
        client = active_clients.get(phone)
        if not client:
            failed += 1
            continue
        try:
            if chat_id:
                try:
                    message = await client.get_messages(chat_id, ids=message_id)
                    if message:
                        success += 1
                        await log_activity(phone, "VIEW", post_link, "Success (Private)")
                    else:
                        failed += 1
                        await log_activity(phone, "VIEW", post_link, "Message not found")
                except Exception as e:
                    error = str(e)
                    if "not found" in error.lower() or "invalid" in error.lower():
                        not_member += 1
                        await log_activity(phone, "VIEW", post_link, "Not member of private channel")
                    else:
                        failed += 1
                        await log_activity(phone, "VIEW", post_link, f"Error: {error[:30]}")
            else:
                try:
                    entity = await client.get_entity(channel_username)
                    message = await client.get_messages(entity, ids=message_id)
                    if message:
                        success += 1
                        await log_activity(phone, "VIEW", post_link, "Success (Public)")
                    else:
                        failed += 1
                except Exception as e:
                    error = str(e)
                    if "not found" in error.lower():
                        try:
                            await client(JoinChannelRequest(channel_username))
                            await asyncio.sleep(1)
                            entity = await client.get_entity(channel_username)
                            message = await client.get_messages(entity, ids=message_id)
                            if message:
                                success += 1
                                await log_activity(phone, "VIEW", post_link, "Success after join")
                            else:
                                failed += 1
                        except Exception:
                            failed += 1
                            await log_activity(phone, "VIEW", post_link, "Failed to join")
                    else:
                        failed += 1
                        await log_activity(phone, "VIEW", post_link, f"Error: {error[:30]}")
        except Exception as e:
            failed += 1
            await log_activity(phone, "VIEW", post_link, f"Exception: {str(e)[:30]}")
        percent = int((current_op / total_ops) * 100) if total_ops > 0 else 0
        filled = percent // 10
        bar = "█" * filled + "░" * (10 - filled)
        status_text = style_text(f"""⟪ REAL VIEWS PROGRESS ⟫
━━━━━━━━━━━━━━━━━━━━━━
🎯 Target: {post_link[:35]}
👥 Progress: {acc_idx + 1}/{len(selected)}
📊 Success: {success} | ❌ Failed: {failed}
🚫 Not Member: {not_member}
{bar} {percent}%
━━━━━━━━━━━━━━━━━━━━━━
⏳ Sending views...""")
        try:
            await msg.edit(status_text, buttons=get_stop_button())
        except Exception:
            pass
        if await interruptible_sleep(0.3 + random.uniform(0.05, 0.15), chat_id_task):
            was_cancelled = True
            break
    if chat_id_task in task_states:
        del task_states[chat_id_task]
    title = "⛔ REAL VIEWS FORCE STOPPED!" if was_cancelled else "✅ REAL VIEWS TASK COMPLETE!"
    final_text = style_text(f"""{title}
━━━━━━━━━━━━━━━━━━━━━━
📊 FINAL STATISTICS:
━━━━━━━━━━━━━━━━━━━━━━
👁️ Real Views Sent: {success}
❌ Failed: {failed}
🚫 Not Member: {not_member}
━━━━━━━━━━━━━━━━━━━━━━
📌 Post: {post_link[:50]}
👥 Accounts Used: {len(selected)}
📈 Success Rate: {int((success/(success+failed+not_member))*100) if (success+failed+not_member)>0 else 0}%
━━━━━━━━━━━━━━━━━━━━━━""")
    await msg.edit(final_text, buttons=None)
    await asyncio.sleep(1)
    await show_menu(event, event.sender_id)

async def execute_views_batch(event, links_text, count_per_post):
    chat_id_task = event.chat_id
    task_states[chat_id_task] = {'running': True, 'cancel': False}
    links = [l.strip() for l in links_text.strip().splitlines() if l.strip()]
    if not links:
        if chat_id_task in task_states:
            del task_states[chat_id_task]
        return await event.respond(style_text("❌ No valid links!"))
    if len(links) > 20:
        if chat_id_task in task_states:
            del task_states[chat_id_task]
        return await event.respond(style_text("⚠️ Max 20 posts at once!"))
    msg = await event.respond(style_text(f"👁️ PROCESSING {len(links)} POSTS..."), buttons=get_stop_button())
    total_views = 0
    results = []
    was_cancelled = False
    for idx, link in enumerate(links, 1):
        if task_states.get(chat_id_task, {}).get('cancel'):
            was_cancelled = True
            break
        try:
            await msg.edit(style_text(f"📌 Processing post {idx}/{len(links)}...\n🔗 {link[:50]}"), buttons=get_stop_button())
        except Exception:
            pass
        chat_id = None
        channel_username = None
        message_id = None
        public_match = re.search(r"t\.me/([a-zA-Z0-9_]+)/(\d+)", link)
        if public_match:
            channel_username = public_match.group(1)
            message_id = int(public_match.group(2))
        private_match = re.search(r"t\.me/c/(\d+)/(\d+)", link)
        if private_match:
            channel_id = int(private_match.group(1))
            message_id = int(private_match.group(2))
            chat_id = int(f"-100{channel_id}")
        if not channel_username and not chat_id:
            results.append(style_text(f"❌ {link[:30]}... - Invalid format"))
            continue
        views_sent = 0
        clients_list = list(active_clients.items())
        random.shuffle(clients_list)
        for phone, client in clients_list:
            if task_states.get(chat_id_task, {}).get('cancel'):
                was_cancelled = True
                break
            trigger_temp_online(phone, duration_seconds=90)
            try:
                if chat_id:
                    message = await client.get_messages(chat_id, ids=message_id)
                    if message:
                        views_sent += 1
                        total_views += 1
                else:
                    entity = await client.get_entity(channel_username)
                    message = await client.get_messages(entity, ids=message_id)
                    if message:
                        views_sent += 1
                        total_views += 1
                await log_activity(phone, "VIEW", link, "Success")
            except Exception as e:
                await log_activity(phone, "VIEW", link, str(e)[:30])
            if await interruptible_sleep(0.2 + random.uniform(0.05, 0.15), chat_id_task):
                was_cancelled = True
                break
        results.append(style_text(f"✅ {link[:30]}... - {views_sent} views"))
        if was_cancelled:
            break
    if chat_id_task in task_states:
        del task_states[chat_id_task]
    title = "⛔ BATCH VIEWS FORCE STOPPED!" if was_cancelled else "✅ BATCH VIEWS COMPLETE!"
    result_text = style_text(f"""{title}
━━━━━━━━━━━━━━━━━━━━━━
📊 RESULTS:
━━━━━━━━━━━━━━━━━━━━━━
""")
    for r in results[:10]:
        result_text += f"{r}\n"
    if len(results) > 10:
        result_text += style_text(f"\n+ {len(results)-10} more")
    result_text += style_text(f"\n━━━━━━━━━━━━━━━━━━━━━━\n👁️ Total Views: {total_views}")
    await msg.edit(result_text, buttons=None)
    await asyncio.sleep(1)
    await show_menu(event, event.sender_id)

# ======================= MAIN MENU UI =======================
async def show_menu(event, user_id, edit_msg=None):
    accounts_count = len(active_clients)
    today_joins = await get_today_joins()
    uptime = get_uptime()
    active_vc_monitors = len(VC_MONITORS)
    menu = (
        f"🤖 𝗝ᴏɪɴ / 𝗟ᴇᴀᴠᴇ & 𝗔ᴜᴛᴏ 𝗩ɪᴇᴡᴇʀ 𝗣ʀᴏ\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 𝗔ᴄᴄᴏᴜɴᴛꜱ : {accounts_count}\n"
        f"📊 𝗧ᴏᴅᴀʏ 𝗝ᴏɪɴꜱ : {today_joins}\n"
        f"🎙️ 𝗔ᴄᴛɪᴠᴇ 𝗩𝗖 : {active_vc_monitors}\n"
        f"⏱️ 𝗨ᴘᴛɪᴍᴇ : {uptime}\n"
        f"⚡ 𝗔ᴜᴛᴏ 𝗠ᴏɴɪᴛᴏʀ : 𝗔ᴄᴛɪᴠᴇ (SMART MIXED) 🟢\n"
        f"🛡️ 𝗔ᴅᴍɪɴ 𝗣ʀᴏᴛᴇᴄᴛɪᴏɴ : 𝗔ᴄᴛɪᴠᴇ 🔒\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 𝗦ᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ғʀᴏᴍ ʙᴇʟᴏᴡ :"
    )
    is_owner = user_id in OWNER_IDS
    if is_owner:
        buttons = [
            [Button.inline("➕ 𝗔𝗗𝗗 𝗔𝗖𝗖𝗢𝗨𝗡𝗧", b"add")],
            [Button.inline("🚀 𝗝𝗢𝗜𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟", b"join"), Button.inline("📤 𝗟𝗘𝗔𝗩𝗘 𝗖𝗛𝗔𝗧", b"leave")],
            [Button.inline("🎙️ 𝗝𝗢𝗜𝗡 𝗩𝗖", b"join_vc"), Button.inline("🔴 𝗟𝗘𝗔𝗩𝗘 𝗩𝗖", b"leave_vc")],
            [Button.inline("⚡ 𝗥𝗘𝗔𝗖𝗧 + 𝗩𝗜𝗘𝗪", b"react_view"), Button.inline("💥 𝗠𝗨𝗟𝗧𝗜 𝗥𝗘𝗔𝗖𝗧", b"multi_react")],
            [Button.inline("👁️ 𝗩𝗜𝗘𝗪𝗦 𝗠𝗘𝗡𝗨", b"views_menu")],
            [Button.inline("📋 𝗔𝗖𝗖𝗢𝗨𝗡𝗧𝗦 𝗟𝗜𝗦𝗧", b"list_accounts"), Button.inline("👑 𝗔𝗣𝗣𝗥𝗢𝗩𝗘", b"approve")],
            [Button.inline("📊 𝗦𝗧𝗔𝗧𝗜𝗦𝗧𝗜𝗖𝗦", b"stats")]
        ]
    else:
        buttons = [
            [Button.inline("➕ 𝗔𝗗𝗗 𝗔𝗖𝗖𝗢𝗨𝗡𝗧", b"add")],
            [Button.inline("🚀 𝗝𝗢𝗜𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟", b"join"), Button.inline("📤 𝗟𝗘𝗔𝗩𝗘 𝗖𝗛𝗔𝗧", b"leave")],
            [Button.inline("🎙️ 𝗝𝗢𝗜𝗡 𝗩𝗖", b"join_vc"), Button.inline("🔴 𝗟𝗘𝗔𝗩𝗘 𝗩𝗖", b"leave_vc")],
            [Button.inline("⚡ 𝗥𝗘𝗔𝗖𝗧 + 𝗩𝗜𝗘𝗪", b"react_view"), Button.inline("💥 𝗠𝗨𝗟𝗧𝗜 𝗥𝗘𝗔𝗖𝗧", b"multi_react")],
            [Button.inline("👁️ 𝗩𝗜𝗘𝗪𝗦 𝗠𝗘𝗡𝗨", b"views_menu")],
            [Button.inline("📋 𝗔𝗖𝗖𝗢𝗨𝗡𝗧𝗦 𝗟𝗜𝗦𝗧", b"list_accounts")]
        ]
    if edit_msg:
        try:
            await edit_msg.edit(menu, buttons=buttons)
        except MessageNotModifiedError:
            pass
        except Exception:
            try:
                await event.respond(menu, buttons=buttons)
            except Exception:
                pass
    else:
        await event.respond(menu, buttons=buttons)

# ======================= BOT INIT =======================
# ✅ FIXED: Safe session file removal
try:
    if os.path.exists('bot_session.session'):
        os.remove('bot_session.session')
    if os.path.exists('bot_session.session-journal'):
        os.remove('bot_session.session-journal')
except Exception as e:
    logger.warning(f"Could not remove session file: {e}")

bot = TelegramClient('bot_session', API_ID, API_HASH)
bot.parse_mode = None

# ======================= AUTO CHANNEL POST LISTENER =======================
@bot.on(events.NewMessage(incoming=True))
async def auto_channel_post_listener(event):
    if not event.is_channel:
        return
    if event.raw_text and event.raw_text.startswith('/'):
        return
    try:
        channel = await event.get_chat()
        msg_id = event.id
        channel_title = getattr(channel, 'title', 'Channel')
        username = getattr(channel, 'username', None)
        logger.info(f"⚡ New Post Detected in: {channel_title} | Msg ID: {msg_id}")
        asyncio.create_task(send_auto_views(event.chat_id, msg_id, username))
    except Exception as e:
        logger.error(f"Auto listener error: {e}")

# ======================= COMMANDS =======================
@bot.on(events.NewMessage(pattern='/start'))
async def start_cmd(event):
    user_id = event.sender_id
    if not await is_user_approved(user_id):
        await event.respond(style_text("⛔ ACCESS DENIED\nContact owner to get approved."))
        return
    # Clear any pending state
    if event.chat_id in task_states:
        del task_states[event.chat_id]
    await show_menu(event, user_id)

@bot.on(events.NewMessage(pattern=r'/add\s+(.+)'))
async def add_user_cmd(event):
    if event.sender_id not in OWNER_IDS:
        return await event.respond(style_text("⛔ Owner only!"))
    try:
        input_data = event.pattern_match.group(1).strip()
        uid, username_str, title = await resolve_user(bot, input_data)
        if not uid:
            return await event.respond(style_text("❌ User not found! Make sure username/ID is correct."))
        if await approve_user(uid, event.sender_id, username=username_str, title=title):
            await event.respond(style_text(f"✅ User {title} ({uid}) approved successfully!"))
        else:
            await event.respond(style_text(f"❌ Failed to approve user {title}."))
    except Exception as e:
        await event.respond(style_text(f"❌ Error: {e}"))

@bot.on(events.NewMessage(pattern=r'/remove\s+(.+)'))
async def remove_user_cmd(event):
    if event.sender_id not in OWNER_IDS:
        return await event.respond(style_text("⛔ Owner only!"))
    try:
        input_data = event.pattern_match.group(1).strip()
        uid, username_str, title = await resolve_user(bot, input_data)
        if not uid:
            return await event.respond(style_text("❌ User not found! Make sure username/ID is correct."))
        if await unapprove_user(uid):
            await event.respond(style_text(f"❌ User {title} ({uid}) removed successfully!"))
        else:
            await event.respond(style_text(f"⚠️ User {title} not found in approved list."))
    except Exception as e:
        await event.respond(style_text(f"❌ Error: {e}"))

@bot.on(events.NewMessage(pattern='/list'))
async def list_cmd(event):
    if not await is_user_approved(event.sender_id):
        return
    users = await get_approved_users()
    if not users:
        await event.respond(style_text("📋 No approved users"))
        return
    msg = style_text("📋 APPROVED USERS\n━━━━━━━━━━━━━━━━\n")
    for i, u in enumerate(users, 1):
        uid = u['user_id']
        uname = u.get('username') or ''
        title = u.get('title') or 'User'
        if uname:
            msg += f"{i}. {title} | {uname} (`{uid}`)\n"
        else:
            msg += f"{i}. {title} (`{uid}`)\n"
    await event.respond(msg)

# ======================= CALLBACK HANDLER =======================
@bot.on(events.CallbackQuery)
async def callback(event):
    user_id = event.sender_id
    if not await is_user_approved(user_id):
        return await event.answer(style_text("Access denied!"), alert=True)
    data = event.data.decode()
    
    if data == "force_stop":
        if event.chat_id in task_states:
            task_states[event.chat_id]['cancel'] = True
            await event.answer(style_text("🛑 Stopping task..."), alert=True)
        else:
            await event.answer(style_text("No running task to stop."), alert=True)
        return
    
    # ✅ FIXED: Back button handler properly cleans up state
    if data == "back":
        await event.answer()
        if event.chat_id in task_states:
            # Clean up login client if exists
            state = task_states[event.chat_id]
            if state.get('type') == 'login' and state.get('client'):
                try:
                    await state['client'].disconnect()
                except:
                    pass
            del task_states[event.chat_id]
        try:
            await show_menu(event, user_id, edit_msg=event.message)
        except Exception as e:
            logger.error(f"Back button error: {e}")
            try:
                await event.respond(style_text("🔙 Main Menu"), buttons=[[Button.inline("🏠 MENU", b"main_menu")]])
            except:
                pass
        return
    
    if data == "main_menu":
        await event.answer()
        if event.chat_id in task_states:
            del task_states[event.chat_id]
        await show_menu(event, user_id, edit_msg=event.message)
        return
    
    await event.answer()
    
    if data == "add":
        await event.edit(style_text("ADD ACCOUNT"), buttons=[
            [Button.inline(style_text("PHONE"), b"add_phone")],
            [Button.inline(style_text("SESSION"), b"add_string")],
            [Button.inline(style_text("🔙 BACK"), b"back")]
        ])
        return
    
    if data == "add_phone":
        task_states[event.chat_id] = {'type': 'login', 'step': 'phone'}
        await event.edit(style_text("📱 Send phone number\nExample: +1234567890"), buttons=get_cancel())
        return
    
    if data == "add_string":
        task_states[event.chat_id] = {'type': 'login', 'step': 'string'}
        await event.edit(style_text("🔑 Send Telethon session string"), buttons=get_cancel())
        return
    
    if data == "join":
        if not active_clients:
            return await event.respond(style_text("❌ No accounts!"))
        task_states[event.chat_id] = {'type': 'join', 'step': 'link'}
        await event.edit(style_text("🔗 Send links (one per line, max 50)"), buttons=get_cancel())
        return
    
    if data == "join_vc":
        if not active_clients:
            return await event.respond(style_text("❌ No accounts!"))
        task_states[event.chat_id] = {'type': 'vc_join', 'step': 'link'}
        await event.edit(style_text("🎙️ Send Voice Chat Link or Channel Username/Invite Link:"), buttons=get_cancel())
        return
    
    if data == "leave_vc":
        if not active_clients:
            return await event.respond(style_text("❌ No accounts!"))
        await event.edit(style_text("🎙️ LEAVING ALL VOICE CHATS..."))
        await execute_vc_leave(event)
        return
    
    if data.startswith("vc_qty_"):
        if event.chat_id not in task_states:
            return await event.answer(style_text("Session expired. Please start again."), alert=True)
        qty = data.replace("vc_qty_", "")
        total = len(active_clients)
        if qty == "custom":
            task_states[event.chat_id]['step'] = 'custom_qty'
            await event.edit(style_text(f"🔢 Enter number of accounts to use:\n(1-{total})"), buttons=get_cancel())
            return
        elif qty == "all":
            count = total
        else:
            count = int(qty)
            if count > total:
                count = total
        vc_link = task_states[event.chat_id].get('vc_link')
        if vc_link:
            await event.delete()
            await execute_vc_join(event, vc_link, count)
        return
    
    if data == "react_view":
        if not active_clients:
            return await event.respond(style_text("❌ No accounts!"))
        task_states[event.chat_id] = {'type': 'react_view', 'step': 'link'}
        await event.edit(style_text("🔗 Send post link(s) (one per line, max 50)"), buttons=get_cancel())
        return
    
    if data == "multi_react":
        if not active_clients:
            return await event.respond(style_text("❌ No accounts!"))
        task_states[event.chat_id] = {'type': 'multi_react', 'step': 'link'}
        await event.edit(style_text("🔗 Send post link(s) (one per line, max 50)"), buttons=get_cancel())
        return
    
    if data == "views_menu":
        await event.edit(style_text("👁️ VIEWS OPTIONS"), buttons=[
            [Button.inline(style_text("SINGLE POST"), b"views_single")],
            [Button.inline(style_text("BATCH POSTS"), b"views_batch")],
            [Button.inline(style_text("🔙 BACK"), b"back")]
        ])
        return
    
    if data == "views_single":
        if not active_clients:
            return await event.respond(style_text("❌ No accounts!"))
        task_states[event.chat_id] = {'type': 'views', 'subtype': 'single', 'step': 'link'}
        await event.edit(style_text("🔗 Send Telegram post link\n\n✅ Valid formats:\n• https://t.me/username/123\n• https://t.me/c/123456789/123"), 
                         buttons=get_cancel())
        return
    
    if data == "views_batch":
        if not active_clients:
            return await event.respond(style_text("❌ No accounts!"))
        task_states[event.chat_id] = {'type': 'views', 'subtype': 'batch', 'step': 'links'}
        await event.edit(style_text("📚 Send multiple post links (one per line, max 20)"), 
                         buttons=get_cancel())
        return
    
    if data.startswith("views_qty_"):
        if event.chat_id not in task_states:
            return await event.answer(style_text("Session expired. Please start again."), alert=True)
        qty = data.replace("views_qty_", "")
        total = len(active_clients)
        if qty == "custom":
            task_states[event.chat_id]['step'] = 'custom_qty'
            await event.edit(style_text(f"🔢 Enter number of accounts to use:\n(1-{total})"), buttons=get_cancel())
            return
        elif qty == "all":
            count = total
        else:
            count = int(qty)
            if count > total:
                count = total
        post_link = task_states[event.chat_id].get('post_link')
        if post_link:
            await event.delete()
            await execute_views(event, post_link, count)
        return
    
    if data.startswith("qty_"):
        if event.chat_id not in task_states:
            return await event.answer(style_text("Session expired. Please start again."), alert=True)
        state = task_states[event.chat_id]
        qty = data.split("_")[1]
        total = len(active_clients)
        if qty == "custom":
            state['step'] = 'custom_qty'
            await event.edit(style_text("🔢 Enter number of accounts"), buttons=get_cancel())
            return
        count = total if qty == "all" else int(qty) if qty.isdigit() else total
        if count > total:
            count = total
        await event.delete()
        if state['type'] == 'join':
            await execute_join(event, state, count)
        elif state['type'] == 'react_view':
            await execute_react_view(event, state, count)
        elif state['type'] == 'multi_react':
            await execute_multi_react_view(event, state, count)
        return
    
    if data == "leave":
        await event.edit(style_text("LEAVE CHAT"), buttons=[
            [Button.inline(style_text("LEAVE ONE"), b"leave_specific")],
            [Button.inline(style_text("LEAVE ALL"), b"leave_all")],
            [Button.inline(style_text("🔙 BACK"), b"back")]
        ])
        return
    
    if data == "leave_specific":
        task_states[event.chat_id] = {'type': 'leave_specific', 'step': 'link'}
        await event.edit(style_text("📤 Send channel link to leave"), buttons=get_cancel())
        return
    
    if data == "leave_all":
        await event.edit(style_text("DANGER ZONE\nLeave ALL channels?\nAre you sure?"), buttons=[
            [Button.inline(style_text("CONFIRM"), b"exec_leave_all")],
            [Button.inline(style_text("CANCEL"), b"back")]
        ])
        return
    
    if data == "exec_leave_all":
        await event.edit(style_text("⚠️ PROCESSING..."))
        await execute_leave_all(event)
        return
    
    if data == "list_accounts":
        sessions = await get_all_sessions()
        if not sessions:
            await event.edit(style_text("📋 No accounts found."), buttons=[[Button.inline(style_text("🔙 BACK"), b"back")]])
            return
        msg = style_text("📋 SAVED ACCOUNTS\n━━━━━━━━━━━━━━━━\n")
        for i, (phone, _) in enumerate(sessions.items(), 1):
            status = "🟢" if phone in active_clients else "🔴"
            mode = "SMART_MIXED"
            msg += f"{i}. {status} {phone} ({mode})\n"
        await event.edit(msg, buttons=[[Button.inline(style_text("🔙 BACK"), b"back")]])
        return
    
    if data == "approve":
        if user_id not in OWNER_IDS:
            return await event.respond(style_text("Owner only!"))
        buttons = [
            [Button.inline(style_text("ADD ADMIN"), b"btn_add_admin"), Button.inline(style_text("REMOVE ADMIN"), b"btn_remove_admin")],
            [Button.inline(style_text("🔙 BACK"), b"back")]
        ]
        await event.edit(style_text("👑 USER MANAGEMENT PANEL\n━━━━━━━━━━━━━━━━\nSelect an action below or use commands directly:\n\n• /add <username/userid>\n• /remove <username/userid>\n• /list"), buttons=buttons)
        return
    
    if data == "btn_add_admin":
        if user_id not in OWNER_IDS:
            return await event.respond(style_text("Owner only!"))
        task_states[event.chat_id] = {'type': 'admin_manage', 'action': 'add'}
        await event.edit(style_text("👤 Send Telegram User ID or @Username to Add Admin:"), buttons=get_cancel())
        return
    
    if data == "btn_remove_admin":
        if user_id not in OWNER_IDS:
            return await event.respond(style_text("Owner only!"))
        task_states[event.chat_id] = {'type': 'admin_manage', 'action': 'remove'}
        await event.edit(style_text("👤 Send Telegram User ID or @Username to Remove Admin:"), buttons=get_cancel())
        return
    
    if data == "stats":
        if user_id not in OWNER_IDS:
            return await event.respond(style_text("Owner only!"))
        users = await get_approved_users()
        today_joins = await get_today_joins()
        uptime = get_uptime()
        msg = style_text(f"📊 STATISTICS\n━━━━━━━━━━━━━━━━\n◎ Approved: {len(users)}\n◎ Accounts: {len(active_clients)}\n  - Status Strategy: SMART MIXED (Natural Jitter)\n◎ Active VC Monitors: {len(VC_MONITORS)}\n◎ Today Joins: {today_joins}\n◎ Uptime: {uptime}")
        await event.edit(msg, buttons=[[Button.inline(style_text("🔙 BACK"), b"back")]])
        return

# ======================= MESSAGE HANDLER =======================
@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    if not await is_user_approved(user_id):
        return
    chat_id = event.chat_id
    if chat_id not in task_states:
        return
    state = task_states[chat_id]
    if state.get('running'):
        return
    text = event.raw_text.strip()
    
    if state.get('type') == 'admin_manage':
        action = state.get('action')
        uid, username_str, title = await resolve_user(bot, text)
        if not uid:
            return await event.respond(style_text("⚠️ User not found! Please send a valid User ID or Username."), buttons=get_cancel())
        if action == 'add':
            if await approve_user(uid, user_id, username=username_str, title=title):
                await event.respond(style_text(f"✅ User {title} ({uid}) approved successfully as Admin!"))
            else:
                await event.respond(style_text(f"❌ Failed to approve user {title}."))
        elif action == 'remove':
            if await unapprove_user(uid):
                await event.respond(style_text(f"❌ User {title} ({uid}) removed successfully!"))
            else:
                await event.respond(style_text(f"⚠️ User {title} not found in approved list."))
        del task_states[chat_id]
        await show_menu(event, user_id)
        return
    
    if state.get('type') == 'login':
        if state['step'] == 'phone':
            phone = text.replace(" ", "")
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            try:
                send = await client.send_code_request(phone)
                state.update({'client': client, 'phone': phone, 'hash': send.phone_code_hash, 'step': 'otp'})
                await event.respond(style_text(f"📩 OTP sent to {phone}\nEnter code:"), buttons=get_cancel())
            except Exception as e:
                await event.respond(style_text(f"❌ Error: {e}"), buttons=get_cancel())
        elif state['step'] == 'otp':
            try:
                await state['client'].sign_in(phone=state['phone'], code=text, phone_code_hash=state['hash'])
                await add_session(state['phone'], state['client'].session.save())
                active_clients[state['phone']] = state['client']
                account_modes[state['phone']] = "SMART_MIXED"
                next_random_toggle[state['phone']] = time.time() + random.randint(10, 300)
                asyncio.create_task(keep_alive(state['client'], state['phone']))
                trigger_temp_online(state['phone'], duration_seconds=90)
                del task_states[chat_id]
                await event.respond(style_text(f"✅ Added: {state['phone']}"))
                await show_menu(event, user_id)
            except SessionPasswordNeededError:
                state['step'] = '2fa'
                await event.respond(style_text("🔐 Enter 2FA password:"), buttons=get_cancel())
            except Exception as e:
                await event.respond(style_text(f"❌ Failed: {e}"), buttons=get_cancel())
        elif state['step'] == '2fa':
            try:
                await state['client'].sign_in(password=text)
                await add_session(state['phone'], state['client'].session.save())
                active_clients[state['phone']] = state['client']
                account_modes[state['phone']] = "SMART_MIXED"
                next_random_toggle[state['phone']] = time.time() + random.randint(10, 300)
                asyncio.create_task(keep_alive(state['client'], state['phone']))
                trigger_temp_online(state['phone'], duration_seconds=90)
                del task_states[chat_id]
                await event.respond(style_text(f"✅ Added: {state['phone']} (2FA saved)"))
                await show_menu(event, user_id)
            except Exception as e:
                await event.respond(style_text(f"❌ Wrong password: {e}"), buttons=get_cancel())
        elif state['step'] == 'string':
            try:
                client = TelegramClient(StringSession(text), API_ID, API_HASH)
                await client.connect()
                me = await client.get_me()
                phone = f"+{me.phone}" if me.phone else f"id_{me.id}"
                await add_session(phone, client.session.save())
                active_clients[phone] = client
                account_modes[phone] = "SMART_MIXED"
                next_random_toggle[phone] = time.time() + random.randint(10, 300)
                asyncio.create_task(keep_alive(client, phone))
                trigger_temp_online(phone, duration_seconds=90)
                del task_states[chat_id]
                await event.respond(style_text(f"✅ Added: {phone}"))
                await show_menu(event, user_id)
            except Exception as e:
                await event.respond(style_text(f"❌ Invalid session string: {e}"), buttons=get_cancel())
    
    elif state.get('type') == 'join':
        if state['step'] == 'link':
            links = text.strip().splitlines()
            valid = []
            for link in links:
                ltype, target = parse_target(link)
                if ltype:
                    valid.append({'link': link, 'type': ltype, 'target': target})
            if not valid:
                return await event.respond(style_text("❌ No valid links!"), buttons=get_cancel())
            if len(valid) > 50:
                return await event.respond(style_text("⚠️ Max 50 links!"), buttons=get_cancel())
            state['links_data'] = valid
            state['step'] = 'delay'
            await event.respond(style_text(f"✅ {len(valid)} links accepted\n⏱️ Enter delay (seconds):"), buttons=get_cancel())
        elif state['step'] == 'delay':
            if not text.isdigit():
                return await event.respond(style_text("⚠️ Numbers only!"), buttons=get_cancel())
            state['delay'] = int(text)
            state['step'] = 'qty'
            await event.respond(style_text(f"👥 Total accounts: {len(active_clients)}\nSelect quantity:"), buttons=get_qty_buttons())
        elif state['step'] == 'custom_qty':
            if not text.isdigit():
                return await event.respond(style_text("⚠️ Numbers only!"), buttons=get_cancel())
            count = int(text)
            total = len(active_clients)
            if count > total:
                count = total
            await event.delete()
            await execute_join(event, state, count)
    
    elif state.get('type') == 'vc_join':
        if state['step'] == 'link':
            vc_link = text.strip()
            state['vc_link'] = vc_link
            state['step'] = 'qty'
            await event.respond(
                style_text(f"🎙️ Link received!\n\n👥 Total accounts: {len(active_clients)}\nHow many accounts to join Voice Chat?"),
                buttons=get_vc_qty_buttons()
            )
        elif state['step'] == 'custom_qty':
            if not text.isdigit():
                return await event.respond(style_text("⚠️ Numbers only!"), buttons=get_cancel())
            count = int(text)
            total = len(active_clients)
            if count > total:
                count = total
            vc_link = state.get('vc_link')
            await event.delete()
            if vc_link:
                await execute_vc_join(event, vc_link, count)
    
    elif state.get('type') in ('react_view', 'multi_react'):
        if state['step'] == 'link':
            links = text.strip().splitlines()
            valid = []
            for link in links:
                ltype, target = parse_target(link)
                if ltype and ('t.me/' in link):
                    valid.append({'link': link, 'type': ltype, 'target': target})
            if not valid:
                return await event.respond(style_text("❌ No valid links!"), buttons=get_cancel())
            if len(valid) > 50:
                return await event.respond(style_text("⚠️ Max 50 links!"), buttons=get_cancel())
            state['links_data'] = valid
            state['step'] = 'emoji'
            if state['type'] == 'react_view':
                await event.respond(style_text("😀 Enter one emoji (e.g. ❤️):"), buttons=get_cancel())
            else:
                await event.respond(style_text("🔥 Enter multiple emojis, separated by commas (e.g. ❤️,🔥,👍):"), buttons=get_cancel())
        elif state['step'] == 'emoji':
            if state['type'] == 'react_view':
                emoji = text.strip()
                if len(emoji) == 0:
                    return await event.respond(style_text("⚠️ Please provide an emoji."), buttons=get_cancel())
                state['emoji'] = emoji
            else:
                emojis = [e.strip() for e in text.split(',') if e.strip()]
                if not emojis:
                    return await event.respond(style_text("⚠️ Please provide at least one emoji."), buttons=get_cancel())
                state['emojis'] = emojis
            state['step'] = 'speed'
            await event.respond(style_text("⏱️ Enter delay between accounts (seconds, e.g. 0.2):"), buttons=get_cancel())
        elif state['step'] == 'speed':
            try:
                speed = float(text.replace(',', '.'))
                if speed < 0:
                    raise ValueError
            except Exception:
                return await event.respond(style_text("⚠️ Enter a valid number (e.g. 0.2)."), buttons=get_cancel())
            state['speed'] = speed
            state['step'] = 'qty'
            await event.respond(style_text(f"👥 Total accounts: {len(active_clients)}\nSelect quantity:"), buttons=get_qty_buttons())
        elif state['step'] == 'custom_qty':
            if not text.isdigit():
                return await event.respond(style_text("⚠️ Numbers only!"), buttons=get_cancel())
            count = int(text)
            total = len(active_clients)
            if count > total:
                count = total
            await event.delete()
            if state['type'] == 'react_view':
                await execute_react_view(event, state, count)
            else:
                await execute_multi_react_view(event, state, count)
    
    elif state.get('type') == 'views':
        if state.get('subtype') == 'single':
            if state['step'] == 'link':
                post_link = text.strip()
                if not re.search(r"t\.me/([a-zA-Z0-9_]+|\d+)/\d+", post_link) and not re.search(r"t\.me/c/\d+/\d+", post_link):
                    return await event.respond(style_text("❌ Invalid post link!\n\n✅ Valid formats:\n• https://t.me/username/123\n• https://t.me/c/123456789/123"), 
                                                buttons=get_cancel())
                state['post_link'] = post_link
                state['step'] = 'qty'
                await event.respond(style_text(f"✅ Post accepted!\n\n👥 Total accounts: {len(active_clients)}\n\nHow many accounts to use for views?"),
                                    buttons=get_views_qty_buttons())
        elif state.get('subtype') == 'batch':
            if state['step'] == 'links':
                links = text.strip().splitlines()
                valid_count = 0
                for link in links:
                    if re.search(r"t\.me/([a-zA-Z0-9_]+|\d+)/\d+", link) or re.search(r"t\.me/c/\d+/\d+", link):
                        valid_count += 1
                if valid_count == 0:
                    return await event.respond(style_text("❌ No valid links found!"), buttons=get_cancel())
                if valid_count > 20:
                    return await event.respond(style_text("⚠️ Max 20 posts allowed!"), buttons=get_cancel())
                await event.respond(style_text(f"✅ {valid_count} posts accepted!\n\n📤 Sending views from ALL {len(active_clients)} accounts..."))
                await execute_views_batch(event, text, len(active_clients))
        elif state['step'] == 'custom_qty':
            if not text.isdigit():
                return await event.respond(style_text("⚠️ Numbers only!"), buttons=get_cancel())
            count = int(text)
            total = len(active_clients)
            if count > total:
                count = total
            post_link = state.get('post_link')
            if post_link:
                await execute_views(event, post_link, count)
    
    elif state.get('type') == 'leave_specific':
        if state['step'] == 'link':
            del task_states[chat_id]  # Clean up before executing
            await execute_leave_specific(event, text)

# ======================= MAIN =======================
async def main():
    print("=" * 60)
    print("🤖 COMPLETE BOT (SMART MIXED + VC ENGINE INTEGRATED)")
    print("=" * 60)
    print("✅ Bot Token Loaded")
    print("✅ Using JSON File Storage (No MongoDB Required)")
    print(f"👑 Owners: {OWNER_IDS}")
    print("=" * 60)
    await start_saved_clients()
    print(f"✅ Active Accounts: {len(active_clients)}")
    print("✅ Bot Ready!")
    await bot.start(bot_token=BOT_TOKEN)
    await bot.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")