# Port 80 Connection Fix - LotusTCG

## Issue
"Failed to connect to static IP port 80" means either nginx isn't running or there's a configuration problem.

## Diagnostic Commands

### 1. Check Service Status
```bash
sudo systemctl status nginx --no-pager
sudo systemctl status lotustcg --no-pager
```

### 2. Check Port Binding
```bash
# Use ss command (modern replacement for netstat)
sudo ss -tlnp | grep :80
sudo ss -tlnp | grep :5000

# Alternative: install net-tools if needed
sudo apt install -y net-tools
sudo netstat -tlnp | grep :80
```

### 3. Test Local Connections
```bash
curl http://localhost:80
curl http://localhost:5000
```

## Quick Fix Steps

### Step 1: Ensure Services Are Running
```bash
# Start nginx if stopped
sudo systemctl start nginx
sudo systemctl enable nginx

# Restart lotustcg service
sudo systemctl restart lotustcg

# Check status
sudo systemctl status nginx lotustcg --no-pager
```

### Step 2: Check Nginx Configuration
```bash
# Test nginx configuration
sudo nginx -t

# If config is broken, recreate it
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

# Enable site and restart
sudo ln -sf /etc/nginx/sites-available/lotustcg /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### Step 3: Check AWS Lightsail Firewall
```bash
# In AWS Lightsail Console:
# 1. Go to your instance
# 2. Click Networking tab
# 3. Ensure these ports are open:
#    - SSH (22) ✓
#    - HTTP (80) ✓
#    - HTTPS (443) ✓
#    - Custom (5000) ✓ (for testing)
```

### Step 4: Test Application Chain
```bash
# Test LotusTCG app directly
curl -v http://localhost:5000

# Test nginx proxy
curl -v http://localhost:80

# Test from external (use your static IP)
curl -v http://YOUR_STATIC_IP
```

## Common Issues and Solutions

### Issue 1: Nginx Not Running
```bash
sudo systemctl start nginx
sudo systemctl enable nginx
```

### Issue 2: LotusTCG App Not Responding
```bash
sudo journalctl -u lotustcg -n 20 --no-pager

# If app has issues, test manually
cd /home/ubuntu/lotustcg
source venv/bin/activate
export $(cat .env | xargs)
gunicorn --bind 0.0.0.0:5000 --workers 1 main:app
```

### Issue 3: Port Already in Use
```bash
# Check what's using port 80
sudo lsof -i :80

# If something else is using it, stop it
sudo systemctl stop apache2  # if Apache is running
```

### Issue 4: Firewall Blocking
```bash
# Check if UFW is blocking (Ubuntu firewall)
sudo ufw status

# If UFW is active, allow port 80
sudo ufw allow 80
sudo ufw allow 5000
```

## Emergency Bypass Test
If nginx continues to have issues, test the app directly:
```bash
# Stop nginx temporarily
sudo systemctl stop nginx

# Run LotusTCG directly on port 80 (requires sudo)
cd /home/ubuntu/lotustcg
source venv/bin/activate
export $(cat .env | xargs)
sudo venv/bin/gunicorn --bind 0.0.0.0:80 --workers 1 main:app

# Test from browser: http://YOUR_STATIC_IP
```

## Verification Steps
When working correctly, you should see:
```bash
# Services running
sudo systemctl status nginx lotustcg

# Ports bound
sudo netstat -tlnp | grep :80    # nginx
sudo netstat -tlnp | grep :5000  # lotustcg

# Application responding
curl http://localhost:80          # Should return HTML
curl http://YOUR_STATIC_IP        # Should return HTML
```