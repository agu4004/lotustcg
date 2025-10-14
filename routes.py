from flask import render_template, request, redirect, url_for, flash, session, jsonify, current_app, get_flashed_messages
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from app import app, db
from storage_db import storage
from models import (
    User, Card, Order, OrderItem,
    UserInventory, InventoryItem, TradeOffer, TradeItem,
    CartSession, CartItem, UserAuditLog, VerificationAuditLog,
    Coupon, ShopInventoryItem, ShopConsignmentLog,
    InventoryTransferLog,
)
from auth import admin_required, get_redirect_target
from decimal import Decimal
import logging
import re
from functools import wraps
from sqlalchemy.orm import load_only
from sqlalchemy import String
from datetime import datetime
import uuid

from credit_service import (
    issue_credits as svc_issue_credits,
    transfer_item as svc_transfer_item,
    apply_credits as svc_apply_credits,
    ServiceError,
)
from metrics import COUNTERS

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


# ---------------------------
# CREDIT API ENDPOINTS (JSON)
# ---------------------------

def _json_error(code: str, message: str, http: int = 400, **extra):
    payload = {'success': False, 'error': code, 'message': message}
    if extra:
        payload.update(extra)
    return jsonify(payload), http


def _get_idem_key():
    return request.headers.get('Idempotency-Key') or request.json.get('idempotency_key') if request.is_json else None


def _log_event(event: str, **fields):
    req_id = request.headers.get('X-Request-Id') or str(uuid.uuid4())
    fields = {'event': event, 'request_id': req_id, **fields}
    logger.info(fields)


@app.route('/admin/credit/issue', methods=['POST'])
@login_required
def admin_credit_issue(): 
    if not current_user.is_admin(): 
        return _json_error('FORBIDDEN', 'Admin privileges required', 403) 
    if not request.is_json: 
        return _json_error('INVALID_JSON', 'Request must be JSON', 400) 
    data = request.get_json(silent=True) or {} 
    # Best-effort: ensure credit tables exist (idempotent)
    try:
        db.create_all()
    except Exception:
        pass
    idem = _get_idem_key() 
    try:
        user_id = int(data.get('user_id'))
        denom = int(data.get('denomination_vnd') or data.get('amount_vnd'))
        units = int(data.get('units', 1))
    except Exception:
        return _json_error('INVALID_REQUEST', 'Invalid or missing fields')

    try:
        res = svc_issue_credits(current_user, user_id, denom, units=units, idempotency_key=idem, notes=data.get('notes'))
        COUNTERS.inc('credits.issued.count', amount=1)
        COUNTERS.inc('credits.issued.sum', amount=int(res['total_vnd']))
        _log_event('credit_issue', idempotency_key=idem, user_id=user_id, denom=denom, units=units)
        return jsonify({'success': True, **res})
    except ServiceError as se:
        if se.code == 'IDEMPOTENT_REPLAY':
            COUNTERS.inc('idempotent.replay')
        return _json_error(se.code, str(se), se.http, **se.extra)
    except Exception as e:
        logger.exception({'event': 'credit_issue_error', 'error': str(e)})
        return _json_error('INTERNAL_ERROR', 'Unexpected error', 500)


@app.route('/inventory/transfer', methods=['POST'])
@login_required
def inventory_transfer():
    if not request.is_json:
        return _json_error('INVALID_JSON', 'Request must be JSON', 400)
    data = request.get_json(silent=True) or {}
    idem = _get_idem_key()
    try:
        from_user_id = int(data.get('from_user_id'))
        # Allow either to_user_id (int) or to_username (string)
        to_user_id_raw = data.get('to_user_id')
        to_username = data.get('to_username')
        item_id = int(data.get('inventory_item_id'))
        quantity = int(data.get('quantity', 1))
    except Exception:
        return _json_error('INVALID_REQUEST', 'Invalid or missing fields')

    # Resolve recipient if username provided
    if (to_user_id_raw is None or to_user_id_raw == '') and to_username:
        user_rec = User.query.filter_by(username=to_username).first()
        if not user_rec:
            return _json_error('USER_NOT_FOUND', 'Recipient user not found', 404)
        to_user_id = user_rec.id
    else:
        try:
            to_user_id = int(to_user_id_raw)
        except Exception:
            return _json_error('INVALID_REQUEST', 'Invalid recipient user', 400)
        # Early existence check for recipient when id is provided
        rec = User.query.get(to_user_id)
        if not rec:
            return _json_error('USER_NOT_FOUND', 'Recipient user not found', 404)

    if current_user.id != from_user_id and not current_user.is_admin():
        return _json_error('FORBIDDEN', 'Cannot transfer items you do not own', 403)

    try:
        res = svc_transfer_item(from_user_id, to_user_id, item_id, quantity, idempotency_key=idem)
        if res.get('is_credit'):
            COUNTERS.inc('credits.transferred.count')
            COUNTERS.inc('credits.transferred.units', amount=quantity)
        _log_event('inventory_transfer', idempotency_key=idem, **res)
        return jsonify({'success': True, **res})
    except ServiceError as se:
        return _json_error(se.code, str(se), se.http, **se.extra)
    except Exception as e:
        logger.exception({'event': 'inventory_transfer_error', 'error': str(e)})
        return _json_error('INTERNAL_ERROR', 'Unexpected error', 500)


@app.route('/checkout/apply-credits', methods=['POST'])
@login_required
def checkout_apply_credits():
    if not request.is_json:
        return _json_error('INVALID_JSON', 'Request must be JSON', 400)
    data = request.get_json(silent=True) or {}
    idem = _get_idem_key()

    try:
        user_id = int(data.get('user_id') or current_user.id)
        amount_due_vnd = int(data.get('amount_due_vnd'))
        mode = data.get('mode', 'auto')
        breakdown = data.get('breakdown')
        coupon_pct = data.get('coupon_percentage')
    except Exception:
        return _json_error('INVALID_REQUEST', 'Invalid or missing fields')

    if user_id != current_user.id and not current_user.is_admin():
        return _json_error('FORBIDDEN', 'Cannot redeem credits for another user', 403)

    # Apply percentage coupon first if provided
    if coupon_pct is not None:
        try:
            pct = float(coupon_pct)
            if pct < 0 or pct > 100:
                return _json_error('INVALID_COUPON', 'Coupon percentage must be 0-100')
            discounted = int(amount_due_vnd - (amount_due_vnd * (pct / 100.0)))
            if discounted < 0:
                discounted = 0
            amount_after_pct = discounted
        except Exception:
            return _json_error('INVALID_COUPON', 'Invalid coupon percentage value')
    else:
        amount_after_pct = amount_due_vnd

    # Support manual breakdown by denomination (client doesn't know card IDs)
    breakdown_by_denom = data.get('breakdown_by_denom') or {}
    if mode == 'manual' and breakdown_by_denom and not breakdown:
        # Convert to card-id based breakdown using canonical CREDIT cards
        b = []
        for denom_str, units in breakdown_by_denom.items():
            try:
                denom = int(denom_str)
                units = int(units)
            except Exception:
                continue
            # Lookup card id
            from credit_service import get_or_create_credit_card
            card = get_or_create_credit_card(denom)
            b.append({'card_id': card.id, 'units': units})
        breakdown = b

    try:
        # Preview only; no deduction here
        res = svc_apply_credits(user_id, amount_after_pct, mode=mode, breakdown=breakdown, idempotency_key=None, related_order_id=None, preview=True)
        COUNTERS.inc('credits.redeemed.count')
        COUNTERS.inc('credits.redeemed.sum', amount=int(res['credits_applied_vnd']))
        _log_event('credit_redeem', idempotency_key=idem, user_id=user_id, amount_due_vnd=amount_due_vnd, amount_after_pct=amount_after_pct)
        # Persist plan in session so checkout POST can redeem later
        try:
            session['credit_amount_after_pct'] = int(amount_after_pct)
            session['credit_applied_vnd'] = int(res.get('credits_applied_vnd') or 0)
            session['credit_remaining_vnd'] = int(res.get('remaining_vnd') or (amount_after_pct - (res.get('credits_applied_vnd') or 0)))
            session['credit_breakdown'] = res.get('applied_breakdown') or []
            session['credit_mode'] = mode
        except Exception:
            # Do not fail the request if session cannot be updated
            pass
        return jsonify({'success': True, **res, 'amount_due_vnd': amount_due_vnd, 'amount_after_pct': amount_after_pct})
    except ServiceError as se:
        COUNTERS.inc('credits.errors')
        return _json_error(se.code, str(se), se.http, **se.extra)
    except Exception as e:
        logger.exception({'event': 'credit_redeem_error', 'error': str(e)})
        COUNTERS.inc('credits.errors')
        return _json_error('INTERNAL_ERROR', 'Unexpected error', 500)


