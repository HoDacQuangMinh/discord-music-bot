import discord
from discord.ext import commands
import asyncio
import yt_dlp
import os
import aiohttp
import random
from datetime import datetime, timezone, timedelta
from typing import Optional

# config
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-:%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

# Paste the full path to your ffmpeg.exe file here, using a raw string
FFMPEG_PATH = r'C:\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe'

# Create an 'uploads' directory if it doesn't exist
if not os.path.exists('./uploads'):
    os.makedirs('./uploads')

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
ytdl_cache = {}


# music player
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url')

    @classmethod
    async def from_data(cls, data):
        filename = data['url']
        return cls(discord.FFmpegPCMAudio(filename, executable=FFMPEG_PATH, **FFMPEG_OPTIONS), data=data)


class LocalSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, file_path, volume=0.5):
        super().__init__(source, volume)
        self.title = os.path.basename(file_path)
        self.url = None

    @classmethod
    async def from_file(cls, file_path):
        return cls(discord.FFmpegPCMAudio(file_path, executable=FFMPEG_PATH), file_path=file_path)


# setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Data storage (in-memory)
music_queues = {}
disconnect_tasks = {}
loop_states = {}
user_balances = {}
daily_claims = {}


# helper
def check_queue(ctx):
    guild_id = ctx.guild.id
    if guild_id in loop_states:
        loop_mode = loop_states[guild_id]
        if ctx.voice_client and ctx.voice_client.source:
            source = ctx.voice_client.source
            if loop_mode == 'ONE':
                music_queues[guild_id].insert(0, source)
            elif loop_mode == 'ALL':
                music_queues[guild_id].append(source)

    if guild_id in music_queues and music_queues[guild_id]:
        queue = music_queues[guild_id]
        if ctx.voice_client and not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
            source = queue.pop(0)
            ctx.voice_client.play(source,
                                  after=lambda e: check_queue(ctx) if e is None else print(f'Player error: {e}'))
            embed = discord.Embed(
                title="📻 On The Radio",
                description=f"Haha, yes! Simply lovely! Now playing: **[{source.title}]({source.url if source.url else 'Local File'})**",
                color=discord.Color.dark_blue()
            )
            asyncio.run_coroutine_threadsafe(ctx.send(embed=embed), bot.loop)


# commands
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('Max Verstappen is ready to go P1!')


@bot.event  # leave when only bot in room after 3min
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id: return
    voice_client = member.guild.voice_client
    if not voice_client: return
    guild_id = voice_client.guild.id
    channel = voice_client.channel
    if len(channel.members) > 1:
        if guild_id in disconnect_tasks:
            disconnect_tasks[guild_id].cancel()
            del disconnect_tasks[guild_id]
    elif len(channel.members) == 1:
        if guild_id not in disconnect_tasks:
            async def disconnect_after_delay():
                await asyncio.sleep(180)
                if voice_client.is_connected() and len(channel.members) == 1:
                    await voice_client.disconnect()
                    if guild_id in music_queues: del music_queues[guild_id]
                    if guild_id in loop_states: del loop_states[guild_id]
                    text_channel = discord.utils.get(member.guild.text_channels, name='general') or \
                                   member.guild.text_channels[0]
                    await text_channel.send("Looks like everyone left. I'm not sitting here by myself. Boxing.")
                if guild_id in disconnect_tasks: del disconnect_tasks[guild_id]

            disconnect_tasks[guild_id] = bot.loop.create_task(disconnect_after_delay())


@bot.command()  # balance
async def balance(ctx):
    user_id = ctx.author.id
    balance = user_balances.get(user_id, 0)
    await ctx.send(f"{ctx.author.mention}, you have **{balance} MV**. Let's see you use it.")


