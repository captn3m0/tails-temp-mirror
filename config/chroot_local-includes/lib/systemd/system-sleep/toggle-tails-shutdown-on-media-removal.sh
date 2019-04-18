#!/bin/sh
set -e
set -u

case "$1" in
    pre)
        systemctl stop tails-shutdown-on-media-removal.service
        ;;
    post)
        systemctl start tails-shutdown-on-media-removal.service
        ;;
esac
