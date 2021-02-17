FROM debian:bullseye

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && apt-get install -y \
    # Required to clone jenkins-tools
    git \
    # Required by lint-latest-po
    i18nspector \
    intltool \
    # Remove APT lists to produce a smaller image
    && rm -rf /var/lib/apt/lists/* \
    # Clone jenkins tools (required by lint-po)
    git clone https://gitlab.tails.boum.org/tails/jenkins-tools.git /tmp/jenkins-tools
