# 🌸 LotusTCG Deployment Package

## What's Included

This deployment package contains everything you need to deploy your LotusTCG Flask application to AWS Lightsail.

### Application Files
- `app.py` - Flask application factory and configuration
- `models.py` - Database models (User, Card)
- `routes.py` - All application routes and endpoints
- `auth.py` - Authentication decorators and utilities
- `main.py` - Application entry point
- `storage_db.py` - Database operations and utilities
- `seed_database.py` - Sample data seeding script
- `templates/` - Jinja2 HTML templates
- `static/` - CSS, JavaScript, and asset files

### Deployment Guides
- `LOTUSTCG_DEPLOYMENT_GUIDE.md` - Complete step-by-step deployment guide
- `LOTUSTCG_QUICK_SETUP.md` - Fast deployment commands
- `LOTUSTCG_TROUBLESHOOTING.md` - Common issues and solutions

## Quick Start

1. **Upload Files**: Extract this package to `/home/ubuntu/lotustcg/` on your AWS Lightsail Ubuntu server

2. **Run Quick Setup**: Follow commands in `LOTUSTCG_QUICK_SETUP.md`

3. **Access Application**: Your LotusTCG site will be available at your server's IP address

## Default Login Credentials

- **Admin**: admin@lotustcg.com / admin123
- **User**: user@lotustcg.com / user123

**Important**: Change these passwords after first login!

## Database Configuration

The application uses these database settings:
- **Database**: `lotustcg`
- **User**: `ltcguser`
- **Password**: `ltcg_secure_password_2024`
- **Connection**: `postgresql://ltcguser:ltcg_secure_password_2024@localhost:5432/lotustcg`

## Features

- User authentication and role-based access control
- Card catalog with search and filtering
- Shopping cart functionality
- Admin panel for inventory management
- CSV import/export for bulk operations
- Responsive Bootstrap design
- PostgreSQL database persistence

## System Requirements

- AWS Lightsail Ubuntu 20.04+ instance
- Minimum 2GB RAM, 1 vCPU ($10/month plan)
- PostgreSQL 12+
- Python 3.8+
- Nginx web server

## Support

If you encounter issues:
1. Check `LOTUSTCG_TROUBLESHOOTING.md`
2. Verify all steps in `LOTUSTCG_DEPLOYMENT_GUIDE.md`
3. Check service logs: `sudo journalctl -u lotustcg -n 50`

Your LotusTCG application is ready for deployment!