from flask import render_template, request, redirect, url_for, flash, session, jsonify
from app import app
from storage import storage
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
        if request.args.get('min_price'):
            min_price = float(request.args.get('min_price'))
    except (ValueError, TypeError):
        pass
    
    try:
        if request.args.get('max_price'):
            max_price = float(request.args.get('max_price'))
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

@app.route('/admin')
def admin():
    """Admin panel"""
    cards = storage.get_all_cards()
    return render_template('admin.html', cards=cards)

@app.route('/admin/upload_csv', methods=['POST'])
def upload_csv():
    """Handle CSV upload"""
    if 'csv_file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('admin'))
    
    file = request.files['csv_file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('admin'))
    
    if not file.filename.endswith('.csv'):
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
def clear_cards():
    """Clear all cards"""
    storage.clear_all_cards()
    flash('All cards cleared', 'info')
    return redirect(url_for('admin'))

@app.route('/admin/sample_csv')
def download_sample_csv():
    """Download sample CSV template"""
    from flask import Response
    
    sample_csv = """name,set_name,rarity,condition,price,quantity,description
"Lightning Bolt","Core Set","Common","Near Mint",1.50,10,"Classic red instant spell"
"Black Lotus","Alpha","Mythic Rare","Light Play",5000.00,1,"The most powerful mox"
"Counterspell","Beta","Common","Near Mint",25.00,5,"Counter target spell"
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
