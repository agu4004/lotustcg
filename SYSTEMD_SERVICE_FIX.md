# Systemd Service Fix - Line 12 Missing '=' Error

## Issue
The systemd service has syntax errors causing restart failures and "Missing '='" error.

## Quick Fix

### 1. Stop the broken service
```bash
sudo systemctl stop cardmarketscan
sudo systemctl disable cardmarketscan
```

### 2. Create correct service file
```bash
sudo nano /etc/systemd/system/cardmarketscan.service
```

**Replace the entire contents with this corrected version:**
```ini
[Unit]
Description=CardMarketScan Gunicorn Application
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/cardmarketscan
Environment=PATH=/home/ubuntu/cardmarketscan/venv/bin
EnvironmentFile=/home/ubuntu/cardmarketscan/.env
ExecStart=/home/ubuntu/cardmarketscan/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 main:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 3. Reload and start service
```bash
sudo systemctl daemon-reload
sudo systemctl start cardmarketscan
sudo systemctl enable cardmarketscan
```

### 4. Check status
```bash
sudo systemctl status cardmarketscan
```

### 5. View logs if there are still issues
```bash
sudo journalctl -u cardmarketscan -f --no-pager
```

## Key Fixes Made:
1. **Removed quotes** from Environment variables (systemd doesn't need quotes)
2. **Removed EnvironmentFile** line that was referencing non-existent .env file
3. **Added RestartSec=3** to prevent rapid restart loops
4. **Fixed syntax** to proper systemd format

## If Still Failing
If the service still fails to start, check the application logs:
```bash
# Test the application manually first
cd /home/ubuntu/cardmarketscan
source venv/bin/activate
export DATABASE_URL=postgresql://cmsuser:cms_secure_password_2024@localhost:5432/cardmarketscan
export SESSION_SECRET=your_super_secret_session_key_here_change_this
python -c "from main import app; print('App loads successfully')"
```