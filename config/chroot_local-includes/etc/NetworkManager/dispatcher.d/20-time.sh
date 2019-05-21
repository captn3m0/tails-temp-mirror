#!/bin/sh

# Rationale: Tor needs a somewhat accurate clock to work.
# If the clock is wrong enough to prevent it from opening circuits,
# we set the time to the middle of the valid time interval found
# in the Tor consensus, and we restart it.
# In any case, we use HTP to ask more accurate time information to
# a few authenticated HTTPS servers.

# Get LIVE_USERNAME
. /etc/live/config.d/username.conf

# Import export_gnome_env().
. /usr/local/lib/tails-shell-library/gnome.sh

# Import tor_control_*(), tor_is_working(), TOR_LOG, TOR_DIR
. /usr/local/lib/tails-shell-library/tor.sh

# Import tails_netconf()
. /usr/local/lib/tails-shell-library/tails-greeter.sh

### Init variables

TORDATE_DIR=/run/tordate
TORDATE_DONE_FILE=${TORDATE_DIR}/done
TOR_CONSENSUS=${TOR_DIR}/cached-microdesc-consensus
TOR_UNVERIFIED_CONSENSUS=${TOR_DIR}/unverified-microdesc-consensus
TOR_UNVERIFIED_CONSENSUS_HARDLINK=${TOR_UNVERIFIED_CONSENSUS}.bak
INOTIFY_TIMEOUT=60
DATE_RE='[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]'

### Exit conditions

# Run only when the interface is not "lo":
if [ -z "$1" ] || [ "$1" = "lo" ]; then
	exit 0
fi

# Run whenever an interface gets "up", not otherwise:
if [ "$2" != "up" ]; then
	exit 0
fi

# Do not run twice
if [ -e "$TORDATE_DONE_FILE" ]; then
	exit 0
fi


### Functions

log() {
	logger -t time "$@"
}

has_consensus() {
	local files="${TOR_CONSENSUS} ${TOR_UNVERIFIED_CONSENSUS}"

	if [ $# -ge 1 ]; then
		files="$@"
	fi
	grep -qs "^valid-until ${DATE_RE}"'$' ${files}
}

has_only_unverified_consensus() {
	[ ! -e ${TOR_CONSENSUS} ] && has_consensus ${TOR_UNVERIFIED_CONSENSUS}
}

wait_for_tor_consensus_helper() {
	tries=0
	while ! has_consensus && [ $tries -lt 10 ]; do
		inotifywait -q -t 30 -e close_write -e moved_to ${TOR_DIR} || log "timeout"
		tries=$(expr $tries + 1)
	done

	# return some kind of success measurement
	has_consensus
}

wait_for_tor_consensus() {
	log "Waiting for a Tor consensus file to contain a valid time interval"
	if ! has_consensus && ! wait_for_tor_consensus_helper; then
		log "Unsuccessfully retried waiting for Tor consensus, aborting."
	fi
	if has_consensus; then
		log "A Tor consensus file now contains a valid time interval."
	else
		log "Waited for too long, let's stop waiting for Tor consensus."
		# FIXME: gettext-ize
		/usr/local/sbin/tails-notify-user "Synchronizing the system's clock" \
			"Could not fetch Tor consensus."
		exit 2
	fi
}

wait_for_working_tor() {
	local waited=0

	log "Waiting for Tor to be working..."
	while ! tor_is_working; do
		if [ "$waited" -lt ${INOTIFY_TIMEOUT} ]; then
			sleep 2
			waited=$(($waited + 2))
		else
			log "Timed out waiting for Tor to be working"
			return 1
		fi
	done
	log "Tor is now working."
}

start_notification_helper() {
	export_gnome_env
	exec /bin/su -c /usr/local/lib/tails-htp-notify-user "$LIVE_USERNAME" &
}


### Main

start_notification_helper

# Delegate time setting to other daemons if Tor connections work
if tor_is_working; then
	log "Tor has already opened a circuit"
else
	wait_for_tor_consensus
fi

wait_for_working_tor

touch $TORDATE_DONE_FILE

log "Restarting htpdate"
systemctl restart htpdate.service
log "htpdate service restarted with return code $?"
