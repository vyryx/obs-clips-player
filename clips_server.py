import asyncio
import websockets
import http.server
import socketserver
import os
import json
import re
import configparser
import requests
import random
import subprocess
from threading import Thread
from mute_application import mute_applications

def log_message(level, message):
    """Log a message based on the log level."""
    if level <= LOG_LEVEL:
        print(message)

config = configparser.ConfigParser()
config.read("resources.ini")

CLIENT_ID = config.get("Twitch", "CLIENT_ID", fallback="")
CLIENT_SECRET = config.get("Twitch", "CLIENT_SECRET", fallback="")
BROADCASTER_NAME = config.get("Twitch", "BROADCASTER_NAME", fallback="vyrx22")
CHAT_COMMAND = config.get("Twitch", "CHAT_COMMAND", fallback="!show")
DIRECTORY = config.get("Server", "DIRECTORY", fallback="./")
PORT = config.getint("Server", "PORT", fallback=8000)
PLAYER_APP_NAMES = config.get("General", "PLAYER_APP_NAMES", fallback="firefox.exe,librewolf.exe").split(",")
AUTHORIZED_USERS = config.get("General", "AUTHORIZED_USERS", fallback="vyrx22").split(",")

try:
    COMMAND_COOLDOWN = int(config.get("Twitch", "COMMAND_COOLDOWN", fallback="30"))
    LOG_LEVEL = int(config.get("General", "LOG_LEVEL", fallback="1"))  # 0: Errors only, 1: Normal, 2: Debug
except Exception as e:
    print(f"Error parsing from configuration: {e}")
    COMMAND_COOLDOWN = 30
    LOG_LEVEL = 1 

connected_clients = set()

last_command_time = 0

muting_enabled = True

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

async def fetch_oauth_token():
    """Fetch OAuth token from Twitch."""
    url = 'https://id.twitch.tv/oauth2/token'
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'client_credentials'
    }
    response = requests.post(url, data=data)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch OAuth token: {response.text}")
    return response.json()['access_token']

async def get_broadcaster_id(channel_name, token):
    """Get broadcaster ID by channel name."""
    url = f"https://api.twitch.tv/helix/users?login={channel_name}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Client-Id": CLIENT_ID
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch broadcaster ID: {response.text}")
    data = response.json()
    if data["data"] and len(data["data"]) > 0:
        return data["data"][0]["id"]
    else:
        raise Exception(f"Broadcaster not found: {channel_name}")

