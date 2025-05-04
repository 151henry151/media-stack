#!/bin/bash

# Define services and their ports
declare -A services=(
    ["radarr"]="7878"
    ["sonarr"]="8989"
    ["jellyfin"]="8096"
    ["jellyseerr"]="5055"
    ["qbittorrent"]="5080"
    ["prowlarr"]="9696"
)

# Generate config for each service
for service in "${!services[@]}"; do
    port=${services[$service]}
    sed -e "s/{SERVICE}/$service/g" -e "s/{PORT}/$port/g" \
        conf.d/service.conf.template > conf.d/$service.conf
done

echo "Generated configurations for: ${!services[@]}" 