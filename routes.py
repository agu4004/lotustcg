from flask import render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from app import app, db
from storage_db import storage
from models import User
from auth import admin_required, get_redirect_target
import logging

logger = logging.getLogger(__name__)

@app.route('/')
def index():
    """Home page with featured cards"""
    cards = storage.get_all_cards()
    # Show first 6 cards as featured
    featured_cards = cards[:6] if cards else []
    return render_template('index.html', featured_cards=featured_cards, total_cards=len(cards))

@app.route('/catalog')
def catalog():
    """Card catalog with search and filtering"""
    # Get search parameters
    query = request.args.get('q', '').strip()
    set_filter = request.args.get('set', '')
    rarity_filter = request.args.get('rarity', '')
    
    # Price range filters
    min_price = None
    max_price = None
    try:
        min_price_str = request.args.get('min_price')
        if min_price_str:
            min_price = float(min_price_str)
    except (ValueError, TypeError):
        pass
    
    try:
        max_price_str = request.args.get('max_price')
        if max_price_str:
            max_price = float(max_price_str)
    except (ValueError, TypeError):
        pass
    
    # Search cards
    cards = storage.search_cards(
        query=query,
        set_filter=set_filter,
        rarity_filter=rarity_filter,
        min_price=min_price,
        max_price=max_price
    )
    
    # Get filter options
    all_sets = storage.get_unique_sets()
    all_rarities = storage.get_unique_rarities()
    
    return render_template('catalog.html', 
                         cards=cards, 
                         all_sets=all_sets,
                         all_rarities=all_rarities,
                         current_filters={
                             'q': query,
                             'set': set_filter,
                             'rarity': rarity_filter,
                             'min_price': request.args.get('min_price', ''),
                             'max_price': request.args.get('max_price', '')
                         })

@app.route('/card/<card_id>')
def card_detail(card_id):
    """Card detail page"""
    card = storage.get_card(card_id)
    if not card:
        flash('Card not found', 'error')
        return redirect(url_for('catalog'))
    
    return render_template('card_detail.html', card=card)

@app.route('/add_to_cart/<card_id>', methods=['POST'])
def add_to_cart(card_id):
    """Add card to cart"""
    card = storage.get_card(card_id)
    if not card:
        flash('Card not found', 'error')
        return redirect(url_for('catalog'))
    
    quantity = int(request.form.get('quantity', 1))
    
    # Check if enough quantity is available
    if quantity > card['quantity']:
        flash(f'Only {card["quantity"]} copies available', 'error')
        return redirect(url_for('card_detail', card_id=card_id))
    
    # Initialize cart if not exists
    if 'cart' not in session:
        session['cart'] = {}
    
    # Add to cart
    if card_id in session['cart']:
        session['cart'][card_id] += quantity
    else:
        session['cart'][card_id] = quantity
    
    # Update session
    session.modified = True
    
    flash(f'Added {quantity} x {card["name"]} to cart', 'success')
    return redirect(url_for('card_detail', card_id=card_id))

@app.route('/cart')
def view_cart():
    """View shopping cart"""
    cart_items = []
    cart = session.get('cart', {})
    total_price = 0
    
    for card_id, quantity in cart.items():
        card = storage.get_card(card_id)
        if card:
            item_total = card['price'] * quantity
            cart_items.append({
                'card': card,
                'quantity': quantity,
                'item_total': item_total
            })
            total_price += item_total
    
    return render_template('cart.html', cart_items=cart_items, total_price=total_price)

@app.route('/update_cart/<card_id>', methods=['POST'])
def update_cart(card_id):
    """Update cart item quantity"""
    if 'cart' not in session:
        session['cart'] = {}
    
    quantity = int(request.form.get('quantity', 0))
    
    if quantity <= 0:
        # Remove item from cart
        if card_id in session['cart']:
            del session['cart'][card_id]
            flash('Item removed from cart', 'info')
    else:
        # Update quantity
        card = storage.get_card(card_id)
        if card and quantity <= card['quantity']:
            session['cart'][card_id] = quantity
            flash('Cart updated', 'success')
        else:
            flash('Invalid quantity', 'error')
    
    session.modified = True
    return redirect(url_for('view_cart'))

