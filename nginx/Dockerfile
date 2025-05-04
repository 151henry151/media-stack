FROM nginx:alpine

# Install certbot and dependencies
RUN apk add --no-cache \
    certbot \
    certbot-nginx \
    python3 \
    py3-pip \
    git \
    openssl

# Create and activate virtual environment, then install certbot-dns-gandi
RUN python3 -m venv /opt/certbot-venv && \
    /opt/certbot-venv/bin/pip install --no-cache-dir git+https://github.com/obynio/certbot-plugin-gandi.git

# Copy configuration files
COPY conf.d /etc/nginx/conf.d
COPY auth /etc/nginx/auth

# Create necessary directories
RUN mkdir -p /etc/letsencrypt/gandi

# Create wrapper script for certbot with venv
RUN printf '#!/bin/sh\n. /opt/certbot-venv/bin/activate && certbot "$@"' > /usr/local/bin/certbot-with-gandi && \
    chmod +x /usr/local/bin/certbot-with-gandi

# Expose ports
EXPOSE 80 443

# Start nginx
CMD ["nginx", "-g", "daemon off;"] 