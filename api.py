import os
import json
import asyncio
import threading
from flask import Flask, request, jsonify
from telethon import TelegramClient, errors
from telethon.errors import UserPrivacyRestrictedError, FloodWaitError, ChatAdminRequiredError
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty, Channel, ChatBannedRights
from telethon.tl.functions.channels import InviteToChannelRequest, EditBannedRequest
# from telethon.sessions import StringSession
from dotenv import load_dotenv

load_dotenv()

api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
phone_number = os.getenv('PHONE_NUMBER')
session_file = 'session_name'
groups_file = 'groups.json'

app = Flask(__name__)

loop = asyncio.new_event_loop()
thread = threading.Thread(target=loop.run_forever)
thread.start()

client = None

async def initialize_telegram_client():
    global client
    if client:
        await client.disconnect()
    if os.path.exists(f'{session_file}.session'):
        os.remove(f'{session_file}.session')
    client = TelegramClient(session_file, api_id, api_hash)
    await client.connect()
    await client.send_code_request(phone_number)

asyncio.run_coroutine_threadsafe(initialize_telegram_client(), loop).result()

@app.route('/update_api_credentials', methods=['POST'])
def update_api_credentials():
    global api_id, api_hash, phone_number
    data = request.json
    api_id = data.get('api_id')
    api_hash = data.get('api_hash')
    phone_number = data.get('phone_number')

    if not all([api_id, api_hash, phone_number]):
        return jsonify({"error": "All fields (api_id, api_hash, phone_number) are required."}), 400

    os.environ['API_ID'] = api_id
    os.environ['API_HASH'] = api_hash
    os.environ['PHONE_NUMBER'] = phone_number

    future = asyncio.run_coroutine_threadsafe(initialize_telegram_client(), loop)
    future.result()

    return jsonify({"message": "API credentials updated and Telegram client reinitialized."})

@app.route('/input_code', methods=['POST'])
def input_code():
    data = request.json
    code = data.get('code')

    if not code:
        return jsonify({"error": "Code is required."}), 400

    async def complete_login():
        global client
        try:
            await client.sign_in(phone_number, code)
            return {"message": "Login successful."}
        except errors.SessionPasswordNeededError:
            return {"error": "Two-step verification enabled. Password needed."}
        except Exception as e:
            return {"error": str(e)}

    future = asyncio.run_coroutine_threadsafe(complete_login(), loop)
    result = future.result()
    return jsonify(result)

async def get_active_groups_inner():
    dialogs = await client(GetDialogsRequest(
        offset_date=None,
        offset_id=0,
        offset_peer=InputPeerEmpty(),
        limit=200,
        hash=0
    ))

    current_groups = {dialog.id: {
        'title': dialog.title,
        'username': dialog.username
    } for dialog in dialogs.chats if isinstance(dialog, Channel) and (dialog.megagroup or dialog.broadcast)}

    if not os.path.exists(groups_file):
        with open(groups_file, 'w') as f:
            json.dump(current_groups, f, indent=4)
        return {"message": "Initial group list saved."}

    with open(groups_file, 'r') as f:
        previous_groups = json.load(f)

    new_groups = {gid: details for gid, details in current_groups.items() if str(gid) not in previous_groups}

    response = {}
    if new_groups:
        response["new_groups_detected"] = len(new_groups)
        response["groups"] = new_groups
    else:
        response["message"] = "No new groups detected."

    with open(groups_file, 'w') as f:
        json.dump(current_groups, f, indent=4)

    return response

@app.route('/get_groups', methods=['GET'])
def get_active_groups():
    future = asyncio.run_coroutine_threadsafe(get_active_groups_inner(), loop)
    result = future.result()
    return jsonify(result)

async def invite_user_to_groups_inner(user_username, group_usernames):
    try:
        user = await client.get_entity(f'@{user_username}')
    except ValueError as e:
        return {"error": f"Cannot find user by username: {user_username}. Error: {e}"}, 400

    for group_username in group_usernames:
        try:
            group = await client.get_entity(f'@{group_username}')
            await client(InviteToChannelRequest(group, [user]))
            await asyncio.sleep(30)
        except UserPrivacyRestrictedError:
            return {"error": f"Cannot invite {user_username} to {group_username} due to privacy settings."}, 400
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except ChatAdminRequiredError:
            return {"error": f"Cannot invite {user_username} to {group_username}. Account lacks admin privileges."}, 400
        except Exception as e:
            return {"error": f"An error occurred: {e}"}, 500

    return {"message": f"User {user_username} invited to groups {group_usernames}"}

@app.route('/invite_user', methods=['POST'])
def invite_user_to_groups():
    data = request.json
    user_username = data['user_username']
    group_usernames = data['group_usernames']
    future = asyncio.run_coroutine_threadsafe(invite_user_to_groups_inner(user_username, group_usernames), loop)
    result = future.result()
    return jsonify(result)

async def remove_user_from_group_inner(user_username, group_usernames):
    try:
        user = await client.get_entity(f'@{user_username}')
    except ValueError as e:
        return {"error": f"Cannot find user by username: {user_username}. Error: {e}"}, 400

    for group_username in group_usernames:
        try:
            group = await client.get_entity(f'@{group_username}')
            banned_rights = ChatBannedRights(until_date=None, view_messages=True)
            await client(EditBannedRequest(channel=group, participant=user, banned_rights=banned_rights))
            await asyncio.sleep(30)  # Adding a delay of 30 seconds
        except UserPrivacyRestrictedError:
            return {"error": f"Cannot remove {user_username} from {group_username} due to privacy settings."}, 400
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except ChatAdminRequiredError:
            return {"error": f"Cannot remove {user_username} from {group_username}. Account lacks admin privileges."}, 400
        except Exception as e:
            return {"error": f"An error occurred: {e}"}, 500

    return {"message": f"User {user_username} removed from group {group_usernames}"}

@app.route('/remove_user', methods=['POST'])
def remove_user_from_group():
    data = request.json
    user_username = data['user_username']
    group_usernames = data['group_usernames']
    future = asyncio.run_coroutine_threadsafe(remove_user_from_group_inner(user_username, group_usernames), loop)
    result = future.result()
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
