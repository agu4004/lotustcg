# SSL Setup Options - LotusTCG Deployment

## Option 1: Skip SSL for Now (Recommended for Testing)

Since you don't have a domain yet, you can skip the SSL step and access your site via HTTP:

```bash
# Your LotusTCG site will be accessible at:
http://YOUR_STATIC_IP

# Example: http://13.229.123.45
```

**Pros:** Quick deployment, works immediately
**Cons:** Not secure (HTTP only), browsers may show warnings

## Option 2: Use AWS Lightsail Static IP + Free Domain

### Get a Free Domain
1. **Freenom** (free .tk, .ml domains)
2. **GitHub Pages** domain redirect
3. **Netlify** free subdomain

### Point Domain to Your Static IP
```bash
# In your domain DNS settings, create an A record:
Type: A
Name: @ (or subdomain like 'shop')
Value: YOUR_LIGHTSAIL_STATIC_IP
TTL: 3600
```

### Then Run Certbot
```bash
sudo certbot --nginx -d your-new-domain.com
```

## Option 3: Self-Signed Certificate (Development Only)

Create a self-signed certificate for testing:

```bash
# Create certificate
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/lotustcg.key \
  -out /etc/ssl/certs/lotustcg.crt

# Update nginx config for HTTPS
sudo tee /etc/nginx/sites-available/lotustcg > /dev/null << 'EOF'
server {
    listen 80;
    listen 443 ssl;
    server_name _;

    ssl_certificate /etc/ssl/certs/lotustcg.crt;
    ssl_certificate_key /etc/ssl/private/lotustcg.key;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo systemctl reload nginx
```

**Note:** Browsers will show security warnings with self-signed certificates.

## Option 4: Buy a Domain (Best Long-term Solution)

### Cheap Domain Registrars
- **Namecheap**: $8-12/year (.com domains)
- **Google Domains**: $12/year
- **Cloudflare**: $8/year + free CDN/security

### After Getting Domain
1. Point domain to your Lightsail static IP
2. Wait for DNS propagation (5-30 minutes)
3. Run certbot: `sudo certbot --nginx -d yourdomain.com`

## Current Recommendation

**For immediate testing:** Skip SSL, use HTTP with your static IP

```bash
# Test your site at:
http://YOUR_STATIC_IP

# Continue with nginx installation first:
sudo apt install -y nginx
# Then configure nginx as shown in the deployment guide
```

**For production:** Get a domain name and use Let's Encrypt SSL.

Your LotusTCG app will work perfectly fine without SSL for development and testing purposes.