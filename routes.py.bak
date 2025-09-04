from flask import render_template, request, redirect, url_for, flash, session, jsonify, current_app, get_flashed_messages
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from app import app, db
from storage_db import storage
from models import (
    User, Card, Order, OrderItem,
    UserInventory, InventoryItem, TradeOffer, TradeItem,
    CartSession, CartItem, UserAuditLog, VerificationAuditLog,
    Coupon
)
from auth import admin_required, get_redirect_target
from decimal import Decimal
import logging
import re
from functools import wraps
from datetime import datetime

logger = logging.getLogger(__name__)

# Validation decorators and helper functions
def validate_inventory_item_data(data):
    """Validate inventory item data with comprehensive error handling"""
    errors = []

    # Required fields validation
    card_name = data.get('card_name', '').strip()
    if not card_name:
        errors.append('Card name is required')
    elif len(card_name) > 120:  # Database field limit
        errors.append('Card name cannot exceed 120 characters')
    elif not re.match(r'^[a-zA-Z0-9\s\-\.\'\",\(\)]+$', card_name):
        errors.append('Card name contains invalid characters')

    # Quantity validation
    try:
        quantity = int(data.get('quantity', 1))
        if quantity <= 0:
            errors.append('Quantity must be greater than 0')
        elif quantity > 1000:  # Reasonable upper limit
            errors.append('Quantity cannot exceed 1000')
    except (ValueError, TypeError, OverflowError):
        errors.append('Invalid quantity format')


    # Condition validation
    valid_conditions = ['Near Mint', 'Light Play', 'Moderate Play', 'Heavy Play', 'Damaged']
    if data.get('condition') and data['condition'] not in valid_conditions:
        errors.append(f'Invalid condition. Must be one of: {", ".join(valid_conditions)}')

    # Language validation
    valid_languages = ['English', 'Not English']
    if data.get('language') and data['language'] not in valid_languages:
        errors.append(f'Invalid language. Must be one of: {", ".join(valid_languages)}')

    # Notes validation
    if data.get('notes') and len(str(data['notes'])) > 1000:
        errors.append('Notes cannot exceed 1000 characters')

    # Grade validation
    if data.get('grade') and len(str(data['grade'])) > 20:
        errors.append('Grade cannot exceed 20 characters')

    # Foil type validation
    valid_foil_types = ['Non Foil', 'Rainbow Foil', 'Cold Foil']
    if data.get('foil_type') and data['foil_type'] not in valid_foil_types and data['foil_type'] != '':
        errors.append(f'Invalid foil type. Must be one of: {", ".join(valid_foil_types)} or empty')

    return errors

def handle_database_error(operation, error):
    """Handle database errors with appropriate logging and user messages"""
    logger.error(f"Database error during {operation}: {error}")

    # Check for specific error types
    if "UNIQUE constraint failed" in str(error):
        return "This item already exists in your inventory"
    elif "FOREIGN KEY constraint failed" in str(error):
        return "Referenced item not found"
    elif "CHECK constraint failed" in str(error):
        return "Invalid data provided"
    elif "NOT NULL constraint failed" in str(error):
        return "Required field is missing"
    else:
        return "A database error occurred. Please try again."

def safe_db_operation(operation_func, operation_name, rollback_on_error=True):
    """Decorator for safe database operations with error handling"""
    def wrapper(*args, **kwargs):
        try:
            result = operation_func(*args, **kwargs)
            return result
        except Exception as e:
            if rollback_on_error:
                try:
                    db.session.rollback()
                except Exception as rollback_error:
                    logger.error(f"Error during rollback: {rollback_error}")

            error_message = handle_database_error(operation_name, e)
            logger.error(f"Operation {operation_name} failed: {e}")
            return None, error_message
    return wrapper

