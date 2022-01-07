#!/usr/bin/env python3

import argparse
import evdev
import logging
import os
import re
import selectors
import signal
import subprocess
import sys
import threading
import yaml

from copy import copy


def int_handler(sig, frame):
    os._exit(1)


class HidEventProcessor:
    def __init__(self, log, config, get_devices=True):
        self.log = log
        self.cache = []

        # Load config
        self.config = self.get_config(config)

        # Prepare selector
        self.selector = selectors.DefaultSelector()

        # Get devices
        if get_devices:
            self._get_devices_periodic()

    def _get_devices_periodic(self):
        self.get_devices()
        threading.Timer(5, self._get_devices_periodic).start()

    def get_config(self, filename):
        self.log.debug("Getting config...")

        try:
            with open(filename, "r") as stream:
                try:
                    data = yaml.safe_load(stream)
                except yaml.YAMLError as e:
                    raise Exception("cannot parse config file '%s': %s" % (filename, e))
        except IOError as e:
            raise Exception("cannot open file '%s': %s" % (filename, e))

        # Validate config
        if not isinstance(data, list):
            raise Exception("there is no configuration in the config file")
        else:
            for i, d in enumerate(data):
                if "device" not in d or not isinstance(d["device"], dict):
                    raise Exception(
                        "configuration #%d has no valid device block defined" % i
                    )
                if "keys" not in d or not isinstance(d["keys"], list):
                    raise Exception(
                        "configuration #%d has no valid keys block defined" % i
                    )

                    for j, k in enumerate(d["keys"]):
                        if not isinstance(k, dict):
                            raise Exception(
                                "key #%d in configuration #%d has no valid block defined"
                                % (j, i)
                            )

                        if "command" not in k and not (
                            isinstance(k["command"], list)
                            or isinstance(k["command"], str)
                        ):
                            raise Exception(
                                "key #%d in configuration #%d has no valid command defined"
                                % i
                            )

        return data

    def _value(self, value):
        if value < 0:
            value = value + 2 ** 32

        return "%x" % value

    def _is_device(self, device, config):
        if (
            (
                "vendor" not in config["device"]
                or device.info.vendor == config["device"]["vendor"]
                or config["device"]["vendor"] == "any"
            )
            and (
                "product" not in config["device"]
                or device.info.product == config["device"]["product"]
                or config["device"]["product"] == "any"
            )
            and (
                "version" not in config["device"]
                or device.info.version == config["device"]["version"]
                or config["device"]["version"] == "any"
            )
        ):
            return True
        else:
            return False

    def _is_key(self, event, config):
        for k in config["keys"]:
            if (
                ("code" not in k or event.code == k["code"] or k["code"] == "any")
                and ("type" not in k or event.type == k["type"] or k["type"] == "any")
                and (
                    "value" not in k
                    or self._value(event.value) == str(k["value"])
                    or k["value"] == "any"
                )
                and "command" in k
            ):
                if isinstance(k["command"], list):
                    cmd = k["command"].copy()
                else:
                    cmd = [str(k["command"])]

                bg = False

                if "background" in k and k["background"]:
                    bg = True

                return True, cmd, bg
        else:
            return False, [], False

    def get_devices(self):
        self.log.debug("Getting devices...")

        unregister = []

        # Check if devices still exist
        for k, data in copy(self.selector.get_map().items()):
            if not os.path.exists(data.fileobj.path):
                unregister.append(k)

        # Unregister non-existing devices
        for u in unregister:
            data = self.selector.get_key(u)

            self.log.info("Unregistering %s" % data.fileobj.path)
            self.selector.unregister(data.fileobj)

        devices_all = [evdev.InputDevice(path) for path in evdev.list_devices()]

        for d in devices_all:
            for c in self.config:
                if self._is_device(d, c):
                    # Check it device is already watched
                    for k, data in self.selector.get_map().items():
                        if data.fileobj == d:
                            self.log.debug("Device %s already registered" % d.path)

                            break
                    else:
                        self.log.info(
                            "Adding %s (%s): vendor=0x%04x, product=0x%04x, version=0x%04x"
                            % (
                                d.path,
                                d.name,
                                d.info.vendor,
                                d.info.product,
                                d.info.version,
                            )
                        )

                        self.cache.append({"device": d, "cap": d.capabilities()})

                        self.selector.register(d, selectors.EVENT_READ)

    def read_events(self):
        self.log.debug("Reading events...")

        while True:
            s = self.selector.select()

            for key, _ in s:
                device = key.fileobj

                try:
                    for event in device.read():
                        self.proccess_event(device, event)
                except OSError as e:
                    self.log.debug("error reading device %s: %s" % (device.path, e))

                    self.get_devices()

    def _replace_placeholder(self, device, event, cmd):
        for i, m in enumerate(cmd):
            result = re.search(r"^{{\s*(.[^}\s]+)\s*}}$", m)

            if result is not None:
                ph = result.group(1)
                result_cap = re.search(r"^device\[(.[^\]]+)\]\.(.+)$", ph)

                if ph == "device.path":
                    cmd[i] = device.path
                elif ph == "device.info.vendor":
                    cmd[i] = device.info.vendor
                elif ph == "device.info.product":
                    cmd[i] = device.info.product
                elif ph == "device.info.version":
                    cmd[i] = device.info.version
                elif ph == "event.type":
                    cmd[i] = event.type
                elif ph == "event.code":
                    cmd[i] = event.code
                elif ph == "event.value":
                    cmd[i] = event.value
                elif result_cap is not None:
                    rule_string = result_cap.group(1)
                    path = result_cap.group(2).split(".")
                    pairs = rule_string.split(",")
                    rules = {}

                    for p in pairs:
                        k, v = p.split("=")
                        rules[k] = int(v)

                    this = None

                    for d in self.cache:
                        if "cap" in rules and rules["cap"] in d["cap"]:
                            if "subcap" in rules:
                                if rules["subcap"] in d["cap"][rules["cap"]]:
                                    this = d["device"]

                                    break
                            else:
                                this = d["device"]

                                break

                    if this is not None:
                        for p in path:
                            if hasattr(this, p):
                                this = getattr(this, p, None)
                            else:
                                self.log.error("%s has no attribute %s" % (this, p))

                                break
                        else:
                            cmd[i] = this

    def proccess_event(self, device, event):
        self.log.debug("Processing event...")

        value = self._value(event.value)

        for c in self.config:
            is_key, cmd, bg = self._is_key(event, c)

            if self._is_device(device, c) and is_key:
                # Replace placeholders with real value
                self._replace_placeholder(device, event, cmd)

                self.log.info(
                    "Executing command for %s: type=%d, code=%d, value=%s, background=%s, command=%s"
                    % (device.path, event.type, event.code, value, bg, cmd)
                )

                cmd[0] = os.path.expanduser(cmd[0])

                if bg:
                    result = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                    )
                else:
                    result = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        text=True,
                    )

                    self.log.debug(
                        "rc=%d, stdout=%s, stderr=%s"
                        % (result.returncode, result.stdout.strip(), result.stderr)
                    )
            else:
                self.log.debug(
                    "Non-matching event %s: type=%d, code=%d, value=%s"
                    % (device.path, event.type, event.code, value)
                )


