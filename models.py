"""
SQLAlchemy models for The Lotus TCG
"""
import os
from datetime import datetime, timedelta
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import String, Integer, Numeric, DateTime, Text, func, ForeignKey, BigInteger, CheckConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped, mapped_column

# Import db from app - will be available after app initialization
from app import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default='user')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Enhanced user management fields
    last_login: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    account_status: Mapped[str] = mapped_column(String(20), nullable=False, default='active')  # active, suspended, banned
    suspension_reason: Mapped[str] = mapped_column(Text, nullable=True)
    suspension_expires: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    password_reset_token: Mapped[str] = mapped_column(String(256), nullable=True)
    password_reset_expires: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    two_factor_enabled: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False)
    two_factor_secret: Mapped[str] = mapped_column(String(256), nullable=True)
    # Contact and address fields
    full_name: Mapped[str] = mapped_column(String(100), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=True)
    address_line: Mapped[str] = mapped_column(Text, nullable=True)
    address_city: Mapped[str] = mapped_column(String(100), nullable=True)
    address_province: Mapped[str] = mapped_column(String(100), nullable=True)
    address_postal_code: Mapped[str] = mapped_column(String(20), nullable=True)
    address_country: Mapped[str] = mapped_column(String(100), nullable=True, default='Vietnam')
    # Temporarily comment out these columns until database is updated
    # login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # locked_until: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    def check_password(self, password: str) -> bool:
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self) -> bool:
        """Check if user has admin role"""
        return self.role in ['admin', 'super_admin']

    def is_super_admin(self) -> bool:
        """Check if user has super admin role"""
        return self.role == 'super_admin'

    def is_active(self) -> bool:
        """Check if user account is active"""
        return self.account_status == 'active'

    def is_suspended(self) -> bool:
        """Check if user account is suspended"""
        return self.account_status == 'suspended'

    def is_banned(self) -> bool:
        """Check if user account is banned"""
        return self.account_status == 'banned'

    def can_login(self) -> bool:
        """Check if user can login"""
        if self.is_banned():
            return False
        if self.is_suspended() and self.suspension_expires:
            if datetime.utcnow() < self.suspension_expires:
                return False
            else:
                # Suspension expired, reactivate account
                self.account_status = 'active'
                self.suspension_reason = None
                self.suspension_expires = None
        return self.is_active()

    def update_last_login(self):
        """Update last login timestamp"""
        self.last_login = datetime.utcnow()

    def suspend_account(self, reason: str = None, expires_at: datetime = None, admin_user=None):
        """Suspend user account and synchronize inventory verification status"""
        old_status = self.account_status
        self.account_status = 'suspended'
        self.suspension_reason = reason
        self.suspension_expires = expires_at

        # Synchronize inventory items - set all to unverified when user is suspended
        self._sync_inventory_verification_status('unverified', admin_user, f"User account suspended: {reason}")

    def ban_account(self, reason: str = None, admin_user=None):
        """Ban user account and synchronize inventory verification status"""
        old_status = self.account_status
        self.account_status = 'banned'
        self.suspension_reason = reason
        self.suspension_expires = None

        # Synchronize inventory items - set all to unverified when user is banned
        self._sync_inventory_verification_status('unverified', admin_user, f"User account banned: {reason}")

    def reactivate_account(self, admin_user=None):
        """Reactivate suspended account"""
        old_status = self.account_status
        self.account_status = 'active'
        self.suspension_reason = None
        self.suspension_expires = None

        # Note: When reactivating, we don't automatically change inventory status
        # The admin can manually review and re-verify items if needed

    def _sync_inventory_verification_status(self, new_status, admin_user=None, reason=None):
        """Synchronize verification status of all user's inventory items"""
        try:
            # Get user's inventory
            user_inventory = UserInventory.query.filter_by(user_id=self.id).first()
            if not user_inventory:
                return

            # Update all inventory items
            updated_count = 0
            for item in user_inventory.items:
                if item.verification_status != new_status:
                    old_item_status = item.verification_status
                    item.verification_status = new_status
                    item.is_verified = (new_status == 'verified')

                    if new_status == 'verified':
                        item.verified_at = datetime.utcnow()
                        item.verified_by = admin_user.id if admin_user else None
                    elif new_status == 'unverified':
                        item.verified_at = None
                        item.verified_by = None

                    item.updated_at = datetime.utcnow()

                    # Create verification audit log
                    if admin_user:
                        VerificationAuditLog.create_log(
                            inventory_item_id=item.id,
                            admin_id=admin_user.id,
                            action='bulk_status_change',
                            previous_status=old_item_status,
                            new_status=new_status,
                            notes=f"User account status change: {reason}",
                            ip_address=None,
                            user_agent=None
                        )
                    updated_count += 1

            if updated_count > 0:
                db.session.commit()
                print(f"Synchronized {updated_count} inventory items for user {self.username}")

        except Exception as e:
            db.session.rollback()
            print(f"Error synchronizing inventory verification status: {e}")

    def record_login_attempt(self, success: bool = True):
        """Record login attempt"""
        if success:
            # Temporarily disabled until database columns are added
            # self.login_attempts = 0
            # self.locked_until = None
            self.update_last_login()
        else:
            # Temporarily disabled until database columns are added
            # self.login_attempts += 1
            # if self.login_attempts >= 5:  # Lock account after 5 failed attempts
            #     self.locked_until = datetime.utcnow() + timedelta(minutes=30)
            pass

    def is_locked(self) -> bool:
        """Check if account is temporarily locked"""
        # Temporarily disabled until database columns are added
        # if self.locked_until and datetime.utcnow() < self.locked_until:
        #     return True
        # elif self.locked_until:
        #     # Lock expired, reset
        #     self.login_attempts = 0
        #     self.locked_until = None
        return False

    def to_dict(self):
        """Convert user to dictionary for API responses"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'account_status': self.account_status,
            'suspension_reason': self.suspension_reason,
            'suspension_expires': self.suspension_expires.isoformat() if self.suspension_expires else None,
            'two_factor_enabled': self.two_factor_enabled
        }

    def __str__(self) -> str:
        """String representation of user"""
        return f"User: {self.username} ({self.role}) - {self.account_status}"


class Card(db.Model):
    __tablename__ = "cards"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    set_name: Mapped[str] = mapped_column(String(80), nullable=False, default='Unknown')
    rarity: Mapped[str] = mapped_column(String(20), nullable=False, default='Common')
    condition: Mapped[str] = mapped_column(String(20), nullable=False, default='Near Mint')
    # Default language for this catalog card entry (used in catalog/home/orders when not a user item)
    language: Mapped[str] = mapped_column(String(20), nullable=True, default='English')
    price: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0.0)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    # Optional external/system card identifier (e.g., TCG code)
    card_code: Mapped[str] = mapped_column(String(80), nullable=True)
    foiling: Mapped[str] = mapped_column(String(20), nullable=False, default='NF')
    art_style: Mapped[str] = mapped_column(String(20), nullable=False, default='normal')
    card_class: Mapped[str] = mapped_column(String(50), nullable=True, default='General')
    # Owner of the catalog item: 'shop' for admin-managed stock
    owner: Mapped[str] = mapped_column(String(80), nullable=True, default='shop')
    is_deleted: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        # Prevent duplicate CREDIT denominations across canonical attributes we track
        Index(
            'ux_credit_card_denom',
            'set_name', 'price', 'foiling', 'rarity', 'art_style', unique=True,
            postgresql_where=db.text("set_name = 'CREDIT'")
        ),
    )
    
    def to_dict(self):
        """Convert card to dictionary for templates"""
        return {
            'id': str(self.id),
            'name': self.name,
            'set_name': self.set_name,
            'rarity': self.rarity,
            'condition': self.condition,
            'language': self.language or 'English',
            'price': float(self.price),
            'quantity': self.quantity,
            'description': self.description or '',
            'image_url': self.image_url or '',
            'card_code': self.card_code or '',
            'foiling': self.foiling,
            'art_style': self.art_style,
            'card_class': self.card_class or 'General',
            'is_deleted': self.is_deleted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def soft_delete(self):
        """Mark card as deleted without removing from database"""
        self.is_deleted = True
        self.updated_at = func.now()
    
    def __str__(self) -> str:
        """String representation of card"""
        return f"Card: {self.name} ({self.set_name}) - {self.price} VND"

    @property
    def is_credit(self) -> bool:
        return self.set_name == 'CREDIT'


class Order(db.Model):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g., ORD-20240101-001
    # Human-friendly order number for display (can mirror id)
    order_number: Mapped[str] = mapped_column(String(30), nullable=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=True)
    email: Mapped[str] = mapped_column(String(120), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_number: Mapped[str] = mapped_column(String(20), nullable=False)
    facebook_details: Mapped[str] = mapped_column(Text, nullable=True)
    shipment_method: Mapped[str] = mapped_column(String(20), nullable=False)  # 'shipping' or 'pickup'
    pickup_location: Mapped[str] = mapped_column(String(50), nullable=True)  # 'Iron Hammer' or 'Floating Dojo'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # Shipping address fields (required when shipment_method is 'shipping')
    shipping_address: Mapped[str] = mapped_column(Text, nullable=True)
    shipping_city: Mapped[str] = mapped_column(String(100), nullable=True)
    shipping_province: Mapped[str] = mapped_column(String(100), nullable=True)
    shipping_postal_code: Mapped[str] = mapped_column(String(20), nullable=True)
    shipping_country: Mapped[str] = mapped_column(String(100), nullable=True, default='Vietnam')
    tracking_number: Mapped[str] = mapped_column(String(120), nullable=True)
    tracking_carrier: Mapped[str] = mapped_column(String(80), nullable=True)
    tracking_url: Mapped[str] = mapped_column(String(255), nullable=True)
    tracking_notes: Mapped[str] = mapped_column(Text, nullable=True)
    shipped_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Coupon-related fields
    coupon_id: Mapped[int] = mapped_column(Integer, ForeignKey('coupons.id'), nullable=True)
    coupon_code: Mapped[str] = mapped_column(String(20), nullable=True)  # Store coupon code at time of order
    discount_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)  # Discount applied
    discounted_total: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)  # Final total after discount

    # Relationship to order items
    items = relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    user = relationship('User')
    coupon = relationship('Coupon')  # Relationship to applied coupon

    def to_dict(self):
        """Convert order to dictionary for templates"""
        return {
            'id': self.id,
            'customer_name': self.customer_name,
            'contact_number': self.contact_number,
            'facebook_details': self.facebook_details,
            'shipment_method': self.shipment_method,
            'pickup_location': self.pickup_location,
            'status': self.status,
            'total_amount': float(self.total_amount),
            'discount_amount': float(self.discount_amount),
            'discounted_total': float(self.discounted_total) if self.discounted_total else float(self.total_amount),
            'coupon_code': self.coupon_code,
            'coupon': self.coupon.to_dict() if self.coupon else None,
            'shipping_address': self.shipping_address,
            'shipping_city': self.shipping_city,
            'shipping_province': self.shipping_province,
            'shipping_postal_code': self.shipping_postal_code,
            'shipping_country': self.shipping_country,
            'tracking_number': self.tracking_number,
            'tracking_carrier': self.tracking_carrier,
            'tracking_url': self.tracking_url,
            'tracking_notes': self.tracking_notes,
            'shipped_at': self.shipped_at.isoformat() if self.shipped_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __str__(self) -> str:
        """String representation of order"""
        return f"Order: {self.id} - {self.customer_name} - {self.total_amount} VND"


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[str] = mapped_column(String(20), ForeignKey('orders.id'), nullable=False)
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey('cards.id'), nullable=False)
    # Link back to a user inventory item when the order line originates from a user-listed item
    inventory_item_id: Mapped[int] = mapped_column(Integer, ForeignKey('inventory_items.id'), nullable=True)
    # Seller user id for user-listed items (None for store/admin items)
    seller_user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # Relationship to card
    card = relationship('Card', backref='order_items')
    inventory_item = relationship('InventoryItem', foreign_keys=[inventory_item_id])
    seller = relationship('User', foreign_keys=[seller_user_id])

    def to_dict(self):
        """Convert order item to dictionary for templates"""
        return {
            'id': self.id,
            'order_id': self.order_id,
            'card_id': self.card_id,
            'inventory_item_id': self.inventory_item_id,
            'seller_user_id': self.seller_user_id,
            'quantity': self.quantity,
            'unit_price': float(self.unit_price),
            'total_price': float(self.total_price),
            'card': self.card.to_dict() if self.card else None
        }

    def __str__(self) -> str:
        """String representation of order item"""
        return f"OrderItem: {self.card.name if self.card else 'Unknown Card'} x{self.quantity}"
# User Inventory Management Models

class UserInventory(db.Model):
    """User's personal inventory for managing their card collection"""
    __tablename__ = "user_inventories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False)
    is_public: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="inventory")
    items = relationship("InventoryItem", back_populates="inventory", cascade="all, delete-orphan")

    def __str__(self) -> str:
        """String representation of user inventory"""
        return f"UserInventory: {self.user.username} ({'Public' if self.is_public else 'Private'})"