def inventory_item_owner_required(f):
    """Decorator to ensure user owns the inventory item"""
    @wraps(f)
    def decorated_function(item_id, *args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this feature.', 'error')
            return redirect(url_for('login'))

        try:
            item = InventoryItem.query.get_or_404(item_id)
            if item.inventory.user_id != current_user.id:
                flash('You do not have permission to access this item.', 'error')
                return redirect(url_for('user_inventory'))
        except Exception as e:
            logger.error(f"Error checking item ownership: {e}")
            flash('An error occurred while checking permissions.', 'error')
            return redirect(url_for('user_inventory'))

        return f(item_id, *args, **kwargs)
    return decorated_function

def rate_limit_inventory_operations(f):
    """Decorator to rate limit inventory operations"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Simple rate limiting - could be enhanced with Redis or similar
        import time
        now = time.time()

        # Check if user has made too many requests recently
        last_request = session.get('last_inventory_request', 0)
        if now - last_request < 0.5:  # 2 requests per second max
            return jsonify({'success': False, 'error': 'Too many requests'}), 429

        session['last_inventory_request'] = now
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """Home page with featured cards"""
    cards = storage.get_all_cards()
    # Filter out out-of-stock cards and show first 6 as featured
    in_stock_cards = [card for card in cards if card.get('quantity', 0) > 0]
    featured_cards = in_stock_cards[:6] if in_stock_cards else []
    return render_template('index.html', featured_cards=featured_cards, total_cards=len(cards))

@app.route('/catalog')
def catalog():
    """Card catalog with search and filtering - supports both admin and user inventory"""
    # Get search parameters
    query = request.args.get('q', '').strip()
    set_filter = request.args.get('set', '')
    rarity_filter = request.args.get('rarity', '')
    foiling_filter = request.args.get('foiling', '')

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

    # Get pagination parameters
    try:
        page = int(request.args.get('page', 1))
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1

    per_page = 30

    # Get sort parameter
    sort_by = request.args.get('sort', 'name_asc')

    # Get admin cards
    admin_cards = storage.search_cards(
        query=query,
        set_filter=set_filter,
        rarity_filter=rarity_filter,
        foiling_filter=foiling_filter,
        min_price=min_price,
        max_price=max_price
    )

    # Get user inventory items
    user_inventory_items = []
    if query or set_filter or rarity_filter or foiling_filter or min_price or max_price:
        # Apply filters to user inventory items
        user_items_query = InventoryItem.query.join(Card).filter(
            InventoryItem.is_verified == True,
            InventoryItem.quantity > 0,
            InventoryItem.is_public == True
        )

        if query:
            user_items_query = user_items_query.filter(Card.name.ilike(f'%{query}%'))
        if set_filter:
            user_items_query = user_items_query.filter(Card.set_name == set_filter)
        if rarity_filter:
            user_items_query = user_items_query.filter(Card.rarity == rarity_filter)
        if foiling_filter:
            user_items_query = user_items_query.filter(Card.foiling == foiling_filter)
        # Price filtering removed - no longer using sale_price

        user_inventory_items = user_items_query.all()

    # Convert user inventory items to display format
    user_cards = []
    for item in user_inventory_items:
        card_data = item.card.to_dict()
        card_data.update({
            'item_type': 'user',
            'inventory_item_id': item.id,
            'seller_info': {
                'type': 'user',
                'name': item.inventory.user.username,
                'user_id': item.inventory.user.id
            },
            'display_price': float(item.card.price) if item.card else 0,
            'condition': item.condition,
            'quantity': item.quantity
        })
        user_cards.append(card_data)

    # Combine admin and user cards
    all_cards = []
    for card in admin_cards:
        card_data = card.copy()
        card_data['item_type'] = 'admin'
        card_data['seller_info'] = {'type': 'admin', 'name': 'Lotus TCG Store'}
        card_data['display_price'] = card_data['price']
        all_cards.append(card_data)

    all_cards.extend(user_cards)

    # Apply sorting
    if sort_by == 'name_asc':
        all_cards.sort(key=lambda x: x.get('name', '').lower())
    elif sort_by == 'name_desc':
        all_cards.sort(key=lambda x: x.get('name', '').lower(), reverse=True)
    elif sort_by == 'price_asc':
        all_cards.sort(key=lambda x: float(x.get('display_price', 0)))
    elif sort_by == 'price_desc':
        all_cards.sort(key=lambda x: float(x.get('display_price', 0)), reverse=True)

    # Separate in-stock and out-of-stock cards
    in_stock_cards = [card for card in all_cards if card.get('quantity', 0) > 0]
    out_of_stock_cards = [card for card in all_cards if card.get('quantity', 0) == 0]

    # Combine with in-stock cards first, then out-of-stock cards
    sorted_cards = in_stock_cards + out_of_stock_cards

    # Calculate pagination
    total_cards = len(sorted_cards)
    total_pages = (total_cards + per_page - 1) // per_page  # Ceiling division

    # Ensure page is within valid range
    if page > total_pages and total_pages > 0:
        page = total_pages

    # Get cards for current page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_cards = sorted_cards[start_idx:end_idx]

    # Get filter options (combine from both sources)
    all_sets = storage.get_unique_sets()
    all_rarities = storage.get_unique_rarities()
    all_foilings = storage.get_unique_foilings()

    # Add user inventory sets/rarities/foilings (only public items)
    user_sets = db.session.query(Card.set_name.distinct()).join(InventoryItem).filter(
        InventoryItem.is_verified == True,
        InventoryItem.is_public == True
    ).all()
    user_rarities = db.session.query(Card.rarity.distinct()).join(InventoryItem).filter(
        InventoryItem.is_verified == True,
        InventoryItem.is_public == True
    ).all()
    user_foilings = db.session.query(Card.foiling.distinct()).join(InventoryItem).filter(
        InventoryItem.is_verified == True,
        InventoryItem.is_public == True
    ).all()

    all_sets.extend([s[0] for s in user_sets if s[0] not in all_sets])
    all_rarities.extend([r[0] for r in user_rarities if r[0] not in all_rarities])
    all_foilings.extend([f[0] for f in user_foilings if f[0] not in all_foilings])

    # Calculate pagination info
    has_prev = page > 1
    has_next = page < total_pages
    prev_page = page - 1 if has_prev else None
    next_page = page + 1 if has_next else None

    # Generate page numbers for pagination control
    page_numbers = []
    if total_pages <= 7:
        page_numbers = list(range(1, total_pages + 1))
    else:
        if page <= 4:
            page_numbers = [1, 2, 3, 4, 5, '...', total_pages]
        elif page >= total_pages - 3:
            page_numbers = [1, '...', total_pages - 4, total_pages - 3, total_pages - 2, total_pages - 1, total_pages]
        else:
            page_numbers = [1, '...', page - 1, page, page + 1, '...', total_pages]

    # Calculate display range for template
    start_display = ((page - 1) * per_page) + 1
    end_display = min(page * per_page, total_cards)

    return render_template('catalog.html',
                          cards=page_cards,
                          in_stock_count=len(in_stock_cards),
                          out_of_stock_count=len(out_of_stock_cards),
                          all_sets=all_sets,
                          all_rarities=all_rarities,
                          all_foilings=all_foilings,
                          current_filters={
                              'q': query,
                              'set': set_filter,
                              'rarity': rarity_filter,
                              'foiling': foiling_filter,
                              'min_price': request.args.get('min_price', ''),
                              'max_price': request.args.get('max_price', ''),
                              'sort': sort_by
                          },
                          # Pagination data
                          page=page,
                          per_page=per_page,
                          total_cards=total_cards,
                          total_pages=total_pages,
                          has_prev=has_prev,
                          has_next=has_next,
                          prev_page=prev_page,
                          next_page=next_page,
                          page_numbers=page_numbers,
                          start_display=start_display,
                          end_display=end_display)

@app.route('/card/<card_id>')
def card_detail(card_id):
    """Card detail page"""
    card = storage.get_card(card_id)
    if not card:
        flash('Card not found', 'error')
        return redirect(url_for('catalog'))
    
    return render_template('card_detail.html', card=card)

# REMOVED: Obsolete function replaced by cart_add_json
# The old add_to_cart route has been removed to prevent conflicts with the new database-based cart system

@app.route('/cart')
def view_cart():
    """View shopping cart with mixed inventory support"""
    logger.info("=== VIEW CART DEBUG ===")
    logger.info(f"Session ID: {session.get('_id', 'None')}")
    logger.info(f"Current user: {current_user.username if current_user.is_authenticated else 'Anonymous'}")

    cart_items = []
    total_price = 0

    # Get or create cart session
    cart_session = _get_or_create_cart_session()
    logger.info(f"Cart session: {cart_session.id if cart_session else 'None'}")
    logger.info(f"Cart session user_id: {cart_session.user_id if cart_session else 'None'}")

    if cart_session:
        logger.info(f"Number of cart items in session: {len(cart_session.items)}")
        # Load cart items with seller information
        for cart_item in cart_session.items:
            logger.info(f"Cart item: {cart_item.card.name if cart_item.card else 'Unknown'} x {cart_item.quantity}")
            cart_items.append(cart_item.to_dict())
            total_price += cart_item.item_total
    else:
        logger.error("Failed to get or create cart session")

    logger.info(f"Total cart items: {len(cart_items)}, Total price: {total_price}")
    return render_template('cart.html', cart_items=cart_items, total_price=total_price)

@app.route('/update_cart/<card_id>', methods=['POST'])
def update_cart(card_id):
    """Update cart item quantity"""
    try:
        cart_session = _get_or_create_cart_session()
        quantity = int(request.form.get('quantity', 0))

        # Find the cart item
        cart_item = CartItem.query.filter_by(
            session_id=cart_session.id,
            card_id=card_id
        ).first()

        if not cart_item:
            flash('Item not found in cart', 'error')
            return redirect(url_for('view_cart'))

        if quantity <= 0:
            # Remove item from cart
            db.session.delete(cart_item)
            db.session.commit()
            flash('Item removed from cart', 'info')
        else:
            # Validate new quantity
            card = cart_item.card
            if card and quantity <= cart_item.available_quantity:
                cart_item.quantity = quantity
                db.session.commit()
                flash('Cart updated', 'success')
            else:
                flash('Invalid quantity', 'error')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating cart: {e}")
        flash('Error updating cart', 'error')

    return redirect(url_for('view_cart'))

@app.route('/clear_cart', methods=['POST'])
def clear_cart():
    """Clear shopping cart"""
    try:
        cart_session = _get_or_create_cart_session()

        # Delete all cart items
        CartItem.query.filter_by(session_id=cart_session.id).delete()
        db.session.commit()

        flash('Cart cleared', 'info')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error clearing cart: {e}")
        flash('Error clearing cart', 'error')

    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    """Checkout page - display form and process orders with mixed cart support"""
    # Check if cart is empty
    cart_session = _get_or_create_cart_session()
    if not cart_session.items:
        flash('Your cart is empty', 'warning')
        return redirect(url_for('view_cart'))

    if request.method == 'POST':
        logger.info("=== ORDER PROCESSING DEBUG ===")
        try:
            # Validate required fields
            customer_name = request.form.get('customer_name', '').strip()
            contact_number = request.form.get('contact_number', '').strip()
            shipment_method = request.form.get('shipment_method', '')

            logger.info(f"Order details: customer_name='{customer_name}', contact_number='{contact_number}', shipment_method='{shipment_method}'")

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
            pickup_location = None

            if shipment_method == 'shipping':
                shipping_address = request.form.get('shipping_address', '').strip()
                shipping_city = request.form.get('shipping_city', '').strip()
                shipping_province = request.form.get('shipping_province', '').strip()
                shipping_postal_code = request.form.get('shipping_postal_code', '').strip()
                shipping_country = request.form.get('shipping_country', 'Vietnam')

                if not all([shipping_address, shipping_city, shipping_province, shipping_postal_code]):
                    flash('All shipping address fields are required for shipping orders', 'error')
                    return redirect(url_for('checkout'))
            elif shipment_method == 'pickup':
                pickup_location = request.form.get('pickup_location', '').strip()
                if not pickup_location:
                    flash('Please select a pickup location', 'error')
                    return redirect(url_for('checkout'))
                if pickup_location not in ['Iron Hammer', 'Floating Dojo']:
                    flash('Please select a valid pickup location', 'error')
                    return redirect(url_for('checkout'))

            # Calculate order total and validate stock
            logger.info(f"Processing {len(cart_session.items)} cart items")
            cart_items = []
            total_amount = 0

            for cart_item in cart_session.items:
                logger.info(f"Processing cart item: {cart_item.card.name if cart_item.card else 'Unknown'} x {cart_item.quantity}")
                logger.info(f"  - Available quantity: {cart_item.available_quantity}")
                logger.info(f"  - Item total: {cart_item.item_total}")

                # Validate stock availability
                if cart_item.quantity > cart_item.available_quantity:
                    item_name = cart_item.card.name if cart_item.card else cart_item.inventory_item.card.name
                    flash(f'Insufficient stock for {item_name}. Only {cart_item.available_quantity} available.', 'error')
                    return redirect(url_for('checkout'))

                cart_items.append(cart_item.to_dict())
                total_amount += float(cart_item.item_total)

            logger.info(f"Total order amount: {total_amount}")

            # Generate order ID
            import random
            import string

            order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=3))}"
            logger.info(f"Generated order ID: {order_id}")

            # Handle coupon discount in order total
            applied_coupon = None
            discount_amount = 0
            final_total = total_amount

            if 'applied_coupon_id' in session:
                try:
                    coupon_id = session['applied_coupon_id']
                    coupon = Coupon.query.get(coupon_id)
                    if coupon and coupon.is_active:
                        applied_coupon = coupon
                        discount_percentage = float(coupon.discount_percentage)
                        discount_amount = total_amount * (discount_percentage / 100)
                        final_total = total_amount - discount_amount

                        logger.info(f"Coupon applied to order: {coupon.code}, discount={discount_amount}, final_total={final_total}")

                        # Increment coupon usage count
                        coupon.usage_count += 1
                        db.session.add(coupon)
                except Exception as e:
                    logger.error(f"Error processing coupon for order: {e}")

            # Create order with final total (including discount)
            logger.info("Creating order...")
            order = Order(
                id=order_id,
                customer_name=customer_name,
                contact_number=contact_number,
                facebook_details=request.form.get('facebook_details', ''),
                shipment_method=shipment_method,
                pickup_location=pickup_location,
                status='pending',
                total_amount=final_total,  # Use discounted total
                shipping_address=shipping_address,
                shipping_city=shipping_city,
                shipping_province=shipping_province,
                shipping_postal_code=shipping_postal_code,
                shipping_country=shipping_country
            )

            db.session.add(order)
            logger.info("Order created successfully")

            # Create order items and deduct stock
            logger.info("Creating order items and deducting stock...")
            for cart_item in cart_session.items:
                logger.info(f"Processing order item: {cart_item.card.name if cart_item.card else 'Unknown'}")

                # Create order item
                order_item = OrderItem(
                    order_id=order_id,
                    card_id=cart_item.card_id if cart_item.card else cart_item.inventory_item.card_id,
                    quantity=cart_item.quantity,
                    unit_price=float(cart_item.display_price),
                    total_price=float(cart_item.item_total)
                )
                db.session.add(order_item)
                logger.info("Order item created")

                # Deduct stock based on item type
                if cart_item.item_type == 'admin' and cart_item.card:
                    logger.info(f"Deducting {cart_item.quantity} from admin stock for {cart_item.card.name}")
                    cart_item.card.quantity -= cart_item.quantity
                elif cart_item.item_type == 'user' and cart_item.inventory_item:
                    logger.info(f"Deducting {cart_item.quantity} from user inventory for {cart_item.inventory_item.card.name}")
                    cart_item.inventory_item.quantity -= cart_item.quantity

            # Commit transaction
            logger.info("Committing transaction...")
            db.session.commit()
            logger.info("Transaction committed successfully")

            # Clear cart
            logger.info("Clearing cart...")
            CartItem.query.filter_by(session_id=cart_session.id).delete()
            db.session.commit()
            logger.info("Cart cleared")

            # Clear coupon from session
            if 'applied_coupon_id' in session:
                session.pop('applied_coupon_id', None)
                session.pop('applied_coupon_code', None)
                session.pop('discount_amount', None)
                session.pop('final_total', None)

            flash(f'Order {order_id} placed successfully!', 'success')
            logger.info(f"Order {order_id} completed successfully")
            return redirect(url_for('order_confirmation', order_id=order_id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing order: {e}")
            import traceback
            logger.error(f"Full order processing traceback: {traceback.format_exc()}")
            flash('An error occurred while processing your order. Please try again.', 'error')
            return redirect(url_for('checkout'))

    # GET request - display checkout form
    logger.info("=== CHECKOUT PAGE LOAD DEBUG ===")
    cart_items = []
    total_price = 0

    logger.info(f"Cart session items count: {len(cart_session.items)}")
    for cart_item in cart_session.items:
        item_dict = cart_item.to_dict()
        logger.info(f"Cart item: {cart_item.card.name if cart_item.card else 'Unknown'} x {cart_item.quantity}")
        logger.info(f"  - Item type: {cart_item.item_type}")
        logger.info(f"  - Display price: {cart_item.display_price}")
        logger.info(f"  - Item total: {cart_item.item_total}")
        cart_items.append(item_dict)
        total_price += float(cart_item.item_total)

    logger.info(f"Total cart price: {total_price}")

    # Handle coupon data
    applied_coupon = None
    discount_amount = 0
    final_total = total_price

    logger.info(f"Session coupon data: applied_coupon_id={session.get('applied_coupon_id')}, applied_coupon_code={session.get('applied_coupon_code')}")

    if 'applied_coupon_id' in session:
        try:
            coupon_id = session['applied_coupon_id']
            logger.info(f"Loading coupon with ID: {coupon_id}")
            coupon = Coupon.query.get(coupon_id)
            if coupon:
                logger.info(f"Coupon found: {coupon.code}, active={coupon.is_active}, percentage={coupon.discount_percentage}")
                if coupon.is_active:
                    # Validate coupon is still valid
                    now = datetime.utcnow()
                    logger.info(f"Current time: {now}, coupon valid_from: {coupon.valid_from}, valid_until: {coupon.valid_until}")

                    if (not coupon.valid_from or now >= coupon.valid_from) and \
                       (not coupon.valid_until or now <= coupon.valid_until) and \
                       (not coupon.usage_limit or coupon.usage_count < coupon.usage_limit):

                        applied_coupon = coupon
                        discount_percentage = float(coupon.discount_percentage)
                        discount_amount = total_price * (discount_percentage / 100)
                        final_total = total_price - discount_amount

                        logger.info(f"Coupon applied: percentage={discount_percentage}, discount_amount={discount_amount}, final_total={final_total}")
                    else:
                        logger.info("Coupon validation failed - removing from session")
                        # Coupon is no longer valid, remove from session
                        session.pop('applied_coupon_id', None)
                        session.pop('applied_coupon_code', None)
                        session.pop('discount_amount', None)
                        session.pop('final_total', None)
                else:
                    logger.info("Coupon is not active - removing from session")
                    session.pop('applied_coupon_id', None)
                    session.pop('applied_coupon_code', None)
                    session.pop('discount_amount', None)
                    session.pop('final_total', None)
            else:
                logger.info("Coupon not found - removing from session")
                session.pop('applied_coupon_id', None)
                session.pop('applied_coupon_code', None)
                session.pop('discount_amount', None)
                session.pop('final_total', None)
        except Exception as e:
            logger.error(f"Error loading applied coupon: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            # Remove invalid coupon data from session
            session.pop('applied_coupon_id', None)
            session.pop('applied_coupon_code', None)
            session.pop('discount_amount', None)
            session.pop('final_total', None)

    logger.info(f"Final values: total_price={total_price}, discount_amount={discount_amount}, final_total={final_total}")

    return render_template('checkout.html',
                          cart_items=cart_items,
                          total_price=total_price,
                          applied_coupon=applied_coupon,
                          discount_amount=discount_amount,
                          final_total=final_total)

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
        if user and user.check_password(password) and user.is_active():
            # Record successful login
            user.record_login_attempt(success=True)
            db.session.commit()

            login_user(user, remember=remember)
            flash(f'Welcome back, {user.username}!', 'success')

            # Redirect to next page or home
            next_page = get_redirect_target()
            return redirect(next_page or url_for('index'))
        else:
            # Record failed login attempt
            if user:
                user.record_login_attempt(success=False)
                db.session.commit()

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

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            # Get form data
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            first_name = request.form.get('first_name', '').strip()
            last_name = request.form.get('last_name', '').strip()
            accept_terms = request.form.get('accept_terms')

            # Basic validation
            if not username or not email or not password:
                flash('Please fill in all required fields', 'error')
                return render_template('register.html')

            if password != confirm_password:
                flash('Passwords do not match', 'error')
                return render_template('register.html')

            if not accept_terms:
                flash('You must accept the terms and conditions', 'error')
                return render_template('register.html')

            # Check if username already exists
            if User.query.filter_by(username=username).first():
                flash('Username already exists', 'error')
                return render_template('register.html')

            # Check if email already exists
            if User.query.filter_by(email=email).first():
                flash('Email address already registered', 'error')
                return render_template('register.html')

            # Validate password strength
            if len(password) < 8:
                flash('Password must be at least 8 characters long', 'error')
                return render_template('register.html')

            if not any(c.isupper() for c in password):
                flash('Password must contain at least one uppercase letter', 'error')
                return render_template('register.html')

            if not any(c.islower() for c in password):
                flash('Password must contain at least one lowercase letter', 'error')
                return render_template('register.html')

            if not any(c.isdigit() for c in password):
                flash('Password must contain at least one number', 'error')
                return render_template('register.html')

            if not any(c in '!@#$%^&*(),.?":{}|<>' for c in password):
                flash('Password must contain at least one special character', 'error')
                return render_template('register.html')

            # Validate username format
            if not re.match(r'^[a-zA-Z0-9_]+$', username):
                flash('Username can only contain letters, numbers, and underscores', 'error')
                return render_template('register.html')

            if len(username) < 3:
                flash('Username must be at least 3 characters long', 'error')
                return render_template('register.html')

            # Validate email format
            if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
                flash('Please enter a valid email address', 'error')
                return render_template('register.html')

            # Create new user
            from werkzeug.security import generate_password_hash
            hashed_password = generate_password_hash(password)

            new_user = User(
                username=username,
                email=email,
                password_hash=hashed_password,
                role='user'
            )

            db.session.add(new_user)

            # Create default user inventory
            from models import UserInventory
            user_inventory = UserInventory(
                user=new_user,
                is_public=False  # Private by default
            )
            db.session.add(user_inventory)

            db.session.commit()

            flash('Account created successfully! You can now log in.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Registration error: {e}")
            flash('An error occurred during registration. Please try again.', 'error')
            return render_template('register.html')

    return render_template('register.html')

@app.route('/users')
@login_required
def users():
    """General user list page - accessible to all logged-in users"""
    try:
        # Get query parameters
        search = request.args.get('search', '').strip()
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))

        # Build query - only show active users, exclude super admins
        query = User.query.filter(
            db.and_(
                User.account_status == 'active',
                User.role != 'super_admin'
            )
        )

        # Apply search filter
        if search:
            query = query.filter(
                db.or_(
                    User.username.ilike(f'%{search}%'),
                    User.email.ilike(f'%{search}%')
                )
            )

        # Order by creation date (newest first)
        query = query.order_by(User.created_at.desc())

        # Get paginated results
        users_pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        users_list = users_pagination.items

        # Add inventory count to each user
        for user in users_list:
            user_inventory = UserInventory.query.filter_by(user_id=user.id).first()
            if user_inventory:
                user.inventory_count = sum(item.quantity for item in user_inventory.items)
            else:
                user.inventory_count = 0

        return render_template('users.html',
                              users=users_list,
                              pagination=users_pagination,
                              search=search,
                              per_page=per_page)

    except Exception as e:
        logger.error(f"Error loading users page: {e}")
        flash('An error occurred while loading the users page.', 'error')
        return redirect(url_for('index'))

@app.route('/inventory')
@login_required
def user_inventory():
    """User's personal inventory page"""
    try:
        # Get or create user's inventory
        user_inventory = UserInventory.query.filter_by(user_id=current_user.id).first()

        if not user_inventory:
            # Create inventory if it doesn't exist
            user_inventory = UserInventory(user=current_user, is_public=False)
            db.session.add(user_inventory)
            db.session.commit()

        # Get inventory items with card details
        inventory_items = []
        if user_inventory.items:
            for item in user_inventory.items:
                item_data = {
                    'id': item.id,
                    'card_name': item.card.name if item.card else 'Unknown Card',
                    'card_set': item.card.set_name if item.card else 'Unknown',
                    'quantity': item.quantity,
                    'condition': item.condition,
                    'is_verified': item.is_verified,
                    'verification_status': item.verification_status,
                    'added_at': item.added_at,
                    'card_image': item.card.image_url if item.card else None,
                    'card_rarity': item.card.rarity if item.card else 'Unknown',
                    'card_price': float(item.card.price) if item.card else 0
                }
                inventory_items.append(item_data)

        # Sort items by card name
        inventory_items.sort(key=lambda x: x['card_name'].lower())

        # Calculate inventory statistics
        total_items = sum(item['quantity'] for item in inventory_items)
        verified_items = sum(1 for item in inventory_items if item['is_verified'])
        total_value = sum(item['card_price'] * item['quantity']
                          for item in inventory_items)

        return render_template('inventory.html',
                              inventory_items=inventory_items,
                              user_inventory=user_inventory,
                              total_items=total_items,
                              verified_items=verified_items,
                              total_value=total_value)

    except Exception as e:
        logger.error(f"Error loading user inventory: {e}")
        flash('An error occurred while loading your inventory.', 'error')
        return redirect(url_for('index'))


@app.route('/user/<int:user_id>/inventory')
@login_required
def view_user_inventory(user_id):
    """View another user's public inventory"""
    try:
        # Get the target user
        target_user = User.query.get_or_404(user_id)

        # Check if the target user's inventory is public
        user_inventory = UserInventory.query.filter_by(user_id=user_id).first()

        if not user_inventory or not user_inventory.is_public:
            flash('This user\'s inventory is not public.', 'error')
            return redirect(url_for('users'))

        # Get inventory items with card details (only verified items for public view)
        inventory_items = []
        if user_inventory.items:
            for item in user_inventory.items:
                if item.is_verified:  # Only show verified items in public view
                    item_data = {
                        'id': item.id,
                        'card_name': item.card.name if item.card else 'Unknown Card',
                        'card_set': item.card.set_name if item.card else 'Unknown',
                        'quantity': item.quantity,
                        'condition': item.condition,
                        'verification_status': item.verification_status,
                        'added_at': item.added_at,
                        'card_image': item.card.image_url if item.card else None,
                        'card_rarity': item.card.rarity if item.card else 'Unknown',
                        'card_price': float(item.card.price) if item.card else 0
                    }
                    inventory_items.append(item_data)

        # Sort items by card name
        inventory_items.sort(key=lambda x: x['card_name'].lower())

        # Calculate inventory statistics
        total_items = sum(item['quantity'] for item in inventory_items)
        total_value = sum(item['card_price'] * item['quantity']
                          for item in inventory_items)

        return render_template('user_inventory.html',
                              inventory_items=inventory_items,
                              target_user=target_user,
                              user_inventory=user_inventory,
                              total_items=total_items,
                              total_value=total_value)

    except Exception as e:
        logger.error(f"Error loading user inventory for user {user_id}: {e}")
        flash('An error occurred while loading the user\'s inventory.', 'error')
        return redirect(url_for('users'))

@app.route('/api/inventory/toggle-visibility', methods=['POST'])
@login_required
def toggle_inventory_visibility():
    """API endpoint to toggle inventory visibility"""
    try:
        data = request.get_json()
        is_public = data.get('is_public', False)

        # Get or create user's inventory
        user_inventory = UserInventory.query.filter_by(user_id=current_user.id).first()

        if not user_inventory:
            user_inventory = UserInventory(user=current_user, is_public=is_public)
            db.session.add(user_inventory)
        else:
            user_inventory.is_public = is_public

        db.session.commit()

        return jsonify({
            'success': True,
            'is_public': user_inventory.is_public,
            'message': f'Inventory is now {"public" if user_inventory.is_public else "private"}'
        })

    except Exception as e:
        logger.error(f"Error toggling inventory visibility: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to update inventory visibility'
        }), 500