@app.route('/clear_cart', methods=['POST'])
def clear_cart():
    """Clear shopping cart"""
    session.pop('cart', None)
    flash('Cart cleared', 'info')
    return redirect(url_for('view_cart'))

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        
        if not username or not password:
            flash('Please enter both username and password', 'error')
            return render_template('login.html')
        
        # Authenticate user with database
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash(f'Welcome back, {user.username}!', 'success')
            
            # Redirect to next page or home
            next_page = get_redirect_target()
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    username = current_user.username
    logout_user()
    flash(f'Goodbye, {username}!', 'info')
    return redirect(url_for('index'))

@app.route('/admin')
@admin_required
def admin():
    """Admin panel - requires admin role"""
    cards = storage.get_all_cards()
    users = User.query.all()
    return render_template('admin.html', cards=cards, users=users)

@app.route('/admin/upload_csv', methods=['POST'])
@admin_required
def upload_csv():
    """Handle CSV upload - admin only"""
    if 'csv_file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('admin'))
    
    file = request.files['csv_file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('admin'))
    
    if not file.filename or not file.filename.endswith('.csv'):
        flash('Please upload a CSV file', 'error')
        return redirect(url_for('admin'))
    
    try:
        # Read file content
        csv_content = file.read().decode('utf-8')
        
        # Process CSV
        results = storage.process_csv_upload(csv_content)
        
        # Show results
        if results['success'] > 0:
            flash(f'Successfully imported {results["success"]} cards', 'success')
        
        if results['errors']:
            for error in results['errors'][:10]:  # Show first 10 errors
                flash(error, 'error')
            
            if len(results['errors']) > 10:
                flash(f'... and {len(results["errors"]) - 10} more errors', 'error')
    
    except Exception as e:
        flash(f'Error processing file: {str(e)}', 'error')
        logger.error(f"CSV upload error: {e}")
    
    return redirect(url_for('admin'))

@app.route('/admin/clear_cards', methods=['POST'])
@admin_required
def clear_cards():
    """Clear all cards - admin only"""
    storage.clear_all_cards()
    flash('All cards cleared', 'info')
    return redirect(url_for('admin'))

# CRUD API endpoints for cards
@app.route('/api/cards', methods=['POST'])
@admin_required
def create_card():
    """Create a new card - admin only"""
    try:
        data = request.get_json()
        if not data or not data.get('name'):
            return jsonify({'error': 'Card name is required'}), 400
        
        card_id = storage.add_card(data)
        card = storage.get_card(card_id)
        return jsonify({'success': True, 'card': card, 'id': card_id}), 201
    except Exception as e:
        logger.error(f"Error creating card: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cards/<card_id>', methods=['PUT'])
@admin_required
def update_card(card_id):
    """Update a card - admin only"""
    try:
        from models import Card
        card = Card.query.get(int(card_id))
        if not card:
            return jsonify({'error': 'Card not found'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Update card data
        for key, value in data.items():
            if key != 'id' and hasattr(card, key):  # Don't allow ID changes
                setattr(card, key, value)
        
        db.session.commit()
        return jsonify({'success': True, 'card': card.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating card: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cards/<card_id>', methods=['DELETE'])
@admin_required
def delete_card(card_id):
    """Delete a card - admin only"""
    try:
        from models import Card
        card = Card.query.get(int(card_id))
        if not card:
            return jsonify({'error': 'Card not found'}), 404
        
        # Remove card from database
        db.session.delete(card)
        db.session.commit()
        logger.debug(f"Deleted card: {card.name} (ID: {card_id})")
        return jsonify({'success': True, 'message': 'Card deleted'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting card: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/sample_csv')
def download_sample_csv():
    """Download sample CSV template"""
    from flask import Response
    
    sample_csv = """name,set_name,rarity,condition,price,quantity,description,image_url
"Lightning Bolt","Core Set","Common","Near Mint",1.50,10,"Classic red instant spell","https://example.com/lightning-bolt.jpg"
"Black Lotus","Alpha","Mythic Rare","Light Play",5000.00,1,"The most powerful mox","https://example.com/black-lotus.jpg"
"Counterspell","Beta","Common","Near Mint",25.00,5,"Counter target spell","https://example.com/counterspell.jpg"
"""
    
    return Response(
        sample_csv,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=sample_cards.csv'}
    )

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('base.html', error_title="Page Not Found", 
                         error_message="The page you're looking for doesn't exist."), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('base.html', error_title="Internal Server Error", 
                         error_message="Something went wrong on our end."), 500

# Template context processors
@app.context_processor
def cart_processor():
    """Add cart info to all templates"""
    cart = session.get('cart', {})
    cart_count = sum(cart.values()) if cart else 0
    return {'cart_count': cart_count}

@app.context_processor
def auth_processor():
    """Add authentication info to all templates"""
    return {
        'current_user': current_user,
        'is_admin': current_user.is_authenticated and current_user.is_admin() if hasattr(current_user, 'is_admin') else False
    }

# New admin routes for inline editing and deletion
@app.route('/admin/edit_card/<card_id>', methods=['POST'])
@admin_required
def edit_card_form(card_id):
    """Handle inline card editing - admin only"""
    try:
        from models import Card
        card = Card.query.get(int(card_id))
        if not card:
            flash('Card not found', 'error')
            return redirect(url_for('admin'))
        
        # Get form data
        card.name = request.form.get('name', card.name)
        card.set_name = request.form.get('set_name', card.set_name)
        card.rarity = request.form.get('rarity', card.rarity)
        card.condition = request.form.get('condition', card.condition)
        card.description = request.form.get('description', card.description)
        card.image_url = request.form.get('image_url', card.image_url)
        
        # Handle numeric fields with validation
        try:
            price = request.form.get('price')
            if price:
                card.price = float(price)
        except (ValueError, TypeError):
            flash('Invalid price format', 'error')
            return redirect(url_for('admin'))
        
        try:
            quantity = request.form.get('quantity')
            if quantity:
                card.quantity = int(quantity)
        except (ValueError, TypeError):
            flash('Invalid quantity format', 'error')
            return redirect(url_for('admin'))
        
        db.session.commit()
        flash(f'Card "{card.name}" updated successfully', 'success')
        logger.debug(f"Updated card: {card.name} (ID: {card_id})")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating card: {e}")
        flash(f'Error updating card: {str(e)}', 'error')
    
    return redirect(url_for('admin'))

@app.route('/admin/delete_card/<card_id>', methods=['POST'])
@admin_required
def delete_card_form(card_id):
    """Handle card deletion - admin only"""
    try:
        from models import Card
        card = Card.query.get(int(card_id))
        if not card:
            flash('Card not found', 'error')
            return redirect(url_for('admin'))
        
        card_name = card.name
        db.session.delete(card)
        db.session.commit()
        
        flash(f'Card "{card_name}" deleted successfully', 'success')
        logger.debug(f"Deleted card: {card_name} (ID: {card_id})")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting card: {e}")
        flash(f'Error deleting card: {str(e)}', 'error')
    
    return redirect(url_for('admin'))

@app.route('/admin/add_card', methods=['POST'])
@admin_required
def add_card_form():
    """Handle manual card addition - admin only"""
    try:
        from models import Card
        
        # Validate required fields
        name = request.form.get('name', '').strip()
        if not name:
            flash('Card name is required', 'error')
            return redirect(url_for('admin'))
        
        # Create new card
        card = Card(
            name=name,
            set_name=request.form.get('set_name', 'Unknown'),
            rarity=request.form.get('rarity', 'Common'),
            condition=request.form.get('condition', 'Near Mint'),
            description=request.form.get('description', ''),
            image_url=request.form.get('image_url', '')
        )
        
        # Handle numeric fields with validation
        try:
            price = request.form.get('price', '0')
            card.price = float(price) if price else 0.0
        except (ValueError, TypeError):
            card.price = 0.0
        
        try:
            quantity = request.form.get('quantity', '0')
            card.quantity = int(quantity) if quantity else 0
        except (ValueError, TypeError):
            card.quantity = 0
        
        db.session.add(card)
        db.session.commit()
        
        flash(f'Card "{card.name}" added successfully', 'success')
        logger.debug(f"Added card: {card.name} (ID: {card.id})")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding card: {e}")
        flash(f'Error adding card: {str(e)}', 'error')
    
    return redirect(url_for('admin'))
