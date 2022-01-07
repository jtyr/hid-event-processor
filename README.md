# HID Event Processor (HEP)

This is a simple event processor for HID devices (e.g. USB keyboards or
headsets) which allows to run a command when a key (e.g. multimedia key or
headset button) is pressed.

## Motivation

I got the [Bose
700](https://www.bose.co.uk/en_gb/products/headphones/noise_cancelling_headphones/noise-cancelling-headphones-700.html)
for free with my new phone but unfortunately the headphones, when connected
directly via Bluetooth, don't have any way how I can mute the mic when on a
conference call (e.g. Zoom, Teams, Google Chat). So I bought the [Bose USB
Link](https://www.bose.co.uk/en_gb/products/headphones/headphone_accessories/bose-usb-link.html)
that should solve this problem. Unfortunately the muting (long-press on the
right hand side ear cup) didn't work out of the box and required to remap the
`KEY_MICMUTE` key to `F20` key. That was simply done using UDEV:

```shell
sudo cat <<END > /etc/udev/hwdb.d/99-bose.hwdb`
evdev:input:b0003v05a7pa310*
 KEYBOARD_KEY_b002f=f20
 KEYBOARD_KEY_ff990004=f20
END
sudo systemd-hwdb update
sudo udevadm trigger
```

Unfortunately this way it didn't visually nor acoustically indicate if the mic
is muted or unmuted. That's why I have decided to write HEP which allows to run
a script on any event from the headphones without the need to remap any keys.

The
[script](https://github.com/jtyr/hid-event-processor/blob/main/scripts/bose.sh)
can mute/unmute the mic and change the light color on the Bose USB Link (that
makes the headphones to play a sound) using system tools like
[`evtest`](https://cgit.freedesktop.org/evtest/),
[`pactl`](https://www.freedesktop.org/wiki/Software/PulseAudio/) and
[`evemu-event`](https://www.freedesktop.org/wiki/Evemu).

## Installation

### Python packages

HEP requires some non-standard packages. Those can be installed by using `pip`
(the `requirements.txt` file can be found in the [HEP Git
repository](https://github.com/jtyr/hid-event-processor)):

```shell
pip install -r requirements.txt
```

On Arch Linux it can be installed using system packages:

```shell
pacman -S python-evdev python-yaml
```

### Using per-user Systemd instance

> This requires [Systemd instance running under a
user](https://wiki.archlinux.org/title/systemd/User).

The HEP can be installed like this:

```shell
cd ~/
git clone https://github.com/jtyr/hid-event-processor.git
mkdir -p ~/.config/systemd/user/
ln -s ~/hid-event-processor/systemd/hep.service ~/.config/systemd/user/
cat <<END > ~/.config/systemd/hep.conf
HEP_PATH=~/hid-event-processor/hep.py
END
systemd --user enable hep
systemd --user start hep
```

### Ad-hoc from command line

```shell
cd ~/
git clone https://github.com/jtyr/hid-event-processor.git
cd hid-event-processor
./hep.py
```

## Configuration

Configuration is done by creating a YAML file that contains definition which
devices and keys should be monitored and what command to execute when the event
appears:

```yaml
# Configuration for the "Logitech Pro Gaming Keyboard"
- device:
    # Device identification
    vendor: 0x46d
    product: 0xc339
    version: 0x111
  keys:
    # Play/Pause key down
    - type: 1
      code: 164
      value: 1
      # Simple command to run
      command: kcalc
      # Run on background
      background: true
    # FastForward key down
    - type: 1
      code: 163
      value: 1
      # Simple command to run
      command: drawio
      # Run on background
      background: true

# Configuration for the "Bose 700 ACM Headphones"
- device:
    # Device identification
    vendor: 0x5a7
    product: 0xa310
    version: 0x111
  keys:
    # MSC_SCAN on KEY_MICMUTE longpress
    - type: 4
      code: 4
      value: b002f
      # Multi-argument command to run
      command:
        - ~/bin/bose.sh
        - toggle
        # Use the actual device path as one of the command parameters
        - "{{ device.path }}"
    # MSC_SCAN on BTN_0 press
    - type: 4
      code: 4
      value: ff990004
      # Multi-argument command to run
      command:
        - ~/bin/bose.sh
        - toggle
        # Find a device that has the specivied capability (17=EV_LED, 7=LED_MUTE)
        - "{{ device[cap=17,subcap=7].path }}"
    # MSC_SCAN on KEY_PLAY (hangup)
    - type: 4
      code: 4
      value: c00b0
      # Multi-argument command to run
      command:
        - ~/bin/bose.sh
        - hangup
        # Find a device that has the specivied capability (17=EV_LED, 7=LED_MUTE)
        - "{{ device[cap=17,subcap=7].path }}"
```

The device and key details can be found by using
[`evtest`](https://cgit.freedesktop.org/evtest/) tool.

## Author

Jiri Tyr

## License

MIT
