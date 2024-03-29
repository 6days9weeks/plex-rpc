# type: ignore

import hashlib
import threading
import time
import requests
import urllib.parse

from plexapi.alert import AlertListener
from plexapi.myplex import MyPlexAccount

from utils.logging import LoggerWithPrefix
from utils.text import formatSeconds

from .config import config
from .DiscordRpcService import DiscordRpcService


class PlexAlertListener(threading.Thread):

    productName = "Plex Media Server"
    updateTimeoutTimerInterval = 30
    connectionTimeoutTimerInterval = 60
    maximumIgnores = 2

    def __init__(self, token, serverConfig):
        super().__init__()
        self.daemon = True
        self.token = token
        self.serverConfig = serverConfig
        self.logger = LoggerWithPrefix(
            f"[{self.serverConfig['name']}/{hashlib.md5(str(id(self)).encode('UTF-8')).hexdigest()[:5].upper()}] "
        )
        self.discordRpcService = DiscordRpcService()
        self.updateTimeoutTimer = None
        self.connectionTimeoutTimer = None
        self.IMAGES_URL = requests.get("https://hiumee.github.io/kodi/images_url").text.strip()
        self.reset()
        self.start()

    def reset(self):
        self.plexAccount = None
        self.listenForUser = ""
        self.plexServer = None
        self.isServerOwner = False
        self.plexAlertListener = None
        self.lastState = ""
        self.lastSessionKey = 0
        self.lastRatingKey = 0
        self.ignoreCount = 0

    def run(self):
        connected = False
        while not connected:
            try:
                self.plexAccount = MyPlexAccount(token=self.token)
                self.logger.info('Signed in as Plex User "%s"', self.plexAccount.username)
                self.listenForUser = self.serverConfig.get(
                    "listenForUser", self.plexAccount.username
                )
                self.plexServer = None
                for resource in self.plexAccount.resources():
                    if (
                        resource.product == self.productName
                        and resource.name.lower() == self.serverConfig["name"].lower()
                    ):
                        self.logger.info(
                            'Connecting to %s "%s"', self.productName, self.serverConfig["name"]
                        )
                        self.plexServer = resource.connect()
                        try:
                            self.plexServer.account()
                            self.isServerOwner = True
                        except:
                            pass
                        self.logger.info('Connected to %s "%s"', self.productName, resource.name)
                        self.plexAlertListener = AlertListener(
                            self.plexServer, self.handlePlexAlert, self.reconnect
                        )
                        self.plexAlertListener.start()
                        self.logger.info('Listening for alerts from user "%s"', self.listenForUser)
                        self.connectionTimeoutTimer = threading.Timer(
                            self.connectionTimeoutTimerInterval, self.connectionTimeout
                        )
                        self.connectionTimeoutTimer.start()
                        connected = True
                        break
                if not self.plexServer:
                    self.logger.error(
                        '%s "%s" not found', self.productName, self.serverConfig["name"]
                    )
                    break
            except Exception as e:
                self.logger.error(
                    'Failed to connect to %s "%s": %s',
                    self.productName,
                    self.serverConfig["name"],
                    e,
                )
                self.logger.error("Reconnecting in 10 seconds")
                time.sleep(10)

    def disconnect(self):
        self.discordRpcService.disconnect()
        self.cancelTimers()
        try:
            self.plexAlertListener.stop()
        except:
            pass
        self.reset()
        self.logger.info("Stopped listening for alerts")

    def reconnect(self, exception):
        self.logger.error("Connection to Plex lost: %s", exception)
        self.disconnect()
        self.logger.error("Reconnecting")
        self.run()

    def cancelTimers(self):
        if self.updateTimeoutTimer:
            self.updateTimeoutTimer.cancel()
            self.updateTimeoutTimer = None
        if self.connectionTimeoutTimer:
            self.connectionTimeoutTimer.cancel()
            self.connectionTimeoutTimer = None

    def updateTimeout(self):
        self.logger.debug("No recent updates from session key %s", self.lastSessionKey)
        self.discordRpcService.disconnect()
        self.cancelTimers()

    def connectionTimeout(self):
        try:
            self.logger.debug(
                "Request for list of clients to check connection: %s", self.plexServer.clients()
            )
        except Exception as e:
            self.reconnect(e)
        else:
            self.connectionTimeoutTimer = threading.Timer(
                self.connectionTimeoutTimerInterval, self.connectionTimeout
            )
            self.connectionTimeoutTimer.start()

    def handlePlexAlert(self, data):
        try:
            if data["type"] == "playing" and "PlaySessionStateNotification" in data:
                alert = data["PlaySessionStateNotification"][0]
                state = alert["state"]
                sessionKey = int(alert["sessionKey"])
                ratingKey = int(alert["ratingKey"])
                viewOffset = int(alert["viewOffset"])
                self.logger.debug("Received alert: %s", alert)
                item = self.plexServer.fetchItem(ratingKey)
                libraryName = item.section().title
                if (
                    "blacklistedLibraries" in self.serverConfig
                    and libraryName in self.serverConfig["blacklistedLibraries"]
                ):
                    self.logger.debug('Library "%s" is blacklisted, ignoring', libraryName)
                    return
                if (
                    "whitelistedLibraries" in self.serverConfig
                    and libraryName not in self.serverConfig["whitelistedLibraries"]
                ):
                    self.logger.debug('Library "%s" is not whitelisted, ignoring', libraryName)
                    return
                if self.lastSessionKey == sessionKey and self.lastRatingKey == ratingKey:
                    if self.updateTimeoutTimer:
                        self.updateTimeoutTimer.cancel()
                        self.updateTimeoutTimer = None
                    if self.lastState == state and self.ignoreCount < self.maximumIgnores:
                        self.logger.debug("Nothing changed, ignoring")
                        self.ignoreCount += 1
                        self.updateTimeoutTimer = threading.Timer(
                            self.updateTimeoutTimerInterval, self.updateTimeout
                        )
                        self.updateTimeoutTimer.start()
                        return
                    else:
                        self.ignoreCount = 0
                        if state == "stopped":
                            self.lastState, self.lastSessionKey, self.lastRatingKey = (
                                None,
                                None,
                                None,
                            )
                            self.discordRpcService.disconnect()
                            self.cancelTimers()
                            return
                elif state == "stopped":
                    self.logger.debug(
                        'Received "stopped" state alert from unknown session key, ignoring'
                    )
                    return
                if self.isServerOwner:
                    self.logger.debug("Searching sessions for session key %s", sessionKey)
                    plexServerSessions = self.plexServer.sessions()
                    if len(plexServerSessions) < 1:
                        self.logger.debug("Empty session list, ignoring")
                        return
                    for session in plexServerSessions:
                        self.logger.debug(
                            "%s, Session Key: %s, Usernames: %s",
                            session,
                            session.sessionKey,
                            session.usernames,
                        )
                        if session.sessionKey == sessionKey:
                            self.logger.debug("Session found")
                            sessionUsername = session.usernames[0]
                            if sessionUsername.lower() == self.listenForUser.lower():
                                self.logger.debug(
                                    'Username "%s" matches "%s", continuing',
                                    sessionUsername,
                                    self.listenForUser,
                                )
                                break
                            self.logger.debug(
                                'Username "%s" doesn\'t match "%s", ignoring',
                                sessionUsername,
                                self.listenForUser,
                            )
                            return
                    else:
                        self.logger.debug("No matching session found, ignoring")
                        return
                if self.updateTimeoutTimer:
                    self.updateTimeoutTimer.cancel()
                self.updateTimeoutTimer = threading.Timer(
                    self.updateTimeoutTimerInterval, self.updateTimeout
                )
                self.updateTimeoutTimer.start()
                self.lastState, self.lastSessionKey, self.lastRatingKey = (
                    state,
                    sessionKey,
                    ratingKey,
                )
                if state != "playing":
                    stateText = f"{formatSeconds(viewOffset / 1000, ':')} / {formatSeconds(item.duration / 1000, ':')}"
                else:
                    stateText = formatSeconds(item.duration / 1000)
                mediaType = item.type
                thumbUrl = None
                if mediaType == "movie":
                    title = f"{item.title} ({item.year})"
                    if len(item.genres) > 0:
                        stateText += f" · {', '.join(genre.tag for genre in item.genres[:3])}"
                    largeText = "Watching a movie"
                    thumbUrl = self.IMAGES_URL + "?name=" + urllib.parse.quote(title) + "&type=movie"
                elif mediaType == "episode":
                    title = item.grandparentTitle
                    stateText += f" · S{item.parentIndex:02}E{item.index:02} - {item.title}"
                    largeText = "Watching a TV show"
                    thumbUrl = self.IMAGES_URL + "?name=" + urllib.parse.quote(title) + "&type=tv"
                elif mediaType == "track":
                    title = item.title
                    artist = item.originalTitle
                    if not artist:
                        artist = item.grandparentTitle
                    stateText = f"{artist} - {item.parentTitle}"
                    largeText = "Listening to music"
                else:
                    self.logger.debug('Unsupported media type "%s", ignoring', mediaType)
                    return
                
                if thumbUrl is None:
                    thumbUrl = self.IMAGES_URL + "?name=" + urllib.parse.quote(title)

                activity = {
                    "details": title[:128],
                    "state": stateText[:128],
                    "assets": {
                        "large_text": largeText,
                        "large_image": thumbUrl,
                        "small_text": state.capitalize(),
                        "small_image": state,
                    },
                    "type": 3 if mediaType in ["movie", "episode"] else 2,
                }
                if state == "playing":
                    currentTimestamp = int(time.time())
                    if config["display"]["useRemainingTime"]:
                        activity["timestamps"] = {
                            "end": round(currentTimestamp + ((item.duration - viewOffset) / 1000))
                        }
                    else:
                        activity["timestamps"] = {
                            "start": round(currentTimestamp - (viewOffset / 1000))
                        }
                if not self.discordRpcService.connected:
                    self.discordRpcService.connect()
                if self.discordRpcService.connected:
                    self.discordRpcService.sendActivity(activity)
        except:
            self.logger.exception("An unexpected error occured in the alert handler")