def parse_args():
    parser = argparse.ArgumentParser(description="Run command on input event.")

    os.path.normpath(os.path.join(os.path.dirname(__file__), "config"))

    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Show debug messages.",
    )
    parser.add_argument(
        "-s",
        "--silent",
        action="store_true",
        help="Don't show any messages.",
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        default=os.path.normpath(
            os.path.join(os.path.dirname(__file__), "config.yaml")
        ),
        help="Path to the config file. (default: %s)"
        % os.path.normpath(os.path.join(os.path.dirname(__file__), "config.yaml")),
    )
    parser.add_argument(
        "-t",
        "--timestamp",
        action="store_true",
        help="Add timestamp into the log.",
    )
    parser.add_argument(
        "-D",
        "--daemon",
        action="store_true",
        help="Run on the background.",
    )

    return parser, parser.parse_args()


def main():
    # Catch CTRL+C
    signal.signal(signal.SIGINT, int_handler)

    # Read command line arguments
    parser, args = parse_args()

    # Check input parameters
    if "config" not in args:
        logging.error("No action specified!")
        parser.print_help()
        sys.exit(1)

    # Setup logger
    format = "%(levelname)s: %(message)s"

    if args.timestamp:
        format = "[%%(asctime)s] %s" % format

    log_level = logging.ERROR

    if args.debug:
        log_level = logging.DEBUG
    elif not args.silent:
        log_level = logging.INFO

    logging.basicConfig(level=log_level, format=format)

    log = logging.getLogger(__name__)

    # Run on the background
    if args.daemon:
        pid = os.fork()

        # stop first thread
        if pid > 0:
            sys.exit(0)

    # Create event processor instance
    try:
        hep = HidEventProcessor(log, args.config)
    except Exception as e:
        log.error("Failed to create event processor: %s" % e)
        sys.exit(1)

    # Read events
    hep.read_events()


if __name__ == "__main__":
    main()
