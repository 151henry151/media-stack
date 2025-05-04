# SSL Certificate Management for romptele.com

## Current Setup
- Certificate issued by Let's Encrypt
- Valid from May 2, 2025 to July 31, 2025
- Covers all subdomains:
  - romptele.com
  - admin.romptele.com
  - authentik.romptele.com
  - jellyfin.romptele.com
  - jellyseerr.romptele.com
  - prowlarr.romptele.com
  - qbittorrent.romptele.com
  - radarr.romptele.com
  - sonarr.romptele.com

## Certificate Renewal Process

### Manual Renewal
If automatic renewal fails or you need to force a renewal:

1. Stop the nginx container:
```bash
docker compose -f docker-compose-nginx.yml down
```

2. Clear the certificate directory (optional, only if needed):
```bash
rm -rf ./certbot/conf/*
```

3. Restart the nginx container to trigger certificate renewal:
```bash
docker compose -f docker-compose-nginx.yml up -d
```

### Verify Certificate
To check certificate details:
```bash
docker exec nginx openssl x509 -in /etc/letsencrypt/live/romptele.com/fullchain.pem -text -noout
```

## Troubleshooting
- If certificate dates appear incorrect, verify the system date is accurate
- Check nginx logs for any SSL-related errors:
```bash
docker logs nginx
```

## Notes
- Certificates are stored in `./certbot/conf/`
- Nginx configuration is in `./nginx/conf.d/`
- Automatic renewal is handled by the certbot container
- Certificate renewal should happen automatically before expiration 