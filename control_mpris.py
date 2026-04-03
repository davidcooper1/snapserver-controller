#!/usr/bin/env python3

import json
import logging
import sys
import threading
import weakref

from gi.repository import Playerctl, GLib

log_level = logging.INFO
logger = logging.getLogger("control_mpris")
logger.propagate = False
log_handler = logging.StreamHandler()
log_handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)s: %(message)s"))
logger.addHandler(log_handler)
logger.setLevel(log_level)

def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

class MprisControl:
    def __init__(self):
        self._properties = {
            "playbackStatus": "stopped",
            "shuffle": False,
            "loopStatus": "none",
            "volume": 100,
            "mute": False,
            "position": 0.0,
            "canGoNext": True,
            "canGoPrevious": True,
            "canPlay": True,
            "canPause": True,
            "canSeek": True,
            "canControl": True,
            "metadata": {
                "title": "",
                "artist": [],
                "album": "",
                "duration": 0.0,
            },
        }

        self._player = None

    def set_player(self, player):
        self._player = weakref(player)
        player.connect('metadata', self.on_metadata)
        player.connect('playback_status', self.on_playback_status)

    def on_metadata(self, player, metadata):
        self._properties["metadata"].update({
            "title": metadata.get("xesam:title", ""),
            "artist": metadata.get("xesam:artist", ""),
            "album": metadata.get("xesam:album", ""),
            "duration": metadata.get("mpris:length", 0) / 1000000.0,
        })
        self.send_update()

    def on_playback_status(self, player, playback_status):
        if playback_status == "playing":
            self._properties["playbackStatus"] = "playing"
        elif playback_status == "paused":
            self._properties["playbackStatus"] = "paused"
        elif playback_status == "stopped":
            self._properites["playbackStatus"] = "stopped"
        self.send_update()

    def send_update(self):
        self._properties["position"] = self._player.get_position() / 1000000.0
        send({
            "jsonrpc": "2.0",
            "method": "Plugin.Stream.Player.Properties",
            "params": self._properties
        })

    def control(self, cmd):
        if not cmd:
            return
        try:
            req = json.loads(cmd)
            method = req.get("method", "")
            id_ = req.get("id")

            if method.endswith(".Control"):
                action = req["params"].get("command", "")
                logger.debug(f"Control command: {action}")

                if action == "play":
                    self._player.play()
                elif action == "pause":
                    self._player.pause()
                elif action == "playPause":
                    self._player.play_pause()

                elif action == "previous":
                    self._player.previous()

                elif action == "next":
                    self._player.next()

                elif action == "setPosition":
                    pos = float(req["params"].get(
                        "params", {}).get("position", 0))
                    self._player.set_position(int(pos * 1000000))

                elif action == "seek":
                    pos = float(req["params"].get(
                        "params", {}).get("offset", 0))
                    self._player.seek(int(pos * 1000000))

                # ack
                if id_ is not None:
                    send({"jsonrpc": "2.0", "result": "ok", "id": id_})

            elif method.endswith(".GetProperties"):
                send({"jsonrpc": "2.0", "id": id_, "result": self._properties})

            elif method.endswith(".SetProperty"):
                # We keep Spotify volume fixed; ignore for now.
                if id_ is not None:
                    send({"jsonrpc": "2.0", "id": id_, "result": "ok"})

        except Exception as e:
            logger.debug(f"Error processing command: {e}")




cntrl = MprisControl()
manager = Playerctl.PlayerManager()

def init_player(name):
    player = Playerctl.Player.new_from_name(name)
    cntrl.set_player(player)
    manager.manage_player(player)

def on_name_appeared(manager, name):
    init_player(name)

manager.connect('name-appeared', on_name_appeared)

for name in manager.props.player_names:
    init_player(name)

loop = GLib.MainLoop()

def run_loop():
    logger.debug("Starting GLib loop in background thread...")
    loop.run()
    logger.debug("GLib loop stopped.")

thread = threading.Thread(target=run_loop)
thread.daemon = True
thread.start()

if __name__ == "__main__":
    try:
        for line in sys.stdin:
            cntrl.control(line)
    except KeyboardInterrupt:
        exit()