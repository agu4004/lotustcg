# Lotus TCG with Authentication

A Flask-based trading card game storefront with secure role-based authentication, featuring admin controls for inventory management and user access to browse and purchase cards.

## Features

### 🔐 Authentication & Authorization
- **Flask-Login** integration for session-based authentication
- **Role-based access control** (Admin/User roles)
- Secure password hashing with werkzeug
- User registration and login system
- Admin-only areas and functionality

### 🃏 Card Management
- Browse card catalog with advanced search and filtering
- Session-based shopping cart
- Admin card CRUD operations via API
- CSV bulk import/export for inventory management
- Card details with quantities and pricing

### 🎨 User Interface
- Responsive Bootstrap 5 dark theme design
- Font Awesome icons throughout
- Conditional UI elements based on user role
- Mobile-friendly responsive layout
- Real-time cart updates

## Quick Start

### 1. Set Replit Secrets

In your Replit project, go to **Secrets** tab and add:

```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_admin_password
SESSION_SECRET=your_secret_session_key
```

### 2. Start the Development Server

The application starts automatically with Replit's workflow system:

```bash
# Development mode (auto-reload)
flask run --reload --host=0.0.0.0 --port=5000

# Or use the production server
gunicorn -w 1 -b 0.0.0.0:5000 app:app
```

### 3. Access the Application

- **Home**: Browse featured cards and get started
- **Catalog**: Search and filter available cards
- **Cart**: Manage selected items
- **Admin** (admin only): Manage inventory and users

## Demo Credentials

### Admin Account
- **Username**: `admin`
- **Password**: `admin123` (or your custom password from secrets)
- **Permissions**: Full access to admin panel, card CRUD, CSV management

### Regular User Account
- **Username**: `user`
- **Password**: `user123`
- **Permissions**: Browse catalog, manage cart (no admin access)

## API Endpoints

### Public Routes
- `GET /` - Home page with featured cards
- `GET /catalog` - Card catalog with search/filters
- `GET /card/<id>` - Individual card details
- `GET /cart` - Shopping cart view

### Authentication Routes
- `GET/POST /login` - User login
- `GET/POST /register` - User registration
- `GET /logout` - User logout

### Admin-Only Routes
- `GET /admin` - Admin dashboard
- `POST /admin/upload_csv` - CSV card upload
- `POST /admin/clear_cards` - Clear all inventory

### Admin-Only API
- `POST /api/cards` - Create new card
- `PUT /api/cards/<id>` - Update existing card
- `DELETE /api/cards/<id>` - Delete card

## CSV Format for Bulk Import

The system accepts CSV files with the following columns:

| Column | Required | Description | Example |
|--------|----------|-------------|---------|
| `name` | Yes | Card name | "Lightning Bolt" |
| `set_name` | No | Set/expansion | "Core Set" |
| `rarity` | No | Card rarity | "Common", "Rare", "Mythic Rare" |
| `condition` | No | Card condition | "Near Mint", "Light Play" |
| `price` | No | Price in dollars | 1.50 |
| `quantity` | No | Number available | 10 |
| `description` | No | Card description | "Classic red instant spell" |

### Sample CSV
```csv
name,set_name,rarity,condition,price,quantity,description
"Lightning Bolt","Core Set","Common","Near Mint",1.50,10,"Classic red instant spell"
"Black Lotus","Alpha","Mythic Rare","Light Play",5000.00,1,"The most powerful mox"
"Counterspell","Beta","Common","Near Mint",25.00,5,"Counter target spell"
```

## Acceptance Testing

### Test 1: Guest Access
1. Visit `/` as a guest
2. ✅ See cards without admin buttons
3. ✅ Cannot access `/admin` (redirects to login)

### Test 2: Regular User
1. Register new user or login with `user/user123`
2. ✅ Browse catalog and add to cart
3. ✅ No admin buttons visible
4. ❌ POST to `/api/cards` returns **403 Forbidden**

### Test 3: Admin Access
1. Login with admin credentials (`admin/admin123`)
2. ✅ `/admin` dashboard loads successfully
3. ✅ CRUD API routes return **200 OK**
4. ✅ Admin buttons visible throughout interface

### Test 4: CSV Workflow
1. Login as admin
2. Add cards via CSV upload
3. Export current inventory
4. Clear all cards
5. Re-import from exported CSV
6. ✅ Data restored successfully

## Technical Architecture

### Backend Stack
- **Flask 3.x** - Web framework
- **Flask-Login** - Authentication management
- **Werkzeug** - Password hashing and utilities
- **Gunicorn** - Production WSGI server
- **Python 3.11** - Runtime environment

### Frontend Stack
- **Jinja2** - Template engine
- **Bootstrap 5** - CSS framework with dark theme
- **Font Awesome 6** - Icon library
- **Vanilla JavaScript** - Interactive features

### Data Layer
- **In-memory storage** - Dictionary-based card storage
- **Flask sessions** - Cart and user session management
- **CSV processing** - Built-in Python module for bulk operations

### Security Features
- Password hashing with salt
- Session-based authentication
- Role-based access control
- CSRF protection on forms
- Input validation and sanitization

## Project Structure

```
├── app.py              # Flask application factory
├── main.py             # Application entry point
├── models.py           # User models and authentication
├── auth.py             # Authentication decorators
├── routes.py           # All route handlers
├── storage.py          # In-memory data storage
├── templates/          # Jinja2 templates
│   ├── base.html       # Master template
│   ├── index.html      # Home page
│   ├── catalog.html    # Card catalog
│   ├── cart.html       # Shopping cart
│   ├── admin.html      # Admin dashboard
│   ├── login.html      # Login form
│   └── register.html   # Registration form
├── static/
│   └── style.css       # Custom styles
└── README.md           # This file
```

## Development Notes

- Uses in-memory storage suitable for development/demo
- Cart data persists through login/logout via sessions
- Admin user automatically created from environment variables
- No database required - perfect for Replit deployment
- Production-ready with proper error handling and logging

## Scaling Considerations

For production deployment, consider:
- Replace in-memory storage with PostgreSQL/SQLite
- Add user email verification
- Implement proper password reset functionality  
- Add rate limiting for API endpoints
- Set up proper logging and monitoring
- Enable HTTPS in production environment

## License

This project is for educational and demonstration purposes.