@app.route('/api/inventory/add-item', methods=['POST'])
@login_required
@rate_limit_inventory_operations
def add_inventory_item():
    """API endpoint to add item to user's inventory with flexible catalog support"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        # Basic validation - bypass catalog validation for card_name but enforce basic constraints
        errors = []

        # Required fields validation
        card_name = data.get('card_name', '').strip()
        if not card_name:
            errors.append('Card name is required')
        elif len(card_name) > 120:  # Database field limit
            errors.append('Card name cannot exceed 120 characters')

        # Quantity validation
        try:
            quantity = int(data.get('quantity', 1))
            if quantity <= 0:
                errors.append('Quantity must be greater than 0')
            elif quantity > 1000:  # Reasonable upper limit
                errors.append('Quantity cannot exceed 1000')
        except (ValueError, TypeError, OverflowError):
            errors.append('Invalid quantity format')

        # Condition validation
        valid_conditions = ['Near Mint', 'Light Play', 'Moderate Play', 'Heavy Play', 'Damaged']
        if data.get('condition') and data['condition'] not in valid_conditions:
            errors.append(f'Invalid condition. Must be one of: {", ".join(valid_conditions)}')

        # Language validation
        valid_languages = ['English', 'Not English']
        if data.get('language') and data['language'] not in valid_languages:
            errors.append(f'Invalid language. Must be one of: {", ".join(valid_languages)}')

        # Notes validation
        if data.get('notes') and len(str(data['notes'])) > 1000:
            errors.append('Notes cannot exceed 1000 characters')

        # Grade validation
        if data.get('grade') and len(str(data['grade'])) > 20:
            errors.append('Grade cannot exceed 20 characters')

        # Foil type validation
        valid_foil_types = ['Non Foil', 'Rainbow Foil', 'Cold Foil']
        if data.get('foil_type') and data['foil_type'] not in valid_foil_types and data['foil_type'] != '':
            errors.append(f'Invalid foil type. Must be one of: {", ".join(valid_foil_types)} or empty')

        if errors:
            return jsonify({
                'success': False,
                'error': errors[0],
                'validation_errors': errors
            }), 400

        # Get or create user's inventory
        user_inventory = UserInventory.query.filter_by(user_id=current_user.id).first()
        if not user_inventory:
            user_inventory = UserInventory(user=current_user, is_public=False)
            db.session.add(user_inventory)
            db.session.commit()

        # Check if card already exists in catalog, if not create it
        card = Card.query.filter_by(name=card_name).first()
        if not card:
            # Create new card with user-provided data
            card = Card(
                name=card_name,
                set_name=data.get('card_set', 'Unknown'),
                rarity=data.get('card_rarity', 'Common'),
                condition=data.get('condition', 'Near Mint'),
                price=float(data.get('market_price', 0.0)),  # Use market_price if provided
                quantity=0,  # This is user inventory, not admin stock
                description=data.get('description', ''),
                image_url=data.get('card_image', ''),
                foiling=data.get('foil_type', 'NF') if data.get('foil_type') else 'NF',
                art_style='normal'  # Default
            )
            db.session.add(card)
            db.session.commit()

        # Check if user already has this card in their inventory
        existing_item = InventoryItem.query.filter_by(
            inventory_id=user_inventory.id,
            card_id=card.id
        ).first()

        action_taken = 'added'
        if existing_item:
            # Check if existing item is verified
            if existing_item.is_verified:
                # Create duplicate entry with unverified status
                duplicate_item = InventoryItem(
                    inventory_id=user_inventory.id,
                    card_id=card.id,
                    quantity=quantity,
                    condition=data.get('condition', existing_item.condition),
                    verification_status='unverified',
                    is_verified=False,
                    notes=data.get('notes', f'Duplicate of verified item - {existing_item.notes or ""}'),
                    grade=data.get('grade', existing_item.grade),
                    language=data.get('language', existing_item.language),
                    foil_type=data.get('foil_type', existing_item.foil_type),
                    is_mint=data.get('is_mint', existing_item.is_mint),
                    updated_at=datetime.utcnow()  # Explicitly set updated_at
                )
                db.session.add(duplicate_item)
                action_taken = 'duplicated'
            else:
                # Update existing unverified item quantity
                existing_item.quantity += quantity
                # Update other fields if provided
                if data.get('condition'):
                    existing_item.condition = data.get('condition')
                if data.get('notes'):
                    existing_item.notes = data.get('notes')
                if data.get('grade'):
                    existing_item.grade = data.get('grade')
                if data.get('language'):
                    existing_item.language = data.get('language')
                if data.get('foil_type'):
                    existing_item.foil_type = data.get('foil_type')
                if data.get('is_mint') is not None:
                    existing_item.is_mint = data.get('is_mint')
                existing_item.updated_at = datetime.utcnow()  # Explicitly set updated_at
                action_taken = 'updated'
        else:
            # Create new inventory item
            inventory_item = InventoryItem(
                inventory_id=user_inventory.id,
                card_id=card.id,
                quantity=quantity,
                condition=data.get('condition', 'Near Mint'),
                verification_status='unverified',
                is_verified=False,  # New items need verification
                notes=data.get('notes', ''),
                grade=data.get('grade'),
                language=data.get('language', 'English'),
                foil_type=data.get('foil_type', 'Non Foil'),
                is_mint=data.get('is_mint', False),
                updated_at=datetime.utcnow()  # Explicitly set updated_at
            )
            db.session.add(inventory_item)
            action_taken = 'added'

        db.session.commit()

        # Log the action for auditing
        UserAuditLog.create_log(
            user_id=current_user.id,
            admin_id=current_user.id,  # Self-action
            action='inventory_add',
            details=f'{action_taken.capitalize()} {quantity} x {card_name} to inventory',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        return jsonify({
            'success': True,
            'message': f'Successfully {action_taken} {quantity} x {card_name} to your inventory',
            'action': action_taken
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding item to inventory: {e}")
        return jsonify({
            'success': False,
            'error': 'An error occurred while adding the item to your inventory'
        }), 500

@app.route('/inventory/item/<int:item_id>')
@login_required
def view_inventory_item(item_id):
    """View detailed information about a specific inventory item"""
    try:
        # Get the inventory item
        item = InventoryItem.query.get_or_404(item_id)

        # Check if user owns this item
        if item.inventory.user_id != current_user.id:
            flash('You do not have permission to view this item.', 'error')
            return redirect(url_for('user_inventory'))

        # Get related data
        card = item.card
        owner = item.inventory.user
        verifier = item.verifier

        return render_template('inventory_item_detail.html',
                             item=item,
                             card=card,
                             owner=owner,
                             verifier=verifier)

    except Exception as e:
        logger.error(f"Error viewing inventory item {item_id}: {e}")
        flash('An error occurred while loading the item details.', 'error')
        return redirect(url_for('user_inventory'))

@app.route('/api/inventory/item/<int:item_id>', methods=['GET'])
@login_required
def get_inventory_item_api(item_id):
    """API endpoint to get inventory item details"""
    try:
        item = InventoryItem.query.get_or_404(item_id)

        # Check if user owns this item
        if item.inventory.user_id != current_user.id:
            return jsonify({'error': 'Permission denied'}), 403

        return jsonify({
            'success': True,
            'item': item.to_dict()
        }), 200

    except Exception as e:
        logger.error(f"Error getting inventory item {item_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'Item not found'
        }), 404

@app.route('/inventory/item/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
@inventory_item_owner_required
def edit_inventory_item(item_id):
    """Edit an inventory item"""
    try:
        # Get the inventory item
        item = InventoryItem.query.get_or_404(item_id)

        # Check if user owns this item
        if not item.can_edit(current_user):
            flash('You do not have permission to edit this item.', 'error')
            return redirect(url_for('user_inventory'))

        if request.method == 'POST':
            # Update item from form data
            try:
                update_data = {
                    'quantity': request.form.get('quantity'),
                    'condition': request.form.get('condition'),
                    'notes': request.form.get('notes'),
                    'grade': request.form.get('grade'),
                    'language': request.form.get('language'),
                    'foil_type': request.form.get('foil_type'),
                    'is_mint': 'is_mint' in request.form,
                    'is_public': 'is_public' in request.form
                }

                # Validate quantity
                if update_data['quantity']:
                    quantity = int(update_data['quantity'])
                    if quantity <= 0:
                        flash('Quantity must be greater than 0.', 'error')
                        return redirect(request.url)
                    update_data['quantity'] = quantity


                # Update the item
                try:
                    item.update_from_dict(update_data)
                    db.session.commit()
                except ValueError as e:
                    flash(str(e), 'error')
                    return redirect(request.url)

                flash('Item updated successfully!', 'success')
                return redirect(url_for('view_inventory_item', item_id=item.id))

            except Exception as e:
                db.session.rollback()
                logger.error(f"Error updating inventory item {item_id}: {e}")
                flash('An error occurred while updating the item.', 'error')
                return redirect(request.url)

        # GET request - show edit form
        return render_template('inventory_item_edit.html', item=item)

    except Exception as e:
        logger.error(f"Error editing inventory item {item_id}: {e}")
        flash('An error occurred while loading the edit form.', 'error')
        return redirect(url_for('user_inventory'))

@app.route('/api/inventory/item/<int:item_id>', methods=['PUT'])
@login_required
def update_inventory_item_api(item_id):
    """API endpoint to update inventory item"""
    try:
        item = InventoryItem.query.get_or_404(item_id)

        # Check if user owns this item
        if not item.can_edit(current_user):
            return jsonify({'success': False, 'error': 'Permission denied'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        # Update the item
        item.update_from_dict(data)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Item updated successfully',
            'item': item.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating inventory item {item_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'An error occurred while updating the item'
        }), 500

@app.route('/api/inventory/item/<int:item_id>', methods=['DELETE'])
@login_required
def delete_inventory_item_api(item_id):
    """API endpoint to delete inventory item"""
    try:
        item = InventoryItem.query.get_or_404(item_id)

        # Check if user owns this item
        if not item.can_delete(current_user):
            return jsonify({'success': False, 'error': 'Permission denied'}), 403

        # Delete the item
        db.session.delete(item)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Item deleted successfully'
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting inventory item {item_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'An error occurred while deleting the item'
        }), 500

@app.route('/api/inventory/items', methods=['GET'])
@login_required
def get_inventory_items_api():
    """API endpoint to get all inventory items for the current user"""
    try:
        # Get user's inventory
        user_inventory = UserInventory.query.filter_by(user_id=current_user.id).first()
        if not user_inventory:
            return jsonify({
                'success': True,
                'items': [],
                'total_items': 0,
                'total_value': 0
            }), 200

        # Get items with pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        search = request.args.get('search', '').strip()
        rarity_filter = request.args.get('rarity')
        condition_filter = request.args.get('condition')

        query = InventoryItem.query.filter_by(inventory_id=user_inventory.id)

        # Apply filters
        if search:
            query = query.filter(InventoryItem.card.has(Card.name.ilike(f'%{search}%')))

        if rarity_filter:
            query = query.filter(InventoryItem.card.has(Card.rarity == rarity_filter))

        if condition_filter:
            query = query.filter(InventoryItem.condition == condition_filter)

        # Get paginated results
        items = query.paginate(page=page, per_page=per_page, error_out=False)

        # Calculate totals
        all_items = query.all()
        total_value = sum(item.total_value for item in all_items)

        return jsonify({
            'success': True,
            'items': [item.to_dict() for item in items.items],
            'total_items': len(all_items),
            'total_value': float(total_value),
            'page': page,
            'per_page': per_page,
            'total_pages': items.pages,
            'has_next': items.has_next,
            'has_prev': items.has_prev
        }), 200

    except Exception as e:
        logger.error(f"Error getting inventory items: {e}")
        return jsonify({
            'success': False,
            'error': 'An error occurred while retrieving inventory items'
        }), 500

@app.route('/api/inventory/stats', methods=['GET'])
@login_required
def get_inventory_stats_api():
    """API endpoint to get inventory statistics"""
    try:
        # Get user's inventory
        user_inventory = UserInventory.query.filter_by(user_id=current_user.id).first()
        if not user_inventory:
            return jsonify({
                'success': True,
                'stats': {
                    'total_items': 0,
                    'total_value': 0,
                    'verified_items': 0,
                    'for_sale_items': 0,
                    'unique_cards': 0,
                    'by_rarity': {},
                    'by_condition': {}
                }
            }), 200

        items = user_inventory.items

        # Calculate statistics
        total_items = sum(item.quantity for item in items)
        total_value = sum(item.total_value for item in items)
        verified_items = sum(1 for item in items if item.is_verified)
        unique_cards = len(items)

        # Group by rarity
        by_rarity = {}
        for item in items:
            rarity = item.card_rarity
            if rarity not in by_rarity:
                by_rarity[rarity] = {'count': 0, 'value': 0}
            by_rarity[rarity]['count'] += item.quantity
            by_rarity[rarity]['value'] += item.total_value

        # Group by condition
        by_condition = {}
        for item in items:
            condition = item.condition
            if condition not in by_condition:
                by_condition[condition] = {'count': 0, 'value': 0}
            by_condition[condition]['count'] += item.quantity
            by_condition[condition]['value'] += item.total_value

        return jsonify({
            'success': True,
            'stats': {
                'total_items': total_items,
                'total_value': float(total_value),
                'verified_items': verified_items,
                'unique_cards': unique_cards,
                'by_rarity': by_rarity,
                'by_condition': by_condition
            }
        }), 200

    except Exception as e:
        logger.error(f"Error getting inventory stats: {e}")
        return jsonify({
            'success': False,
            'error': 'An error occurred while retrieving inventory statistics'
        }), 500

@app.route('/api/inventory/bulk-update', methods=['POST'])
@login_required
def bulk_update_inventory_api():
    """API endpoint to bulk update inventory items"""
    try:
        data = request.get_json()
        if not data or 'items' not in data:
            return jsonify({'success': False, 'error': 'No items provided'}), 400

        updates = data['items']
        results = {'updated': 0, 'failed': 0, 'errors': []}

        for update in updates:
            try:
                item_id = update.get('id')
                if not item_id:
                    results['failed'] += 1
                    results['errors'].append('Missing item ID')
                    continue

                item = InventoryItem.query.get(item_id)
                if not item or not item.can_edit(current_user):
                    results['failed'] += 1
                    results['errors'].append(f'Item {item_id}: Permission denied or not found')
                    continue

                # Update item
                item.update_from_dict(update)
                results['updated'] += 1

            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f'Item {item_id}: {str(e)}')

        # Commit all changes
        db.session.commit()

        return jsonify({
            'success': True,
            'results': results,
            'message': f'Updated {results["updated"]} items, {results["failed"]} failed'
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in bulk update: {e}")
        return jsonify({
            'success': False,
            'error': 'An error occurred during bulk update'
        }), 500

@app.route('/api/inventory/duplicate/<int:item_id>', methods=['POST'])
@login_required
def duplicate_inventory_item_api(item_id):
    """API endpoint to duplicate an inventory item"""
    try:
        # Get original item
        original_item = InventoryItem.query.get_or_404(item_id)

        # Check if user owns this item
        if not original_item.can_edit(current_user):
            return jsonify({'success': False, 'error': 'Permission denied'}), 403

        # Create duplicate
        duplicate_item = InventoryItem(
            inventory_id=original_item.inventory_id,
            card_id=original_item.card_id,
            quantity=original_item.quantity,
            condition=original_item.condition,
            is_verified=False,  # New item needs verification
            notes=f"Duplicate of {original_item.card_name}",
            grade=original_item.grade,
            language=original_item.language,
            foil_type=original_item.foil_type,
            is_mint=original_item.is_mint
        )

        db.session.add(duplicate_item)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Item duplicated successfully',
            'item': duplicate_item.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error duplicating inventory item {item_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'An error occurred while duplicating the item'
        }), 500


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
    """Soft delete a card - admin only"""
    try:
        success = storage.soft_delete_card(card_id)
        if success:
            logger.debug(f"Soft deleted card (ID: {card_id})")
            return jsonify({'success': True, 'message': 'Card deleted successfully (order history preserved)'}), 200
        else:
            return jsonify({'error': 'Card not found or already deleted'}), 404
    except Exception as e:
        logger.error(f"Error soft deleting card: {e}")
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
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'inventory_export_{timestamp}.csv'

    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/inventory/upload_csv', methods=['POST'])
@login_required
def upload_user_inventory_csv():
    """Handle CSV upload for user inventory"""
    if 'csv_file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('user_inventory'))

    file = request.files['csv_file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('user_inventory'))

    if not file.filename or not file.filename.endswith('.csv'):
        flash('Please upload a CSV file', 'error')
        return redirect(url_for('user_inventory'))

    # Security check: validate file size (max 10MB)
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Seek back to beginning

    if file_size > 10 * 1024 * 1024:  # 10MB limit
        flash('File size exceeds 10MB limit', 'error')
        return redirect(url_for('user_inventory'))

    try:
        # Read file content with UTF-8 encoding
        csv_content = file.read().decode('utf-8-sig')  # Handle BOM if present

        # Process CSV
        results = storage.process_user_inventory_csv_upload(csv_content, current_user.id)

        # Show results
        if results['success'] > 0:
            message_parts = []
            if results.get('created', 0) > 0:
                message_parts.append(f'created {results["created"]} new items')
            if results.get('updated', 0) > 0:
                message_parts.append(f'updated {results["updated"]} existing items')
            flash(f'Successfully processed {results["success"]} items ({", ".join(message_parts)})', 'success')

        if results['errors']:
            for error in results['errors'][:10]:  # Show first 10 errors
                flash(error, 'error')

            if len(results['errors']) > 10:
                flash(f'... and {len(results["errors"]) - 10} more errors', 'error')

    except UnicodeDecodeError:
        flash('Invalid file encoding. Please ensure the CSV file is saved with UTF-8 encoding.', 'error')
    except Exception as e:
        flash(f'Error processing file: {str(e)}', 'error')
        logger.error(f"User inventory CSV upload error: {e}")

    return redirect(url_for('user_inventory'))

@app.route('/inventory/download_csv')
@login_required
def download_user_inventory_csv():
    """Download user's inventory as CSV"""
    from flask import Response
    import csv
    import io

    try:
        # Get user's inventory
        user_inventory = UserInventory.query.filter_by(user_id=current_user.id).first()
        if not user_inventory:
            flash('No inventory found', 'error')
            return redirect(url_for('user_inventory'))

        # Get inventory items
        inventory_items = user_inventory.items

        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'name', 'set_name', 'rarity', 'condition', 'quantity',
            'market_price', 'language', 'notes', 'grade', 'foil_type',
            'description', 'image_url'
        ])

        # Write item data
        for item in inventory_items:
            writer.writerow([
                item.card.name if item.card else 'Unknown Card',
                item.card.set_name if item.card else 'Unknown',
                item.card.rarity if item.card else 'Unknown',
                item.condition,
                item.quantity,
                item.card.price if item.card else 0,
                item.language or 'English',  # Use default value if None
                item.notes or '',
                item.grade or '',
                item.foil_type or '',
                item.card.description if item.card else '',
                item.card.image_url if item.card else ''
            ])

        csv_content = output.getvalue()
        output.close()

        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'user_inventory_export_{timestamp}.csv'

        return Response(
            csv_content,
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )

    except Exception as e:
        flash(f'Error generating CSV: {str(e)}', 'error')
        logger.error(f"Error downloading user inventory CSV: {e}")
        return redirect(url_for('user_inventory'))

