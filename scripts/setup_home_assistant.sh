#!/usr/bin/env bash
# One-time setup for FR-1300 (smart home): installs Docker (if missing) and runs
# Home Assistant as a container alongside willy-rover.service. Safe to re-run —
# skips steps that are already done.
set -euo pipefail

CONFIG_DIR="/home/hhimmel/homeassistant"

echo "== Docker =="
if command -v docker >/dev/null 2>&1; then
    echo "Docker already installed, skipping."
else
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sudo sh
fi

if ! groups "$USER" | grep -qw docker; then
    echo "Adding $USER to the docker group (takes effect after you log out/in)..."
    sudo usermod -aG docker "$USER"
fi

echo "== Home Assistant container =="
mkdir -p "$CONFIG_DIR"

if sudo docker ps -a --format '{{.Names}}' | grep -qx homeassistant; then
    echo "Container 'homeassistant' already exists."
    if [ "$(sudo docker inspect -f '{{.State.Running}}' homeassistant)" != "true" ]; then
        echo "Starting it..."
        sudo docker start homeassistant
    else
        echo "Already running."
    fi
else
    echo "Creating and starting the container..."
    sudo docker run -d \
        --name homeassistant \
        --privileged \
        --restart=unless-stopped \
        -e TZ=America/New_York \
        -v "$CONFIG_DIR:/config" \
        --network=host \
        ghcr.io/home-assistant/home-assistant:stable
fi

echo
echo "== Done =="
echo "Home Assistant is starting up (first boot can take a minute or two)."
echo "Open http://$(hostname -I | awk '{print $1}'):8123 in a browser to finish onboarding"
echo "(create the admin account, etc. — that part's a web wizard, not scriptable)."
