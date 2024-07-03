import os
import asyncio
import json
from telethon import TelegramClient, errors
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty, Channel, ChannelParticipantsRecent, ChatBannedRights
from telethon.tl.functions.channels import InviteToChannelRequest, GetParticipantsRequest, EditBannedRequest
from telethon.errors import UserPrivacyRestrictedError, FloodWaitError, ChatAdminRequiredError
from dotenv import load_dotenv

load_dotenv()

api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
phone_number = os.getenv('PHONE_NUMBER')

client = TelegramClient('session_name', api_id, api_hash)
groups_file = 'groups.json'


async def get_active_groups():
    await client.start(phone_number)

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
        print("Initial group list saved.")
        return

    with open(groups_file, 'r') as f:
        previous_groups = json.load(f)

    new_groups = {gid: details for gid, details in current_groups.items() if str(gid) not in previous_groups}

    if new_groups:
        print(f"New groups detected: {len(new_groups)}")
        print('-' * 30)
        for gid, details in new_groups.items():
            print(f"Title: {details['title']}")
            print(f"Username: {details['username']}")
            print('-' * 30)
    else:
        print("No new groups detected.")

    with open(groups_file, 'w') as f:
        json.dump(current_groups, f, indent=4)


async def invite_user_to_groups(user_username, group_usernames):
    await client.start(phone_number)

    try:
        user = await client.get_entity(f'@{user_username}')
        print(f"Found user by username: {user.id}")
    except ValueError as e:
        print(f"Cannot find user by username: {user_username}. Error: {e}")
        return

    for group_username in group_usernames:
        try:
            group = await client.get_entity(f'@{group_username}')
            print(f"Found group/channel: {group.id}")
            await client(InviteToChannelRequest(group, [user]))
            print(f"Invited {user_username} to {group_username}")
            participants = await client(GetParticipantsRequest(
                channel=group,
                filter=ChannelParticipantsRecent(),
                offset=0,
                limit=100,
                hash=0
            ))

            user_in_group = any(participant.user_id == user.id for participant in participants.participants)
            if user_in_group:
                print(f"{user_username} successfully joined {group_username}")
            else:
                print(f"{user_username} did not join {group_username}")
        except UserPrivacyRestrictedError:
            print(f"Cannot invite {user_username} to {group_username} due to privacy settings.")
        except FloodWaitError as e:
            print(f"Flood wait error. Waiting for {e.seconds} seconds.")
            await asyncio.sleep(e.seconds)
        except ChatAdminRequiredError:
            print(f"Cannot invite {user_username} to {group_username}. Account lacks admin privileges.")
        except Exception as e:
            print(f"An error occurred: {e}")

        await asyncio.sleep(30)


async def remove_user_from_group(user_username, group_username):
    await client.start(phone_number)

    try:
        user = await client.get_entity(f'@{user_username}')
        print(f"Found user by username: {user.id}")
    except ValueError as e:
        print(f"Cannot find user by username: {user_username}. Error: {e}")
        return

    try:
        group = await client.get_entity(f'@{group_username}')
        print(f"Found group/channel: {group.id}")
        banned_rights = ChatBannedRights(until_date=None, view_messages=True)
        await client(EditBannedRequest(channel=group, participant=user, banned_rights=banned_rights))
        print(f"Removed {user_username} from {group_username}")
    except UserPrivacyRestrictedError:
        print(f"Cannot remove {user_username} from {group_username} due to privacy settings.")
    except FloodWaitError as e:
        print(f"Flood wait error. Waiting for {e.seconds} seconds.")
        await asyncio.sleep(e.seconds)
    except ChatAdminRequiredError:
        print(f"Cannot remove {user_username} from {group_username}. Account lacks admin privileges.")
    except Exception as e:
        print(f"An error occurred: {e}")

    await asyncio.sleep(30)


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python script.py <mode> [args]")
        print("Modes: get_groups | invite_user <user_username> <group_username1> <group_username2> ... | remove_user <user_username> <group_username>")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == 'get_groups':
        asyncio.run(get_active_groups())
    elif mode == 'invite_user' and len(sys.argv) >= 4:
        user_username = sys.argv[2]
        group_usernames = sys.argv[3:]
        asyncio.run(invite_user_to_groups(user_username, group_usernames))
    elif mode == 'remove_user' and len(sys.argv) == 4:
        user_username = sys.argv[2]
        group_username = sys.argv[3]
        asyncio.run(remove_user_from_group(user_username, group_username))
    else:
        print("Invalid mode or arguments")