class InventoryItem(db.Model):
    """Individual item in a user's inventory"""
    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint('quantity >= 0', name='chk_qty_nonneg'),
        Index('ix_inventory_items_market', 'listed_for_sale', 'is_verified', 'quantity'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_id: Mapped[int] = mapped_column(Integer, ForeignKey('user_inventories.id'), nullable=False)
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey('cards.id'), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    condition: Mapped[str] = mapped_column(String(20), nullable=False, default='Near Mint')
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default='unverified')  # unverified, pending, verified
    is_verified: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False)  # Keep for backward compatibility
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    verified_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    verified_by: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)  # Additional notes about the item
    grade: Mapped[str] = mapped_column(String(10), nullable=True)  # PSA/BGS grade if applicable
    language: Mapped[str] = mapped_column(String(20), nullable=True, default='English')  # Card language
    foil_type: Mapped[str] = mapped_column(String(20), nullable=True, default='Non Foil')  # Specific foil type
    is_mint: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=True)  # Mint condition flag
    is_public: Mapped[bool] = mapped_column(db.Boolean, default=True, nullable=False)  # Whether item appears in public inventory
    listed_for_sale: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False)  # Whether item appears in shop

    # Relationships
    inventory = relationship("UserInventory", back_populates="items")
    card = relationship("Card")
    verifier = relationship("User", foreign_keys=[verified_by])

    @property
    def owner(self):
        """Get the owner of this inventory item"""
        return self.inventory.user if self.inventory else None

    @property
    def card_name(self):
        """Get card name through relationship"""
        return self.card.name if self.card else 'Unknown Card'

    @property
    def card_set(self):
        """Get card set through relationship"""
        return self.card.set_name if self.card else 'Unknown'

    @property
    def card_rarity(self):
        """Get card rarity through relationship"""
        return self.card.rarity if self.card else 'Unknown'

    @property
    def market_value(self):
        """Get market value from card"""
        return float(self.card.price) if self.card else 0.0

    @property
    def total_value(self):
        """Calculate total value based on market value"""
        return self.market_value * self.quantity

    @property
    def verification_status_display(self):
        """Get human-readable verification status"""
        status_map = {
            'unverified': 'Unverified',
            'pending': 'Pending Review',
            'verified': 'Verified'
        }
        return status_map.get(self.verification_status, 'Unknown')

    def update_verification_status(self, new_status, admin_user, notes=None):
        """Update verification status with audit logging and user account status check"""
        from datetime import datetime

        old_status = self.verification_status

        # Check user's account status before allowing verification changes
        owner = self.owner
        if owner and not owner.is_active():
            # If user account is suspended or banned, prevent verification
            if new_status == 'verified':
                raise ValueError(f"Cannot verify item: User account is {owner.account_status}")
            elif new_status == 'pending':
                # Allow setting to pending even for suspended users (for review later)
                pass

        # Update the status
        self.verification_status = new_status
        self.is_verified = (new_status == 'verified')  # Keep backward compatibility

        if new_status == 'verified':
            self.verified_at = datetime.utcnow()
            self.verified_by = admin_user.id
        elif new_status == 'unverified':
            self.verified_at = None
            self.verified_by = None

        self.updated_at = datetime.utcnow()

        # Create audit log
        VerificationAuditLog.create_log(
            inventory_item_id=self.id,
            admin_id=admin_user.id,
            action='status_change',
            previous_status=old_status,
            new_status=new_status,
            notes=notes,
            ip_address=None,  # Will be set by the route
            user_agent=None   # Will be set by the route
        )

    def to_dict(self):
        """Convert inventory item to dictionary for API responses"""
        return {
            'id': self.id,
            'inventory_id': self.inventory_id,
            'card_id': self.card_id,
            'card_name': self.card_name,
            'card_set': self.card_set,
            'card_rarity': self.card_rarity,
            'quantity': self.quantity,
            'condition': self.condition,
            'verification_status': self.verification_status,
            'verification_status_display': self.verification_status_display,
            'is_verified': self.is_verified,
            'market_value': self.market_value,
            'total_value': self.total_value,
            'added_at': self.added_at.isoformat() if self.added_at else None,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'notes': self.notes,
            'grade': self.grade,
            'language': self.language,
            'foil_type': self.foil_type,
            'is_mint': self.is_mint,
            'is_public': self.is_public,
            'listed_for_sale': self.listed_for_sale,
            'card_image': self.card.image_url if self.card else None,
            'owner_username': self.owner.username if self.owner else None,
            'verifier_username': self.verifier.username if self.verifier else None
        }

    def update_from_dict(self, data):
        """Update item from dictionary data with validation"""
        allowed_fields = [
            'quantity', 'condition', 'notes', 'grade', 'language', 'foil_type', 'is_mint', 'is_public'
        ]

        validation_errors = []

        for field in allowed_fields:
            if field in data:
                try:
                    if field == 'quantity' and data[field] is not None:
                        value = int(data[field])
                        if value <= 0:
                            validation_errors.append('Quantity must be greater than 0')
                            continue
                        elif value > 1000:
                            validation_errors.append('Quantity cannot exceed 1000')
                            continue
                        setattr(self, field, value)
                    elif field == 'is_mint':
                        setattr(self, field, bool(data[field]))
                    elif field == 'notes' and data[field] and len(str(data[field])) > 1000:
                        validation_errors.append('Notes cannot exceed 1000 characters')
                        continue
                    elif field == 'grade' and data[field] and len(str(data[field])) > 20:
                        validation_errors.append('Grade cannot exceed 20 characters')
                        continue
                    else:
                        setattr(self, field, data[field])
                except (ValueError, TypeError) as e:
                    validation_errors.append(f'Invalid value for {field}: {str(e)}')

        self.updated_at = func.now()

        if validation_errors:
            raise ValueError('; '.join(validation_errors))

    def can_edit(self, user):
        """Check if user can edit this item"""
        return self.owner and self.owner.id == user.id

    def can_delete(self, user):
        """Check if user can delete this item"""
        return self.owner and self.owner.id == user.id

    def __str__(self) -> str:
        """String representation of inventory item"""
        return f"InventoryItem: {self.card_name} x{self.quantity} ({self.condition})"


