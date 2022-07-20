import os
import sys

name = "Discord Rich Presence for Plex"
version = "1.0.0"

plexClientID = "discord-rich-presence-plex"
discordClientID = "999298904728285215"
configFilePath = "config.json"
cacheFilePath = "cache.json"

isUnix = sys.platform in ["linux", "darwin"]
processID = os.getpid()