@app.route('/inventory/download_template_csv')
@login_required
def download_user_inventory_template_csv():
    """Download CSV template for user inventory import"""
    from flask import Response

    sample_csv = """name,set_name,rarity,condition,quantity,market_price,language,notes,grade,foil_type,description,image_url
"Lightning Bolt","Core Set","Common","Near Mint",10,1200,English,"Classic instant spell","PSA 10","Non Foil","A classic red instant spell","https://example.com/lightning-bolt.jpg"
"Black Lotus","Alpha","Legendary","Light Play",1,4500000,Not English,"The most powerful mox","BGS 9.5","Cold Foil","Most powerful card ever","https://example.com/black-lotus.jpg"
"Counterspell","Beta","Common","Near Mint",5,20000,English,"Counter target spell","","Normal","Blue counterspell","https://example.com/counterspell.jpg"
"""

    return Response(
        sample_csv,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=user_inventory_template.csv'}
    )


@app.route('/account/settings', methods=['GET', 'POST'])
@login_required
def account_settings():
    """User account settings page"""
    if request.method == 'POST':
        try:
            # Get form data
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            two_factor_enabled = 'two_factor_enabled' in request.form

            # Validate username
            if not username:
                flash('Username is required.', 'error')
                return redirect(request.url)

            if len(username) < 3:
                flash('Username must be at least 3 characters long.', 'error')
                return redirect(request.url)

            if not re.match(r'^[a-zA-Z0-9_]+$', username):
                flash('Username can only contain letters, numbers, and underscores.', 'error')
                return redirect(request.url)

            # Check if username is already taken by another user
            existing_user = User.query.filter(
                db.and_(User.username == username, User.id != current_user.id)
            ).first()

            if existing_user:
                flash('Username is already taken.', 'error')
                return redirect(request.url)

            # Validate email if provided
            if email and not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
                flash('Please enter a valid email address.', 'error')
                return redirect(request.url)

            # Check if email is already taken by another user
            if email:
                existing_email = User.query.filter(
                    db.and_(User.email == email, User.id != current_user.id)
                ).first()

                if existing_email:
                    flash('Email address is already registered.', 'error')
                    return redirect(request.url)

            # Handle password change
            if new_password:
                # Verify current password
                if not current_user.check_password(current_password):
                    flash('Current password is incorrect.', 'error')
                    return redirect(request.url)

                # Validate new password
                if len(new_password) < 8:
                    flash('New password must be at least 8 characters long.', 'error')
                    return redirect(request.url)

                if new_password != confirm_password:
                    flash('New passwords do not match.', 'error')
                    return redirect(request.url)

                if not any(c.isupper() for c in new_password):
                    flash('New password must contain at least one uppercase letter.', 'error')
                    return redirect(request.url)

                if not any(c.islower() for c in new_password):
                    flash('New password must contain at least one lowercase letter.', 'error')
                    return redirect(request.url)

                if not any(c.isdigit() for c in new_password):
                    flash('New password must contain at least one number.', 'error')
                    return redirect(request.url)

                if not any(c in '!@#$%^&*(),.?":{}|<>' for c in new_password):
                    flash('New password must contain at least one special character.', 'error')
                    return redirect(request.url)

                # Hash and set new password
                from werkzeug.security import generate_password_hash
                current_user.password_hash = generate_password_hash(new_password)

            # Update user information
            changes_made = []

            if current_user.username != username:
                changes_made.append(f'username: {current_user.username} → {username}')
                current_user.username = username

            if current_user.email != email:
                changes_made.append(f'email: {current_user.email or "None"} → {email or "None"}')
                current_user.email = email

            if new_password:
                changes_made.append('password changed')

            if current_user.two_factor_enabled != two_factor_enabled:
                changes_made.append(f'two-factor auth: {"enabled" if current_user.two_factor_enabled else "disabled"} → {"enabled" if two_factor_enabled else "disabled"}')
                current_user.two_factor_enabled = two_factor_enabled

            # Save changes
            db.session.commit()

            # Log the changes
            if changes_made:
                UserAuditLog.create_log(
                    user_id=current_user.id,
                    admin_id=current_user.id,  # Self-action
                    action='account_update',
                    details=f'Updated account settings: {", ".join(changes_made)}',
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )

            flash('Account settings updated successfully!', 'success')
            return redirect(request.url)

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating account settings for user {current_user.id}: {e}")
            flash('An error occurred while updating your account settings.', 'error')

    return render_template('account_settings.html')

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
    try:
        cart_session = _get_or_create_cart_session()
        cart_count = sum(item.quantity for item in cart_session.items)
    except:
        cart_count = 0
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