@bot.command()  # claim
async def claim(ctx):
    user_id = ctx.author.id
    now = datetime.now(timezone.utc)

    if user_id in daily_claims and now - daily_claims[user_id] < timedelta(hours=24):
        time_left = timedelta(hours=24) - (now - daily_claims[user_id])
        hours, remainder = divmod(time_left.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return await ctx.send(f"Stop being greedy. You have to wait another **{hours}h {minutes}m**.")

    amount = 250
    user_balances[user_id] = user_balances.get(user_id, 0) + amount
    daily_claims[user_id] = now
    await ctx.send(f"Alright, here's your sponsor money. You get **{amount} MV**. Don't waste it.")


@bot.command()  # coinflip
async def coinflip(ctx, amount: int, choice: str):
    user_id = ctx.author.id
    balance = user_balances.get(user_id, 0)
    choice = choice.lower()

    if amount <= 0:
        return await ctx.send("Don't be stupid. Bet a real amount.")
    if balance < amount:
        return await ctx.send(f"You don't have enough MV for that, mate. Your balance is **{balance} MV**.")
    if choice not in ['heads', 'tails']:
        return await ctx.send("It's a coinflip. Pick 'heads' or 'tails', it's not complicated.")

    result = random.choice(['heads', 'tails'])

    await ctx.send("Okay, full send... The coin is in the air...")
    await asyncio.sleep(2)

    if choice == result:
        user_balances[user_id] += amount
        await ctx.send(
            f"It's **{result.capitalize()}**! Haha, yes! Simply lovely! You win **{amount} MV**. Your new balance is **{user_balances[user_id]} MV**.")
    else:
        user_balances[user_id] -= amount
        await ctx.send(
            f"It's **{result.capitalize()}**! Unlucky, mate. You lose **{amount} MV**. Your new balance is **{user_balances[user_id]} MV**.")


@bot.command()  # add mv (admin only)
async def addmv(ctx, member: discord.Member, amount: int):
    # This new check is more reliable
    if not (ctx.author.guild_permissions.administrator or ctx.author == ctx.guild.owner):
        return await ctx.send("You're not the team principal. You can't use this command.")

    if amount <= 0:
        return await ctx.send("You have to add a positive amount, mate.")

    user_id = member.id
    user_balances[user_id] = user_balances.get(user_id, 0) + amount
    await ctx.send(
        f"Okay, I've given **{amount} MV** to {member.mention}. Their new balance is **{user_balances[user_id]} MV**.")


@bot.command()  # schedule
async def schedule(ctx):
    async with ctx.typing():
        current_year = datetime.now().year
        url = f"https://api.openf1.org/v1/sessions?year={current_year}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return await ctx.send("The FIA is playing games. Couldn't get the schedule right now.")
                all_sessions = await response.json()

        now = datetime.now(timezone.utc)

        # Find the first upcoming session of any kind to identify the next race weekend
        future_sessions = sorted([s for s in all_sessions if datetime.fromisoformat(s['date_start']) > now],
                                 key=lambda x: x['date_start'])

        if not future_sessions:
            return await ctx.send("The season's over, mate. We won. Time for a break.")

        next_event_session = future_sessions[0]
        next_meeting_key = next_event_session['meeting_key']

        # Now, find the actual "Race" session for that specific weekend
        next_race_session = None
        for session in all_sessions:
            if session['meeting_key'] == next_meeting_key and session['session_name'] == 'Race':
                next_race_session = session
                break

        # If the "Race" session isn't listed yet, fall back to the first available session of the weekend
        if next_race_session is None:
            next_race_session = next_event_session

        race_name = next_race_session['meeting_name']
        circuit_name = next_race_session['circuit_short_name']
        race_location = next_race_session['country_name']
        race_time = datetime.fromisoformat(next_race_session['date_start'])

        countdown = race_time - now
        days, rem = divmod(countdown.total_seconds(), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        countdown_str = f"{int(days)}d {int(hours)}h {int(minutes)}m {int(secs)}s"

        embed = discord.Embed(title=f"Lights Out: {race_name}", color=0xFF1801)
        embed.add_field(name="Circuit", value=circuit_name.title(), inline=False)
        embed.add_field(name="Location", value=race_location, inline=False)
        embed.add_field(name=f"Next Session: {next_race_session['session_name']}",
                        value=f"<t:{int(race_time.timestamp())}:F>", inline=False)
        embed.add_field(name="Countdown", value=f"**{countdown_str}**", inline=False)
        embed.set_footer(text="Let's go for the win. Full send.")

        await ctx.send(embed=embed)


@bot.command()  # join room
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send(f"Are you going to get in the car or what? A 4-time world champion doesn't wait around.")
    channel = ctx.author.voice.channel
    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    await ctx.send(f"Okay, I'm in. Let's see what this car can do: **{channel}**!")


@bot.command()  # add playlist/single music
async def play(ctx, *, search: str):
    if ctx.voice_client is None: await ctx.invoke(bot.get_command('join'))
    async with ctx.typing():
        try:
            if search in ytdl_cache:
                data = ytdl_cache[search]
            else:
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search, download=False))
                ytdl_cache[search] = data
            if ctx.guild.id not in music_queues: music_queues[ctx.guild.id] = []
            if 'entries' in data and len(data['entries']) > 1:
                playlist_entries = data['entries']
                await ctx.send(
                    f"A whole playlist? Okay, let's see what the strategy is. Adding {len(playlist_entries)} points to the board.")
                for entry in playlist_entries:
                    player = await YTDLSource.from_data(entry)
                    music_queues[ctx.guild.id].append(player)
                await ctx.send(
                    f"Right, the full strategy is on the board. {len(playlist_entries)} points in the queue. Let's see if it's any good.")
            else:
                song_data = data['entries'][0] if 'entries' in data else data
                player = await YTDLSource.from_data(song_data)
                music_queues[ctx.guild.id].append(player)
                await ctx.send(f"Copy. Added to the queue: **{player.title}**")
            if not ctx.voice_client.is_playing(): check_queue(ctx)
        except Exception as e:
            await ctx.send(f"Absolute disaster! What the fuck was that? My engineer could do better. Try again.")
            print(f"Error in play command: {e}")


