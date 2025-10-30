# Example configurations for common deployment scenarios

## 1. Behind Nginx Reverse Proxy

### .env configuration:
```bash
# Application runs on internal port 5000
PORT=5000
HOST=0.0.0.0
HOST_PORT=5000

# Or use a different internal port
# PORT=8080
# HOST_PORT=8080
```

### Nginx configuration example:
```nginx
server {
    listen 80;
    server_name attendance.example.com;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 2. Behind Caddy Reverse Proxy

### .env configuration:
```bash
# Application runs on internal port 5000
PORT=5000
HOST=0.0.0.0
HOST_PORT=5000
```

### Caddyfile example (automatic HTTPS):
```caddy
attendance.example.com {
    reverse_proxy localhost:5000
}

# Multiple sites with different paths
example.com {
    # Main site
    reverse_proxy /attendance/* localhost:5000
    
    # Strip the /attendance prefix
    handle /attendance/* {
        uri strip_prefix /attendance
        reverse_proxy localhost:5000
    }
}

# Local development (no HTTPS)
:8080 {
    reverse_proxy localhost:5000
}
```

### Docker Compose with Caddy:
```yaml
version: '3.8'

services:
  attendance-app:
    build: .
    container_name: attendance-system
    networks:
      - web
    env_file:
      - .env
    environment:
      - DATABASE=/app/data/attendance.db
      - FLASK_ENV=production
    volumes:
      - ./data:/app/data

  caddy:
    image: caddy:alpine
    container_name: caddy-proxy
    ports:
      - "80:80"
      - "443:443"
    networks:
      - web
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config

networks:
  web:
    driver: bridge

volumes:
  caddy_data:
  caddy_config:
```

### Advanced Caddy Configuration:
```caddy
# Multiple attendance instances with load balancing
attendance.example.com {
    reverse_proxy localhost:5001 localhost:5002 localhost:5003 {
        health_uri /
        health_interval 30s
        health_timeout 5s
    }
}

# With basic auth (additional security layer)
secure-attendance.example.com {
    basicauth {
        admin $2a$14$...  # Generate with: caddy hash-password
    }
    reverse_proxy localhost:5000
}

# Custom headers for security
attendance.example.com {
    header {
        # Security headers
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        X-XSS-Protection "1; mode=block"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
    reverse_proxy localhost:5000
}

# Rate limiting (requires caddy-rate-limit plugin)
attendance.example.com {
    rate_limit {
        zone attendance_zone {
            key {remote_host}
            events 100
            window 1m
        }
    }
    reverse_proxy localhost:5000
}
```

## 3. Behind Traefik (Docker)

### docker-compose.yml with Traefik labels:
```yaml
services:
  attendance-app:
    build: .
    container_name: attendance-system
    # No ports mapping needed - Traefik handles it
    networks:
      - traefik
    env_file:
      - .env
    environment:
      - DATABASE=/app/data/attendance.db
      - FLASK_ENV=production
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.attendance.rule=Host(`attendance.example.com`)"
      - "traefik.http.services.attendance.loadbalancer.server.port=5000"
    volumes:
      - ./data:/app/data

networks:
  traefik:
    external: true
```

## 4. Multiple Instances

### Run on different ports:
```bash
# Instance 1 - Department A
HOST_PORT=5001 docker-compose -p attendance-dept-a up -d

# Instance 2 - Department B  
HOST_PORT=5002 docker-compose -p attendance-dept-b up -d
```

## 5. Local Development with Different Port

### config.py:
```python
PORT = 8080
HOST = "127.0.0.1"
```

Then access at: http://localhost:8080