# REMOVED: Old cart helper functions for session-based cart system
# These functions have been removed as they are no longer needed with the database-based cart system

# ---- ENHANCED: endpoint JSON để thêm vào giỏ (supports both admin and user items) ----
@app.post("/cart/add")
def cart_add_json():
    """
    Body: JSON {
        "item_type": "admin|user",
        "card_id": <int> (for admin items),
        "inventory_item_id": <int> (for user items),
        "qty": <int (optional, default 1)>
    }
    Trả: { ok, at_max, item_qty, cart_qty, subtotal, message, flashed_messages }
    """
    logger.info("=== CART ADD JSON DEBUG ===")

    # Handle both JSON and form data
    if request.is_json:
        payload = request.get_json()
        logger.info(f"JSON payload: {payload}")
        item_type = payload.get("item_type", "admin")
        qty = payload.get("qty", 1)
        card_id = payload.get("card_id")
        inventory_item_id = payload.get("inventory_item_id")
    else:
        # Handle form data
        payload = request.form
        logger.info(f"Form payload: {payload}")
        item_type = payload.get("item_type", "admin")
        qty = payload.get("qty", 1)
        card_id = payload.get("card_id")
        inventory_item_id = payload.get("inventory_item_id")

    logger.info(f"Item type: {item_type}, Quantity: {qty}, Card ID: {card_id}, Inventory Item ID: {inventory_item_id}")

    try:
        qty = max(1, int(qty))
    except Exception as e:
        logger.error(f"Invalid quantity: {qty}, Error: {e}")
        flash('Invalid quantity', 'error')
        return jsonify(ok=False, message="Invalid quantity",
                      flashed_messages=list_flashed_messages()), 400

    # Handle admin items using new database system
    if item_type == "admin":
        if not card_id:
            flash('Invalid card ID', 'error')
            return jsonify(ok=False, message="Invalid card_id",
                          flashed_messages=list_flashed_messages()), 400

        try:
            card_id = int(card_id)
        except Exception:
            flash('Invalid card ID', 'error')
            return jsonify(ok=False, message="Invalid card_id",
                          flashed_messages=list_flashed_messages()), 400

        success, message = _add_to_cart("admin", card_id, qty)

        if not success:
            flash(message, 'error')
            return jsonify(ok=False, message=message,
                          flashed_messages=list_flashed_messages()), 400

        # Get updated cart info
        cart_session = _get_or_create_cart_session()
        cart_item = CartItem.query.filter_by(
            session_id=cart_session.id,
            card_id=card_id
        ).first()

        if cart_item:
            card = cart_item.card
            card_name = card.name if card else "Unknown Card"
            flash(f'Added {qty} x {card_name} to cart', 'success')
            return jsonify(ok=True,
                          at_max=(cart_item.quantity >= cart_item.available_quantity),
                          item_qty=cart_item.quantity,
                          cart_qty=len(cart_session.items),
                          subtotal=str(sum(item.item_total for item in cart_session.items)),
                          flashed_messages=list_flashed_messages()), 200
        else:
            flash('Error adding item to cart', 'error')
            return jsonify(ok=False, message="Error adding item to cart",
                          flashed_messages=list_flashed_messages()), 500

    # Handle user inventory items
    elif item_type == "user":
        if not inventory_item_id:
            logger.error("No inventory_item_id provided for user item")
            flash('Invalid inventory item ID', 'error')
            return jsonify(ok=False, message="Invalid inventory_item_id",
                          flashed_messages=list_flashed_messages()), 400

        try:
            inventory_item_id = int(inventory_item_id)
        except Exception as e:
            logger.error(f"Invalid inventory_item_id format: {inventory_item_id}, Error: {e}")
            flash('Invalid inventory item ID', 'error')
            return jsonify(ok=False, message="Invalid inventory_item_id",
                          flashed_messages=list_flashed_messages()), 400

        logger.info(f"Processing user item with inventory_item_id: {inventory_item_id}")
        success, message = _add_to_cart("user", inventory_item_id, qty)

        if not success:
            logger.error(f"Failed to add user item to cart: {message}")
            flash(message, 'error')
            return jsonify(ok=False, message=message,
                          flashed_messages=list_flashed_messages()), 400

        # Get updated cart info
        cart_session = _get_or_create_cart_session()
        cart_item = CartItem.query.filter_by(
            session_id=cart_session.id,
            inventory_item_id=inventory_item_id
        ).first()

        if cart_item:
            card_name = cart_item.inventory_item.card.name if cart_item.inventory_item and cart_item.inventory_item.card else "Unknown Card"
            logger.info(f"Successfully added user item: {card_name} x {cart_item.quantity}")
            flash(f'Added {qty} x {card_name} to cart', 'success')
            return jsonify(ok=True,
                          at_max=(cart_item.quantity >= cart_item.available_quantity),
                          item_qty=cart_item.quantity,
                          cart_qty=len(cart_session.items),
                          subtotal=str(sum(item.item_total for item in cart_session.items)),
                          flashed_messages=list_flashed_messages()), 200

    logger.error(f"Invalid item type: {item_type}")
    flash('Invalid item type', 'error')
    return jsonify(ok=False, message="Invalid item type",
                  flashed_messages=list_flashed_messages()), 400

def list_flashed_messages():
    """Helper function to get all flashed messages"""
    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append({
            'category': category,
            'message': message
        })
    return messages

def _get_or_create_cart_session():
    """Get or create a cart session for the current user"""
    logger.info("=== GET OR CREATE CART SESSION DEBUG ===")

    # Use session ID as cart session identifier
    session_id = session.get('_id')
    logger.info(f"Current session _id: {session_id}")

    if not session_id:
        import uuid
        session_id = str(uuid.uuid4())
        session['_id'] = session_id
        logger.info(f"Generated new session ID: {session_id}")

    # Try to find existing cart session
    cart_session = CartSession.query.filter_by(id=session_id).first()
    logger.info(f"Found existing cart session: {cart_session.id if cart_session else 'None'}")

    if not cart_session:
        logger.info("Creating new cart session...")
        # Create new cart session
        cart_session = CartSession(
            id=session_id,
            user_id=current_user.id if current_user.is_authenticated else None
        )
        db.session.add(cart_session)
        try:
            db.session.commit()
            logger.info(f"Successfully created cart session: {cart_session.id}")
        except Exception as e:
            logger.error(f"Failed to create cart session: {e}")
            db.session.rollback()
            return None

    return cart_session

