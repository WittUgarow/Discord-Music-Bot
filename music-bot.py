from googleapiclient.discovery import build

import discord
import html
from discord import app_commands
from yt_dlp import YoutubeDL
import asyncio
from pathlib import Path

import os
from dotenv import load_dotenv
import base64
import requests

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"

spotify_id = os.getenv("SPOTIFY_CLIENT_ID")
spotify_secret = os.getenv("SPOTIFY_SECRET")

def getSpotifyToken():
    credentials = f"{spotify_id}:{spotify_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()

    response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": "Basic " + encoded
        },
        data={
            "grant_type": "client_credentials"
        }
    )

    data = response.json()
    print(data)
    return data["access_token"]

def spotifySearch(search):
    spotifyToken = getSpotifyToken()
    url = "https://api.spotify.com/v1/search"
    params = {"q": search, "type": "track", "limit": 1, "market": "US"}
    headers = {"Authorization": "Bearer "+spotifyToken}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    title = data["tracks"]["items"][0]["name"]
    artist = data["tracks"]["items"][0]["artists"][0]["name"]
    return {"title": title, "artist": artist, "search": f"{title} by {artist}"}

youtube_api_key = os.getenv("YOUTUBE_API_KEY")
youtube = build("youtube", "v3", developerKey=youtube_api_key)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
MY_GUILD = discord.Object(id=os.getenv("DISCORD_GUILD_ID"))
players = {}

class MusicPlayer():
    def __init__(self, guild):
        self.guild = guild
        self.queue = []
        self.voice_client = None
        self.currentSong = None

    async def connect(self, channel):
        if self.voice_client is None:
            self.voice_client = await channel.connect()
        elif self.voice_client.channel != channel:
            await self.voice_client.move_to(channel)
        return f"Connect to Voice Channel!"

    async def addSongToQueue(self, song):
        self.queue.append(song)
        if self.currentSong is None:
            return await self.playNextInQueue() 
        else:
            return f"Added {song} to the queue"

    async def playNextInQueue(self):
        if len(self.queue) == 0:
            self.currentSong = None
            await self.stop()
            return

        self.currentSong = self.queue.pop(0)

        audio_source = discord.FFmpegPCMAudio(self.currentSong.path)

        self.voice_client.play(
            audio_source,
            after=self.songFinished
        )

        return f"Now playing {self.currentSong}"

    def songFinished(self, error):
        if error:
            print(f"Playback error: {error}")

        asyncio.run_coroutine_threadsafe(self.playNextInQueue(), client.loop)

    def pause(self):
        self.voice_client.pause()
        return f"Paused"

    def resume(self):
        self.voice_client.resume()
        return f"Resuming playback"


    def skip(self):
        if self.voice_client.is_playing():
                self.voice_client.stop()
                return "Skipped!"
        return "Nothing is playing!" 

    async def stop(self):
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
            self.queue = []

        self.currentSong = None
        return "Left!"

class MusicControls(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.primary)
    async def pause_button(self, interaction, button):
        if self.player.voice_client.is_playing():
            self.player.pause()
            button.label = "Resume"
        else:
            self.player.resume()
            button.label = "Pause"

        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction, button):
        message = self.player.skip()
        await interaction.response.send_message(message, ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.secondary)
    async def stop_button(self, interaction, button):
        await self.player.stop()
        await interaction.response.send_message("Stopped!", ephemeral=True)

class Song:
    def __init__(self, title, artist, path, url):
        self.title = title
        self.artist = artist
        self.path = path
        self.url = url

    def __repr__(self):
        return (f"{self.title} by {self.artist}")


def get_player(guild):
    if guild.id not in players:
        players[guild.id] = MusicPlayer(guild)

    return players[guild.id]


def findSongURL(search):
    request = youtube.search().list(
        part="snippet",
        q=search,
        type="video",
        maxResults=1
    )

    response = request.execute()
    # video_title = html.unescape(response['items'][0]['snippet']['title'])
    video_id = response['items'][0]['id']['videoId']
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    return video_url


def downloadURL(url):
    options = {
        "format": "bestaudio",
        "outtmpl": str(DOWNLOADS_DIR / "%(title)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }], 
    }
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename.rsplit(".", 1)[0] + ".mp3"

async def createSongObject(search):
    songData = spotifySearch(search)
    url = findSongURL(songData["search"])
    print(f"URL found: {url}")
    path = await asyncio.to_thread(downloadURL, url)
    print(f"Downloaded to: {path}")
    song = Song(songData["title"], songData["artist"], path, url)
    print(f"Song Object Created: {song}")
    return song

import atexit
import shutil

def clearDownloads():
    if not DOWNLOADS_DIR.exists():
        return

    for path in DOWNLOADS_DIR.iterdir():
        try:
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
        except Exception as e:
            print(f"Could not delete {path}: {e}")

@client.event
async def on_ready():
    tree.copy_global_to(guild=MY_GUILD)
    await tree.sync(guild=MY_GUILD)
    print(f'We have logged in as {client.user}')

@tree.command(name="play", description="Play a song/add it to the queue")
async def play(interaction: discord.Interaction, search: str):
    if not interaction.user.voice:
        return await interaction.response.send_message(
            "Join a voice channel first!"
        )

    await interaction.response.defer()
    player = get_player(interaction.guild)
    await player.connect(interaction.user.voice.channel)
    song = await createSongObject(search)
    await interaction.followup.send(f"Song: {song}")
    await player.addSongToQueue(song)
    view = MusicControls(player)
    await interaction.followup.send("Playing:", view=view)

@tree.command(name="queue", description="See the current song queue")
async def queue(interaction: discord.Interaction):
    if not interaction.user.voice:
        return await interaction.response.send_message("Join a voice channel first!")
    player = get_player(interaction.guild)
    string = f"**Currently playing**: {player.currentSong}\n"
    string += "**Queue:**\n"
    for i in range(len(player.queue)):
        string += f"{i+1}. {player.queue[i]}\n"
    await interaction.response.send_message(string)
 
@tree.command(name="remove", description="Remove a song from the queue")
async def remove(interaction: discord.Interaction, number: int):
    if not interaction.user.voice:
        return await interaction.response.send_message("Join a voice channel first!")
    player = get_player(interaction.guild)
    if number < 1 or number > len(player.queue):
        return await interaction.response.send_message(
            "Invalid queue number."
        )

    removedItem  = player.queue.pop(number-1)
    await interaction.response.send_message(f"Removed \"{removedItem}\" from queue")

@tree.command(name="clear", description="Clear the queue")
async def clear(interaction: discord.Interaction):
    if not interaction.user.voice:
        return await interaction.response.send_message("Join a voice channel first!")
    player = get_player(interaction.guild)
    player.queue = []
    await interaction.response.send_message(f"Queue cleared!")

atexit.register(clearDownloads)
bot_token = os.getenv("BOT_TOKEN")
client.run(bot_token)
