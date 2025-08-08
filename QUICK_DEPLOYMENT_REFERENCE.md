# Quick Deployment Commands Reference

## Immediate Diagnostic Commands
Run these in sequence to identify the issue:

```bash
# 1. Check service status
sudo systemctl status cardmarketscan --no-pager

# 2. Check recent logs  
sudo journalctl -u cardmarketscan -n 30 --no-pager

# 3. Check if port is bound
sudo netstat -tlnp | grep 5000

# 4. Check environment
cd /home/ubuntu/cardmarketscan
cat .env

# 5. Test app manually
source venv/bin/activate
export $(cat .env | xargs)
python -c "from main import app; print('App loads:', app is not None)"
```

## Quick Restart Procedure
```bash
# Stop everything
sudo systemctl stop cardmarketscan
sudo pkill -f gunicorn

# Start fresh
cd /home/ubuntu/cardmarketscan
source venv/bin/activate
export $(cat .env | xargs)

# Test manually first
gunicorn --bind 0.0.0.0:5000 --workers 1 --timeout 120 main:app &
sleep 3
curl http://localhost:5000
pkill gunicorn

# If manual test works, restart service
sudo systemctl start cardmarketscan
sudo systemctl status cardmarketscan
```

## Alternative Port Test
If port 5000 has issues:
```bash
# Test on different port
cd /home/ubuntu/cardmarketscan  
source venv/bin/activate
export $(cat .env | xargs)
gunicorn --bind 0.0.0.0:8080 main:app &
curl http://localhost:8080
pkill gunicorn
```

## Emergency Working Solution
If service continues to fail:
```bash
# Run manually in background
cd /home/ubuntu/cardmarketscan
source venv/bin/activate
export $(cat .env | xargs)
nohup gunicorn --bind 0.0.0.0:5000 main:app > app.log 2>&1 &
```