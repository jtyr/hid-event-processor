#!/bin/bash

ACTION=${1:-toggle}
DEVICE=${2:-/dev/input/event23}

evtest --query "$DEVICE" EV_LED LED_MUTE

RC="$?"

if [[ $ACTION == 'toggle' ]]; then
    if [[ $RC == 0 ]]; then
        evemu-event "$DEVICE" --type 17 --code 7 --value 1
        pactl set-source-mute alsa_input.usb-Bose_Bose_USB_Link_082063Z03330148AE-00.mono-fallback 1
    else
        evemu-event "$DEVICE" --type 17 --code 7 --value 0
        pactl set-source-mute alsa_input.usb-Bose_Bose_USB_Link_082063Z03330148AE-00.mono-fallback 0
    fi
elif [[ $ACTION == 'hangup' ]]; then
    if [[ $RC != 0 ]]; then
        evemu-event "$DEVICE" --type 17 --code 7 --value 0
    fi
else
    echo "Unknown action: $ACTION"
fi
