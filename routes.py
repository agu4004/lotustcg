from flask import render_template, request, redirect, url_for, flash, session, jsonify, current_app, get_flashed_messages
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from app import app, db
from storage_db import storage
from models import User, Card, Order, OrderItem
from auth import admin_required, get_redirect_target
from decimal import Decimal
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

#obsolete function, replaced by cart_add_json
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
    if request.is_json or request.accept_mimetypes.best == "application/json":
        request_json = {"card_id": card_id, "qty": request.json.get("qty", 1) if request.is_json else 1}
        # giả lập gọi /cart/add
        with current_app.test_request_context(json=request_json):
            return cart_add_json()
    # ---- hành vi cũ (giữ nguyên) ----
    cart = _get_cart()
    cur = int(cart.get(str(card_id), 0))
    card = Card.query.get_or_404(card_id)
    limit = _per_item_limit()
    stock = int(card.quantity or 0)
    max_allowed = stock if limit <= 0 else min(stock, limit)
    new_qty = min(cur + 1, max_allowed)
    cart[str(card_id)] = new_qty
    _set_cart(cart)

    return redirect(url_for('view_cart'))

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

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    """Checkout page - display form and process orders"""
    # Check if cart is empty
    cart = session.get('cart', {})
    if not cart:
        flash('Your cart is empty', 'warning')
        return redirect(url_for('view_cart'))

    if request.method == 'POST':
        try:
            # Validate required fields
            customer_name = request.form.get('customer_name', '').strip()
            contact_number = request.form.get('contact_number', '').strip()
            shipment_method = request.form.get('shipment_method', '')

            if not customer_name:
                flash('Customer name is required', 'error')
                return redirect(url_for('checkout'))

            if not contact_number:
                flash('Contact number is required', 'error')
                return redirect(url_for('checkout'))

            if shipment_method not in ['shipping', 'pickup']:
                flash('Please select a valid shipment method', 'error')
                return redirect(url_for('checkout'))

            # Validate shipping address if shipping is selected
            shipping_address = None
            shipping_city = None
            shipping_province = None
            shipping_postal_code = None
            shipping_country = None

            if shipment_method == 'shipping':
                shipping_address = request.form.get('shipping_address', '').strip()
                shipping_city = request.form.get('shipping_city', '').strip()
                shipping_province = request.form.get('shipping_province', '').strip()
                shipping_postal_code = request.form.get('shipping_postal_code', '').strip()
                shipping_country = request.form.get('shipping_country', 'Vietnam')

                if not all([shipping_address, shipping_city, shipping_province, shipping_postal_code]):
                    flash('All shipping address fields are required for shipping orders', 'error')
                    return redirect(url_for('checkout'))

            # Calculate order total and validate stock
            cart_items = []
            total_amount = 0

            for card_id, quantity in cart.items():
                card = Card.query.get(int(card_id))
                if not card:
                    flash(f'Card with ID {card_id} not found', 'error')
                    return redirect(url_for('checkout'))

                if quantity > card.quantity:
                    flash(f'Insufficient stock for {card.name}. Only {card.quantity} available.', 'error')
                    return redirect(url_for('checkout'))

                item_total = float(card.price) * quantity
                total_amount += item_total

                cart_items.append({
                    'card': card,
                    'quantity': quantity,
                    'unit_price': float(card.price),
                    'total_price': item_total
                })

            # Generate order ID
            import random
            import string
            from datetime import datetime

            order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=3))}"

            # Create order
            order = Order(
                id=order_id,
                customer_name=customer_name,
                contact_number=contact_number,
                facebook_details=request.form.get('facebook_details', ''),
                shipment_method=shipment_method,
                status='pending',
                total_amount=total_amount,
                shipping_address=shipping_address,
                shipping_city=shipping_city,
                shipping_province=shipping_province,
                shipping_postal_code=shipping_postal_code,
                shipping_country=shipping_country
            )

            db.session.add(order)

            # Create order items and deduct stock
            for item in cart_items:
                order_item = OrderItem(
                    order_id=order_id,
                    card_id=item['card'].id,
                    quantity=item['quantity'],
                    unit_price=item['unit_price'],
                    total_price=item['total_price']
                )
                db.session.add(order_item)

                # Deduct stock
                item['card'].quantity -= item['quantity']

            # Commit transaction
            db.session.commit()

            # Clear cart
            session.pop('cart', None)

            flash(f'Order {order_id} placed successfully!', 'success')
            return redirect(url_for('order_confirmation', order_id=order_id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing order: {e}")
            flash('An error occurred while processing your order. Please try again.', 'error')
            return redirect(url_for('checkout'))

    # GET request - display checkout form
    cart_items = []
    total_price = 0

    for card_id, quantity in cart.items():
        card = Card.query.get(int(card_id))
        if card:
            item_total = float(card.price) * quantity
            cart_items.append({
                'card': card,
                'quantity': quantity,
                'item_total': item_total
            })
            total_price += item_total

    return render_template('checkout.html', cart_items=cart_items, total_price=total_price)

@app.route('/order/<order_id>')
def order_confirmation(order_id):
    """Order confirmation page"""
    order = Order.query.get_or_404(order_id)

    # Get order items with card details
    order_items = []
    for item in order.items:
        order_items.append({
            'card': item.card,
            'quantity': item.quantity,
            'unit_price': float(item.unit_price),
            'total_price': float(item.total_price)
        })

    return render_template('order_confirmation.html',
                         order=order,
                         order_items=order_items)

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
            message_parts = []
            if results.get('created', 0) > 0:
                message_parts.append(f'created {results["created"]} new cards')
            if results.get('updated', 0) > 0:
                message_parts.append(f'updated {results["updated"]} existing cards')
            flash(f'Successfully processed {results["success"]} cards ({", ".join(message_parts)})', 'success')
        
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
    
    sample_csv = """name,set_name,rarity,condition,price,quantity,description,image_url,foiling,art_style
"Lightning Bolt","Core Set","Common","Near Mint",1.50,10,"Classic red instant spell","https://example.com/lightning-bolt.jpg","NF","normal"
"Black Lotus","Alpha","Legendary","Light Play",5000.00,1,"The most powerful mox","https://example.com/black-lotus.jpg","NF","normal"
"Counterspell","Beta","Common","Near Mint",25.00,5,"Counter target spell","https://example.com/counterspell.jpg","RF","EA"
"""
    
    return Response(
        sample_csv,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=sample_cards.csv'}
    )

@app.route('/admin/download_inventory_csv')
@admin_required
def download_inventory_csv():
    """Download current inventory as CSV"""
    from flask import Response
    import csv
    import io
    
    # Get all cards from inventory
    cards = storage.get_all_cards()
    
    # Create CSV content
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header (same format as sample CSV)
    writer.writerow(['name', 'set_name', 'rarity', 'condition', 'price', 'quantity', 'description', 'image_url', 'foiling', 'art_style'])

    # Write card data
    for card in cards:
        writer.writerow([
            card['name'],
            card['set_name'],
            card['rarity'],
            card['condition'],
            card['price'],
            card['quantity'],
            card['description'],
            card['image_url'],
            card['foiling'],
            card['art_style']
        ])
    
    csv_content = output.getvalue()
    output.close()
    
    # Generate filename with timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'inventory_export_{timestamp}.csv'
    
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
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
        card.foiling = request.form.get('foiling', card.foiling)
        card.art_style = request.form.get('art_style', card.art_style)
        
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
    """Handle card soft deletion - admin only"""
    try:
        success = storage.soft_delete_card(card_id)
        if success:
            flash('Card deleted successfully (order history preserved)', 'success')
            logger.debug(f"Soft deleted card (ID: {card_id})")
        else:
            flash('Card not found or already deleted', 'error')

    except Exception as e:
        logger.error(f"Error soft deleting card: {e}")
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
            image_url=request.form.get('image_url', ''),
            foiling=request.form.get('foiling', 'NF'),
            art_style=request.form.get('art_style', 'normal')
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

def _per_item_limit():
    # ưu tiên config (ví dụ set trong app.config['CART_MAX_PER_ITEM'])
    v = current_app.config.get('CART_MAX_PER_ITEM')
    if v:
        try:
            return int(v)
        except Exception:
            pass
    # fallback ENV (nếu bạn dùng python-dotenv)
    import os
    v = os.getenv("CART_MAX_PER_ITEM", "").strip()
    if v.isdigit():
        return int(v)
    return 0  # 0 = chỉ giới hạn bởi tồn kho

def _get_cart():
    cart = session.get("cart")
    if not isinstance(cart, dict):
        cart = {}
    return cart

def _set_cart(cart):
    session["cart"] = cart
    session.modified = True

def _cart_totals(cart: dict):
    """Tính tổng số item & subtotal (Decimal)"""
    ids = [int(i) for i in cart.keys()]
    cards = {c.id: c for c in Card.query.filter(Card.id.in_(ids)).all()} if ids else {}
    count = 0
    subtotal = Decimal("0")
    for sid, qty in cart.items():
        try:
            cid = int(sid); q = int(qty)
        except Exception:
            continue
        count += q
        card = cards.get(cid)
        if card and card.price is not None:
            subtotal += Decimal(card.price) * q
    return {"count": count, "subtotal": subtotal}

# ---- NEW: endpoint JSON để thêm vào giỏ mà không redirect ----
@app.post("/cart/add")
def cart_add_json():
    """
    Body: JSON { "card_id": <int>, "qty": <int (optional, default 1)> }
    Trả: { ok, at_max, item_qty, cart_qty, subtotal, message, flashed_messages }
    """
    payload = request.get_json(silent=True) or {}
    card_id = payload.get("card_id") or request.form.get("card_id")
    qty = payload.get("qty") or request.form.get("qty") or 1
    try:
        card_id = int(card_id); qty = max(1, int(qty))
    except Exception:
        flash('Invalid card ID or quantity', 'error')
        return jsonify(ok=False, message="Invalid card_id/qty",
                      flashed_messages=list_flashed_messages()), 400

    card = Card.query.get_or_404(card_id)

    # max theo tồn kho và/hoặc giới hạn mỗi sản phẩm
    limit = _per_item_limit()
    stock = int(card.quantity or 0)
    max_allowed = stock if limit <= 0 else min(stock, limit)

    cart = _get_cart()
    cur = int(cart.get(str(card_id), 0))

    if max_allowed <= 0:
        # hết hàng hoặc không cho mua
        flash('Out of stock', 'error')
        totals = _cart_totals(cart)
        return jsonify(ok=False, at_max=True, item_qty=cur, cart_qty=totals["count"],
                      subtotal=str(totals["subtotal"]), 
                      flashed_messages=list_flashed_messages()), 200

    if cur >= max_allowed:
        flash('Maximum quantity reached for this item', 'warning')
        totals = _cart_totals(cart)
        return jsonify(ok=False, at_max=True, item_qty=cur, cart_qty=totals["count"],
                      subtotal=str(totals["subtotal"]),
                      flashed_messages=list_flashed_messages()), 200

    new_qty = min(cur + qty, max_allowed)
    cart[str(card_id)] = new_qty
    _set_cart(cart)
    totals = _cart_totals(cart)

    flash(f'Added {qty} x {card.name} to cart', 'success')
    return jsonify(ok=True,
                  at_max=(new_qty >= max_allowed),
                  item_qty=new_qty,
                  cart_qty=totals["count"],
                  subtotal=str(totals["subtotal"]),
                  flashed_messages=list_flashed_messages()), 200

def list_flashed_messages():
    """Helper function to get all flashed messages"""
    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append({
            'category': category,
            'message': message
        })
    return messages

# Admin Order Management Routes
@app.route('/admin/orders')
@admin_required
def admin_orders():
    """Admin orders list page"""
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('admin_orders.html', orders=orders)

@app.route('/admin/orders/<order_id>')
@admin_required
def admin_order_detail(order_id):
    """Admin order detail page"""
    order = Order.query.get_or_404(order_id)

    # Get order items with card details
    order_items = []
    for item in order.items:
        order_items.append({
            'card': item.card,
            'quantity': item.quantity,
            'unit_price': float(item.unit_price),
            'total_price': float(item.total_price)
        })

    return render_template('admin_order_detail.html',
                         order=order,
                         order_items=order_items)

@app.route('/admin/orders/<order_id>/fulfill', methods=['POST'])
@admin_required
def admin_fulfill_order(order_id):
    """Fulfill an order"""
    order = Order.query.get_or_404(order_id)

    if order.status != 'pending':
        flash('Only pending orders can be fulfilled', 'warning')
        return redirect(url_for('admin_orders'))

    try:
        order.status = 'fulfilled'
        order.updated_at = db.func.now()
        db.session.commit()

        flash(f'Order {order_id} has been fulfilled successfully', 'success')
        logger.info(f"Order {order_id} fulfilled by admin")

    except Exception as e:
        db.session.rollback()
        flash(f'Error fulfilling order: {str(e)}', 'error')
        logger.error(f"Error fulfilling order {order_id}: {e}")

    return redirect(url_for('admin_orders'))

@app.route('/admin/orders/<order_id>/reject', methods=['POST'])
@admin_required
def admin_reject_order(order_id):
    """Reject an order and restore stock"""
    order = Order.query.get_or_404(order_id)

    if order.status != 'pending':
        flash('Only pending orders can be rejected', 'warning')
        return redirect(url_for('admin_orders'))

    try:
        # Restore stock for all order items
        for item in order.items:
            if item.card:
                item.card.quantity += item.quantity
                logger.info(f"Restored {item.quantity} units of {item.card.name} (ID: {item.card.id})")

        order.status = 'rejected'
        order.updated_at = db.func.now()
        db.session.commit()

        flash(f'Order {order_id} has been rejected and stock restored', 'success')
        logger.info(f"Order {order_id} rejected by admin - stock restored")

    except Exception as e:
        db.session.rollback()
        flash(f'Error rejecting order: {str(e)}', 'error')
        logger.error(f"Error rejecting order {order_id}: {e}")

    return redirect(url_for('admin_orders'))