import os
import time
import psutil
import discord
import configparser
import traceback 

from gpiozero import CPUTemperature
from mcstatus import MinecraftServer
from discord.ext import tasks, commands
from itertools import cycle
from subprocess import check_output
from dotenv import load_dotenv

# Read configuration settings
config = configparser.ConfigParser()
config.read('settings.ini')

# Start Defining Settings
TOKEN = config['SETTINGS']['bot_token']
minutes_until_shutdown = int(config['SETTINGS']['minutes_until_shutdown'])
server_address = config['SETTINGS']['server_address']
service_to_restart = config['SETTINGS']['service_to_restart']

# Start initializing variables
load_dotenv()

client = discord.Client() # Start the discord client
server = MinecraftServer.lookup(server_address) # Set the server's address

startingTime = time.time() # Log the starting time

minutesWithoutPlayers = -1 # Track how many minutes with no players
serverOffline = False # Boolean showing if the server is offline

# Runs when the bot is connected
@client.event
async def on_ready():
    change_status.start() # Start the timer that changes the discord status
    check_for_shutdown.start() # Starts the loop that checks if a shutdown is needed
    print(f'{client.user} has connected to Discord!')
    
# Checks if a shutdown is needed, runs every 60 seconds
@tasks.loop(seconds=60)
async def check_for_shutdown():
    print("Checking if there are no players...")

    global minutesWithoutPlayers
    global serverOffline

    # If the server is already offline return
    if serverOffline:
        print("Server already offline!")
        minutesWithoutPlayers = 0
        return

    try:
        query = server.query() # Query the server, throws an exception if servers offline
        currentOnline = query.players.online # Fetch the current amount of players
        print(f"Players found: {currentOnline}")

        if currentOnline == 0:
            # No ones online, increment the player count and check for shutdown
            minutesWithoutPlayers = minutesWithoutPlayers + 1
            print(f"No players online!...(Minutes at {minutesWithoutPlayers})")

            if minutesWithoutPlayers >= minutes_until_shutdown:
                # If we hit the number of minutes with no players, shut it down
                print("Shutting down...")

                pid = check_output(["pidof", "java"]).decode("utf-8").replace('\n', '') # Fetch the PID of the java instance
                print("Attempting to kill process: " + pid)

                os.system('kill ' + pid) # Kill the process, needs root
                print("Server was shutdown")

                minutesWithoutPlayers = 0 # Reset the minutes
        
        else:
            minutesWithoutPlayers = 0 # Reset the timer if there's players online

    except Exception:
        # Server is offline
        traceback.print_exc()
        print("Server already offline!")
        serverOffline = True
        minutesWithoutPlayers = 0

# Checks for a status. If the server's offline set the status to reflect that, otherwise, display that it's offline
@tasks.loop(seconds=10)
async def change_status():

    global serverOffline

    try:
        query = server.query() # Query the server
        currentOnline = query.players.online # Check for number of players online
        maxOnline = query.players.max # Set the max amount of players online
        serverOffline = False

        await client.change_presence(status=discord.Status.online, activity=discord.Game(f"Players Online: {currentOnline} / {maxOnline}"))
    except Exception:
        # Server is offline
        serverOffline = True
        await client.change_presence(status=discord.Status.online, activity=discord.Game(f"Server is Offline: Use /start to start it!"))

# On message received
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    elif message.content == '/ping':
        channel = message.channel
        await channel.send('pong')

    elif message.content == '/status':
        channel = message.channel

        serverOnline = True # Variable to track if the server's online

        # Collect information on the server, this fails if it's offline
        try:
            if (serverOffline):
                serverOnline = False

            else:
                server = MinecraftServer.lookup(server_address) # Fetch the server address, will fail if it's offline

                query = server.query()
                latency = server.ping()

        except Exception:
            serverOnline = False # Server is offline

        embedVar = None # Create the embed var

        # Check if the server is online, then print online or offline
        if (serverOnline):
            embedVar = discord.Embed(title="Minecraft Server Status", description="The Server is Online", color=0x00ff00)
        else:
            embedVar = discord.Embed(title="Minecraft Server Status", description="The Server is Offline", color=0xff0000)

        # Embed the thumbnail if it exists
        file = discord.File("/var/opt/minecraft/server/server-icon.png")
        embedVar.set_thumbnail(url="attachment://server-icon.png")

        # Print server statistics if the server is online
        if (serverOnline):
            playersOnline = "{0}".format(", ".join(query.players.names))
            embedVar.add_field(name="Server Ping", value=f"Replied in {latency} ms", inline=False)
            embedVar.add_field(name="Players Online", value="- {0}".format("\n- ".join(query.players.names)), inline=False)

        # Print out some hardware info

        try:
            cpu = CPUTemperature()
            cpuUsage = psutil.cpu_percent()
            ramUsage = psutil.virtual_memory().percent

            embedVar.add_field(name="CPU Usage", value=f"Usage: {cpuUsage}%", inline=False)
            embedVar.add_field(name="RAM Usage", value=f"{ramUsage}%", inline=False)
            embedVar.add_field(name="CPU Temperature", value=f"{cpu.temperature}°C", inline=False)
        except Exception:
            print("Could not get hardware stats due to not running as root")

        # Add the uptime field
        embedVar.add_field(name="Bot Uptime", value=f"{int((time.time() - startingTime) / 60)} minutes", inline=False)

        # Print the message
        await channel.send(file=file, embed=embedVar)

    elif message.content == '/start':
        # Only allow starting if the servers offline
        if not serverOffline:
            await channel.send('The server is already online!')
            return

        channel = message.channel
        print("Attempting to restart...")

        # Start the server
        await channel.send('Server is starting up, it will be ready in 3-5 minutes...')
        time.sleep(1)
        os.system(f'systemctl restart {service_to_restart}')
        
client.run(TOKEN)