class ShopInventoryItem(db.Model):
    """Consigned inventory moved into shop for sale, retaining original owner."""
    __tablename__ = 'shop_inventory_items'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey('cards.id'), nullable=False, index=True)
    from_user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    source_inventory_item_id: Mapped[int] = mapped_column(Integer, ForeignKey('inventory_items.id'), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    # Denormalized owner username for quick display/exports
    owner: Mapped[str] = mapped_column(String(80), nullable=True)

    # Relationships
    card = relationship('Card')
    from_user = relationship('User', foreign_keys=[from_user_id])
    source_item = relationship('InventoryItem', foreign_keys=[source_inventory_item_id])

    def __str__(self) -> str:
        return f"ShopStock: {self.card.name if self.card else self.card_id} x{self.quantity} (from {self.from_user.username if self.from_user else self.from_user_id})"


class ShopConsignmentLog(db.Model):
    """History of items sent to or returned from shop (consignment)."""
    __tablename__ = 'shop_consignment_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey('cards.id'), nullable=False, index=True)
    from_user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    source_inventory_item_id: Mapped[int] = mapped_column(Integer, ForeignKey('inventory_items.id'), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # 'list' or 'unlist'
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    card = relationship('Card')
    from_user = relationship('User', foreign_keys=[from_user_id])
    source_item = relationship('InventoryItem', foreign_keys=[source_inventory_item_id])

class CreditLedger(db.Model):
    """Balanced ledger for credit issuance, transfers, and redemptions."""
    __tablename__ = 'credit_ledger'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False)
    entry_ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # 'debit' or 'credit'
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # 'issue','redeem','transfer_in','transfer_out','revoke','adjust'
    related_order_id: Mapped[int] = mapped_column(Integer, nullable=True)
    related_inventory_item_id: Mapped[int] = mapped_column(Integer, ForeignKey('inventory_items.id'), nullable=True)
    admin_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=True, unique=False)
    notes: Mapped[str] = mapped_column(Text, nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    admin = relationship("User", foreign_keys=[admin_id])
    inventory_item = relationship("InventoryItem", foreign_keys=[related_inventory_item_id])

    __table_args__ = (
        CheckConstraint('amount_vnd > 0', name='chk_credit_amount_positive'),
        CheckConstraint("direction in ('debit','credit')", name='chk_credit_direction'),
        CheckConstraint("kind in ('issue','redeem','transfer_in','transfer_out','revoke','adjust')", name='chk_credit_kind'),
        Index('ix_credit_ledger_user_ts', 'user_id', 'entry_ts'),
        Index('ux_credit_ledger_idem', 'idempotency_key', unique=True, postgresql_where=db.text('idempotency_key is not null')),
    )


class IdempotencyKey(db.Model):
    """Simple DB-backed idempotency key registry to prevent replay across operations."""
    __tablename__ = 'idempotency_keys'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    # Optional fields to aid debugging
    scope: Mapped[str] = mapped_column(String(100), nullable=True)
    request_fingerprint: Mapped[str] = mapped_column(String(255), nullable=True)


class TradeOffer(db.Model):
    """Trade offer between users"""
    __tablename__ = "trade_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False)
    receiver_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')
    message: Mapped[str] = mapped_column(Text, nullable=True)
    counter_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Relationships
    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])
    offered_items = relationship("TradeItem", foreign_keys="TradeItem.trade_offer_id",
                                cascade="all, delete-orphan")

    def __str__(self) -> str:
        """String representation of trade offer"""
        return f"TradeOffer: {self.sender.username} → {self.receiver.username} ({self.status})"


