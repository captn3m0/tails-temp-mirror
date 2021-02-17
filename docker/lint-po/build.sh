#!/bin/bash

set -euo pipefail
set -x

print_usage() {
  cat << EOF
usage: $0 [OPTIONS]

Build the docker image.

Options:
--push
    Push the image after building it.
-h, --help
    Print usage message.
EOF
}

# Parse arguments
while [ "$#" -gt 0 ]; do
case "$1" in
    --push)
    PUSH=1
    shift
    ;;
    -h|--help)
    print_usage
    exit 0
    ;;
    *) # unknown option
    echo "unknown option: $1"
    print_usage
    exit 1
    ;;
esac
done

TAG="${TAG:-"tailslive/lint-po:v1"}"

# Build the image
DOCKER_BUILDKIT=1 docker build \
 --cache-from "${TAG}" \
 --build-arg BUILDKIT_INLINE_CACHE=1 \
 --tag "${TAG}" \
 .

# Push the image (if requested)
if [ -n "${PUSH:-}" ]; then
  docker push "${TAG}"
fi