@bot.command()  # upload files from computer
async def upload(ctx):
    if not ctx.message.attachments:
        return await ctx.send("You need to attach a file to upload, mate. I can't read your mind.")
    attachment = ctx.message.attachments[0]
    if not attachment.filename.lower().endswith(('.mp3', '.wav', '.flac', '.ogg')):
        return await ctx.send("This isn't a proper audio file. Give me an mp3, wav, or flac.")
    if ctx.voice_client is None: await ctx.invoke(bot.get_command('join'))
    async with ctx.typing():
        try:
            file_path = f'./uploads/{attachment.filename}'
            await attachment.save(file_path)
            player = await LocalSource.from_file(file_path)
            if ctx.guild.id not in music_queues: music_queues[ctx.guild.id] = []
            music_queues[ctx.guild.id].append(player)
            await ctx.send(f"Okay, your local file is in the queue: **{player.title}**")
            if not ctx.voice_client.is_playing(): check_queue(ctx)
        except Exception as e:
            await ctx.send("Something went wrong with the upload. The car is broken.")
            print(f"Error in upload command: {e}")


@bot.command()  # loop
async def loop(ctx):
    guild_id = ctx.guild.id
    current_mode = loop_states.get(guild_id)
    if current_mode is None:
        loop_states[guild_id] = 'ONE'
        await ctx.send("Okay, this one's good. Looping this single song.")
    elif current_mode == 'ONE':
        loop_states[guild_id] = 'ALL'
        await ctx.send("Alright, the whole strategy is good. Looping the entire queue.")
    elif current_mode == 'ALL':
        del loop_states[guild_id]
        await ctx.send("Looping is off. Back to the original plan.")


@bot.command()  # queue
async def queue(ctx):
    if ctx.guild.id in music_queues and music_queues[ctx.guild.id]:
        queue_list = music_queues[ctx.guild.id]
        embed = discord.Embed(title="Race Strategy", color=0x060070)
        if ctx.voice_client and ctx.voice_client.source:
            embed.add_field(name="Current Strategy",
                            value=f"[{ctx.voice_client.source.title}]({ctx.voice_client.source.url if ctx.voice_client.source.url else 'Local File'})",
                            inline=False)
        if not queue_list:
            embed.description = "The queue is empty. What are we doing here, just driving around? Give me some music."
        else:
            total_songs = len(queue_list)
            description = f"**Upcoming Strategy Points: {total_songs}**\n\n"
            for i, source in enumerate(queue_list[:10]):
                description += f"Strategy {i + 1}: {source.title}\n"
            if total_songs > 10:
                description += f"\n...and {total_songs - 10} more."
            embed.description = description
        await ctx.send(embed=embed)
    else:
        await ctx.send("The queue is empty. What are we doing here, just driving around? Give me some music.")


@bot.command()  # pause
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Okay, holding in the pit lane. Paused. Don't talk to me during the break.")
    else:
        await ctx.send("Nothing is playing, mate. The car is already in the garage.")


@bot.command()  # resume
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Okay, back on the throttle. Full send.")
    else:
        await ctx.send("Can't resume, we're already at full pace.")


@bot.command()  # skip
async def skip(ctx, to_skip: Optional[int] = None):
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        return await ctx.send("Nothing to skip, mate.")
    guild_id = ctx.guild.id
    if to_skip is None:
        if guild_id in loop_states and loop_states[guild_id] == 'ONE': del loop_states[guild_id]
        ctx.voice_client.stop()
        return await ctx.send("This one is shit. On to the next one. Full send.")
    queue = music_queues.get(guild_id)
    if not queue: return await ctx.send("The queue is empty, can't skip to a specific song.")
    if 1 <= to_skip <= len(queue):
        music_queues[guild_id] = queue[to_skip - 1:]
        if guild_id in loop_states and loop_states[guild_id] == 'ONE': del loop_states[guild_id]
        ctx.voice_client.stop()
        await ctx.send(
            f"Right, forget the current plan. We're jumping to Strategy {to_skip}. Let's see if this is any better.")
    else:
        await ctx.send(f"That's not a valid strategy point. Check the `!queue` and give me a proper number.")


@bot.command()  # stop
async def stop(ctx):
    guild_id = ctx.guild.id
    if guild_id in music_queues: music_queues[guild_id].clear()
    if guild_id in loop_states: del loop_states[guild_id]
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.send("Okay, box, box, box! This is a joke. Clearing the whole damn strategy.")
    else:
        await ctx.send("The car is already in the garage, mate.")


@bot.command()  # leave
async def leave(ctx):
    guild_id = ctx.guild.id
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        if guild_id in music_queues: del music_queues[guild_id]
        if guild_id in loop_states: del loop_states[guild_id]
        await ctx.send("This car is undriveable, I'm done. Bringing it back to the garage.")
    else:
        await ctx.send("I'm not on track, mate.")


@bot.command()  # clear cache
async def clearcache(ctx):
    global ytdl_cache
    ytdl_cache.clear()
    await ctx.send("Okay, I've cleared my head. The cache is empty.")


# run bot
bot.run('BOT TOKEN')
