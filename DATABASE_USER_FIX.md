# Database User Authentication Fix

## Issue
Getting password authentication failed for user "cmsuser", but that's not your actual database user.

## Solution Steps

### 1. Identify Your Actual Database User
```bash
# Check what database and user you actually created
sudo -u postgres psql -c "\l" | grep cardmarketscan
sudo -u postgres psql -c "\du"
```

This will show:
- Your actual database name
- Your actual database user name

### 2. Common Scenarios

**If you used the original setup:**
- Database: `tcg_card_shop` 
- User: `tcguser`
- Password: `tcg_secure_password_2024`

**If you followed the CardMarketScan rebrand:**
- Database: `cardmarketscan`
- User: `cmsuser` 
- Password: `cms_secure_password_2024`

**If you created your own names:**
- Check the output from step 1 above

### 3. Update Environment Variables

Once you know your actual database details, update the DATABASE_URL:

```bash
# For original setup (tcguser):
export DATABASE_URL=postgresql://tcguser:tcg_secure_password_2024@localhost:5432/tcg_card_shop

# For CardMarketScan setup (cmsuser):
export DATABASE_URL=postgresql://cmsuser:cms_secure_password_2024@localhost:5432/cardmarketscan

# For custom setup - replace with your actual values:
export DATABASE_URL=postgresql://YOUR_USER:YOUR_PASSWORD@localhost:5432/YOUR_DATABASE
```

### 4. Test Database Connection
```bash
# Test the connection directly
psql "$DATABASE_URL" -c "\dt"
```

### 5. Create Missing User (if needed)

If the user doesn't exist, create it:
```bash
sudo -u postgres psql
CREATE USER cmsuser WITH ENCRYPTED PASSWORD 'cms_secure_password_2024';
GRANT ALL PRIVILEGES ON DATABASE cardmarketscan TO cmsuser;
ALTER DATABASE cardmarketscan OWNER TO cmsuser;
\q
```

## Quick Diagnostic Commands

Run these to identify your setup:
```bash
echo "=== Checking PostgreSQL databases ==="
sudo -u postgres psql -c "\l" | grep -E "(tcg|card)"

echo "=== Checking PostgreSQL users ==="
sudo -u postgres psql -c "\du" | grep -E "(tcg|cms|user)"

echo "=== Current DATABASE_URL ==="
echo $DATABASE_URL
```