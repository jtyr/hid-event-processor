#!/bin/bash

# Input parameters
ACTION=${1:-toggle}
DEVICE=${2:-/dev/input/event23}

# Name of the device to be muted
CARD='alsa_input.usb-Bose_Bose_USB_Link_082063Z03330148AE-00.mono-fallback'

# Check if the device is muted or not
MUTED=$(pactl get-source-mute "$CARD" | sed 's/^Mute: //')

# Decide what to do
if [[ $ACTION == 'toggle' ]]; then
    # Change USB LED accordingly
    if [[ $MUTED == 'yes' ]]; then
        evemu-event "$DEVICE" --type 17 --code 7 --value 0
    else
        evemu-event "$DEVICE" --type 17 --code 7 --value 1
    fi

    # Toggle the device mute
    pactl set-source-mute "$CARD" toggle
elif [[ $ACTION == 'hangup' ]]; then
    # Unmute at the end of the call
    if [[ $MUTED == 'yes' ]]; then
        evemu-event "$DEVICE" --type 17 --code 7 --value 0
        pactl set-source-mute "$CARD" 0
    fi
else
    echo "Unknown action: $ACTION"
fi
