#!/bin/sh

TOR_RC=/etc/tor/torrc

tor_append_to_torrc () {
    echo "${@}" >> "${TOR_RC}"
}

# Set a (possibly existing) option $1 to $2 in torrc. Shouldn't be
# used for options that can be set multiple times (e.g. the listener
# options). Does not support configuration entries split into multiple
# lines (with the backslash character).
tor_set_in_torrc () {
    sed -i "/^${1}\s/d" "${TOR_RC}"
    tor_append_to_torrc "${1} ${2}"
}

# shellcheck disable=SC2034
SNOWFLAKE_URL='https://snowflake-broker.torproject.net.global.prod.fastly.net/'
# shellcheck disable=SC2034
SNOWFLAKE_FRONT='cdn.sstatic.net'
# shellcheck disable=SC2034
SNOWFLAKE_ICE='stun:stun.l.google.com:19302,stun:stun.voip.blackberry.com:3478,stun:stun.altar.com.pl:3478,stun:stun.antisip.com:3478,stun:stun.bluesip.net:3478,stun:stun.dus.net:3478,stun:stun.epygi.com:3478,stun:stun.sonetel.com:3478,stun:stun.sonetel.net:3478,stun:stun.stunprotocol.org:3478,stun:stun.uls.co.za:3478,stun:stun.voipgate.com:3478,stun:stun.voys.nl:3478'
