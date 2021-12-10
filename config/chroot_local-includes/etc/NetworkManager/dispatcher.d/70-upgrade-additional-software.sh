#!/bin/sh

set -e

# Import is_real_nic()
. /usr/local/lib/tails-shell-library/hardware.sh

# Run only for "real" interfaces
is_real_nic "$1" || exit 0

# Run whenever an interface gets "up", not otherwise:
if [ "$2" != "up" ]; then
   exit 0
fi

/bin/systemctl --no-block start tails-additional-software-upgrade.path