class TradeItem(db.Model):
    """Individual item in a trade offer"""
    __tablename__ = "trade_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_offer_id: Mapped[int] = mapped_column(Integer, ForeignKey('trade_offers.id'), nullable=False)
    inventory_item_id: Mapped[int] = mapped_column(Integer, ForeignKey('inventory_items.id'), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    item_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'offered' or 'requested'

    # Relationships
    trade_offer = relationship("TradeOffer", back_populates="offered_items")
    inventory_item = relationship("InventoryItem")

    def __str__(self) -> str:
        """String representation of trade item"""
        return f"TradeItem: {self.item_type} - {self.inventory_item.card.name if self.inventory_item and self.inventory_item.card else 'Unknown Card'} x{self.quantity}"


# Enhanced Cart Models for Mixed Inventory Support

class CartSession(db.Model):
    """Shopping cart session for users"""
    __tablename__ = "cart_sessions"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User")
    items = relationship("CartItem", backref="session", lazy=True, cascade="all, delete-orphan")

    def __str__(self) -> str:
        """String representation of cart session"""
        return f"CartSession: {self.id} ({self.user.username if self.user else 'Anonymous'})"


class CartItem(db.Model):
    """Individual item in shopping cart (supports both admin and user inventory)"""
    __tablename__ = "cart_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(255), ForeignKey('cart_sessions.id'), nullable=False)
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey('cards.id'), nullable=True)  # For admin items
    inventory_item_id: Mapped[int] = mapped_column(Integer, ForeignKey('inventory_items.id'), nullable=True)  # For user items
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    card = relationship("Card")  # For admin items
    inventory_item = relationship("InventoryItem")  # For user items

    @property
    def item_type(self):
        """Returns 'admin' or 'user' based on which item is set"""
        if self.card_id:
            return 'admin'
        elif self.inventory_item_id:
            return 'user'
        return None

    @property
    def seller_info(self):
        """Returns seller information for display"""
        if self.item_type == 'admin':
            return {'type': 'admin', 'name': 'Lotus TCG Store'}
        elif self.item_type == 'user' and self.inventory_item:
            seller = self.inventory_item.inventory.user
            return {
                'type': 'user',
                'name': seller.username,
                'user_id': seller.id
            }
        return None

    @property
    def display_price(self):
        """Returns the price to display (admin price or user market price)"""
        if self.item_type == 'admin' and self.card:
            return self.card.price
        elif self.item_type == 'user' and self.inventory_item:
            return self.inventory_item.card.price if self.inventory_item.card else 0
        return 0

    @property
    def available_quantity(self):
        """Returns available quantity based on item type"""
        if self.item_type == 'admin' and self.card:
            return self.card.quantity
        elif self.item_type == 'user' and self.inventory_item:
            return self.inventory_item.quantity
        return 0

    @property
    def item_total(self):
        """Returns the total price for this cart item (price * quantity)"""
        return float(self.display_price * self.quantity)

    def to_dict(self):
        """Convert cart item to dictionary for templates"""
        base_dict = {
            'id': self.id,
            'session_id': self.session_id,
            'quantity': self.quantity,
            'item_type': self.item_type,
            'seller_info': self.seller_info,
            'display_price': float(self.display_price),
            'available_quantity': self.available_quantity,
            'added_at': self.added_at.isoformat() if self.added_at else None
        }

        if self.item_type == 'admin' and self.card:
            base_dict['card'] = self.card.to_dict()
            base_dict['item_total'] = float(self.card.price * self.quantity)
        elif self.item_type == 'user' and self.inventory_item:
            base_dict['inventory_item'] = {
                'id': self.inventory_item.id,
                'condition': self.inventory_item.condition,
                'market_price': float(self.inventory_item.card.price if self.inventory_item.card else 0)
            }
            base_dict['card'] = self.inventory_item.card.to_dict() if self.inventory_item.card else None
            base_dict['item_total'] = float((self.inventory_item.card.price if self.inventory_item.card else 0) * self.quantity)

        return base_dict

    def __str__(self) -> str:
        """String representation of cart item"""
        if self.item_type == 'admin' and self.card:
            return f"CartItem: {self.card.name} x{self.quantity} (Store)"
        elif self.item_type == 'user' and self.inventory_item:
            seller_name = self.inventory_item.inventory.user.username if self.inventory_item.inventory else 'Unknown'
            card_name = self.inventory_item.card.name if self.inventory_item.card else 'Unknown Card'
            return f"CartItem: {card_name} x{self.quantity} (from {seller_name})"
        return f"CartItem: Unknown x{self.quantity}"