def _add_to_cart(item_type, item_id, quantity=1):
    """Add item to cart (supports both admin and user inventory items)"""
    logger.info("=== ADD TO CART DEBUG ===")
    logger.info(f"Item type: {item_type}, Item ID: {item_id}, Quantity: {quantity}")

    try:
        cart_session = _get_or_create_cart_session()
        logger.info(f"Cart session obtained: {cart_session.id if cart_session else 'None'}")

        if not cart_session:
            logger.error("Failed to get cart session")
            return False, "Failed to create cart session"

        # Validate the item and quantity
        if item_type == 'admin':
            card = Card.query.get(item_id)
            logger.info(f"Admin card lookup: {card.name if card else 'None'}")
            if not card or card.is_deleted or card.quantity < quantity:
                logger.error(f"Card not available: deleted={card.is_deleted if card else 'N/A'}, quantity={card.quantity if card else 'N/A'}")
                return False, "Item not available or insufficient stock"
            price = card.price
            available_quantity = card.quantity

        elif item_type == 'user':
            inventory_item = InventoryItem.query.get(item_id)
            logger.info(f"User inventory item lookup: {inventory_item.card.name if inventory_item and inventory_item.card else 'None'}")
            if not inventory_item or not inventory_item.is_verified:
                logger.error(f"Inventory item not available: exists={inventory_item is not None}, verified={inventory_item.is_verified if inventory_item else 'N/A'}")
                return False, "Item not available for purchase"
            if inventory_item.quantity < quantity:
                logger.error(f"Insufficient stock: available={inventory_item.quantity}, requested={quantity}")
                return False, "Insufficient stock"
            price = inventory_item.card.price if inventory_item.card else 0
            available_quantity = inventory_item.quantity
        else:
            logger.error(f"Invalid item type: {item_type}")
            return False, "Invalid item type"

        # Check if item already in cart
        existing_item = None
        if item_type == 'admin':
            existing_item = CartItem.query.filter_by(
                session_id=cart_session.id,
                card_id=item_id
            ).first()
        elif item_type == 'user':
            existing_item = CartItem.query.filter_by(
                session_id=cart_session.id,
                inventory_item_id=item_id
            ).first()

        logger.info(f"Existing cart item: {existing_item.id if existing_item else 'None'}")

        if existing_item:
            # Update quantity
            new_quantity = min(existing_item.quantity + quantity, available_quantity)
            logger.info(f"Updating existing item quantity: {existing_item.quantity} -> {new_quantity}")
            existing_item.quantity = new_quantity
        else:
            # Create new cart item
            logger.info("Creating new cart item")
            cart_item = CartItem(
                session_id=cart_session.id,
                card_id=item_id if item_type == 'admin' else None,
                inventory_item_id=item_id if item_type == 'user' else None,
                quantity=min(quantity, available_quantity)
            )
            db.session.add(cart_item)

        db.session.commit()
        logger.info("Successfully committed cart changes")
        return True, "Item added to cart"

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding item to cart: {e}")
        return False, "Error adding item to cart"

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
    
    
    # User Management Routes
    
    @app.route('/admin/users')
    @admin_required
    def admin_users():
        """Admin user management page with search, filter, and sort capabilities"""
        try:
            # Get query parameters
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
            search = request.args.get('search', '').strip()
            role_filter = request.args.get('role', '')
            status_filter = request.args.get('status', '')
            sort_by = request.args.get('sort', 'created_at_desc')
    
            # Build query
            query = User.query
    
            # Apply search filter
            if search:
                query = query.filter(
                    db.or_(
                        User.username.ilike(f'%{search}%'),
                        User.email.ilike(f'%{search}%')
                    )
                )
    
            # Apply role filter
            if role_filter:
                query = query.filter(User.role == role_filter)
    
            # Apply status filter
            if status_filter:
                query = query.filter(User.account_status == status_filter)
    
            # Apply sorting
            if sort_by == 'username_asc':
                query = query.order_by(User.username.asc())
            elif sort_by == 'username_desc':
                query = query.order_by(User.username.desc())
            elif sort_by == 'email_asc':
                query = query.order_by(User.email.asc())
            elif sort_by == 'email_desc':
                query = query.order_by(User.email.desc())
            elif sort_by == 'created_at_asc':
                query = query.order_by(User.created_at.asc())
            elif sort_by == 'created_at_desc':
                query = query.order_by(User.created_at.desc())
            elif sort_by == 'last_login_asc':
                query = query.order_by(User.last_login.asc().nulls_last())
            elif sort_by == 'last_login_desc':
                query = query.order_by(User.last_login.desc().nulls_first())
            else:
                query = query.order_by(User.created_at.desc())
    
            # Paginate results
            users_pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            users = users_pagination.items
    
            # Get statistics
            total_users = User.query.count()
            active_users = User.query.filter_by(account_status='active').count()
            suspended_users = User.query.filter_by(account_status='suspended').count()
            banned_users = User.query.filter_by(account_status='banned').count()
            admin_users = User.query.filter_by(role='admin').count()
    
            return render_template('admin_users.html',
                                 users=users,
                                 pagination=users_pagination,
                                 search=search,
                                 role_filter=role_filter,
                                 status_filter=status_filter,
                                 sort_by=sort_by,
                                 per_page=per_page,
                                 total_users=total_users,
                                 active_users=active_users,
                                 suspended_users=suspended_users,
                                 banned_users=banned_users,
                                 admin_users=admin_users)
    
        except Exception as e:
            logger.error(f"Error loading admin users page: {e}")
            flash('An error occurred while loading the users page.', 'error')
            return redirect(url_for('admin'))
    
    
    @app.route('/admin/users/<int:user_id>')
    @admin_required
    def admin_user_detail(user_id):
        """View detailed information about a specific user"""
        try:
            user = User.query.get_or_404(user_id)
    
            # Get user's inventory statistics
            user_inventory = UserInventory.query.filter_by(user_id=user_id).first()
            inventory_stats = {'total_items': 0, 'verified_items': 0, 'total_value': 0}
    
            if user_inventory:
                inventory_items = user_inventory.items
                inventory_stats['total_items'] = sum(item.quantity for item in inventory_items)
                inventory_stats['verified_items'] = sum(1 for item in inventory_items if item.is_verified)
                inventory_stats['total_value'] = sum(item.total_value for item in inventory_items)
    
            # Get recent activity (orders)
            recent_orders = Order.query.filter_by(customer_name=user.username).order_by(Order.created_at.desc()).limit(5).all()
    
            return render_template('admin_user_detail.html',
                                 user=user,
                                 inventory_stats=inventory_stats,
                                 recent_orders=recent_orders)
    
        except Exception as e:
            logger.error(f"Error loading user detail page for user {user_id}: {e}")
            flash('An error occurred while loading the user details.', 'error')
            return redirect(url_for('admin_users'))
    
    
    @app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
    @admin_required
    def admin_edit_user(user_id):
        """Edit user account information"""
        try:
            user = User.query.get_or_404(user_id)
    
            if request.method == 'POST':
                # Get form data
                username = request.form.get('username', '').strip()
                email = request.form.get('email', '').strip()
                role = request.form.get('role', 'user')
                account_status = request.form.get('account_status', 'active')
    
                # Validate input
                if not username:
                    flash('Username is required.', 'error')
                    return redirect(request.url)
    
                if not email:
                    flash('Email is required.', 'error')
                    return redirect(request.url)
    
                # Check for duplicate username/email
                existing_user = User.query.filter(
                    db.and_(
                        db.or_(User.username == username, User.email == email),
                        User.id != user_id
                    )
                ).first()
    
                if existing_user:
                    if existing_user.username == username:
                        flash('Username already exists.', 'error')
                    else:
                        flash('Email address already exists.', 'error')
                    return redirect(request.url)
    
                # Update user
                user.username = username
                user.email = email
                user.role = role
                user.account_status = account_status
    
                # Handle suspension details
                if account_status == 'suspended':
                    suspension_reason = request.form.get('suspension_reason', '').strip()
                    suspension_days = request.form.get('suspension_days', type=int)
    
                    user.suspension_reason = suspension_reason
                    if suspension_days and suspension_days > 0:
                        user.suspension_expires = datetime.utcnow() + timedelta(days=suspension_days)
                    else:
                        user.suspension_expires = None
                else:
                    user.suspension_reason = None
                    user.suspension_expires = None
    
                db.session.commit()
    
                # Log the action
                log_user_action(current_user.id, user_id, 'edit', f'Updated user details: role={role}, status={account_status}')
    
                flash(f'User {username} has been updated successfully.', 'success')
                return redirect(url_for('admin_user_detail', user_id=user_id))
    
            return render_template('admin_edit_user.html', user=user)
    
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error editing user {user_id}: {e}")
            flash('An error occurred while updating the user.', 'error')
            return redirect(url_for('admin_users'))
    
    
    @app.route('/admin/users/<int:user_id>/suspend', methods=['POST'])
    @admin_required
    def admin_suspend_user(user_id):
        """Suspend a user account"""
        try:
            user = User.query.get_or_404(user_id)
            reason = request.form.get('reason', '').strip()
            days = request.form.get('days', type=int)
    
            user.suspend_account(reason, datetime.utcnow() + timedelta(days=days) if days else None, current_user)
            db.session.commit()
    
            # Log the action
            log_user_action(current_user.id, user_id, 'suspend', f'Suspended user account: {reason}')
    
            flash(f'User {user.username} has been suspended.', 'warning')
            return redirect(url_for('admin_user_detail', user_id=user_id))
    
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error suspending user {user_id}: {e}")
            flash('An error occurred while suspending the user.', 'error')
            return redirect(url_for('admin_users'))
    
    
    @app.route('/admin/users/<int:user_id>/ban', methods=['POST'])
    @admin_required
    def admin_ban_user(user_id):
        """Ban a user account"""
        try:
            user = User.query.get_or_404(user_id)
            reason = request.form.get('reason', '').strip()
    
            user.ban_account(reason, current_user)
            db.session.commit()
    
            # Log the action
            log_user_action(current_user.id, user_id, 'ban', f'Banned user account: {reason}')
    
            flash(f'User {user.username} has been banned.', 'danger')
            return redirect(url_for('admin_user_detail', user_id=user_id))
    
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error banning user {user_id}: {e}")
            flash('An error occurred while banning the user.', 'error')
            return redirect(url_for('admin_users'))
    
    
    @app.route('/admin/users/<int:user_id>/reactivate', methods=['POST'])
    @admin_required
    def admin_reactivate_user(user_id):
        """Reactivate a suspended user account"""
        try:
            user = User.query.get_or_404(user_id)
    
            user.reactivate_account(current_user)
            db.session.commit()
    
            # Log the action
            log_user_action(current_user.id, user_id, 'reactivate', 'Reactivated user account')
    
            flash(f'User {user.username} has been reactivated.', 'success')
            return redirect(url_for('admin_user_detail', user_id=user_id))
    
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error reactivating user {user_id}: {e}")
            flash('An error occurred while reactivating the user.', 'error')
            return redirect(url_for('admin_users'))
    
    
    @app.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
    @admin_required
    def admin_reset_password(user_id):
        """Reset user password"""
        try:
            user = User.query.get_or_404(user_id)
    
            # Generate new password
            import secrets
            import string
            new_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    
            # Hash and set new password
            user.password_hash = generate_password_hash(new_password)
            user.password_reset_token = None
            user.password_reset_expires = None
            db.session.commit()
    
            # Log the action
            log_user_action(current_user.id, user_id, 'reset_password', 'Password reset by admin')
    
            flash(f'Password for {user.username} has been reset. New password: {new_password}', 'warning')
            return redirect(url_for('admin_user_detail', user_id=user_id))
    
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error resetting password for user {user_id}: {e}")
            flash('An error occurred while resetting the password.', 'error')
            return redirect(url_for('admin_users'))
    
    
    
    
    @app.route('/admin/users/export')
    @admin_required
    def admin_export_users():
        """Export user data as CSV"""
        try:
            # Get all users
            users = User.query.order_by(User.created_at.desc()).all()
    
            # Create CSV content
            import io
            import csv
    
            output = io.StringIO()
            writer = csv.writer(output)
    
            # Write header
            writer.writerow([
                'ID', 'Username', 'Email', 'Role', 'Account Status',
                'Created At', 'Last Login', 'Suspension Reason', 'Suspension Expires'
            ])
    
            # Write user data
            for user in users:
                writer.writerow([
                    user.id,
                    user.username,
                    user.email,
                    user.role,
                    user.account_status,
                    user.created_at.isoformat() if user.created_at else '',
                    user.last_login.isoformat() if user.last_login else '',
                    user.suspension_reason or '',
                    user.suspension_expires.isoformat() if user.suspension_expires else ''
                ])
    
            csv_content = output.getvalue()
            output.close()
    
            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'users_export_{timestamp}.csv'
    
            from flask import Response
            return Response(
                csv_content,
                mimetype='text/csv; charset=utf-8',
                headers={'Content-Disposition': f'attachment; filename={filename}'}
            )
    
        except Exception as e:
            logger.error(f"Error exporting users: {e}")
            flash('An error occurred while exporting user data.', 'error')
            return redirect(url_for('admin_users'))
    
    
    def log_user_action(admin_id, user_id, action, details=None, ip_address=None):
        """Log admin action on user account"""
        try:
            audit_log = UserAuditLog(
                user_id=user_id,
                admin_id=admin_id,
                action=action,
                details=details,
                ip_address=ip_address or request.remote_addr if request else None,
                user_agent=request.headers.get('User-Agent') if request else None
            )
            db.session.add(audit_log)
            db.session.commit()
        except Exception as e:
            logger.error(f"Error logging user action: {e}")
            db.session.rollback()

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


