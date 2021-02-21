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

# Import BASE_IMAGE and BASE_IMAGE_DIGEST
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "${SCRIPT_DIR}/LATEST"

# Pull the latest version of the base image
docker pull "${BASE_IMAGE}"

# 

TAG="${TAG:-"tailslive/debian-buster:${BASE_IMAGE_DIGEST:0:8}"}"

# Build the image
DOCKER_BUILDKIT=1 docker build \
 --cache-from "${TAG}" \
 --build-arg BUILDKIT_INLINE_CACHE=1 \
 --build-arg BASE_IMAGE_DIGEST="${BASE_IMAGE_DIGEST}" \
 --tag "${TAG}" \
 .

# Push the image (if requested)
if [ -n "${PUSH:-}" ]; then
  docker push "${TAG}"

  # Update the BASE_IMAGE_DIGEST in the LATEST file

fi