# Coupon System Models

class Coupon(db.Model):
    """Discount coupon for orders"""
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)  # Coupon code (e.g., SAVE10)
    discount_percentage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)  # Discount percentage (0-100)
    description: Mapped[str] = mapped_column(String(255), nullable=True)  # Optional description
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # Start date for validity
    valid_until: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # End date for validity
    usage_limit: Mapped[int] = mapped_column(Integer, nullable=True)  # Maximum number of uses (None = unlimited)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Current usage count
    is_active: Mapped[bool] = mapped_column(db.Boolean, default=True, nullable=False)  # Whether coupon is active
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def is_valid(self) -> bool:
        """Check if coupon is currently valid"""
        if not self.is_active:
            return False

        now = datetime.utcnow()

        # Check date validity
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False

        # Check usage limit
        if self.usage_limit is not None and self.usage_count >= self.usage_limit:
            return False

        return True

    def can_be_used(self) -> bool:
        """Check if coupon can still be used (considering usage limit)"""
        if self.usage_limit is None:
            return True
        return self.usage_count < self.usage_limit

    def increment_usage(self):
        """Increment usage count"""
        self.usage_count += 1
        self.updated_at = datetime.utcnow()

    def calculate_discount(self, amount: float) -> float:
        """Calculate discount amount for given total"""
        if not self.is_valid():
            return 0.0
        return amount * (self.discount_percentage / 100.0)

    def to_dict(self):
        """Convert coupon to dictionary for API responses"""
        return {
            'id': self.id,
            'code': self.code,
            'discount_percentage': float(self.discount_percentage),
            'description': self.description,
            'valid_from': self.valid_from.isoformat() if self.valid_from else None,
            'valid_until': self.valid_until.isoformat() if self.valid_until else None,
            'usage_limit': self.usage_limit,
            'usage_count': self.usage_count,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_valid': self.is_valid(),
            'can_be_used': self.can_be_used()
        }

    def __str__(self) -> str:
        """String representation of coupon"""
        return f"Coupon: {self.code} ({self.discount_percentage}% off)"


