# Nginx Not Running Fix - LotusTCG

## Issue Confirmed
- LotusTCG app is running on port 5000 ✅
- Nothing listening on port 80 (nginx not running) ❌

## Quick Fix

### 1. Install and Start Nginx
```bash
# Install nginx if not installed
sudo apt update
sudo apt install -y nginx

# Start and enable nginx
sudo systemctl start nginx
sudo systemctl enable nginx

# Check status
sudo systemctl status nginx --no-pager
```

### 2. Create Nginx Configuration for LotusTCG
```bash
sudo tee /etc/nginx/sites-available/lotustcg > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /home/ubuntu/lotustcg/static;
        expires 30d;
    }
}
EOF
```

### 3. Enable the Configuration
```bash
# Remove default nginx page
sudo rm -f /etc/nginx/sites-enabled/default

# Enable LotusTCG site
sudo ln -sf /etc/nginx/sites-available/lotustcg /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

### 4. Verify Everything Works
```bash
# Check nginx is now listening on port 80
sudo ss -tlnp | grep :80

# Test local connections
curl http://localhost:80

# Test your LotusTCG app directly
curl http://localhost:5000

# Both should return HTML content
```

## Expected Results After Fix
- `sudo ss -tlnp | grep :80` should show nginx listening
- `curl http://localhost:80` should return your LotusTCG homepage
- Your AWS static IP should work: `http://YOUR_STATIC_IP`

## If Still Not Working
Check nginx error logs:
```bash
sudo tail -f /var/log/nginx/error.log
```