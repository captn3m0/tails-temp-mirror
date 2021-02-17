FROM debian:buster

ARG packages

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && apt-get install -y \
    apt-file \
    libdist-zilla-plugin-test-notabs-perl \
    libdist-zilla-plugin-test-perl-critic-perl \
    libdist-zilla-app-command-authordebs-perl \
    libmodule-build-perl \
    sudo \
    # Install packages from
    # config/chroot_local-packageslists/tails-perl5lib.list
    ${packages} \
    # Remove APT lists to produce a smaller image
    && rm -rf /var/lib/apt/lists/*
