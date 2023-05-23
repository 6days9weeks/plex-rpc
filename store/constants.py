import os
import sys

name = "Discord Rich Presence for Plex"
version = "1.0.1"

plexClientID = "discord-rich-presence-plex"
discordClientID = "977282085914021928"
configFilePath = "config.json"
cacheFilePath = "cache.json"

isUnix = sys.platform in ["linux", "darwin"]
processID = os.getpid()
