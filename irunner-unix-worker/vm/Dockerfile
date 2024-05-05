FROM ubuntu:focal

RUN apt-get update && apt-get install -y \
    python3-pip \
    sudo \
    psmisc \
    gawk \
    bc \
    unzip \
    clang-10 \
    libc++-10-dev \
    libc++abi-10-dev \
    nasm

RUN update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-10 100 && \
    update-alternatives --install /usr/bin/clang clang /usr/bin/clang-10 100

RUN pip3 install \
    pytest==5.4.2 \
    pytest-timeout==1.3.4

RUN groupadd --gid 999 bsu && \
    useradd --uid 999 --gid bsu --create-home --shell /bin/bash student && \
    usermod -a -G sudo student && \
    echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

RUN mkdir --parents /opt/irunner/src && \
    mkdir --parents /opt/irunner/dst && \
    chown -R student:bsu /opt/irunner/dst

USER student

WORKDIR /home/student

ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