@app.route('/metrics', methods=['GET'])
def metrics():
    body = COUNTERS.render_prom()
    return app.response_class(response=body, status=200, mimetype='text/plain; version=0.0.4')

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
    class_filter = request.args.get('card_class', '')

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
        card_class_filter=class_filter,
        min_price=min_price,
        max_price=max_price
    )

    # Get user inventory items
    user_inventory_items = []
    if query or set_filter or rarity_filter or foiling_filter or class_filter or min_price or max_price:
        # Apply filters to user inventory items
        user_items_query = InventoryItem.query.join(Card).filter(
            InventoryItem.is_verified == True,
            InventoryItem.quantity > 0,
            InventoryItem.listed_for_sale == True
        )

        if query:
            user_items_query = user_items_query.filter(Card.name.ilike(f'%{query}%'))
        if set_filter:
            user_items_query = user_items_query.filter(Card.set_name == set_filter)
        if rarity_filter:
            user_items_query = user_items_query.filter(Card.rarity == rarity_filter)
        if foiling_filter:
            user_items_query = user_items_query.filter(Card.foiling == foiling_filter)
        if class_filter:
            user_items_query = user_items_query.filter(Card.card_class == class_filter)
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
            'quantity': item.quantity,
            'language': item.language or card_data.get('language') or 'English'
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

    # Hide out-of-stock items from the catalog listing
    sorted_cards = in_stock_cards

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
    all_classes = storage.get_unique_classes()

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
    user_classes = db.session.query(Card.card_class.distinct()).join(InventoryItem).filter(
        InventoryItem.is_verified == True,
        InventoryItem.is_public == True
    ).all()

    all_sets.extend([s[0] for s in user_sets if s[0] not in all_sets])
    all_rarities.extend([r[0] for r in user_rarities if r[0] not in all_rarities])
    all_foilings.extend([f[0] for f in user_foilings if f[0] not in all_foilings])
    all_classes.extend([(c[0] or 'General') for c in user_classes if (c[0] or 'General') not in all_classes])

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
                          all_classes=all_classes,
                          current_filters={
                              'q': query,
                              'set': set_filter,
                              'rarity': rarity_filter,
                              'foiling': foiling_filter,
                              'min_price': request.args.get('min_price', ''),
                              'max_price': request.args.get('max_price', ''),
                              'card_class': class_filter,
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
    # Related cards from same set (admin catalog)
    try:
        set_name = card.get('set_name') if isinstance(card, dict) else getattr(card, 'set_name', None)
        related_cards = []
        if set_name:
            candidates = storage.search_cards(
                query='',
                set_filter=set_name,
                rarity_filter='',
                foiling_filter='',
                min_price=None,
                max_price=None
            ) or []
            related_cards = [c for c in candidates if str(c.get('id')) != str(card_id)]
            in_stock = [c for c in related_cards if c.get('quantity', 0) > 0]
            out_stock = [c for c in related_cards if c.get('quantity', 0) == 0]
            related_cards = (in_stock + out_stock)[:9]
    except Exception:
        related_cards = []

    return render_template('card_detail.html', card=card, related_cards=related_cards)

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
            customer_email = request.form.get('customer_email', '').strip()
            customer_name = request.form.get('customer_name', '').strip()
            contact_number = request.form.get('contact_number', '').strip()
            shipment_method = request.form.get('shipment_method', '')

            logger.info(f"Order details: customer_name='{customer_name}', contact_number='{contact_number}', shipment_method='{shipment_method}'")

            if not customer_email:
                flash('Email is required', 'error')
                return redirect(url_for('checkout'))

            if not customer_name:
                flash('Customer name is required', 'error')
                return redirect(url_for('checkout'))

            if not contact_number:
                flash('Contact number is required', 'error')
                return redirect(url_for('checkout'))

            if shipment_method not in ['shipping', 'pickup', 'inventory']:
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
            elif shipment_method == 'inventory':
                # No extra fields required; inventory addition on admin approval
                pass

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

            # Generate a unique order ID and avoid collisions
            import random
            import string

            def _generate_unique_order_id(max_attempts: int = 10) -> str:
                for _ in range(max_attempts):
                    candidate = f"ORD-{datetime.now().strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=6))}"
                    try:
                        row = db.session.execute(db.text("SELECT 1 FROM orders WHERE id = :id"), {"id": candidate}).first()
                        if not row:
                            return candidate
                    except Exception:
                        # If SELECT fails due to schema, fall back to optimistic return
                        return candidate
                # As a very last resort, extend with more randomness
                from uuid import uuid4
                return f"ORD-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:8]}"

            order_id = _generate_unique_order_id()
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

            # Apply credits at order placement if a plan exists from preview
            try:
                credit_after_pct = session.get('credit_amount_after_pct')
                credit_breakdown = session.get('credit_breakdown')
                if credit_breakdown is not None:
                    expected_base = int(round(final_total))
                    if credit_after_pct is None or abs(int(credit_after_pct) - expected_base) <= 1:
                        # Redeem now, atomically, using breakdown
                        idem_key = f"order:{order_id}"
                        # Do not pass related_order_id (ledger column is integer in DB, order id is string)
                        res = svc_apply_credits(current_user.id, expected_base, mode='manual', breakdown=credit_breakdown, idempotency_key=idem_key, related_order_id=None, preview=False)
                        final_total = float(res.get('remaining_vnd'))
                        logger.info(f"Credits redeemed at order placement: applied={res.get('credits_applied_vnd')}, remaining={final_total}")
                    else:
                        logger.warning("Credit base mismatch at order placement; skipping redemption")
            except Exception as e:
                logger.error(f"Error applying session credits to order: {e}")

            # Create order with final total (including coupon and credit discounts)
            logger.info("Creating order...")
            # Be resilient if DB hasn't been migrated yet (no 'email' / 'order_number' / 'user_id' columns)
            try:
                from sqlalchemy import inspect as _sa_inspect
                _cols = {col.get('name') for col in _sa_inspect(db.engine).get_columns('orders')}
                has_email_col = 'email' in _cols
                has_order_number_col = 'order_number' in _cols
                has_user_id_col = 'user_id' in _cols
            except Exception:
                has_email_col = False
                has_order_number_col = False
                has_user_id_col = False

            order_kwargs = dict(
                id=order_id,
                **({ 'order_number': order_id } if has_order_number_col else {}),
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
                shipping_country=shipping_country,
            )
            # Attach user_id if present and user authenticated
            if has_user_id_col and current_user.is_authenticated:
                try:
                    order_kwargs['user_id'] = int(current_user.id)
                except Exception:
                    pass
            # Ensure discount_amount is never NULL
            try:
                order_kwargs['discount_amount'] = float(discount_amount or 0.0)
            except Exception:
                order_kwargs['discount_amount'] = 0.0
            # Optionally set discounted_total when a coupon is applied
            if 'applied_coupon' in locals() and applied_coupon:
                order_kwargs['discounted_total'] = float(final_total)
            if has_email_col:
                # Ensure orders are linked to the logged-in user for My Orders listing
                acct_email = None
                try:
                    if current_user.is_authenticated:
                        acct_email = getattr(current_user, 'email', None)
                except Exception:
                    acct_email = None
                order_kwargs['email'] = acct_email or customer_email
            else:
                logger.warning("Orders table missing 'email' column; please run migrations. Proceeding without storing email.")

            if has_email_col:
                order = Order(**order_kwargs)
                db.session.add(order)
                logger.info("Order created successfully (ORM)")
            else:
                # Insert without email column since DB hasn't been migrated
                cols = [
                    'id','customer_name','contact_number','facebook_details','shipment_method','pickup_location',
                    'status','total_amount','shipping_address','shipping_city','shipping_province','shipping_postal_code','shipping_country',
                    'coupon_id','coupon_code','discount_amount','discounted_total'
                ]
                if has_order_number_col:
                    cols.insert(1, 'order_number')
                if has_user_id_col:
                    cols.insert(1, 'user_id')
                params = {c: order_kwargs.get(c) for c in cols}
                # Ensure NOT NULL discount_amount has a value
                if params.get('discount_amount') is None:
                    params['discount_amount'] = float(discount_amount or 0.0)
                # If discounted_total is required for downstream display, leave as None unless coupon applied
                if params.get('discounted_total') is None and applied_coupon:
                    params['discounted_total'] = float(final_total)
                placeholders = ", ".join([f":{c}" for c in cols])
                col_list = ", ".join(cols)
                sql = f"INSERT INTO orders ({col_list}) VALUES ({placeholders})"
                db.session.execute(db.text(sql), params)
                logger.info("Order created successfully (raw SQL)")

            # Create order items and deduct stock
            logger.info("Creating order items and deducting stock...")
            for cart_item in cart_session.items:
                logger.info(f"Processing order item: {cart_item.card.name if cart_item.card else 'Unknown'}")

                # Create order items
                if getattr(cart_item, 'item_type', None) == 'user' and cart_item.inventory_item:
                    # Single order line for user item
                    order_item_kwargs = {
                        'order_id': order_id,
                        'card_id': cart_item.inventory_item.card_id,
                        'quantity': cart_item.quantity,
                        'unit_price': float(cart_item.display_price),
                        'total_price': float(cart_item.item_total),
                        'inventory_item_id': cart_item.inventory_item_id,
                        'seller_user_id': cart_item.inventory_item.inventory.user_id if cart_item.inventory_item.inventory else None
                    }
                    db.session.add(OrderItem(**order_item_kwargs))
                    logger.info("Order item created (user inventory)")
                else:
                    # Admin item: attribute to consigned shop stock first (FIFO), remainder as store
                    allocations = []  # list of (seller_user_id, qty, source_inventory_item_id)
                    remaining = int(cart_item.quantity)
                    try:
                        cons_rows = (ShopInventoryItem.query
                                     .filter(ShopInventoryItem.card_id == cart_item.card.id)
                                     .filter(ShopInventoryItem.quantity > 0)
                                     .order_by(ShopInventoryItem.created_at.asc(), ShopInventoryItem.id.asc())
                                     .all())
                    except Exception:
                        cons_rows = []
                    for row in cons_rows:
                        if remaining <= 0:
                            break
                        take = min(int(row.quantity), remaining)
                        if take > 0:
                            allocations.append((row.from_user_id, take, row.source_inventory_item_id))
                            row.quantity = int(row.quantity) - take
                            remaining -= take
                    # Create order items per allocation
                    unit_price = float(cart_item.display_price)
                    for seller_uid, q, src_item_id in allocations:
                        db.session.add(OrderItem(
                            order_id=order_id,
                            card_id=cart_item.card.id,
                            quantity=q,
                            unit_price=unit_price,
                            total_price=float(unit_price * q),
                            inventory_item_id=src_item_id,
                            seller_user_id=seller_uid
                        ))
                    # Remainder belongs to store
                    if remaining > 0:
                        db.session.add(OrderItem(
                            order_id=order_id,
                            card_id=cart_item.card.id,
                            quantity=remaining,
                            unit_price=unit_price,
                            total_price=float(unit_price * remaining)
                        ))
                    logger.info("Order item(s) created (admin with consignment attribution)")

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
            # Clear credit session markers
            session.pop('credit_amount_after_pct', None)
            session.pop('credit_applied_vnd', None)
            session.pop('credit_remaining_vnd', None)
            session.pop('credit_breakdown', None)
            session.pop('credit_mode', None)

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

    # Prefill checkout form from account settings when available
    prefill = {
        'customer_email': '',
        'customer_name': '',
        'contact_number': '',
        'shipping_address': '',
        'shipping_city': '',
        'shipping_province': '',
        'shipping_postal_code': '',
        'shipping_country': 'Vietnam',
        'default_shipment_method': '',
    }
    try:
        if current_user.is_authenticated:
            # Inspect user table to avoid touching missing columns
            try:
                from sqlalchemy import inspect as _sa_inspect
                _user_cols = {c.get('name') for c in _sa_inspect(db.engine).get_columns('users')}
            except Exception:
                _user_cols = set()

            def _u(field):
                if field in _user_cols:
                    try:
                        return getattr(current_user, field) or ''
                    except Exception:
                        return ''
                return ''

            prefill.update({
                'customer_email': (getattr(current_user, 'email', '') or ''),
                'customer_name': (_u('full_name') or getattr(current_user, 'username', '') or ''),
                'contact_number': _u('phone_number'),
                'shipping_address': _u('address_line'),
                'shipping_city': _u('address_city'),
                'shipping_province': _u('address_province'),
                'shipping_postal_code': _u('address_postal_code'),
                'shipping_country': (_u('address_country') or 'Vietnam'),
            })
            # Choose default shipment method based on presence of address
            if any([
                prefill['shipping_address'],
                prefill['shipping_city'],
                prefill['shipping_province'],
                prefill['shipping_postal_code'],
            ]):
                prefill['default_shipment_method'] = 'shipping'
    except Exception:
        pass

    return render_template('checkout.html',
                          cart_items=cart_items,
                          total_price=total_price,
                          applied_coupon=applied_coupon,
                          discount_amount=discount_amount,
                          final_total=final_total,
                          prefill=prefill)

@app.route('/order/<order_id>')
def order_confirmation(order_id):
    """Order confirmation page"""
    # Avoid selecting columns that may not exist yet (e.g., 'email' before migration)
    order = (
        Order.query.options(
            load_only(
                Order.id,
                Order.customer_name,
                Order.contact_number,
                Order.facebook_details,
                Order.shipment_method,
                Order.pickup_location,
                Order.status,
                Order.total_amount,
                Order.shipping_address,
                Order.shipping_city,
                Order.shipping_province,
                Order.shipping_postal_code,
                Order.shipping_country,
                Order.created_at,
                Order.updated_at,
                Order.coupon_id,
                Order.coupon_code,
                Order.discount_amount,
                Order.discounted_total,
            )
        ).get_or_404(order_id)
    )

    # Get order items with card and seller details
    order_items = []
    for item in order.items:
        seller_name = 'Lotus TCG Store'
        try:
            if getattr(item, 'seller', None):
                seller_name = item.seller.username
            elif getattr(item, 'seller_user_id', None):
                u = User.query.get(item.seller_user_id)
                if u:
                    seller_name = u.username
        except Exception:
            pass
        order_items.append({
            'card': item.card,
            'quantity': item.quantity,
            'unit_price': float(item.unit_price),
            'total_price': float(item.total_price),
            'foiling': item.card.foiling if item.card else None,
            'art_style': item.card.art_style if item.card else None,
            'seller': seller_name
        })

    return render_template('order_confirmation.html',
                          order=order,
                          order_items=order_items)

@app.route('/withdraw/<order_id>')
@login_required
def withdrawal_confirmation(order_id):
    """Specialized confirmation page for withdrawal-created orders."""
    order = (
        Order.query.options(
            load_only(
                Order.id,
                Order.customer_name,
                Order.contact_number,
                Order.shipment_method,
                Order.pickup_location,
                Order.status,
                Order.total_amount,
                Order.shipping_address,
                Order.shipping_city,
                Order.shipping_province,
                Order.shipping_postal_code,
                Order.shipping_country,
                Order.created_at,
                Order.updated_at,
                Order.order_number,
            )
        ).get_or_404(order_id)
    )

    # Guard: ensure current user owns the order OR is an admin
    try:
        owner_ok = (getattr(order, 'user_id', None) in (None, current_user.id))
        admin_ok = bool(getattr(current_user, 'is_admin', lambda: False)())
        if not (owner_ok or admin_ok):
            return redirect(url_for('my_orders'))
    except Exception:
        pass

    order_items = []
    for item in order.items:
        order_items.append({
            'card': item.card,
            'quantity': item.quantity,
            'unit_price': float(item.unit_price),
            'total_price': float(item.total_price)
        })

    return render_template('withdrawal_confirmation.html', order=order, order_items=order_items)

@app.route('/my-orders')
@login_required
def my_orders():
    """Show the current user's previous orders and status.

    Preference is to match by email on the orders table when available.
    Falls back to matching by customer_name using full_name or username if needed.
    """
    try:
        from sqlalchemy import inspect as _sa_inspect
        order_cols = {c.get('name') for c in _sa_inspect(db.engine).get_columns('orders')}
    except Exception:
        order_cols = set()

    q = Order.query
    filters = []

    # Cache user email for hinting and matching
    user_email = getattr(current_user, 'email', None)

    # Prefer strong match by user_id when available
    if 'user_id' in order_cols:
        q = q.filter(Order.user_id == current_user.id)
    # Else prefer email match if both column and user email exist
    elif 'email' in order_cols and user_email:
        q = q.filter(Order.email == user_email)
    else:
        # Fallback to name match (less precise)
        full_name = getattr(current_user, 'full_name', None)
        username = getattr(current_user, 'username', None)
        names = [n for n in (full_name, username) if n]
        if names:
            from sqlalchemy import or_
            q = q.filter(or_(*[Order.customer_name == n for n in names]))
        else:
            # Nothing to match; render empty list with hint
            q = q.filter(db.text('1=0'))

    # Order by latest first; avoid selecting non-existent columns
    try:
        q = q.order_by(Order.created_at.desc())
    except Exception:
        pass

    try:
        orders = q.all()
    except Exception:
        orders = []

    # Prepare lightweight dicts for template
    rows = []
    for o in orders:
        try:
            _fb = (getattr(o, 'facebook_details', '') or '')
            rows.append({
                'id': o.id,
                'order_number': getattr(o, 'order_number', None),
                'created_at': o.created_at,
                'status': o.status,
                'shipment_method': o.shipment_method,
                'pickup_location': o.pickup_location,
                'total_amount': float(o.total_amount),
                'discount_amount': float(getattr(o, 'discount_amount', 0) or 0),
                'discounted_total': float(getattr(o, 'discounted_total', 0) or o.total_amount),
                'is_withdrawal': _fb.startswith('withdrawal:'),
            })
        except Exception:
            # Best-effort fallback
            rows.append({
                'id': getattr(o, 'id', ''),
                'order_number': getattr(o, 'order_number', None),
                'created_at': getattr(o, 'created_at', None),
                'status': getattr(o, 'status', ''),
                'shipment_method': getattr(o, 'shipment_method', ''),
                'pickup_location': getattr(o, 'pickup_location', ''),
                'total_amount': float(getattr(o, 'total_amount', 0) or 0),
                'discount_amount': float(getattr(o, 'discount_amount', 0) or 0),
                'discounted_total': float(getattr(o, 'discounted_total', 0) or 0),
                'is_withdrawal': False,
            })

    hint = None
    if 'user_id' in order_cols:
        hint = None
    elif ('email' in order_cols) and not user_email:
        hint = 'Add your email in Account Settings to link your orders.'
    elif 'email' not in order_cols:
        hint = "Orders don't store email yet; please run migrations to enable linking by email."

    return render_template('my_orders.html', orders=rows, hint=hint)

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

            # Derive full name from first and last name provided
            derived_full_name = ' '.join([n for n in (first_name, last_name) if n]).strip() or None

            new_user = User(
                username=username,
                email=email,
                password_hash=hashed_password,
                role='user',
                full_name=derived_full_name
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
                # Hide items with zero quantity from inventory display
                if getattr(item, 'quantity', 0) <= 0:
                    continue
                item_data = {
                    'id': item.id,
                    'card_name': item.card.name if item.card else 'Unknown Card',
                    'card_set': item.card.set_name if item.card else 'Unknown',
                    'card_code': getattr(item.card, 'card_code', '') if item.card else '',
                    'quantity': item.quantity,
                    'condition': item.condition,
                    'language': item.language or 'English',
                    'is_verified': item.is_verified,
                    'verification_status': item.verification_status,
                    'added_at': item.added_at,
                    'card_image': item.card.image_url if item.card else None,
                    'card_rarity': item.card.rarity if item.card else 'Unknown',
                    'card_price': float(item.card.price) if item.card else 0,
                    'listed_for_sale': item.listed_for_sale
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


@app.route('/inventory/consigned')
@login_required
def inventory_consigned():
    """Show current user's cards that have been sent to the shop (consigned)."""
    try:
        rows = (
            db.session.query(ShopInventoryItem, Card)
            .join(Card, Card.id == ShopInventoryItem.card_id)
            .filter(ShopInventoryItem.from_user_id == current_user.id, ShopInventoryItem.quantity > 0)
            .order_by(Card.name.asc())
            .all()
        )
        consigned_items = []
        for s, card in rows:
            consigned_items.append({
                'id': s.id,
                'card_name': card.name,
                'set_name': card.set_name,
                'foiling': card.foiling,
                'art_style': card.art_style,
                'quantity': int(s.quantity),
                'source_inventory_item_id': s.source_inventory_item_id
            })

        return render_template('inventory_consigned.html', items=consigned_items)
    except Exception as e:
        logger.error(f"Error loading consigned items for user {getattr(current_user, 'id', '?')}: {e}")
        flash('Failed to load cards sent to shop.', 'error')
        return redirect(url_for('user_inventory'))


@app.route('/api/inventory/consignment/<int:shop_item_id>/withdraw', methods=['POST'])
@login_required
def api_withdraw_consignment(shop_item_id):
    """Withdraw a specified quantity from a consigned shop row back to user's inventory."""
    try:
        payload = request.get_json() or {}
        qty_req = int(payload.get('quantity', 0))
        if qty_req <= 0:
            return jsonify({'success': False, 'error': 'Invalid quantity'}), 400

        s = ShopInventoryItem.query.get_or_404(shop_item_id)
        if s.from_user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Not authorized'}), 403

        if s.quantity <= 0:
            return jsonify({'success': False, 'error': 'Nothing to withdraw'}), 400

        qty = min(qty_req, int(s.quantity))

        # Reduce admin stock
        try:
            c = Card.query.get(s.card_id)
            if c:
                c.quantity = max(0, int(c.quantity) - qty)
        except Exception:
            pass

        # Return to user's inventory
        src_item = InventoryItem.query.get(s.source_inventory_item_id) if s.source_inventory_item_id else None
        if src_item and src_item.inventory and src_item.inventory.user_id == current_user.id:
            src_item.quantity += qty
            src_item.updated_at = db.func.now()
        else:
            # Merge into or create a matching inventory item for this user
            inv = UserInventory.query.filter_by(user_id=current_user.id).first()
            if not inv:
                inv = UserInventory(user_id=current_user.id, is_public=False)
                db.session.add(inv)
                db.session.flush()
            merge_item = InventoryItem.query.filter_by(inventory_id=inv.id, card_id=s.card_id).first()
            if merge_item:
                merge_item.quantity += qty
                merge_item.updated_at = db.func.now()
            else:
                merge_item = InventoryItem(
                    inventory_id=inv.id,
                    card_id=s.card_id,
                    quantity=qty,
                    condition='Near Mint',
                    verification_status='verified',
                    is_verified=True,
                    notes='[withdraw_from_shop]',
                    language='English',
                    foil_type='Non Foil',
                    is_mint=False,
                    is_public=False,
                )
                db.session.add(merge_item)

        # Decrement consigned row and log
        s.quantity = int(s.quantity) - qty
        try:
            db.session.add(ShopConsignmentLog(
                card_id=s.card_id,
                from_user_id=s.from_user_id,
                source_inventory_item_id=s.source_inventory_item_id,
                quantity=qty,
                action='withdraw'
            ))
        except Exception:
            pass

        db.session.commit()
        return jsonify({'success': True, 'withdrawn': qty, 'remaining': int(s.quantity), 'card_id': s.card_id})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error withdrawing consignment {shop_item_id}: {e}")
        return jsonify({'success': False, 'error': 'Failed to withdraw'}), 500

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
                # Only show verified items with positive quantity in public view
                    if item.is_verified and getattr(item, 'quantity', 0) > 0:
                        item_data = {
                            'id': item.id,
                            'card_name': item.card.name if item.card else 'Unknown Card',
                            'card_set': item.card.set_name if item.card else 'Unknown',
                            'card_code': getattr(item.card, 'card_code', '') if item.card else '',
                            'quantity': item.quantity,
                            'condition': item.condition,
                            'language': item.language or 'English',
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

@app.route('/api/users/search')
@login_required
def api_search_users():
    """Autocomplete search for users by username/email/full name (active only)."""
    try:
        q = (request.args.get('q') or '').strip()
        try:
            limit = max(1, min(25, int(request.args.get('limit', 10))))
        except Exception:
            limit = 10

        if not q:
            return jsonify({'results': []})

        # Only active users, exclude super_admins and self
        base = User.query.filter(
            db.and_(
                User.account_status == 'active',
                User.role != 'super_admin',
                User.id != current_user.id
            )
        )

        like = f"%{q}%"
        base = base.filter(
            db.or_(
                User.username.ilike(like),
                User.email.ilike(like),
                User.full_name.ilike(like)
            )
        ).order_by(User.username.asc()).limit(limit)

        results = [
            {
                'id': u.id,
                'username': u.username,
                'full_name': u.full_name
            } for u in base.all()
        ]
        return jsonify({'results': results})
    except Exception as e:
        logger.error({'event': 'api_search_users_error', 'error': str(e)})
        return jsonify({'results': []}), 200

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

        # Disallow adding CREDIT tokens into personal inventory
        token_names = {'copper token', 'silver token', 'gold token'}
        requested_set = str(data.get('card_set', '') or '').strip()
        if card_name.lower() in token_names or requested_set.upper() == 'CREDIT':
            return jsonify({'success': False, 'error': 'Credit tokens cannot be imported into personal inventory'}), 400

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
                card_class=(str(data.get('card_class') or data.get('class') or 'General').strip() or 'General'),
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
        # Block if card is a CREDIT token card
        try:
            if getattr(card, 'is_credit', False) or (str(card.set_name).upper() == 'CREDIT'):
                return jsonify({'success': False, 'error': 'Credit tokens cannot be imported into personal inventory'}), 400
        except Exception:
            pass

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

@app.route('/admin/consignments')
@admin_required
def admin_consignments():
    """List cards consigned to shop with owner info"""
    try:
        rows = (db.session.query(ShopInventoryItem, Card, User)
                .join(Card, Card.id == ShopInventoryItem.card_id)
                .join(User, User.id == ShopInventoryItem.from_user_id)
                .filter(ShopInventoryItem.quantity > 0)
                .order_by(Card.name.asc(), ShopInventoryItem.created_at.asc())
                .all())
        consignments = []
        for s, card, user in rows:
            consignments.append({
                'card_name': card.name,
                'foiling': card.foiling,
                'art_style': card.art_style,
                'owner': user.username,
                'quantity': int(s.quantity)
            })
        # Load history
        hist_rows = (db.session.query(ShopConsignmentLog, Card, User)
                     .join(Card, Card.id == ShopConsignmentLog.card_id)
                     .join(User, User.id == ShopConsignmentLog.from_user_id)
                     .order_by(ShopConsignmentLog.created_at.desc(), ShopConsignmentLog.id.desc())
                     .limit(500)
                     .all())
        history = []
        for h, card, user in hist_rows:
            history.append({
                'created_at': h.created_at,
                'action': h.action,
                'card_name': card.name,
                'foiling': card.foiling,
                'art_style': card.art_style,
                'owner': user.username,
                'quantity': int(h.quantity)
            })
    except Exception as e:
        logger.error(f"Error loading consignments: {e}")
        consignments = []
        history = []
    return render_template('admin_consignments.html', consignments=consignments, history=history)

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

@app.route('/admin/update_prices_csv', methods=['POST'])
@admin_required
def admin_update_prices_csv():
    """Upload a CSV to bulk update prices by matching name, foiling, Rarity, set."""
    if 'csv_file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('admin'))

    file = request.files['csv_file']
    if not file or file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('admin'))

    if not file.filename.lower().endswith('.csv'):
        flash('Please upload a CSV file', 'error')
        return redirect(url_for('admin'))

    try:
        csv_content = file.read().decode('utf-8-sig')  # handle BOM if present
        results = storage.update_prices_from_csv(csv_content)

        msg = f"Processed {results.get('total', 0)} rows: updated {results.get('updated', 0)}, not found {results.get('not_found', 0)}"
        flash(msg, 'success' if results.get('updated', 0) > 0 else 'info')

        errs = results.get('errors') or []
        for e in errs[:10]:
            flash(e, 'error')
        if len(errs) > 10:
            flash(f"... and {len(errs) - 10} more errors", 'error')
    except UnicodeDecodeError:
        flash('Invalid file encoding. Please use UTF-8.', 'error')
    except Exception as e:
        logger.error(f"Price CSV upload error: {e}")
        flash(f"Error processing file: {str(e)}", 'error')

    return redirect(url_for('admin'))

@app.route('/admin/sample_price_csv')
@admin_required
def admin_sample_price_csv():
    """Provide a sample CSV template for price updates."""
    from flask import Response
    sample = (
        "name,foiling,Rarity,code,price\n"
        "Black Lotus,NF,Legendary,BL-ALPHA-000,5000.00\n"
        "Counterspell,RF,Common,CS-BETA-010,25.00\n"
    )
    return Response(sample, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=price_update_template.csv'})

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
    
    sample_csv = """name,set_name,class,rarity,condition,language,price,quantity,description,image_url,foiling,art_style,card_code
"Lightning Bolt","Core Set","Generic","Common","Near Mint","English",1.50,10,"Classic red instant spell","https://example.com/lightning-bolt.jpg","NF","normal","LB-CORE-001"
"Black Lotus","Alpha","Legendary","Legendary","Light Play","English",5000.00,1,"The most powerful mox","https://example.com/black-lotus.jpg","NF","normal","BL-ALPHA-000"
"Counterspell","Beta","Wizard","Common","Near Mint","Not English",25.00,5,"Counter target spell","https://example.com/counterspell.jpg","RF","EA","CS-BETA-010"
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
    writer.writerow(['name', 'set_name', 'class', 'rarity', 'condition', 'language', 'price', 'quantity', 'description', 'image_url', 'foiling', 'art_style', 'card_code'])

    # Write card data
    for card in cards:
        writer.writerow([
            card['name'],
            card['set_name'],
            card.get('card_class', 'General'),
            card['rarity'],
            card['condition'],
            card.get('language', 'English'),
            card['price'],
            card['quantity'],
            card.get('description', ''),
            card.get('image_url', ''),
            card.get('foiling', 'NF'),
            card.get('art_style', 'normal'),
            card.get('card_code', '')
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
            'description', 'image_url', 'card_code'
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
                item.card.image_url if item.card else '',
                (item.card.card_code if item.card and getattr(item.card, 'card_code', None) else '')
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

    sample_csv = """name,set_name,rarity,condition,quantity,market_price,language,notes,grade,foil_type,description,image_url,card_code
"Lightning Bolt","Core Set","Common","Near Mint",10,1200,English,"Classic instant spell","PSA 10","Non Foil","A classic red instant spell","https://example.com/lightning-bolt.jpg","LB-CORE-001"
"Black Lotus","Alpha","Legendary","Light Play",1,4500000,Not English,"The most powerful mox","BGS 9.5","Cold Foil","Most powerful card ever","https://example.com/black-lotus.jpg","BL-ALPHA-000"
"Counterspell","Beta","Common","Near Mint",5,20000,English,"Counter target spell","","Normal","Blue counterspell","https://example.com/counterspell.jpg","CS-BETA-010"
"""

    return Response(
        sample_csv,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=user_inventory_template.csv'}
    )


@app.route('/inventory/withdraw', methods=['POST'])
@login_required
def inventory_withdraw():
    """Withdraw cards from the user's inventory to a pickup location or shipping address.

    Accepts JSON body:
    {
      "items": [{"inventory_item_id": int, "quantity": int}, ...],
      "shipment_method": "pickup"|"shipping",
      "pickup_location": "Iron Hammer"|"Floating Dojo",  # required when pickup
      "shipping": {                                        # required when shipping (missing values fallback to profile)
        "address": str,
        "city": str,
        "province": str,
        "postal_code": str,
        "country": str
      }
    }

    Returns JSON: { success, request_id, method, items, message, ... }
    """
    try:
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Request must be JSON'}), 400

        data = request.get_json(silent=True) or {}
        items = data.get('items') or []
        method = (data.get('shipment_method') or '').strip().lower()

        if not items or not isinstance(items, list):
            return jsonify({'success': False, 'error': 'No items provided'}), 400
        if method not in ('pickup', 'shipping'):
            return jsonify({'success': False, 'error': 'Invalid shipment_method'}), 400

        # Validate destination details
        dest = {}
        if method == 'pickup':
            pickup_location = (data.get('pickup_location') or '').strip()
            if pickup_location not in ('Iron Hammer', 'Floating Dojo'):
                return jsonify({'success': False, 'error': 'Invalid pickup location'}), 400
            dest['pickup_location'] = pickup_location
        else:
            ship = data.get('shipping') or {}
            # Fallback to profile fields if some are missing
            def _profile(field, default=''):
                try:
                    return getattr(current_user, field) or default
                except Exception:
                    return default
            address = (ship.get('address') or _profile('address_line') or '').strip()
            city = (ship.get('city') or _profile('address_city') or '').strip()
            province = (ship.get('province') or _profile('address_province') or '').strip()
            postal_code = (ship.get('postal_code') or _profile('address_postal_code') or '').strip()
            country = (ship.get('country') or _profile('address_country', 'Vietnam') or 'Vietnam').strip()
            if not all([address, city, province, postal_code]):
                return jsonify({'success': False, 'error': 'Shipping address is incomplete'}), 400
            dest.update({
                'address': address,
                'city': city,
                'province': province,
                'postal_code': postal_code,
                'country': country,
            })

        # Load and validate items ownership and quantities
        updated = []
        from models import InventoryItem
        total_units = 0

        for entry in items:
            try:
                item_id = int(entry.get('inventory_item_id'))
                qty = int(entry.get('quantity', 0))
            except Exception:
                return jsonify({'success': False, 'error': 'Invalid item specification'}), 400
            if qty <= 0:
                return jsonify({'success': False, 'error': 'Quantity must be > 0'}), 400

            item = InventoryItem.query.get(item_id)
            if not item or not item.inventory or item.inventory.user_id != current_user.id:
                return jsonify({'success': False, 'error': f'Item {item_id} not found or not owned'}), 404
            # Only verified items may be withdrawn
            try:
                is_verified = bool(getattr(item, 'is_verified', False))
                status = (getattr(item, 'verification_status', None) or '').lower()
            except Exception:
                is_verified = False
                status = ''
            if not (is_verified or status == 'verified'):
                return jsonify({'success': False, 'error': f'Item {item_id} is not verified and cannot be withdrawn'}), 400
            if item.quantity < qty:
                return jsonify({'success': False, 'error': f'Insufficient quantity for item {item_id}'}), 400

            updated.append((item, qty))
            total_units += qty

        # Generate IDs
        from datetime import datetime as _dt
        import random, string
        request_id = f"WD-{_dt.utcnow().strftime('%Y%m%d%H%M%S')}-{''.join(random.choices(string.digits, k=5))}"

        def _generate_order_id(max_attempts: int = 10) -> str:
            for _ in range(max_attempts):
                candidate = f"WD-{_dt.utcnow().strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=6))}"
                try:
                    row = db.session.execute(db.text("SELECT 1 FROM orders WHERE id = :id"), {"id": candidate}).first()
                    if not row:
                        return candidate
                except Exception:
                    return candidate
            from uuid import uuid4
            return f"WD-{_dt.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:6]}"

        order_id = _generate_order_id()

        # Create an Order representing this withdrawal and update inventory atomically
        try:
            # Compute totals and destination string
            total_amount = 0.0
            for it, qty in updated:
                price = float(it.card.price) if it.card else 0.0
                total_amount += price * qty

            # Build order fields
            customer_name = ''
            try:
                customer_name = (getattr(current_user, 'full_name', None) or getattr(current_user, 'username', '') or '').strip()
            except Exception:
                pass
            contact_number = ''
            try:
                contact_number = getattr(current_user, 'phone_number', '') or ''
            except Exception:
                pass

            # Create Order
            order = Order(
                id=order_id,
                order_number=order_id,
                user_id=int(current_user.id),
                email=getattr(current_user, 'email', None),
                customer_name=customer_name or 'Customer',
                contact_number=contact_number,
                facebook_details=f'withdrawal:{request_id}',
                shipment_method=method,
                pickup_location=dest.get('pickup_location') if method == 'pickup' else None,
                status='pending',
                total_amount=float(total_amount),
                shipping_address=dest.get('address') if method == 'shipping' else None,
                shipping_city=dest.get('city') if method == 'shipping' else None,
                shipping_province=dest.get('province') if method == 'shipping' else None,
                shipping_postal_code=dest.get('postal_code') if method == 'shipping' else None,
                shipping_country=dest.get('country') if method == 'shipping' else None,
            )
            db.session.add(order)

            # Create OrderItems and update/delete inventory items
            for it, qty in updated:
                unit_price = float(it.card.price) if it.card else 0.0
                total_price = unit_price * qty
                oi = OrderItem(
                    order_id=order_id,
                    card_id=int(it.card_id),
                    quantity=int(qty),
                    unit_price=float(unit_price),
                    total_price=float(total_price),
                )
                db.session.add(oi)

                # Apply withdrawal to inventory; remove row if zero
                remaining = int(it.quantity) - int(qty)
                if remaining <= 0:
                    db.session.delete(it)
                else:
                    it.quantity = remaining
                    db.session.add(it)

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Withdraw commit failed: {e}")
            return jsonify({'success': False, 'error': 'Failed to process withdrawal'}), 500

        # Audit log
        try:
            dest_desc = dest.get('pickup_location') if method == 'pickup' else (
                f"{dest.get('address')}, {dest.get('city')}, {dest.get('province')} {dest.get('postal_code')}, {dest.get('country')}"
            )
            item_summ = ", ".join([f"{qty} x {it.card.name if it.card else 'Unknown'}(#{it.id})" for it, qty in updated])
            UserAuditLog.create_log(
                user_id=current_user.id,
                admin_id=current_user.id,
                action='inventory_withdraw',
                details=f"request_id={request_id}; method={method}; dest={dest_desc}; items=[{item_summ}]",
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
        except Exception as e:
            logger.warning(f"Audit log failed for withdraw {request_id}: {e}")

        # Response payload
        return jsonify({
            'success': True,
            'request_id': request_id,
            'method': method,
            **({'pickup_location': dest['pickup_location']} if method == 'pickup' else {'shipping': dest}),
            'items': [
                {
                    'inventory_item_id': it.id,
                    'card_name': it.card.name if it.card else 'Unknown',
                    'withdrawn_quantity': qty,
                    'remaining_quantity': max(0, int(it.quantity) - int(qty)),
                }
                for it, qty in updated
            ],
            'total_units': total_units,
            'order_id': order_id,
            'message': 'Withdrawal request recorded and quantities updated.'
        }), 200

    except Exception as e:
        logger.error(f"Error in inventory_withdraw: {e}")
        return jsonify({'success': False, 'error': 'Unexpected error'}), 500

@app.route('/account/settings', methods=['GET', 'POST'])
@login_required
def account_settings():
    """User account settings page"""
    if request.method == 'POST':
        try:
            # Ensure required user contact columns exist (best-effort, idempotent)
            try:
                from sqlalchemy import inspect as _sa_inspect
                _cols = {c.get('name') for c in _sa_inspect(db.engine).get_columns('users')}
                _needed = {
                    'full_name', 'phone_number', 'address_line', 'address_city',
                    'address_province', 'address_postal_code', 'address_country'
                }
                if not _needed.issubset(_cols):
                    try:
                        # Attempt manual migration using current DB path plus common instance DBs
                        from apply_user_contact_fields import apply_user_contact_fields as _apply_user_cols
                        _db_path = getattr(getattr(db, 'engine', None), 'url', None)
                        _db_path = getattr(_db_path, 'database', None)
                        _candidates = [_db_path] if _db_path else None
                        _apply_user_cols(_candidates)
                    except Exception:
                        pass
            except Exception:
                pass
            # Get form data
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            two_factor_enabled = 'two_factor_enabled' in request.form

            # Username changes are disabled; if a different value is submitted, reject
            if username and username != current_user.username:
                flash('Changing username is not permitted.', 'error')
                return redirect(request.url)

            # Validate email if provided
            if email and not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
                flash('Please enter a valid email address.', 'error')
                return redirect(request.url)

            # Check if email is already taken by another user (use minimal projection)
            if email:
                existing_email = db.session.query(User.id).filter(
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

            # Username changes are disabled

            if current_user.email != email:
                changes_made.append(f'email: {current_user.email or "None"} → {email or "None"}')
                current_user.email = email

            if new_password:
                changes_made.append('password changed')

            if current_user.two_factor_enabled != two_factor_enabled:
                changes_made.append(f'two-factor auth: {"enabled" if current_user.two_factor_enabled else "disabled"} → {"enabled" if two_factor_enabled else "disabled"}')
                current_user.two_factor_enabled = two_factor_enabled

            # Contact and address fields
            full_name = request.form.get('full_name', '').strip()
            phone_number = request.form.get('phone_number', '').strip()
            address_line = request.form.get('address_line', '').strip()
            address_city = request.form.get('address_city', '').strip()
            address_province = request.form.get('address_province', '').strip()
            address_postal_code = request.form.get('address_postal_code', '').strip()
            address_country = request.form.get('address_country', '').strip() or 'Vietnam'

            def _apply_change(attr, new_val, label):
                old_val = getattr(current_user, attr, None)
                if old_val != new_val:
                    changes_made.append(f"{label}: {old_val or 'None'} → {new_val or 'None'}")
                    setattr(current_user, attr, new_val)

            _apply_change('full_name', full_name, 'full_name')
            _apply_change('phone_number', phone_number, 'phone_number')
            _apply_change('address_line', address_line, 'address')
            _apply_change('address_city', address_city, 'city')
            _apply_change('address_province', address_province, 'province')
            _apply_change('address_postal_code', address_postal_code, 'postal_code')
            _apply_change('address_country', address_country, 'country')

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
            try:
                uid = current_user.get_id()
            except Exception:
                uid = 'unknown'
            logger.error(f"Error updating account settings for user {uid}: {e}")
            flash('An error occurred while updating your account settings.', 'error')

    # Build a safe profile context that does not touch columns missing in DB
    try:
        from sqlalchemy import inspect as _sa_inspect
        user_cols = {c.get('name') for c in _sa_inspect(db.engine).get_columns('users')}
    except Exception:
        user_cols = set()

    def safe_val(field):
        if field in user_cols:
            try:
                return getattr(current_user, field) or ''
            except Exception:
                return ''
        return ''

    profile = {
        'full_name': safe_val('full_name'),
        'phone_number': safe_val('phone_number'),
        'address_line': safe_val('address_line'),
        'address_city': safe_val('address_city'),
        'address_province': safe_val('address_province'),
        'address_postal_code': safe_val('address_postal_code'),
        'address_country': safe_val('address_country') or 'Vietnam',
        'email': safe_val('email') or (current_user.email if hasattr(current_user, 'email') else ''),
    }

    return render_template('account_settings.html', profile=profile)

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
    try:
        is_admin = bool(current_user.is_authenticated and getattr(current_user, 'role', None) in ('admin', 'super_admin'))
    except Exception:
        is_admin = False
    return {
        'current_user': current_user,
        'is_admin': is_admin,
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
        incoming_class = request.form.get('card_class')
        if incoming_class is not None:
            card.card_class = incoming_class.strip() or 'General'
        card.rarity = request.form.get('rarity', card.rarity)
        card.condition = request.form.get('condition', card.condition)
        try:
            lang = request.form.get('language')
            if lang:
                card.language = lang
        except Exception:
            pass
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
            language=request.form.get('language', 'English'),
            description=request.form.get('description', ''),
            image_url=request.form.get('image_url', ''),
            foiling=request.form.get('foiling', 'NF'),
            art_style=request.form.get('art_style', 'normal'),
            card_class=((request.form.get('card_class') or 'General').strip() or 'General'),
            owner='shop'
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
    # Exclude withdrawal-created orders from the main list
    filtered_orders = []
    for o in orders:
        try:
            fb = (getattr(o, 'facebook_details', '') or '')
            if fb.startswith('withdrawal:'):
                continue
        except Exception:
            pass
        filtered_orders.append(o)

    # Load recent inventory withdrawal requests from audit logs
    try:
        from models import UserAuditLog
        logs = (
            UserAuditLog.query
            .filter_by(action='inventory_withdraw')
            .order_by(UserAuditLog.created_at.desc())
            .limit(100)
            .all()
        )

        def _parse_details(s: str) -> dict:
            out = {}
            try:
                # Split by ';' tokens like 'key=value'
                parts = [p.strip() for p in (s or '').split(';') if p.strip()]
                for p in parts:
                    if '=' in p:
                        k, v = p.split('=', 1)
                        out[k.strip()] = v.strip()
            except Exception:
                pass
            return out

        withdrawals = []
        for log in logs:
            d = _parse_details(getattr(log, 'details', '') or '')
            req_id = d.get('request_id')
            # resolve linked order if present
            order_obj = None
            if req_id:
                try:
                    order_obj = Order.query.filter_by(facebook_details=f'withdrawal:{req_id}').order_by(Order.created_at.desc()).first()
                except Exception:
                    order_obj = None
            withdrawals.append({
                'created_at': getattr(log, 'created_at', None),
                'user': getattr(log, 'user', None),
                'request_id': req_id,
                'method': d.get('method'),
                'dest': d.get('dest'),
                'items': d.get('items'),
                'order': order_obj,
            })
    except Exception as e:
        logger.error(f"Error loading withdrawal logs: {e}")
        withdrawals = []

    return render_template('admin_orders.html', orders=filtered_orders, withdrawals=withdrawals)

@app.route('/admin/withdrawals/<request_id>/approve', methods=['POST'])
@admin_required
def admin_withdraw_approve(request_id):
    """Approve a withdrawal request by marking the linked order confirmed."""
    try:
        order = Order.query.filter_by(facebook_details=f'withdrawal:{request_id}').order_by(Order.created_at.desc()).first()
        if not order:
            flash('Withdrawal order not found', 'error')
            return redirect(url_for('admin_orders'))
        order.status = 'confirmed'
        order.updated_at = db.func.now()
        db.session.commit()
        flash(f'Withdrawal {request_id} approved (order {order.id})', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Approve withdrawal failed: {e}")
        flash('Failed to approve withdrawal', 'error')
    return redirect(url_for('admin_orders'))

@app.route('/admin/withdrawals/<request_id>/reject', methods=['POST'])
@admin_required
def admin_withdraw_reject(request_id):
    """Reject a withdrawal request by marking the linked order rejected."""
    try:
        order = Order.query.filter_by(facebook_details=f'withdrawal:{request_id}').order_by(Order.created_at.desc()).first()
        if not order:
            flash('Withdrawal order not found', 'error')
            return redirect(url_for('admin_orders'))
        order.status = 'rejected'
        order.updated_at = db.func.now()
        db.session.commit()
        flash(f'Withdrawal {request_id} rejected (order {order.id})', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Reject withdrawal failed: {e}")
        flash('Failed to reject withdrawal', 'error')
    return redirect(url_for('admin_orders'))

@app.route('/admin/orders/<order_id>')
@admin_required
def admin_order_detail(order_id):
    """Admin order detail page"""
    order = Order.query.get_or_404(order_id)

    # Get order items with card details and owner attribution
    order_items = []
    for item in order.items:
        # Determine owner: seller username for consigned/user items, otherwise 'shop'
        try:
            owner_username = None
            if getattr(item, 'seller', None) and getattr(item.seller, 'username', None):
                owner_username = item.seller.username
            elif getattr(item, 'inventory_item', None) and getattr(item.inventory_item, 'inventory', None) and getattr(item.inventory_item.inventory, 'user', None):
                owner_username = getattr(item.inventory_item.inventory.user, 'username', None)
        except Exception:
            owner_username = None
        owner_username = owner_username or 'shop'

        # Determine language: prefer inventory item language, fallback to card language
        lang = None
        try:
            if getattr(item, 'inventory_item', None) and getattr(item.inventory_item, 'language', None):
                lang = item.inventory_item.language
            elif getattr(item, 'card', None) and getattr(item.card, 'language', None):
                lang = item.card.language
        except Exception:
            lang = None

        order_items.append({
            'card': item.card,
            'quantity': item.quantity,
            'unit_price': float(item.unit_price),
            'total_price': float(item.total_price),
            'foiling': item.card.foiling if item.card else None,
            'art_style': item.card.art_style if item.card else None,
            'language': lang or 'English',
            'owner': owner_username,
        })

    return render_template('admin_order_detail.html',
                         order=order,
                         order_items=order_items)

# API: Toggle list-for-sale for a user's inventory item
@app.route('/api/inventory/item/<int:item_id>/list', methods=['POST'])
@login_required
def api_list_inventory_item(item_id):
    try:
        data = request.get_json() or {}
        listed = bool(data.get('listed', False))
        qty_req = data.get('quantity')

        item = InventoryItem.query.get_or_404(item_id)
        # Ownership check
        if not item.inventory or item.inventory.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Not authorized'}), 403

        # Validations for listing
        if listed:
            # Block listing credit tokens (CREDIT set) or the known token names
            try:
                token_names = {'copper token', 'silver token', 'gold token'}
                card = item.card
                if card and ((getattr(card, 'is_credit', False)) or str(card.set_name).upper() == 'CREDIT' or str(card.name).lower() in token_names):
                    return jsonify({'success': False, 'error': 'Credit tokens cannot be listed for sale in shop'}), 400
            except Exception:
                pass
            if not item.is_verified:
                return jsonify({'success': False, 'error': 'Item must be verified to list'}), 400
            if item.quantity <= 0:
                return jsonify({'success': False, 'error': 'Item out of stock'}), 400
            # Quantity to move into shop
            try:
                qty_to_move = int(qty_req) if qty_req is not None else int(item.quantity)
            except Exception:
                qty_to_move = int(item.quantity)
            qty_to_move = max(1, min(int(item.quantity), qty_to_move))

            # Ensure public visibility when listing
            item.is_public = True

            # Move to shop inventory (consignment)
            # 1) decrement user inventory
            item.quantity -= qty_to_move
            # If partial consignment, create a duplicate marker item
            if qty_to_move > 0 and item.quantity >= 0 and qty_to_move > 0:
                try:
                    if item.quantity >= 0 and qty_to_move < (item.quantity + qty_to_move):
                        duplicate_item = InventoryItem(
                            inventory_id=item.inventory_id,
                            card_id=item.card_id,
                            quantity=qty_to_move,
                            condition=item.condition,
                            verification_status=item.verification_status,
                            is_verified=item.is_verified,
                            notes=(item.notes or '') + ' [consigned_to_shop]',
                            grade=item.grade,
                            language=item.language,
                            foil_type=item.foil_type,
                            is_mint=item.is_mint,
                            is_public=False
                        )
                        db.session.add(duplicate_item)
                        db.session.flush()
                except Exception:
                    pass
            # 2) increment shop consignment record
            shop_row = ShopInventoryItem.query.filter_by(
                card_id=item.card_id,
                from_user_id=item.inventory.user_id,
                source_inventory_item_id=item.id,
            ).first()
            if not shop_row:
                shop_row = ShopInventoryItem(
                    card_id=item.card_id,
                    from_user_id=item.inventory.user_id,
                    source_inventory_item_id=item.id,
                    quantity=0,
                    owner=(getattr(getattr(item.inventory, 'user', None), 'username', None) or None),
                )
                db.session.add(shop_row)
                db.session.flush()
            shop_row.quantity += qty_to_move
            # Log history
            try:
                db.session.add(ShopConsignmentLog(
                    card_id=item.card_id,
                    from_user_id=item.inventory.user_id,
                    source_inventory_item_id=item.id,
                    quantity=qty_to_move,
                    action='list'
                ))
            except Exception:
                pass

            # 3) optionally reflect in admin stock for catalog visibility
            card = item.card
            if card:
                try:
                    card.quantity = int(card.quantity) + qty_to_move
                except Exception:
                    pass

            # Reset list-for-sale flag after sending
            item.listed_for_sale = False
            item.updated_at = db.func.now()
            db.session.commit()

            return jsonify({'success': True, 'listed_for_sale': False, 'moved': qty_to_move, 'is_public': item.is_public, 'card_id': item.card_id})
        else:
            # Unlist: move all consigned units for this source back to user inventory
            shop_row = ShopInventoryItem.query.filter_by(
                card_id=item.card_id,
                from_user_id=item.inventory.user_id,
                source_inventory_item_id=item.id,
            ).first()
            moved_back = 0
            if shop_row and shop_row.quantity > 0:
                moved_back = int(shop_row.quantity)
                # 1) reduce admin stock
                if item.card:
                    try:
                        item.card.quantity = max(0, int(item.card.quantity) - moved_back)
                    except Exception:
                        pass
                # 2) add back to user inventory
                item.quantity += moved_back
                shop_row.quantity = 0
                # Log history
                try:
                    db.session.add(ShopConsignmentLog(
                        card_id=item.card_id,
                        from_user_id=item.inventory.user_id,
                        source_inventory_item_id=item.id,
                        quantity=moved_back,
                        action='unlist'
                    ))
                except Exception:
                    pass
            item.listed_for_sale = False
            item.updated_at = db.func.now()
            db.session.commit()

            return jsonify({'success': True, 'listed_for_sale': False, 'moved_back': moved_back, 'is_public': item.is_public})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling list-for-sale: {e}")
        return jsonify({'success': False, 'error': 'Failed to update listing status'}), 500

@app.route('/admin/orders/<order_id>/fulfill', methods=['POST'])
@admin_required
def admin_fulfill_order(order_id):
    """Confirm an order"""
    order = Order.query.get_or_404(order_id)

    if order.status != 'pending':
        flash('Only pending orders can be confirmed', 'warning')
        return redirect(url_for('admin_orders'))
    try:
        # If order is 'inventory', add items to the customer's verified inventory
        if getattr(order, 'shipment_method', None) == 'inventory':
            try:
                # Resolve target user
                target_user_id = getattr(order, 'user_id', None)
                if not target_user_id and getattr(order, 'email', None):
                    u = User.query.filter_by(email=order.email).first()
                    if u:
                        target_user_id = u.id
                        try:
                            order.user_id = u.id
                        except Exception:
                            pass

                if target_user_id:
                    # Get or create user's inventory
                    inv = UserInventory.query.filter_by(user_id=target_user_id).first()
                    if not inv:
                        inv = UserInventory(user_id=target_user_id, is_public=False)
                        db.session.add(inv)
                        db.session.flush()

                    # Copy each order item into user's inventory as verified
                    for oi in order.items:
                        if not oi.card_id:
                            continue
                        existing = InventoryItem.query.filter_by(inventory_id=inv.id, card_id=oi.card_id).first()
                        if existing:
                            existing.quantity += int(oi.quantity)
                            existing.is_verified = True
                            existing.verification_status = 'verified'
                            existing.updated_at = db.func.now()
                            db.session.add(existing)
                        else:
                            new_item = InventoryItem(
                                inventory_id=inv.id,
                                card_id=oi.card_id,
                                quantity=int(oi.quantity),
                                condition='Near Mint',
                                verification_status='verified',
                                is_verified=True,
                                notes=f'Added from order {order.id}',
                                language='English',
                                foil_type='Non Foil',
                                is_mint=False,
                            )
                            db.session.add(new_item)

                    # Log the inventory grant
                    try:
                        UserAuditLog.create_log(
                            user_id=target_user_id,
                            admin_id=current_user.id,
                            action='inventory_grant',
                            details=f'Granted items from order {order.id} to user inventory',
                            ip_address=request.remote_addr,
                            user_agent=request.headers.get('User-Agent')
                        )
                    except Exception:
                        pass
            except Exception as inv_e:
                logger.error(f"Error adding items to inventory for order {order_id}: {inv_e}")

        # Mark order as confirmed
        order.status = 'confirmed'
        order.updated_at = db.func.now()
        db.session.commit()

        flash(f'Order {order_id} has been confirmed', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error confirming order: {str(e)}', 'error')
        logger.error(f"Error confirming order {order_id}: {e}")

    return redirect(url_for('admin_orders'))

@app.route('/admin/orders/<order_id>/ship', methods=['POST'])
@admin_required
def admin_ship_order(order_id):
    """Mark an order as shipped (for shipping method)."""
    order = Order.query.get_or_404(order_id)

    if order.status not in ('pending', 'confirmed'):
        flash('Only pending or confirmed orders can be marked as shipped', 'warning')
        return redirect(url_for('admin_orders'))

    try:
        # For shipping method, mark shipped; for pickup/inventory we still allow shipped if desired.
        order.status = 'shipped'
        order.updated_at = db.func.now()
        db.session.commit()
        flash(f'Order {order_id} marked as shipped', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error marking order shipped: {str(e)}', 'error')
        logger.error(f"Error shipping order {order_id}: {e}")

    return redirect(url_for('admin_orders'))
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
        order.status = 'confirmed'
        order.updated_at = db.func.now()
        db.session.commit()

        flash(f'Order {order_id} has been confirmed successfully', 'success')
        logger.info(f"Order {order_id} confirmed by admin")

    except Exception as e:
        db.session.rollback()
        flash(f'Error confirming order: {str(e)}', 'error')
        logger.error(f"Error confirming order {order_id}: {e}")

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
        had_error = False
        # Restore stock for all order items with correct ownership attribution
        from models import ShopInventoryItem, InventoryItem
        for oi in order.items:
            try:
                # Case 1: Order line linked to a specific user inventory item (consignment or direct-user sale)
                if getattr(oi, 'inventory_item_id', None) and getattr(oi, 'seller_user_id', None):
                    # Detect if it was a consigned shop allocation (there will be a shop consignment row)
                    shop_row = ShopInventoryItem.query.filter_by(
                        card_id=oi.card_id,
                        from_user_id=oi.seller_user_id,
                        source_inventory_item_id=oi.inventory_item_id,
                    ).first()
                    if shop_row is not None:
                        # Consigned stock sold from shop: return quantity back to consignment and admin display stock
                        shop_row.quantity = int(shop_row.quantity) + int(oi.quantity)
                        if oi.card:
                            oi.card.quantity += oi.quantity
                            logger.info(f"Restored consigned + admin stock: {oi.quantity} of card {oi.card.id} for user {shop_row.from_user_id}")
                    else:
                        # Direct user inventory sale: return quantity back to the user's inventory item
                        inv_item = InventoryItem.query.get(oi.inventory_item_id)
                        if inv_item:
                            inv_item.quantity = int(inv_item.quantity) + int(oi.quantity)
                            logger.info(f"Restored user inventory item {inv_item.id} by {oi.quantity}")
                        # Do NOT modify admin card stock for direct user sales
                else:
                    # Case 2: Pure admin store item (no seller attribution): restore admin card stock
                    if oi.card:
                        oi.card.quantity += oi.quantity
                        logger.info(f"Restored admin stock: {oi.quantity} units of {oi.card.name} (ID: {oi.card.id})")
            except Exception as r_e:
                logger.error(f"Error restoring stock for order item {getattr(oi,'id',None)}: {r_e}")
                # Roll back to clear failed state and flag error
                try:
                    db.session.rollback()
                except Exception:
                    pass
                had_error = True

        # Refund any credits redeemed against this order
        try:
            from models import CreditLedger, InventoryItem
            from credit_service import _locked_user_inventory, _locked_merge_inventory_item
            # Match redemption ledger rows using idempotency key pattern used at placement
            # Rows created with idempotency_key = f"order:{order_id}:{card_id}"
            like_pat = f"order:{order_id}%"
            ledger_rows = (CreditLedger.query
                           .filter(CreditLedger.kind == 'redeem')
                           .filter(CreditLedger.direction == 'debit')
                           .filter(CreditLedger.idempotency_key.ilike(like_pat))
                           .all())
            for row in ledger_rows:
                user_id = row.user_id
                item_id = row.related_inventory_item_id
                amount_vnd = int(row.amount_vnd)
                inv = _locked_user_inventory(user_id)
                item = InventoryItem.query.get(item_id) if item_id else None
                if item and item.card and item.inventory_id == inv.id:
                    denom = int(item.card.price)
                    units = amount_vnd // denom if denom > 0 else 0
                    if units > 0:
                        item.quantity += units
                        # reversal ledger
                        from credit_service import _safe_add_ledger
                        _safe_add_ledger(CreditLedger(user_id=user_id, amount_vnd=amount_vnd, direction='credit', kind='revoke', related_inventory_item_id=item.id, idempotency_key=f'refund:{order_id}:{row.id}'))
                else:
                    logger.warning(f"Credit refund: inventory item missing or mismatched for order {order_id} row {row.id}")
        except Exception as re:
            logger.error(f"Error refunding credits for order {order_id}: {re}")
            try:
                db.session.rollback()
            except Exception:
                pass
            had_error = True

        if had_error:
            raise RuntimeError("One or more stock/credit refund operations failed; rejection aborted")

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
        # Hide zero-quantity items from admin view lists and stats
        items = [it for it in user_inventory.items if getattr(it, 'quantity', 0) > 0]
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


# ---------------------------------
# Transfer history (user and admin)
# ---------------------------------

@app.route('/inventory/transfers')
@login_required
def my_transfer_history():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        q = InventoryTransferLog.query.filter_by(from_user_id=current_user.id).order_by(InventoryTransferLog.created_at.desc())
        pagination = q.paginate(page=page, per_page=per_page, error_out=False)
        rows = [row.to_dict() for row in pagination.items]
        return render_template('transfer_history.html',
                               transfers=rows,
                               pagination=pagination)
    except Exception as e:
        logger.error({'event': 'my_transfer_history_error', 'error': str(e)})
        flash('Failed to load transfer history.', 'error')
        return redirect(url_for('user_inventory'))


@app.route('/admin/transfers')
@admin_required
def admin_transfer_history():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        search = (request.args.get('q') or '').strip()

        q = InventoryTransferLog.query
        if search:
            # Search on usernames or numeric IDs
            like = f"%{search}%"
            q = (
                q.join(User, InventoryTransferLog.from_user_id == User.id)
                 .outerjoin(Card, InventoryTransferLog.card_id == Card.id)
                 .filter(db.or_(
                    User.username.ilike(like),
                    db.cast(InventoryTransferLog.from_user_id, String).ilike(like),
                    db.cast(InventoryTransferLog.to_user_id, String).ilike(like),
                    Card.name.ilike(like)
                ))
            )
        q = q.order_by(InventoryTransferLog.created_at.desc())
        pagination = q.paginate(page=page, per_page=per_page, error_out=False)
        rows = [row.to_dict() for row in pagination.items]
        return render_template('admin_transfer_history.html',
                               transfers=rows,
                               pagination=pagination,
                               search=search)
    except Exception as e:
        logger.error({'event': 'admin_transfer_history_error', 'error': str(e)})
        flash('Failed to load transfer history.', 'error')
        return redirect(url_for('admin'))


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