async def get_random_clip(broadcaster_id, token):
    """Fetch a random clip for the specified broadcaster."""
    url = f"https://api.twitch.tv/helix/clips?broadcaster_id={broadcaster_id}&first=100"
    headers = {
        "Authorization": f"Bearer {token}",
        "Client-Id": CLIENT_ID
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch clips: {response.text}")
    data = response.json()
    if "data" in data and len(data["data"]) > 0:
        clip = random.choice(data["data"])
        log_message(2, f"Selected clip: {clip}")
        return clip["url"]
    else:
        raise Exception("No clips found for this broadcaster.")

def download_clip_with_twitch_dl(clip_url, save_path):
    """Download the clip using twitch-dl."""
    try:
        command = [
            "twitch-dl",
            "download",
            clip_url,
            "-o", save_path,
            "--overwrite",
            "-q", "360"
        ]
        log_message(2, f"Running command: {' '.join(command)}")
        subprocess.run(command, check=True)
        log_message(1, f"Clip downloaded and saved to {save_path}")
        return save_path
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to download clip: {e}")

async def websocket_handler(websocket):
    """Handle WebSocket connections with the player."""
    log_message(1, "WebSocket client connected")
    connected_clients.add(websocket)
    log_message(2, f"Connected clients: {len(connected_clients)}")
    try:
        async for message in websocket:
            log_message(2, f"Received message from client: {message}")
            try:
                data = json.loads(message)
                if data.get("command") == "clip_finished":
                    log_message(1, f"Clip finished playing. Unmuting players...")
                    if muting_enabled:
                        mute_applications(PLAYER_APP_NAMES, mute=False)
            except json.JSONDecodeError:
                log_message(0, f"Invalid message format: {message}")
    except websockets.exceptions.ConnectionClosed as e:
        log_message(1, f"WebSocket connection closed: {e}")
    finally:
        connected_clients.remove(websocket)
        log_message(2, f"WebSocket client disconnected. Remaining clients: {len(connected_clients)}")

async def send_socket_message(debug_message):
    """Send a message to all connected WebSocket clients."""
    if connected_clients:
        message = json.dumps(debug_message)
        log_message(2, f"Sending debug message to {len(connected_clients)} clients: {message}")
        try:
            # Wrap client.send(message) in asyncio.create_task()
            tasks = [asyncio.create_task(client.send(message)) for client in connected_clients]
            await asyncio.gather(*tasks)  # Wait for all tasks to complete
        except Exception as e:
            log_message(0, f"Error sending debug message: {e}")
    else:
        log_message(1, "No connected clients to send debug message to.")

async def handle_command(command, args, username, ws, token):
    """Handle chat commands."""
    global last_command_time, muting_enabled
    cooldown_seconds = 30  # Set the global cooldown period in seconds

    if command == CHAT_COMMAND:  # !play command
        # Check if the user is authorized to bypass cooldown
        current_time = asyncio.get_event_loop().time()
        if username not in AUTHORIZED_USERS and current_time - last_command_time < cooldown_seconds:
            remaining_time = cooldown_seconds - (current_time - last_command_time)
            log_message(1, f"Command '{CHAT_COMMAND}' is on cooldown for {remaining_time:.1f} seconds.")
            message = {"command": "info", "payload": f"cooldown {remaining_time:.1f} @{username}"}
            await send_socket_message(message)
            return

        # Update the last execution time for the command
        last_command_time = current_time

        channel_name = args[0] if args else None
        if not channel_name:
            log_message(0, "No channel name provided for !play command.")
            return

        log_message(1, f"Play command received for channel: {channel_name}")
        try:
            # Delete cached files if they exist
            cached_clip_path = os.path.join(DIRECTORY, "cached_clip.mp4")
            cached_tmp_path = os.path.join(DIRECTORY, "cached_clip.mp4.tmp")
            if os.path.exists(cached_clip_path):
                os.remove(cached_clip_path)
                log_message(2, f"Deleted cached clip: {cached_clip_path}")
            if os.path.exists(cached_tmp_path):
                os.remove(cached_tmp_path)
                log_message(2, f"Deleted temporary cached clip: {cached_tmp_path}")

            broadcaster_id = await get_broadcaster_id(channel_name, token)
            clip_url = await get_random_clip(broadcaster_id, token)
            log_message(2, f"Fetched random clip URL: {clip_url}")
            message = {"command": "info", "payload": f"looking for {channel_name}..."}
            await send_socket_message(message)

            download_clip_with_twitch_dl(clip_url, cached_clip_path)

            await asyncio.sleep(1)

            if os.path.exists(cached_clip_path):
                log_message(1, f"Clip successfully downloaded: {cached_clip_path}")
                if muting_enabled:
                    log_message(1, "Muting Players...")
                    mute_applications(PLAYER_APP_NAMES, mute=True)
                
                message = {"command": "play_clip", "payload": f"{channel_name}"}
                await send_socket_message(message)
            else:
                log_message(0, f"Clip download failed: {cached_clip_path}")

                if muting_enabled:
                    mute_applications(PLAYER_APP_NAMES, mute=False)
        except Exception as e:
            message = {"command": "error", "payload": f"no clip for {channel_name}"}
            await send_socket_message(message)
            log_message(0, f"Error fetching or downloading clip: {e}")

            if muting_enabled:
                mute_applications(PLAYER_APP_NAMES, mute=False)

    elif command == "!skip":  # Skip the current clip
        if username in AUTHORIZED_USERS:
            log_message(1, f"Skip command received from {username}.")
            # Send a message to the WebSocket client to stop playback
            message = {"command": "skip_clip"}
            await send_socket_message(message)
        else:
            log_message(0, f"Unauthorized user '{username}' tried to use !skip command.")

    elif command == "!mute":  # Toggle muting
        if username in AUTHORIZED_USERS:
            muting_enabled = not muting_enabled
            log_message(1, f"Muting toggled to {'enabled' if muting_enabled else 'disabled'} by {username}.")
            message = {"command": "info", "payload": f"muting {'enabled' if muting_enabled else 'disabled'}"}
            await send_socket_message(message)
        else:
            log_message(0, f"Unauthorized user '{username}' tried to use !mute command.")

    elif command == "!vol":  # !volume command
        if username not in AUTHORIZED_USERS:
            log_message(0, f"Unauthorized user '{username}' tried to use !volume command.")
            return

        if not args or not args[0].isdigit() or not (0 <= int(args[0]) <= 100):
            log_message(0, f"Invalid volume value provided by {username}.")
            return

        volume = int(args[0])
        log_message(1, f"Volume command received from {username}: {volume}")
        # Send the volume command to the WebSocket client
        message = {"command": "volume", "payload": volume}
        await send_socket_message(message)

async def twitch_chat_reader():
    """Connect to Twitch chat and listen for commands."""
    token = await fetch_oauth_token()
    uri = "wss://irc-ws.chat.twitch.tv:443"
    async with websockets.connect(uri) as ws:
        await ws.send("PASS SCHMOOPIIE")
        await ws.send("NICK justinfan12345")  # Anonymous
        await ws.send(f"JOIN #{BROADCASTER_NAME}")
        log_message(1, "Connected to Twitch IRC")

        async for message in ws:
            log_message(2, f"Raw Message: {message}")
            if message.startswith("PING"):
                await ws.send("PONG :tmi.twitch.tv")
                continue

            # Parse chat messages for commands
            match = re.search(r":(\w+)!\w+@\w+\.tmi\.twitch\.tv PRIVMSG #\w+ :!(\w+)\s*(.*)", message)
            if match:
                username = match.group(1)
                command = f"!{match.group(2)}"
                args = match.group(3).split() if match.group(3) else []
                log_message(1, f"Command received: {command} from {username} with args: {args}")
                await handle_command(command, args, username, ws, token)

async def start_websocket_server():
    """Start the WebSocket server."""
    log_message(1, "Initializing WebSocket server...")
    async with websockets.serve(websocket_handler, "localhost", 8765):
        log_message(1, "WebSocket server started on ws://localhost:8765")
        await asyncio.Future()  # Run forever

def start_http_server():
    """Start the HTTP server."""
    with socketserver.TCPServer(("", PORT), CustomHandler) as httpd:
        log_message(1, f"Serving files from {DIRECTORY} at http://localhost:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    # Start the HTTP server in a separate thread
    http_thread = Thread(target=start_http_server)
    http_thread.daemon = True
    http_thread.start()

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(asyncio.gather(
            start_websocket_server(),
            twitch_chat_reader()
        ))
    except KeyboardInterrupt:
        log_message(1, "Shutting down...")