# TCG Card Shop

## Overview

TCG Card Shop is a Flask-based web application for managing and browsing trading card game collections. The application provides a complete e-commerce experience with card catalog browsing, search functionality, shopping cart management, and administrative tools for inventory management. Users can search and filter cards by various criteria, add items to their cart, and administrators can upload card data via CSV files.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Template Engine**: Jinja2 templates with Flask for server-side rendering
- **UI Framework**: Bootstrap 5 with dark theme for responsive design
- **Styling**: Custom CSS with hover effects and responsive design improvements
- **Icons**: Font Awesome for consistent iconography
- **Layout**: Master template (`base.html`) with template inheritance for consistent navigation and styling

### Backend Architecture
- **Web Framework**: Flask with modular route organization
- **Application Structure**: 
  - `app.py` - Application factory and configuration
  - `routes.py` - Route handlers for all endpoints
  - `main.py` - Application entry point
- **Session Management**: Flask sessions with configurable secret key
- **Logging**: Python logging module with debug-level configuration

### Data Storage
- **Storage Layer**: In-memory storage implementation (`storage.py`)
- **Data Structure**: Dictionary-based card storage with auto-incrementing IDs
- **Search Functionality**: Built-in filtering by name, set, rarity, and price range
- **Data Import**: CSV upload functionality for bulk card management

### Core Features
- **Card Management**: CRUD operations for trading cards with attributes (name, set, rarity, condition, price, quantity)
- **Search & Filtering**: Multi-criteria search with real-time filtering
- **Shopping Cart**: Session-based cart management with quantity controls
- **Admin Panel**: CSV upload/download for inventory management
- **Responsive Design**: Mobile-first Bootstrap implementation

### Route Structure
- `/` - Home page with featured cards
- `/catalog` - Card browsing with search and filters
- `/admin` - Administrative interface for card management
- `/cart` - Shopping cart management
- `/card/<id>` - Individual card detail pages

## External Dependencies

### Frontend Libraries
- **Bootstrap 5**: UI component framework with dark theme
- **Font Awesome 6.4.0**: Icon library for interface elements
- **CDN Delivery**: External CDN hosting for CSS frameworks

### Python Packages
- **Flask**: Core web framework for routing and templating
- **Standard Library**: Built-in modules for logging, CSV processing, and file handling

### Development Tools
- **Debug Mode**: Flask development server with auto-reload
- **Logging**: Comprehensive logging for debugging and monitoring

### File Processing
- **CSV Support**: Built-in Python CSV module for data import/export
- **File Uploads**: Flask file handling for CSV uploads
- **Sample Data**: Template generation for CSV format guidance

Note: The application currently uses in-memory storage, making it suitable for development and demonstration purposes. For production deployment, integration with a persistent database solution would be recommended.