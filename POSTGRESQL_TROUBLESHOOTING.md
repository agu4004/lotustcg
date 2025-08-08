# PostgreSQL Installation Troubleshooting

## Issue: PostgreSQL Directory Not Found

### Problem
The deployment guide references `/etc/postgresql/14/main/` but Ubuntu returns "Directory does not exist".

### Root Cause
Different Ubuntu versions and PostgreSQL installations create different version directories:
- Ubuntu 22.04 might install PostgreSQL 14, 15, or 16
- Ubuntu 20.04 might install PostgreSQL 12 or 13
- Package repositories can vary

### Solution Steps

#### Step 1: Find Your PostgreSQL Installation
```bash
# Find all PostgreSQL config directories
sudo find /etc -name "postgresql.conf" 2>/dev/null

# Check what PostgreSQL packages are installed
dpkg -l | grep postgresql

# Check PostgreSQL service status
sudo systemctl status postgresql

# Connect and check version
sudo -u postgres psql -c "SELECT version();"
```

#### Step 2: Determine Correct Paths
```bash
# Get PostgreSQL version number
PGVERSION=$(sudo -u postgres psql -t -c "SELECT version();" | grep -oE '[0-9]+' | head -1)
echo "PostgreSQL major version: $PGVERSION"

# Check if config directory exists
ls -la /etc/postgresql/$PGVERSION/main/

# If multiple versions exist, list them:
ls -la /etc/postgresql/
```

#### Step 3: Use Correct Configuration Path
```bash
# Replace XX with your actual version (15, 16, etc.)
sudo nano /etc/postgresql/XX/main/postgresql.conf
sudo nano /etc/postgresql/XX/main/pg_hba.conf
```

### Alternative: Universal Configuration Method
```bash
# Find config file location automatically
PG_CONFIG=$(sudo -u postgres psql -t -c "SHOW config_file;" | xargs)
echo "Config file location: $PG_CONFIG"

# Edit the config file directly
sudo nano "$PG_CONFIG"

# Find the data directory for pg_hba.conf
PG_HBA=$(sudo -u postgres psql -t -c "SHOW hba_file;" | xargs)
echo "HBA file location: $PG_HBA"

# Edit the HBA file directly
sudo nano "$PG_HBA"
```

### Common Version-Specific Paths

#### Ubuntu 22.04 LTS (Most Common)
```bash
# PostgreSQL 14
/etc/postgresql/14/main/

# PostgreSQL 15
/etc/postgresql/15/main/

# PostgreSQL 16 (if installed from PostgreSQL official repo)
/etc/postgresql/16/main/
```

#### Ubuntu 20.04 LTS
```bash
# PostgreSQL 12
/etc/postgresql/12/main/

# PostgreSQL 13
/etc/postgresql/13/main/
```

### Updated Configuration Steps

#### For PostgreSQL 15 (Most likely on fresh Ubuntu 22.04):
```bash
# Edit main configuration
sudo nano /etc/postgresql/15/main/postgresql.conf

# Uncomment and set:
listen_addresses = 'localhost'
port = 5432

# Edit authentication
sudo nano /etc/postgresql/15/main/pg_hba.conf

# Add BEFORE existing local entries:
local   cardmarketscan   cmsuser                 md5

# Restart service
sudo systemctl restart postgresql
```

#### For PostgreSQL 16:
```bash
# Edit main configuration
sudo nano /etc/postgresql/16/main/postgresql.conf

# Edit authentication  
sudo nano /etc/postgresql/16/main/pg_hba.conf

# Restart service
sudo systemctl restart postgresql
```

### Verification Commands
```bash
# Test database connection
psql -h localhost -U cmsuser -d cardmarketscan

# Check PostgreSQL is listening
sudo netstat -plntu | grep 5432

# View PostgreSQL logs if issues persist
sudo journalctl -u postgresql -n 20
```

### If PostgreSQL Installation Failed

#### Complete Reinstall
```bash
# Remove existing PostgreSQL
sudo apt remove --purge postgresql postgresql-*
sudo apt autoremove

# Clean up remaining files
sudo rm -rf /etc/postgresql/
sudo rm -rf /var/lib/postgresql/

# Install PostgreSQL from official repository (latest version)
sudo apt install -y wget ca-certificates
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
echo "deb http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" | sudo tee /etc/apt/sources.list.d/pgdg.list

sudo apt update
sudo apt install -y postgresql-15 postgresql-client-15 postgresql-contrib-15

# Start and enable service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify installation
sudo systemctl status postgresql
```

### Quick Fix Script
```bash
# Create auto-detection script
cat > ~/fix_postgresql.sh << 'EOF'
#!/bin/bash
echo "🔍 Detecting PostgreSQL installation..."

# Find PostgreSQL version
PGVERSION=$(sudo -u postgres psql -t -c "SELECT version();" 2>/dev/null | grep -oE '[0-9]+' | head -1)

if [ -z "$PGVERSION" ]; then
    echo "❌ PostgreSQL not running or not installed"
    exit 1
fi

echo "✅ Found PostgreSQL version: $PGVERSION"

# Check config directory
CONFIG_DIR="/etc/postgresql/$PGVERSION/main"
if [ -d "$CONFIG_DIR" ]; then
    echo "✅ Config directory exists: $CONFIG_DIR"
    echo "📝 Edit files:"
    echo "   sudo nano $CONFIG_DIR/postgresql.conf"
    echo "   sudo nano $CONFIG_DIR/pg_hba.conf"
else
    echo "❌ Expected directory not found: $CONFIG_DIR"
    echo "🔍 Searching for config files..."
    sudo find /etc -name "postgresql.conf" 2>/dev/null
fi
EOF

chmod +x ~/fix_postgresql.sh
./fix_postgresql.sh
```

### Summary
The most likely solution for your case:
1. Run `sudo -u postgres psql -c "SELECT version();"` to get the version
2. Replace "14" with your actual version number (probably 15 or 16)
3. Use the correct path: `/etc/postgresql/15/main/` or `/etc/postgresql/16/main/`