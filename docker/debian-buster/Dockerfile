FROM debian:buster

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && apt-get install -y \
    # Required by check-po-msgfmt
    python3 \
    gettext \
    # Required by sanity-check-website
    ruby \
    # Required by check-translatable-live-website-urls
    python3-polib \
    # Required by test-iuk
    apt-file \
    libdist-zilla-plugin-test-notabs-perl \
    libdist-zilla-plugin-test-perl-critic-perl \
    libdist-zilla-app-command-authordebs-perl \
    libmodule-build-perl \
    sudo \
    attr \
    bsdtar \
    libdevice-cdio-perl \
    faketime \
    genisoimage \
    gnutls-bin \
    libdata-dumper-concise-perl \
    libdatetime-perl \
    libfile-copy-recursive-perl \
    # Required by perl5lib
    sudo \
    # Required by test-persistent-storage
    python3-gi \
    acl \
    # Required by test-whisperback
    python3-pytest \
    # Required by apt-snapshots-expiry
    curl \
    git \
    # Remove APT lists to produce a smaller image
    && rm -rf /var/lib/apt/lists/*
