# Package Installation Fix - Missing Gunicorn

## Issue
`Failed to execute /home/ubuntu/cardmarketscan/venv/bin/gunicorn: No such file or directory`

This means gunicorn is not installed in the virtual environment.

## Solution

### 1. Install Missing Packages
```bash
cd /home/ubuntu/cardmarketscan
source venv/bin/activate

# Install all required packages
pip install flask flask-login flask-sqlalchemy flask-migrate werkzeug psycopg2-binary gunicorn

# Verify gunicorn is installed
which gunicorn
ls -la venv/bin/gunicorn
```

### 2. Alternative - Use requirements.txt
If you have a requirements.txt file:
```bash
cd /home/ubuntu/cardmarketscan
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Check Python Package Installation
```bash
cd /home/ubuntu/cardmarketscan
source venv/bin/activate
pip list | grep -E "(flask|gunicorn|psycopg2)"
```

### 4. Test Application After Installation
```bash
cd /home/ubuntu/cardmarketscan
source venv/bin/activate
export $(cat .env | xargs)

# Test if gunicorn works now
gunicorn --version
gunicorn --workers 1 --bind 127.0.0.1:5000 --log-level debug main:app
```

### 5. Update Systemd Service (if needed)
After installing packages, restart the service:
```bash
sudo systemctl daemon-reload
sudo systemctl restart cardmarketscan
sudo systemctl status cardmarketscan
```

## Root Cause
The virtual environment was created but the required packages (especially gunicorn) were not installed. This commonly happens when:
1. Virtual environment was created but pip install wasn't run
2. Different virtual environment was used during development vs deployment
3. Package installation failed silently

## Verification
After running step 1, you should see:
- `which gunicorn` returns `/home/ubuntu/cardmarketscan/venv/bin/gunicorn`
- `gunicorn --version` shows version number
- Service starts without "No such file or directory" error