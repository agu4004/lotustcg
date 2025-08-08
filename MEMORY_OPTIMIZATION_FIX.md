# Memory Optimization Fix - LotusTCG

## Issue
Worker process killed with SIGKILL due to out of memory. This is critical for deployment.

## Immediate Fix - Reduce Memory Usage

### 1. Update Systemd Service Configuration
```bash
sudo nano /etc/systemd/system/lotustcg.service

# Change the ExecStart line to use fewer workers and add memory limits:
ExecStart=/home/ubuntu/lotustcg/venv/bin/gunicorn --workers 1 --max-requests 1000 --max-requests-jitter 100 --preload --bind 127.0.0.1:5000 --timeout 30 main:app
```

### 2. Complete Optimized Service File
```bash
sudo tee /etc/systemd/system/lotustcg.service > /dev/null << 'EOF'
[Unit]
Description=LotusTCG Gunicorn Application
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/lotustcg
Environment=PATH=/home/ubuntu/lotustcg/venv/bin:/usr/bin:/bin
EnvironmentFile=/home/ubuntu/lotustcg/.env
ExecStart=/home/ubuntu/lotustcg/venv/bin/gunicorn --workers 1 --max-requests 1000 --max-requests-jitter 100 --preload --bind 127.0.0.1:5000 --timeout 30 main:app
Restart=always
RestartSec=5
MemoryLimit=1G
MemoryHigh=800M

[Install]
WantedBy=multi-user.target
EOF
```

### 3. Restart Service
```bash
sudo systemctl daemon-reload
sudo systemctl restart lotustcg
sudo systemctl status lotustcg --no-pager
```

### 4. Monitor Memory Usage
```bash
# Check current memory usage
free -h

# Monitor the process
ps aux | grep gunicorn

# Check system resources
df -h
```

## Database Connection Optimization

### Optimize PostgreSQL Connections
```bash
# Edit PostgreSQL configuration for lower memory usage
sudo nano /etc/postgresql/*/main/postgresql.conf

# Add these lines:
shared_buffers = 32MB
effective_cache_size = 128MB
work_mem = 2MB
maintenance_work_mem = 32MB
max_connections = 20
```

### Restart PostgreSQL
```bash
sudo systemctl restart postgresql
```

## Application Code Optimization

### Check for Memory Leaks in app.py
```python
# Add to app.py if not present:
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5,
    'pool_recycle': 300,
    'pool_pre_ping': True,
    'max_overflow': 0
}
```

## Emergency - Manual Process Management
If service keeps crashing:
```bash
# Stop systemd service
sudo systemctl stop lotustcg

# Run manually with minimal resources
cd /home/ubuntu/lotustcg
source venv/bin/activate
export $(cat .env | xargs)

# Single worker, minimal memory
gunicorn --workers 1 --max-requests 500 --bind 127.0.0.1:5000 --timeout 30 main:app
```

## AWS Lightsail Instance Upgrade
Consider upgrading your instance:
- Current: $10/month (2GB RAM) 
- Upgrade to: $20/month (4GB RAM) for better performance

## Memory Monitoring Commands
```bash
# Watch memory usage in real-time
watch -n 1 'free -h && ps aux | grep gunicorn'

# Check application logs for memory issues
sudo journalctl -u lotustcg -f | grep -i memory
```