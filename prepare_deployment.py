#!/usr/bin/env python3
"""
Deployment preparation script for CardMarketScan
Creates a deployment package with all necessary files
"""

import os
import shutil
import zipfile
from pathlib import Path

def create_deployment_package():
    """Create a deployment-ready package"""
    
    # Files to include in deployment
    essential_files = [
        'app.py',
        'main.py', 
        'models.py',
        'routes.py',
        'auth.py',
        'storage_db.py',
        'seed_database.py',
        'DEPLOYMENT_GUIDE.md',
        'deployment_checklist.txt',
        'MIGRATION_REPORT.md',
        'README.md'
    ]
    
    # Directories to include
    essential_dirs = [
        'templates',
        'static',
        'migrations'
    ]
    
    # Create deployment directory
    deploy_dir = Path('deployment_package')
    if deploy_dir.exists():
        shutil.rmtree(deploy_dir)
    deploy_dir.mkdir()
    
    # Copy essential files
    print("📁 Copying essential files...")
    for file in essential_files:
        if os.path.exists(file):
            shutil.copy2(file, deploy_dir)
            print(f"  ✓ {file}")
        else:
            print(f"  ⚠️  {file} not found")
    
    # Copy directories
    print("\n📂 Copying directories...")
    for dir_name in essential_dirs:
        if os.path.exists(dir_name):
            shutil.copytree(dir_name, deploy_dir / dir_name)
            print(f"  ✓ {dir_name}/")
        else:
            print(f"  ⚠️  {dir_name}/ not found")
    
    # Create requirements.txt for deployment
    requirements_content = """Flask==3.0.3
Flask-Login==0.6.3
Flask-SQLAlchemy==3.1.1
Flask-Migrate==4.0.5
SQLAlchemy==2.0.23
psycopg2-binary==2.9.9
Werkzeug==3.0.4
gunicorn==21.2.0
email-validator==2.1.1"""
    
    with open(deploy_dir / 'requirements.txt', 'w') as f:
        f.write(requirements_content)
    print("  ✓ requirements.txt created")
    
    # Create environment template
    env_template = """# Environment variables for production deployment
DATABASE_URL=postgresql://tcguser:YOUR_PASSWORD@localhost:5432/tcg_card_shop
SESSION_SECRET=your_super_secret_session_key_here_change_this
FLASK_APP=main.py
FLASK_ENV=production
PGHOST=localhost
PGPORT=5432
PGUSER=tcguser
PGPASSWORD=YOUR_PASSWORD
PGDATABASE=tcg_card_shop"""
    
    with open(deploy_dir / '.env.template', 'w') as f:
        f.write(env_template)
    print("  ✓ .env.template created")
    
    # Create quick start script
    start_script = """#!/bin/bash
# Quick start script for CardMarketScan

echo "🚀 Starting CardMarketScan..."

# Activate virtual environment
source venv/bin/activate

# Load environment variables
export $(cat .env | xargs)

# Start application with Gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 3 main:app

echo "✅ Application started on http://localhost:5000"
echo "📚 Admin login: admin/admin123"
echo "👤 User login: user/user123"
"""
    
    with open(deploy_dir / 'start.sh', 'w') as f:
        f.write(start_script)
    os.chmod(deploy_dir / 'start.sh', 0o755)
    print("  ✓ start.sh created")
    
    # Create deployment info file
    info_content = """CardMarketScan - Deployment Package

This package contains everything needed to deploy the CardMarketScan to AWS Lightsail.

WHAT'S INCLUDED:
- Complete Flask application with PostgreSQL support
- HTML templates with Bootstrap styling
- Database models and migration support
- Authentication system with role-based access
- Admin panel with CSV upload/download
- Comprehensive deployment guide

QUICK START:
1. Follow DEPLOYMENT_GUIDE.md for complete setup
2. Use deployment_checklist.txt to track progress
3. Copy .env.template to .env and update credentials
4. Run ./start.sh to start the application

FEATURES:
- Role-based authentication (admin/user)
- Card catalog with search and filtering
- Shopping cart functionality
- Admin CSV import/export
- PostgreSQL database persistence
- Production-ready with Gunicorn + Nginx

DEMO CREDENTIALS:
- Admin: username=admin, password=admin123
- User: username=user, password=user123

ESTIMATED DEPLOYMENT TIME: 45-60 minutes
MONTHLY HOSTING COST: $10-20 USD on AWS Lightsail

For detailed instructions, see DEPLOYMENT_GUIDE.md
"""
    
    with open(deploy_dir / 'DEPLOYMENT_INFO.txt', 'w') as f:
        f.write(info_content)
    print("  ✓ DEPLOYMENT_INFO.txt created")
    
    # Create ZIP package
    print(f"\n📦 Creating deployment ZIP package...")
    with zipfile.ZipFile('cardmarketscan-deployment.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(deploy_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arc_name = os.path.relpath(file_path, deploy_dir)
                zipf.write(file_path, arc_name)
                
    package_size = os.path.getsize('cardmarketscan-deployment.zip') / 1024 / 1024
    print(f"  ✓ cardmarketscan-deployment.zip created ({package_size:.1f} MB)")
    
    # Summary
    print(f"\n🎉 Deployment package ready!")
    print(f"📁 Files packaged: {len(essential_files)} files + {len(essential_dirs)} directories")
    print(f"📦 ZIP package: cardmarketscan-deployment.zip")
    print(f"📖 Follow DEPLOYMENT_GUIDE.md for AWS Lightsail deployment")
    
    return deploy_dir, 'cardmarketscan-deployment.zip'

if __name__ == '__main__':
    print("🛠️  CardMarketScan - Deployment Package Creator")
    print("=" * 50)
    
    try:
        package_dir, zip_file = create_deployment_package()
        print(f"\n✅ Success! Your deployment package is ready.")
        print(f"📁 Package directory: {package_dir}")
        print(f"📦 ZIP file: {zip_file}")
        print(f"\n🚀 Next step: Upload to your AWS Lightsail instance and follow DEPLOYMENT_GUIDE.md")
        
    except Exception as e:
        print(f"\n❌ Error creating deployment package: {e}")
        exit(1)