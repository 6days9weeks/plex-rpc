
The script must be running on the same machine as your Discord client.


## Installation 

1. `cd <path to directory>`
2. `python3 -m pip install -U -r requirements.txt`
3. `python3 bot.py`

When the script runs for the first time, you have to follow the on screen prompt for connecting to your Plex account, and a `config.json` file will automatically be created in the same directory.


`logging` = (list)
`debug` = (boolean) `true` or `false` - extra logging information
`useRemainingTime` = (boolean) true or flase - Displays your media's remaining time instead of elapsed time in your Rich Presence if enabled.)
`users` = (list)
`token` = (string) - Access token associated with your Plex account.
`servers` = (list)
`name` = (string) - Name of the Plex Media Server.
`listenForUser` (string) [optional] - Finds a session for a specific user like a managed user or shared user. (Defaults to the account username if not set.)
`blacklistedLibraries` (list, optional) - Ignores a session that thats found with this library name.
`whitelistedLibraries` (list, optional) - Only finds a session that thats found with this library name.

EXAMPLE: config.json

```json
{
  "logging": {
    "debug": true
  },
  "display": {
    "useRemainingTime": false,
  "users": [
    {
      "token": "HPbrz2NhfLRjU888Rrdt",
      "servers": [
        {
          "name": "Plex 'N Chill"
        },
        {
          "name": "PlexUser123",
          "listenForUser": "John",
          "whitelistedLibraries": ["Movies"],
          "blacklistedLibraries": ["TV Shows"]
        }
      ]
    }
  ]
}