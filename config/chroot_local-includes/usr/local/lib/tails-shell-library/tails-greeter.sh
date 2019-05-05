#!/bin/sh

PHYSICAL_SECURITY_SETTINGS='/var/lib/live/config/tails.physical_security'

_get_tg_setting() {
    if [ -r "${1}" ]; then
        . "${1}"
        eval "echo \${${2}:-}"
    fi
}

persistence_is_enabled() {
	systemctl --user is-active tails-persistence-is-enabled.target
}

persistence_is_enabled_for() {
    persistence_is_enabled && mountpoint -q "$1" 2>/dev/null
}

mac_spoof_is_enabled() {
    # Only return false when explicitly told so to increase failure
    # safety.
    [ "$(_get_tg_setting "${PHYSICAL_SECURITY_SETTINGS}" TAILS_MACSPOOF_ENABLED)" != false ]
}

tails_netconf() {
    _get_tg_setting "${PHYSICAL_SECURITY_SETTINGS}" TAILS_NETCONF
}
