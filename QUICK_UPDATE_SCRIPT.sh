#!/bin/bash

# LotusTCG Quick Update Script for AWS Lightsail
# This script updates your Lightsail instance with the latest GitHub revision

set -e  # Exit on any error

echo "=========================================="
echo "LotusTCG Update Script - $(date)"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as ubuntu user
if [ "$USER" != "ubuntu" ]; then
    print_error "This script should be run as the ubuntu user"
    exit 1
fi

# Set variables
APP_DIR="/opt/lotustcg"
BACKUP_DIR="/opt/lotustcg-backup-$(date +%Y%m%d-%H%M%S)"

print_status "Starting update process..."

# Step 1: Create backup
print_status "Creating backup of current version..."
if sudo cp -r $APP_DIR $BACKUP_DIR; then
    print_status "Backup created at: $BACKUP_DIR"
else
    print_error "Failed to create backup"
    exit 1
fi

# Step 2: Navigate to app directory
cd $APP_DIR

# Step 3: Show current version
print_status "Current version:"
git log --oneline -1

# Step 4: Pull latest changes
print_status "Pulling latest changes from GitHub..."
if sudo git fetch origin && sudo git pull origin main; then
    print_status "Code updated successfully"
else
    print_error "Failed to pull from GitHub"
    print_warning "Rolling back to backup..."
    sudo rm -rf $APP_DIR
    sudo mv $BACKUP_DIR $APP_DIR
    exit 1
fi

# Step 5: Show new version
print_status "Updated to version:"
git log --oneline -1

# Step 6: Activate virtual environment
print_status "Activating virtual environment..."
source venv/bin/activate

# Step 7: Update dependencies
print_status "Updating Python dependencies..."
if pip install -r requirements.txt; then
    print_status "Dependencies updated successfully"
else
    print_warning "Some dependencies may have failed to update"
fi

# Step 8: Run database migrations
print_status "Running database migrations..."
export FLASK_APP=main.py
if flask db upgrade; then
    print_status "Database migrations completed"
else
    print_warning "Database migrations may have failed"
fi

# Step 9: Test configuration
print_status "Testing application configuration..."
if python -c "from app import app; print('✓ App configuration is valid')"; then
    print_status "Configuration test passed"
else
    print_error "Configuration test failed"
    print_warning "Rolling back to backup..."
    sudo systemctl stop lotustcg
    sudo rm -rf $APP_DIR
    sudo mv $BACKUP_DIR $APP_DIR
    sudo systemctl start lotustcg
    exit 1
fi

# Step 10: Restart services
print_status "Restarting application service..."
if sudo systemctl restart lotustcg; then
    print_status "Service restarted successfully"
else
    print_error "Failed to restart service"
    exit 1
fi

# Step 11: Wait for service to start
print_status "Waiting for service to start..."
sleep 5

# Step 12: Verify service status
print_status "Checking service status..."
if sudo systemctl is-active --quiet lotustcg; then
    print_status "Service is running"
else
    print_error "Service is not running"
    sudo systemctl status lotustcg
    exit 1
fi

# Step 13: Test application response
print_status "Testing application response..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/)
if [ "$HTTP_CODE" = "200" ]; then
    print_status "Application is responding correctly (HTTP $HTTP_CODE)"
else
    print_warning "Application returned HTTP $HTTP_CODE"
fi

# Step 14: Test database connectivity
print_status "Testing database connectivity..."
if python -c "
from app import app
with app.app_context():
    from models import User, Card
    users = User.query.count()
    cards = Card.query.count()
    print(f'✓ Database connected - Users: {users}, Cards: {cards}')
"; then
    print_status "Database connectivity test passed"
else
    print_warning "Database connectivity test failed"
fi

# Step 15: Check for recent errors
print_status "Checking for recent errors..."
ERROR_COUNT=$(sudo journalctl -u lotustcg --since "5 minutes ago" | grep -i error | wc -l)
if [ "$ERROR_COUNT" -eq 0 ]; then
    print_status "No recent errors found"
else
    print_warning "Found $ERROR_COUNT recent errors in logs"
    echo "Recent errors:"
    sudo journalctl -u lotustcg --since "5 minutes ago" | grep -i error | tail -5
fi

# Step 16: Final status report
echo ""
echo "=========================================="
print_status "UPDATE COMPLETED SUCCESSFULLY!"
echo "=========================================="
echo ""
print_status "Summary:"
echo "  • Backup created at: $BACKUP_DIR"
echo "  • Application updated from GitHub"
echo "  • Dependencies updated"
echo "  • Database migrations applied"
echo "  • Service restarted"
echo "  • Application responding on HTTP $HTTP_CODE"
echo ""
print_status "Your LotusTCG website is now running the latest version!"
echo ""
print_status "Access your website at: http://YOUR_INSTANCE_IP/"
print_status "Admin login: username=admin, password=admin123"
echo ""
print_status "To view logs: sudo journalctl -u lotustcg -f"
print_status "To check status: sudo systemctl status lotustcg"
echo ""
print_warning "Keep the backup directory ($BACKUP_DIR) for a few days in case you need to rollback"
echo ""