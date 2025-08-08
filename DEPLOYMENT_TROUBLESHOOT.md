# Complete Deployment Troubleshooting

## Quick Diagnostic Commands

Run these in sequence to identify the exact issue:

```bash
# 1. Check current directory and files
cd /home/ubuntu/cardmarketscan
pwd
ls -la

# 2. Check Python and virtual environment
python3 --version
which python3

# 3. Check if venv exists and contents
ls -la venv/
ls -la venv/bin/ 2>/dev/null || echo "venv/bin not found"

# 4. Try activating venv
source venv/bin/activate 2>/dev/null && echo "venv activated" || echo "venv activation failed"

# 5. Check what's installed
pip list 2>/dev/null || echo "pip not working"

# 6. Check .env file
cat .env

# 7. Check main.py exists
ls -la main.py
```

## Based on Diagnostic Results

**If venv/bin doesn't exist:** Virtual environment wasn't created properly
**If pip list fails:** Virtual environment is broken
**If main.py missing:** Wrong directory or files not copied
**If .env missing:** Environment variables not set up

## Emergency Working Solution

If nothing else works, use this minimal approach:

```bash
cd /home/ubuntu/cardmarketscan
sudo apt install -y python3-pip python3-venv
python3 -m venv fresh_venv
source fresh_venv/bin/activate
pip install --upgrade pip
pip install flask gunicorn psycopg2-binary flask-sqlalchemy flask-login werkzeug

# Test immediately
which gunicorn
gunicorn --version

# Update systemd service path
sudo sed -i 's|/home/ubuntu/cardmarketscan/venv/bin/gunicorn|/home/ubuntu/cardmarketscan/fresh_venv/bin/gunicorn|g' /etc/systemd/system/cardmarketscan.service
sudo systemctl daemon-reload
sudo systemctl restart cardmarketscan
```