# User Management Audit Models

class UserAuditLog(db.Model):
    """Audit log for all user-related admin actions"""
    __tablename__ = "user_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False)
    admin_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # 'suspend', 'ban', 'verify', etc.
    details: Mapped[str] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    admin = relationship("User", foreign_keys=[admin_id])

    @staticmethod
    def create_log(user_id, admin_id, action, details=None, ip_address=None, user_agent=None):
        """Create a new audit log entry"""
        try:
            audit_log = UserAuditLog(
                user_id=user_id,
                admin_id=admin_id,
                action=action,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent
            )
            db.session.add(audit_log)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error creating audit log: {e}")

    def __str__(self) -> str:
        """String representation of audit log"""
        return f"AuditLog: {self.admin.username} {self.action} {self.user.username}"


class VerificationAuditLog(db.Model):
    """Detailed audit log for card verification actions"""
    __tablename__ = "verification_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(Integer, ForeignKey('inventory_items.id'), nullable=False)
    admin_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # 'approve', 'reject', 'flag'
    previous_status: Mapped[bool] = mapped_column(db.Boolean, nullable=True)
    new_status: Mapped[bool] = mapped_column(db.Boolean, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    inventory_item = relationship("InventoryItem")
    admin = relationship("User")

    @staticmethod
    def create_log(inventory_item_id, admin_id, action, previous_status=None, new_status=None, notes=None, ip_address=None, user_agent=None):
        """Create a new verification audit log entry"""
        try:
            # Convert string status values to boolean for database storage
            def status_to_bool(status):
                if status == 'verified':
                    return True
                elif status == 'unverified':
                    return False
                elif status == 'pending':
                    return None
                else:
                    return None  # Unknown status

            audit_log = VerificationAuditLog(
                inventory_item_id=inventory_item_id,
                admin_id=admin_id,
                action=action,
                previous_status=status_to_bool(previous_status),
                new_status=status_to_bool(new_status),
                notes=notes,
                ip_address=ip_address
            )
            db.session.add(audit_log)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error creating verification audit log: {e}")

    def __str__(self) -> str:
        """String representation of verification audit log"""
        return f"VerificationLog: {self.admin.username} {self.action} item {self.inventory_item_id}"


class InventoryTransferLog(db.Model):
    """Audit log for item transfers between users (credit and non-credit)."""
    __tablename__ = 'inventory_transfer_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    to_user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey('cards.id'), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    is_credit: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    from_user = relationship('User', foreign_keys=[from_user_id])
    to_user = relationship('User', foreign_keys=[to_user_id])
    card = relationship('Card')

    def to_dict(self):
        return {
            'id': self.id,
            'from_user_id': self.from_user_id,
            'to_user_id': self.to_user_id,
            'from_username': self.from_user.username if self.from_user else None,
            'to_username': self.to_user.username if self.to_user else None,
            'card_id': self.card_id,
            'card_name': self.card.name if self.card else None,
            'card_set': self.card.set_name if self.card else None,
            'quantity': self.quantity,
            'is_credit': self.is_credit,
            'idempotency_key': self.idempotency_key,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

def initialize_default_users():
    """Initialize default admin and test users if they don't exist"""
    try:
        # Check if admin user exists - use raw SQL to avoid column issues during migration
        result = db.session.execute(db.text("SELECT id, role FROM users WHERE username = 'admin'")).first()
        if not result:
            admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
            admin_hash = generate_password_hash(admin_password)
            # Use raw SQL to insert to avoid column mapping issues
            db.session.execute(db.text("""
                INSERT INTO users (username, password_hash, role, account_status, two_factor_enabled)
                VALUES (:username, :password_hash, :role, :account_status, :two_factor_enabled)
            """), {
                'username': 'admin',
                'password_hash': admin_hash,
                'role': 'super_admin',
                'account_status': 'active',
                'two_factor_enabled': False
            })
        elif result and result[1] != 'super_admin':
            # Update existing admin user to super_admin role
            db.session.execute(db.text("""
                UPDATE users SET role = 'super_admin' WHERE username = 'admin'
            """))

        # Check if test user exists
        result = db.session.execute(db.text("SELECT id FROM users WHERE username = 'user'")).first()
        if not result:
            user_hash = generate_password_hash('user123')
            db.session.execute(db.text("""
                INSERT INTO users (username, password_hash, role, account_status, two_factor_enabled)
                VALUES (:username, :password_hash, :role, :account_status, :two_factor_enabled)
            """), {
                'username': 'user',
                'password_hash': user_hash,
                'role': 'user',
                'account_status': 'active',
                'two_factor_enabled': False
            })

            # Create default inventory for test user
            user_inventory = UserInventory(user_id=db.session.execute(db.text("SELECT id FROM users WHERE username = 'user'")).first()[0], is_public=True)
            db.session.add(user_inventory)

        # Commit changes
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error initializing users: {e}")
