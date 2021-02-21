#!/bin/bash

set -euo pipefail

BASE_IMAGE="debian:buster"



IMAGES="debian-buster iuk lint-po perl5lib"

for image in ${IMAGES}; do
  # Import BASE_IMAGE and BASE_IMAGE_LATEST_DIGEST
  source "${image}/MANIFEST"
  DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' ${BASE_IMAGE})
  if [ "${DIGEST}" -eq "${BASE_IMAGE_LATEST_DIGEST}" ]; then
    # The base image is already the latest version, nothing to do here
    continue
  fi


done