# User Management Routes
@app.route('/admin/users')
@admin_required
def admin_users():
    """Admin user management page - view all users with search/filter/sort"""
    # Get query parameters
    search = request.args.get('search', '').strip()
    role_filter = request.args.get('role', '')
    status_filter = request.args.get('status', '')
    sort_by = request.args.get('sort', 'created_at_desc')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))

    # Build query
    query = User.query

    # Apply filters
    if search:
        query = query.filter(
            db.or_(
                User.username.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%')
            )
        )

    if role_filter:
        query = query.filter(User.role == role_filter)

    if status_filter:
        query = query.filter(User.account_status == status_filter)

    # Apply sorting
    if sort_by == 'username_asc':
        query = query.order_by(User.username.asc())
    elif sort_by == 'username_desc':
        query = query.order_by(User.username.desc())
    elif sort_by == 'email_asc':
        query = query.order_by(User.email.asc())
    elif sort_by == 'email_desc':
        query = query.order_by(User.email.desc())
    elif sort_by == 'created_at_asc':
        query = query.order_by(User.created_at.asc())
    elif sort_by == 'last_login_desc':
        query = query.order_by(User.last_login.desc().nullslast())
    else:  # created_at_desc (default)
        query = query.order_by(User.created_at.desc())

    # Get paginated results
    users = query.paginate(page=page, per_page=per_page, error_out=False)

    # Calculate statistics
    total_users = User.query.count()
    active_users = User.query.filter_by(account_status='active').count()
    suspended_users = User.query.filter_by(account_status='suspended').count()
    banned_users = User.query.filter_by(account_status='banned').count()
    admin_users = User.query.filter_by(role='admin').count()

    return render_template('admin_users.html',
                         users=users,
                         search=search,
                         role_filter=role_filter,
                         status_filter=status_filter,
                         sort_by=sort_by,
                         per_page=per_page,
                         stats={
                             'total': total_users,
                             'active': active_users,
                             'suspended': suspended_users,
                             'banned': banned_users,
                             'admins': admin_users
                         })


@app.route('/admin/users/<int:user_id>')
@admin_required
def admin_user_detail(user_id):
    """View detailed information about a specific user"""
    user = User.query.get_or_404(user_id)

    # Get user's inventory and items
    user_inventory = UserInventory.query.filter_by(user_id=user_id).first()
    inventory_stats = {'total_items': 0, 'verified_items': 0, 'total_value': 0}
    inventory_items = []

    if user_inventory:
        items = user_inventory.items
        inventory_stats['total_items'] = sum(item.quantity for item in items)
        inventory_stats['verified_items'] = sum(1 for item in items if item.is_verified)
        inventory_stats['total_value'] = sum(item.total_value for item in items)

        # Get detailed inventory items with pagination
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))

        # Sort items by card name
        inventory_items = sorted(items, key=lambda x: x.card_name.lower())

        # Apply pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_items = inventory_items[start_idx:end_idx]

        # Calculate pagination info
        total_pages = (len(inventory_items) + per_page - 1) // per_page

        inventory_items = {
            'items': paginated_items,
            'total': len(inventory_items),
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None
        }

    # Get recent orders
    recent_orders = Order.query.filter_by(customer_name=user.username).order_by(Order.created_at.desc()).limit(5).all()

    return render_template('admin_user_detail.html',
                         user=user,
                         inventory_stats=inventory_stats,
                         inventory_items=inventory_items.get('items', []) if isinstance(inventory_items, dict) else [],
                         inventory_pagination=inventory_items if isinstance(inventory_items, dict) else {},
                         recent_orders=recent_orders)


