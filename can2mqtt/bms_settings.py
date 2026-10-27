"""
BMS settings read/write over CAN, exposed to MQTT and Home Assistant.

The BMS uses a multi-frame protocol for its user-configurable settings:
- Read: send 0x500 with data AA AA 02 00 FF FF FF FF; BMS responds with
  `frame_count` frames starting at `read_response_base` (e.g. 0x450..0x45A).
- Write: send `frame_count` frames starting at `write_base` (e.g. 0x410..0x41A)
  containing the full settings payload.

Because writes require the full payload, this module caches the most recent
read and only allows writes after a successful read has populated the cache.
"""

import logging
import math
import threading
import time

import can


class BmsSettings(can.Listener):
    def __init__(self, cfg, bus, client, fallback_unique_id_prefix):
        self.bus = bus
        self.client = client
        self.read_request_canid = _as_int(cfg.get("read_request_canid", "0x500"))
        self.read_request_data = bytes.fromhex(
            cfg.get("read_request_data", "AAAA0200FFFFFFFF").replace(" ", "")
        )
        self.read_response_base = _as_int(cfg.get("read_response_base", "0x450"))
        self.write_base = _as_int(cfg.get("write_base", "0x410"))
        self.frame_count = int(cfg.get("frame_count", 11))
        self.state_topic_prefix = cfg.get("state_topic_prefix", "bms/settings")
        self.command_topic_suffix = cfg.get("command_topic_suffix", "/set")
        self.refresh_topic = cfg.get("refresh_topic", "bms/settings/refresh")
        self.inter_frame_delay = float(cfg.get("inter_frame_delay_ms", 10)) / 1000.0
        self.assembly_timeout = float(cfg.get("assembly_timeout_s", 2.0))
        self.unique_id_prefix = cfg.get("unique_id_prefix", fallback_unique_id_prefix)

        self.settings = {}
        for name, entry in (cfg.get("settings") or {}).items():
            self.settings[name] = {
                "frame_offset": int(entry["frame_offset"]),
                "byte_offset": int(entry["byte_offset"]),
                "size": int(entry["size"]),
                "signed": bool(entry.get("signed", False)),
                "scale": float(entry.get("scale", 1.0)),
                "unit": entry.get("unit"),
                "min": entry.get("min"),
                "max": entry.get("max"),
                "step": entry.get("step"),
                "device_class": entry.get("device_class"),
                "friendly_name": entry.get("friendly_name", name),
                "read_only": bool(entry.get("read_only", False)),
            }

        self._lock = threading.Lock()
        self._raw_frames = [None] * self.frame_count
        self._first_frame_at = None
        self.cache = {}
        self.cache_ready = False

    # ------------------------------------------------------------------ CAN side

    def on_message_received(self, msg):
        idx = msg.arbitration_id - self.read_response_base
        if not (0 <= idx < self.frame_count):
            return
        with self._lock:
            now = time.monotonic()
            if self._first_frame_at is not None and now - self._first_frame_at > self.assembly_timeout:
                self._raw_frames = [None] * self.frame_count
                self._first_frame_at = None
            if all(f is None for f in self._raw_frames):
                self._first_frame_at = now
            self._raw_frames[idx] = bytes(msg.data).ljust(8, b"\x00")[:8]
            if all(f is not None for f in self._raw_frames):
                self._decode_and_publish_locked()
                self._first_frame_at = None

    def _decode_and_publish_locked(self):
        new_cache = {}
        for name, e in self.settings.items():
            frame = self._raw_frames[e["frame_offset"]]
            raw = int.from_bytes(
                frame[e["byte_offset"] : e["byte_offset"] + e["size"]],
                "big",
                signed=e["signed"],
            )
            new_cache[name] = raw * e["scale"]
        self.cache = new_cache
        self.cache_ready = True
        logging.info("BMS settings cache populated (%d entries)", len(new_cache))
        for name, value in new_cache.items():
            self._publish_state(name, value)

    def _publish_state(self, name, value):
        payload = _format_value(value, self.settings[name]["step"])
        self.client.publish(f"{self.state_topic_prefix}/{name}", payload, qos=0, retain=True)

    # ----------------------------------------------------------------- requests

    def request_read(self):
        with self._lock:
            self._raw_frames = [None] * self.frame_count
            self._first_frame_at = None
        try:
            self.bus.send(
                can.Message(
                    arbitration_id=self.read_request_canid,
                    data=self.read_request_data,
                    is_extended_id=False,
                )
            )
            logging.info(
                "Sent BMS settings read request to 0x%X", self.read_request_canid
            )
        except Exception as e:
            logging.error("Error sending BMS settings read request: %s", e)

    # ---------------------------------------------------------------- MQTT side

    def mqtt_subscriptions(self):
        yield f"{self.state_topic_prefix}/+{self.command_topic_suffix}"
        yield self.refresh_topic

    def handle_mqtt(self, topic, payload):
        if topic == self.refresh_topic:
            self.request_read()
            return True
        prefix = self.state_topic_prefix + "/"
        if topic.startswith(prefix) and topic.endswith(self.command_topic_suffix):
            name = topic[len(prefix) : -len(self.command_topic_suffix)]
            if name in self.settings:
                self._handle_write(name, payload)
                return True
        return False

    def _handle_write(self, name, payload):
        entry = self.settings[name]
        if entry["read_only"]:
            logging.warning("BMS settings: ignoring write to read-only setting %s", name)
            return
        try:
            value = float(payload.decode("utf-8").strip() if isinstance(payload, (bytes, bytearray)) else payload)
        except Exception as e:
            logging.error("BMS settings: cannot parse payload for %s: %r (%s)", name, payload, e)
            return

        if not self.cache_ready:
            logging.error(
                "BMS settings cache empty; dropping write to %s=%s (request a refresh first)",
                name, value,
            )
            return

        if entry["min"] is not None and value < entry["min"]:
            logging.error("BMS settings: %s=%s below min %s", name, value, entry["min"])
            return
        if entry["max"] is not None and value > entry["max"]:
            logging.error("BMS settings: %s=%s above max %s", name, value, entry["max"])
            return

        raw = round(value / entry["scale"])
        try:
            raw_bytes = raw.to_bytes(entry["size"], "big", signed=entry["signed"])
        except OverflowError as e:
            logging.error("BMS settings: %s=%s raw=%s does not fit %d-byte %s: %s",
                          name, value, raw, entry["size"],
                          "signed" if entry["signed"] else "unsigned", e)
            return

        with self._lock:
            self.cache[name] = value
            self._raw_frames[entry["frame_offset"]] = (
                self._raw_frames[entry["frame_offset"]][: entry["byte_offset"]]
                + raw_bytes
                + self._raw_frames[entry["frame_offset"]][entry["byte_offset"] + entry["size"] :]
            )
            frames_to_send = list(self._raw_frames)

        logging.info("BMS settings: writing %s=%s (raw=%s)", name, value, raw)
        for i, data in enumerate(frames_to_send):
            try:
                self.bus.send(
                    can.Message(
                        arbitration_id=self.write_base + i,
                        data=data,
                        is_extended_id=False,
                    )
                )
            except Exception as e:
                logging.error("Error sending BMS settings write frame 0x%X: %s",
                              self.write_base + i, e)
                return
            if self.inter_frame_delay > 0 and i < len(frames_to_send) - 1:
                time.sleep(self.inter_frame_delay)

        self._publish_state(name, value)

    # ------------------------------------------------------------- HA discovery

    def augment_ha_payload(self, ha_payload):
        if not ha_payload:
            return
        cmps = ha_payload.setdefault("cmps", {})
        for name, e in self.settings.items():
            component = {
                "p": "sensor" if e["read_only"] else "number",
                "name": e["friendly_name"],
                "state_topic": f"{self.state_topic_prefix}/{name}",
                "unique_id": f"{self.unique_id_prefix}-setting-{name}",
                "value_template": "{{ value }}",
            }
            if not e["read_only"]:
                component["command_topic"] = f"{self.state_topic_prefix}/{name}{self.command_topic_suffix}"
                if e["min"] is not None:
                    component["min"] = e["min"]
                if e["max"] is not None:
                    component["max"] = e["max"]
                if e["step"] is not None:
                    component["step"] = e["step"]
            if e["unit"]:
                component["unit_of_measurement"] = e["unit"]
            if e["device_class"]:
                component["device_class"] = e["device_class"]
            cmps[f"setting_{name}"] = component

        cmps["bms_settings_refresh"] = {
            "p": "button",
            "name": "Refresh BMS Settings",
            "command_topic": self.refresh_topic,
            "payload_press": "1",
            "unique_id": f"{self.unique_id_prefix}-settings-refresh",
            "icon": "mdi:refresh",
        }

    # ------------------------------------------------------------- can.Listener

    def stop(self):
        pass


def _as_int(v):
    if isinstance(v, int):
        return v
    return int(v, 0)


def _format_value(value, step):
    if isinstance(step, (int, float)) and 0 < step < 1:
        decimals = max(0, -int(round(math.log10(step))))
        return f"{value:.{decimals}f}"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"
