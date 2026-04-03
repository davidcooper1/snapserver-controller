#!/usr/bin/env python3

import json
import logging
import sys
import threading
import weakref

import gi
gi.require_version('Playerctl', '2.0')
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

manager = Playerctl.PlayerManager()

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
        logger.info("New player registered")
        self._player = player
        player.connect('metadata', self.on_metadata, manager)
        player.connect('playback_status', self.on_playback_status, manager)

    def on_metadata(self, player, metadata, manager):
        logger.info("Metadata changed")
        self.send_update()

    def on_playback_status(self, player, playback_status, manager):
        logger.info(f"Playback Status Update: {playback_status}")
        if playback_status == Playerctl.PlaybackStatus.PLAYING:
            self._properties["playbackStatus"] = "playing"
        elif playback_status == Playerctl.PlaybackStatus.PAUSED:
            self._properties["playbackStatus"] = "paused"
        elif playback_status == Playerctl.PlaybackStatus.STOPPED:
            self._properites["playbackStatus"] = "stopped"
        self.send_update()

    def send_update(self):
        if (self._player is not None):
            metadata = self._player.props.metadata
            if (metadata is not None):
                keys = metadata.keys()
                self._properties["metadata"].update({
                    "title": metadata["xesam:title"] if "xesam:title" in keys else "",
                    "artist": metadata["xesam:artist"] if "xesam:artist" in keys else [],
                    "album": metadata["xesam:album"] if "xesam:album" in keys else "",
                    "duration": (metadata["mpris:length"] if "mpris:length" in keys else 0) / 1000000.0
                });
            self._properties["position"] = self._player.get_position() / 1000000.0
        send({
            "jsonrpc": "2.0",
            "method": "Plugin.Stream.Player.Properties",
            "params": self._properties
        })

    def control(self, cmd):
        logger.info(f"Command from IPC: {cmd}")
        if not cmd:
            return
        try:
            req = json.loads(cmd)
            method = req.get("method", "")
            id_ = req.get("id")

            if method.endswith(".Control"):
                action = req["params"].get("command", "")
                logger.info(f"Control command: {action}")

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
            logger.info(f"Error processing command: {e}")




cntrl = MprisControl()

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

def run_input_loop():
    logger.info("Doing stdin loop")
    try:
        for line in sys.stdin:
                cntrl.control(line)
    except KeyboardInterrupt:
        exit()

thread = threading.Thread(target=run_input_loop)
thread.daemon = True
thread.start()

cntrl.send_update()
send({"jsonrpc": "2.0", "method": "Plugin.Stream.Ready"})

loop.run()