@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_user(user_id):
    """Edit user details"""
    user = User.query.get_or_404(user_id)

    # Prevent regular admins from editing super admin users
    if user.is_super_admin() and not current_user.is_super_admin():
        flash('You do not have permission to edit super admin users.', 'error')
        return redirect(url_for('admin_users'))

    if request.method == 'POST':
        try:
            # Get form data
            new_role = request.form.get('role', user.role)

            # Prevent setting users to super_admin role unless current user is super_admin
            if new_role == 'super_admin' and not current_user.is_super_admin():
                flash('You do not have permission to set users as super admin.', 'error')
                return redirect(request.url)

            # Prevent changing super_admin role unless current user is super_admin
            if user.is_super_admin() and not current_user.is_super_admin():
                flash('You do not have permission to modify super admin users.', 'error')
                return redirect(request.url)

            # Update user details
            user.username = request.form.get('username', user.username).strip()
            user.email = request.form.get('email', user.email).strip() if request.form.get('email') else None
            user.role = new_role
            user.account_status = request.form.get('account_status', user.account_status)

            # Handle suspension details
            if user.account_status == 'suspended':
                user.suspension_reason = request.form.get('suspension_reason')
                suspension_days = request.form.get('suspension_days')
                if suspension_days and suspension_days.isdigit():
                    user.suspension_expires = datetime.utcnow() + timedelta(days=int(suspension_days))
                else:
                    user.suspension_expires = None
            elif user.account_status == 'banned':
                user.suspension_reason = request.form.get('ban_reason')
                user.suspension_expires = None
            else:
                user.suspension_reason = None
                user.suspension_expires = None

            db.session.commit()

            # Log the action
            UserAuditLog.create_log(
                user_id=user.id,
                admin_id=current_user.id,
                action='edit',
                details=f'Updated user details',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )

            flash(f'User {user.username} updated successfully', 'success')
            return redirect(url_for('admin_user_detail', user_id=user.id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating user {user_id}: {e}")
            flash('Error updating user', 'error')

    return render_template('admin_edit_user.html', user=user)


@app.route('/admin/users/<int:user_id>/suspend', methods=['POST'])
@admin_required
def admin_suspend_user(user_id):
    """Suspend a user account"""
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('You cannot suspend your own account', 'error')
        return redirect(url_for('admin_user_detail', user_id=user_id))

    # Prevent regular admins from suspending super admin users
    if user.is_super_admin() and not current_user.is_super_admin():
        flash('You do not have permission to suspend super admin users.', 'error')
        return redirect(url_for('admin_user_detail', user_id=user_id))

    try:
        reason = request.form.get('reason', 'Administrative suspension')
        suspension_days = request.form.get('days')

        if suspension_days and suspension_days.isdigit():
            expires_at = datetime.utcnow() + timedelta(days=int(suspension_days))
            user.suspend_account(reason, expires_at, current_user)
        else:
            user.suspend_account(reason, admin_user=current_user)

        db.session.commit()

        # Log the action
        UserAuditLog.create_log(
            user_id=user.id,
            admin_id=current_user.id,
            action='suspend',
            details=f'Suspended user account: {reason}',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        flash(f'User {user.username} has been suspended', 'success')
        logger.info(f"User {user.username} suspended by admin {current_user.username}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error suspending user {user_id}: {e}")
        flash('Error suspending user', 'error')

    return redirect(url_for('admin_user_detail', user_id=user_id))


@app.route('/admin/users/<int:user_id>/ban', methods=['POST'])
@admin_required
def admin_ban_user(user_id):
    """Ban a user account"""
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('You cannot ban your own account', 'error')
        return redirect(url_for('admin_user_detail', user_id=user_id))

    # Prevent regular admins from banning super admin users
    if user.is_super_admin() and not current_user.is_super_admin():
        flash('You do not have permission to ban super admin users.', 'error')
        return redirect(url_for('admin_user_detail', user_id=user_id))

    try:
        reason = request.form.get('reason', 'Administrative ban')
        user.ban_account(reason, current_user)
        db.session.commit()

        # Log the action
        UserAuditLog.create_log(
            user_id=user.id,
            admin_id=current_user.id,
            action='ban',
            details=f'Banned user account: {reason}',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        flash(f'User {user.username} has been banned', 'warning')
        logger.info(f"User {user.username} banned by admin {current_user.username}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error banning user {user_id}: {e}")
        flash('Error banning user', 'error')

    return redirect(url_for('admin_user_detail', user_id=user_id))


@app.route('/admin/users/<int:user_id>/reactivate', methods=['POST'])
@admin_required
def admin_reactivate_user(user_id):
    """Reactivate a suspended user account"""
    user = User.query.get_or_404(user_id)

    try:
        user.reactivate_account(current_user)
        db.session.commit()

        # Log the action
        UserAuditLog.create_log(
            user_id=user.id,
            admin_id=current_user.id,
            action='reactivate',
            details='Reactivated user account',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        flash(f'User {user.username} has been reactivated', 'success')
        logger.info(f"User {user.username} reactivated by admin {current_user.username}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error reactivating user {user_id}: {e}")
        flash('Error reactivating user', 'error')

    return redirect(url_for('admin_user_detail', user_id=user_id))


@app.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def admin_reset_password(user_id):
    """Reset user password"""
    user = User.query.get_or_404(user_id)

    # Prevent regular admins from resetting passwords for super admin users
    if user.is_super_admin() and not current_user.is_super_admin():
        flash('You do not have permission to reset passwords for super admin users.', 'error')
        return redirect(url_for('admin_user_detail', user_id=user_id))

    try:
        # Generate a temporary password
        import secrets
        import string
        temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))

        # Hash and set the new password
        user.password_hash = generate_password_hash(temp_password)
        db.session.commit()

        # Log the action
        UserAuditLog.create_log(
            user_id=user.id,
            admin_id=current_user.id,
            action='reset_password',
            details='Password reset by admin',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        flash(f'Password reset for {user.username}. New password: {temp_password}', 'success')
        logger.info(f"Password reset for user {user.username} by admin {current_user.username}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error resetting password for user {user_id}: {e}")
        flash('Error resetting password', 'error')

    return redirect(url_for('admin_user_detail', user_id=user_id))


@app.route('/admin/users/export')
@admin_required
def admin_export_users():
    """Export user data as CSV"""
    from flask import Response
    import csv
    import io

    try:
        users = User.query.order_by(User.created_at.desc()).all()

        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'ID', 'Username', 'Email', 'Role', 'Account Status',
            'Created At', 'Last Login', 'Suspension Reason', 'Suspension Expires'
        ])

        # Write user data
        for user in users:
            writer.writerow([
                user.id,
                user.username,
                user.email or '',
                user.role,
                user.account_status,
                user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else '',
                user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else '',
                user.suspension_reason or '',
                user.suspension_expires.strftime('%Y-%m-%d %H:%M:%S') if user.suspension_expires else ''
            ])

        csv_content = output.getvalue()
        output.close()

        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'users_export_{timestamp}.csv'

        return Response(
            csv_content,
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )

    except Exception as e:
        logger.error(f"Error exporting users: {e}")
        flash('Error exporting users', 'error')
        return redirect(url_for('admin_users'))


# Inventory Verification Management Routes
@app.route('/admin/users/<int:user_id>/inventory/<int:item_id>/verify', methods=['POST'])
@admin_required
def admin_update_verification_status(user_id, item_id):
    """Update verification status of a user's inventory item"""
    user = User.query.get_or_404(user_id)
    item = InventoryItem.query.get_or_404(item_id)

    # Verify the item belongs to the user
    if item.inventory.user_id != user_id:
        flash('Item does not belong to this user', 'error')
        return redirect(url_for('admin_user_detail', user_id=user_id))

    try:
        new_status = request.form.get('verification_status')
        notes = request.form.get('notes', '').strip()

        if new_status not in ['unverified', 'pending', 'verified']:
            flash('Invalid verification status', 'error')
            return redirect(url_for('admin_user_detail', user_id=user_id))

        # Update the verification status
        item.update_verification_status(
            new_status=new_status,
            admin_user=current_user,
            notes=notes
        )

        # Set IP address and user agent for audit log
        audit_log = VerificationAuditLog.query.filter_by(
            inventory_item_id=item.id,
            admin_id=current_user.id
        ).order_by(VerificationAuditLog.created_at.desc()).first()

        if audit_log:
            audit_log.ip_address = request.remote_addr
            audit_log.user_agent = request.headers.get('User-Agent')
            db.session.commit()

        db.session.commit()

        status_display = item.verification_status_display
        flash(f'Item verification status updated to: {status_display}', 'success')
        logger.info(f"Admin {current_user.username} updated verification status of item {item.id} to {new_status}")

    except ValueError as e:
        db.session.rollback()
        logger.error(f"Validation error updating verification status for item {item_id}: {e}")
        flash(str(e), 'error')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating verification status for item {item_id}: {e}")
        flash('Error updating verification status', 'error')

    return redirect(url_for('admin_user_detail', user_id=user_id))


@app.route('/admin/verification-queue')
@admin_required
def admin_verification_queue():
    """View all items pending verification"""
    # Get items that need verification (unverified or pending status)
    pending_items = InventoryItem.query.filter(
        InventoryItem.verification_status.in_(['unverified', 'pending'])
    ).join(UserInventory).join(User).order_by(InventoryItem.added_at.desc()).all()

    return render_template('admin_verification_queue.html',
                          pending_items=pending_items,
                          total_pending=len(pending_items))


# Admin Coupon Management Routes

@app.route('/admin/coupons')
@admin_required
def admin_coupons():
    """Admin coupon management page"""
    try:
        logger.info("=== ADMIN COUPONS DEBUG ===")
        logger.info("Starting admin coupons page load")

        # Get query parameters
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        search = request.args.get('search', '').strip()
        status_filter = request.args.get('status', '')

        logger.info(f"Query parameters: page={page}, per_page={per_page}, search='{search}', status_filter='{status_filter}'")

        # Build query
        query = Coupon.query
        logger.info("Coupon query created")

        # Apply search filter
        if search:
            query = query.filter(Coupon.code.ilike(f'%{search}%'))
            logger.info(f"Applied search filter: {search}")

        # Apply status filter
        if status_filter:
            if status_filter == 'active':
                query = query.filter(Coupon.is_active == True)
            elif status_filter == 'inactive':
                query = query.filter(Coupon.is_active == False)
            elif status_filter == 'expired':
                query = query.filter(Coupon.valid_until < datetime.utcnow())
            logger.info(f"Applied status filter: {status_filter}")

        # Order by creation date (newest first)
        query = query.order_by(Coupon.created_at.desc())
        logger.info("Applied ordering")

        # Get paginated results
        logger.info("Getting paginated results...")
        coupons_pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        coupons = coupons_pagination.items
        logger.info(f"Got {len(coupons)} coupons for page {page}")

        # Calculate statistics
        logger.info("Calculating statistics...")
        total_coupons = Coupon.query.count()
        active_coupons = Coupon.query.filter_by(is_active=True).count()
        used_coupons = Coupon.query.filter(Coupon.usage_count > 0).count()
        logger.info(f"Stats: total={total_coupons}, active={active_coupons}, used={used_coupons}")

        logger.info("Rendering template...")
        return render_template('admin_coupons.html',
                              coupons=coupons,
                              pagination=coupons_pagination,
                              search=search,
                              status_filter=status_filter,
                              per_page=per_page,
                              total_coupons=total_coupons,
                              active_coupons=active_coupons,
                              used_coupons=used_coupons,
                              datetime=datetime,
                              now=datetime.utcnow())

    except Exception as e:
        logger.error(f"Error loading admin coupons page: {e}")
        logger.error(f"Error type: {type(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        flash('An error occurred while loading the coupons page.', 'error')
        return redirect(url_for('admin'))


@app.route('/admin/coupons/create', methods=['GET', 'POST'])
@admin_required
def admin_create_coupon():
    """Create a new coupon"""
    if request.method == 'POST':
        try:
            # Get form data
            code = request.form.get('code', '').strip().upper()
            discount_percentage = float(request.form.get('discount_percentage', 0))
            description = request.form.get('description', '').strip()
            valid_from = request.form.get('valid_from')
            valid_until = request.form.get('valid_until')
            usage_limit = request.form.get('usage_limit')
            is_active = 'is_active' in request.form

            # Validation
            if not code:
                flash('Coupon code is required.', 'error')
                return redirect(request.url)

            if discount_percentage <= 0 or discount_percentage > 100:
                flash('Discount percentage must be between 0 and 100.', 'error')
                return redirect(request.url)

            # Check if code already exists
            existing_coupon = Coupon.query.filter_by(code=code).first()
            if existing_coupon:
                flash('A coupon with this code already exists.', 'error')
                return redirect(request.url)

            # Parse dates
            valid_from_dt = None
            valid_until_dt = None

            if valid_from:
                try:
                    valid_from_dt = datetime.fromisoformat(valid_from.replace('T', ' '))
                except ValueError:
                    flash('Invalid valid from date format.', 'error')
                    return redirect(request.url)

            if valid_until:
                try:
                    valid_until_dt = datetime.fromisoformat(valid_until.replace('T', ' '))
                except ValueError:
                    flash('Invalid valid until date format.', 'error')
                    return redirect(request.url)

            # Parse usage limit
            usage_limit_int = None
            if usage_limit:
                try:
                    usage_limit_int = int(usage_limit)
                    if usage_limit_int <= 0:
                        flash('Usage limit must be greater than 0.', 'error')
                        return redirect(request.url)
                except ValueError:
                    flash('Invalid usage limit format.', 'error')
                    return redirect(request.url)

            # Create coupon
            coupon = Coupon(
                code=code,
                discount_percentage=discount_percentage,
                description=description,
                valid_from=valid_from_dt,
                valid_until=valid_until_dt,
                usage_limit=usage_limit_int,
                is_active=is_active
            )

            db.session.add(coupon)
            db.session.commit()

            flash(f'Coupon "{code}" created successfully!', 'success')
            return redirect(url_for('admin_coupons'))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating coupon: {e}")
            flash('An error occurred while creating the coupon.', 'error')

    return render_template('admin_create_coupon.html')


# Customer Coupon API Routes

@app.route('/api/coupon/apply', methods=['POST'])
def api_apply_coupon():
    """API endpoint to apply a coupon to the current cart session"""
    try:
        data = request.get_json()
        if not data or 'coupon_code' not in data:
            return jsonify({'success': False, 'error': 'Coupon code is required'}), 400

        coupon_code = data['coupon_code'].strip().upper()

        if not coupon_code:
            return jsonify({'success': False, 'error': 'Coupon code cannot be empty'}), 400

        # Get or create cart session
        cart_session = _get_or_create_cart_session()
        if not cart_session or not cart_session.items:
            return jsonify({'success': False, 'error': 'Your cart is empty'}), 400

        # Find the coupon
        coupon = Coupon.query.filter_by(code=coupon_code).first()
        if not coupon:
            return jsonify({'success': False, 'error': 'Invalid coupon code'}), 400

        # Validate coupon
        if not coupon.is_active:
            return jsonify({'success': False, 'error': 'This coupon is not active'}), 400

        # Check validity period
        now = datetime.utcnow()

        if coupon.valid_from and now < coupon.valid_from:
            return jsonify({'success': False, 'error': 'This coupon is not yet valid'}), 400

        if coupon.valid_until and now > coupon.valid_until:
            return jsonify({'success': False, 'error': 'This coupon has expired'}), 400

        # Check usage limit
        if coupon.usage_limit and coupon.usage_count >= coupon.usage_limit:
            return jsonify({'success': False, 'error': 'This coupon has reached its usage limit'}), 400

        # Calculate cart total with proper price conversion
        cart_total = 0
        for item in cart_session.items:
            # Ensure we get the correct price for each item type
            if item.item_type == 'admin' and item.card:
                price = float(item.card.price) if item.card.price else 0
            elif item.item_type == 'user' and item.inventory_item and item.inventory_item.card:
                price = float(item.inventory_item.card.price) if item.inventory_item.card.price else 0
            else:
                price = 0

            item_total = price * item.quantity
            cart_total += item_total

        # Calculate discount
        discount_percentage = float(coupon.discount_percentage)
        discount_amount = cart_total * (discount_percentage / 100)
        final_total = cart_total - discount_amount

        logger.info(f"Coupon calculation: cart_total={cart_total}, discount_percentage={discount_percentage}, discount_amount={discount_amount}, final_total={final_total}")

        # Store coupon in session
        session['applied_coupon_id'] = coupon.id
        session['applied_coupon_code'] = coupon.code
        session['discount_amount'] = float(discount_amount)
        session['final_total'] = float(final_total)

        return jsonify({
            'success': True,
            'message': f'Coupon "{coupon_code}" applied successfully!',
            'coupon_code': coupon.code,
            'discount_percentage': coupon.discount_percentage,
            'discount_amount': f"{discount_amount:,.0f}",
            'original_total': f"{cart_total:,.0f}",
            'final_total': f"{final_total:,.0f}"
        }), 200

    except Exception as e:
        logger.error(f"Error applying coupon: {e}")
        return jsonify({'success': False, 'error': 'An error occurred while applying the coupon'}), 500


@app.route('/api/coupon/remove', methods=['POST'])
def api_remove_coupon():
    """API endpoint to remove the applied coupon from the current cart session"""
    try:
        # Remove coupon from session
        session.pop('applied_coupon_id', None)
        session.pop('applied_coupon_code', None)
        session.pop('discount_amount', None)
        session.pop('final_total', None)

        return jsonify({
            'success': True,
            'message': 'Coupon removed successfully'
        }), 200

    except Exception as e:
        logger.error(f"Error removing coupon: {e}")
        return jsonify({'success': False, 'error': 'An error occurred while removing the coupon'}), 500


@app.route('/admin/coupons/<int:coupon_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_coupon(coupon_id):
    """Edit an existing coupon"""
    coupon = Coupon.query.get_or_404(coupon_id)

    if request.method == 'POST':
        try:
            # Get form data
            code = request.form.get('code', '').strip().upper()
            discount_percentage = float(request.form.get('discount_percentage', 0))
            description = request.form.get('description', '').strip()
            valid_from = request.form.get('valid_from')
            valid_until = request.form.get('valid_until')
            usage_limit = request.form.get('usage_limit')
            is_active = 'is_active' in request.form

            # Validation
            if not code:
                flash('Coupon code is required.', 'error')
                return redirect(request.url)

            if discount_percentage <= 0 or discount_percentage > 100:
                flash('Discount percentage must be between 0 and 100.', 'error')
                return redirect(request.url)

            # Check if code already exists (excluding current coupon)
            existing_coupon = Coupon.query.filter(Coupon.code == code, Coupon.id != coupon_id).first()
            if existing_coupon:
                flash('A coupon with this code already exists.', 'error')
                return redirect(request.url)

            # Parse dates
            valid_from_dt = None
            valid_until_dt = None

            if valid_from:
                try:
                    valid_from_dt = datetime.fromisoformat(valid_from.replace('T', ' '))
                except ValueError:
                    flash('Invalid valid from date format.', 'error')
                    return redirect(request.url)

            if valid_until:
                try:
                    valid_until_dt = datetime.fromisoformat(valid_until.replace('T', ' '))
                except ValueError:
                    flash('Invalid valid until date format.', 'error')
                    return redirect(request.url)

            # Parse usage limit
            usage_limit_int = None
            if usage_limit:
                try:
                    usage_limit_int = int(usage_limit)
                    if usage_limit_int <= 0:
                        flash('Usage limit must be greater than 0.', 'error')
                        return redirect(request.url)
                except ValueError:
                    flash('Invalid usage limit format.', 'error')
                    return redirect(request.url)

            # Update coupon
            coupon.code = code
            coupon.discount_percentage = discount_percentage
            coupon.description = description
            coupon.valid_from = valid_from_dt
            coupon.valid_until = valid_until_dt
            coupon.usage_limit = usage_limit_int
            coupon.is_active = is_active

            db.session.commit()

            flash(f'Coupon "{code}" updated successfully!', 'success')
            return redirect(url_for('admin_coupons'))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating coupon {coupon_id}: {e}")
            flash('An error occurred while updating the coupon.', 'error')

    return render_template('admin_edit_coupon.html', coupon=coupon)


@app.route('/admin/coupons/<int:coupon_id>/delete', methods=['POST'])
@admin_required
def admin_delete_coupon(coupon_id):
    """Delete a coupon"""
    coupon = Coupon.query.get_or_404(coupon_id)

    try:
        # Check if coupon has been used
        if coupon.usage_count > 0:
            flash('Cannot delete a coupon that has been used.', 'error')
            return redirect(url_for('admin_coupons'))

        db.session.delete(coupon)
        db.session.commit()

        flash(f'Coupon "{coupon.code}" deleted successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting coupon {coupon_id}: {e}")
        flash('An error occurred while deleting the coupon.', 'error')

    return redirect(url_for('admin_coupons'))


@app.route('/admin/coupons/<int:coupon_id>/toggle', methods=['POST'])
@admin_required
def admin_toggle_coupon(coupon_id):
    """Toggle coupon active status"""
    coupon = Coupon.query.get_or_404(coupon_id)

    try:
        coupon.is_active = not coupon.is_active
        db.session.commit()

        status = "activated" if coupon.is_active else "deactivated"
        flash(f'Coupon "{coupon.code}" {status} successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling coupon {coupon_id}: {e}")
        flash('An error occurred while updating the coupon.', 'error')

    return redirect(url_for('admin_coupons'))