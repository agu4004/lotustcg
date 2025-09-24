import os
import json
import time
import logging
from contextlib import contextmanager
from typing import List, Optional, Dict, Any, Tuple

from sqlalchemy import select, func
from sqlalchemy.exc import OperationalError, DBAPIError
from sqlalchemy.orm import joinedload

from app import db
from models import User, Card, InventoryItem, UserInventory, CreditLedger, IdempotencyKey, InventoryTransferLog

logger = logging.getLogger(__name__)


# Feature flags (read once at import; tests can monkeypatch env then reload module if needed)
FEAT_ISSUE = os.environ.get('FEAT_CREDIT_ISSUE', os.environ.get('feat.credit.issue', '1')) != '0'
FEAT_TRANSFER = os.environ.get('FEAT_CREDIT_TRANSFER', os.environ.get('feat.credit.transfer', '1')) != '0'
FEAT_REDEEM = os.environ.get('FEAT_CREDIT_REDEEM', os.environ.get('feat.credit.redeem', '1')) != '0'


class ServiceError(Exception):
    def __init__(self, code: str, message: str, http: int = 400, extra: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.http = http
        self.extra = extra or {}


def _to_vnd_int(value) -> int:
    try:
        # Allow Decimal/float/int; enforce non-negative integer
        iv = int(value)
        if iv < 0:
            raise ValueError()
        return iv
    except Exception:
        raise ServiceError('INVALID_AMOUNT', 'Amount must be non-negative integer VND')


def _require_admin(user: User):
    if not user or not user.is_admin():
        raise ServiceError('FORBIDDEN', 'Admin privileges required', http=403)


def _check_idempotency(idem_key: Optional[str], scope: str) -> None:
    if not idem_key:
        return
    # Use a separate table to enforce uniqueness across dialects
    existing = IdempotencyKey.query.filter_by(key=idem_key).first()
    if existing:
        raise ServiceError('IDEMPOTENT_REPLAY', 'Duplicate idempotency key', http=409)
    entry = IdempotencyKey(key=idem_key, scope=scope)
    db.session.add(entry)


@contextmanager
def _txn(retries: int = 3, request_id: Optional[str] = None):
    attempt = 0
    while True:
        try:
            yield
            db.session.commit()
            break
        except (OperationalError, DBAPIError) as e:
            db.session.rollback()
            is_retryable = False
            msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            # Basic detection for serialization/deadlock
            for token in ['deadlock detected', 'could not serialize', 'serialization failure', 'deadlock', 'timeout']:
                if token in msg.lower():
                    is_retryable = True
                    break
            if attempt < retries and is_retryable:
                backoff = 0.05 * (2 ** attempt)
                logger.warning({
                    'event': 'txn_retry', 'attempt': attempt + 1, 'backoff_sec': backoff, 'error': msg, 'request_id': request_id
                })
                time.sleep(backoff)
                attempt += 1
                continue
            raise
        except Exception:
            db.session.rollback()
            raise


def get_or_create_credit_card(denomination_vnd: int) -> Card:
    denom = _to_vnd_int(denomination_vnd)
    # CREDIT canonical attributes
    token_map = {1000: 'Copper Token', 10000: 'Silver Token', 100000: 'Gold Token'}
    base_label = token_map.get(denom, None)
    name = f"{base_label} ({denom} VND)" if base_label else f"Store Credit {denom} VND"
    rarity = 'Token'
    foiling = 'NF'
    art_style = 'normal'
    q = Card.query.filter_by(set_name='CREDIT', price=denom, foiling=foiling, rarity=rarity, art_style=art_style)
    card = q.first()
    if card:
        # Keep canonical name in sync with token naming
        if card.name != name:
            card.name = name
        return card
    card = Card(
        name=name,
        set_name='CREDIT',
        rarity=rarity,
        condition='Near Mint',
        price=denom,  # treat as integer VND
        quantity=0,
        description='Store credit denomination',
        foiling=foiling,
        art_style=art_style,
        
    )
    db.session.add(card)
    db.session.flush()  # get id
    return card


def _locked_user_inventory(user_id: int) -> UserInventory:
    inv = UserInventory.query.filter_by(user_id=user_id).with_for_update().first()
    if inv:
        return inv
    inv = UserInventory(user_id=user_id, is_public=True)
    db.session.add(inv)
    db.session.flush()
    return inv


def _locked_merge_inventory_item(user_id: int, card_id: int) -> InventoryItem:
    inv = _locked_user_inventory(user_id)
    item = (
        InventoryItem.query.options(joinedload(InventoryItem.card))
        .filter_by(inventory_id=inv.id, card_id=card_id)
        .with_for_update()
        .first()
    )
    if item:
        return item
    item = InventoryItem(inventory_id=inv.id, card_id=card_id, quantity=0, verification_status='verified', is_verified=True)
    db.session.add(item)
    db.session.flush()
    return item


def issue_credits(admin_user: User, to_user_id: int, denomination_vnd: int, units: int = 1, idempotency_key: Optional[str] = None, notes: Optional[str] = None) -> Dict[str, Any]:
    if not FEAT_ISSUE:
        raise ServiceError('FEATURE_DISABLED', 'Credit issuing disabled', http=403)
    _require_admin(admin_user)
    if units <= 0:
        raise ServiceError('INVALID_QUANTITY', 'Units must be positive integer')

    with _txn(request_id=None):
        _check_idempotency(idempotency_key, scope='credit_issue')
        user = User.query.get(to_user_id)
        if not user:
            raise ServiceError('USER_NOT_FOUND', 'Recipient user not found', http=404)

        card = get_or_create_credit_card(denomination_vnd)
        item = _locked_merge_inventory_item(user.id, card.id)
        item.quantity += units

        total_vnd = int(card.price) * units
        # ledger entry per operation
        ledger = CreditLedger(
            user_id=user.id,
            amount_vnd=total_vnd,
            direction='credit',
            kind='issue',
            admin_id=admin_user.id,
            idempotency_key=idempotency_key,
            notes=notes
        )
        _safe_add_ledger(ledger)

        return {
            'user_id': user.id,
            'card_id': card.id,
            'denomination_vnd': int(card.price),
            'units_issued': units,
            'total_vnd': total_vnd,
            'inventory_item_id': item.id
        }


def transfer_item(from_user_id: int, to_user_id: int, inventory_item_id: int, quantity: int, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
    if not FEAT_TRANSFER:
        raise ServiceError('FEATURE_DISABLED', 'Credit transfer disabled', http=403)
    if quantity <= 0:
        raise ServiceError('INVALID_QUANTITY', 'Quantity must be positive integer')
    if from_user_id == to_user_id:
        raise ServiceError('INVALID_TRANSFER', 'Cannot transfer to self')

    with _txn(request_id=None):
        _check_idempotency(idempotency_key, scope='inventory_transfer')
        # Validate recipient exists before locking/creating inventories
        recipient = User.query.get(to_user_id)
        if not recipient:
            raise ServiceError('USER_NOT_FOUND', 'Recipient user not found', http=404)

        # Deterministic lock order: lock lower user_id first
        first_uid, second_uid = sorted([from_user_id, to_user_id])
        # Lock inventories
        _locked_user_inventory(first_uid)
        _locked_user_inventory(second_uid)

        src_item = InventoryItem.query.options(joinedload(InventoryItem.card)).filter_by(id=inventory_item_id).with_for_update().first()
        if not src_item:
            raise ServiceError('ITEM_NOT_FOUND', 'Inventory item not found', http=404)
        if not src_item.inventory or src_item.inventory.user_id != from_user_id:
            raise ServiceError('FORBIDDEN', 'Source item not owned by sender', http=403)

        card = src_item.card
        if not card:
            raise ServiceError('CARD_NOT_FOUND', 'Associated card not found', http=404)

        if card.set_name == 'CREDIT':
            if src_item.quantity < quantity:
                raise ServiceError('INSUFFICIENT_QUANTITY', 'Not enough credit units to transfer', http=409)
            src_item.quantity -= quantity
            dst_item = _locked_merge_inventory_item(to_user_id, card.id)
            dst_item.quantity += quantity

            vnd = int(card.price) * quantity
            _safe_add_ledger(CreditLedger(user_id=from_user_id, amount_vnd=vnd, direction='debit', kind='transfer_out', idempotency_key=idempotency_key))
            _safe_add_ledger(CreditLedger(user_id=to_user_id, amount_vnd=vnd, direction='credit', kind='transfer_in', idempotency_key=idempotency_key))
        else:
            # Normal items require verification
            # Block transfer if the item is currently listed for sale to avoid shop inconsistency
            if getattr(src_item, 'listed_for_sale', False):
                raise ServiceError('ITEM_LISTED', 'Item is currently listed for sale', http=409)
            if not src_item.is_verified or src_item.verification_status != 'verified':
                raise ServiceError('NOT_VERIFIED', 'Item must be verified before transfer', http=400)
            if src_item.quantity < quantity:
                raise ServiceError('INSUFFICIENT_QUANTITY', 'Not enough quantity to transfer', http=409)
            src_item.quantity -= quantity
            dst_item = _locked_merge_inventory_item(to_user_id, card.id)
            dst_item.quantity += quantity
            # Preserve verification status for the recipient item
            dst_item.verification_status = src_item.verification_status
            dst_item.is_verified = src_item.is_verified
            # Carry over verification metadata when available
            try:
                if src_item.is_verified:
                    dst_item.verified_at = src_item.verified_at
                    dst_item.verified_by = src_item.verified_by
            except Exception:
                pass

        # Record transfer log (both credit and non-credit)
        try:
            db.session.add(InventoryTransferLog(
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                card_id=card.id,
                quantity=quantity,
                is_credit=(card.set_name == 'CREDIT'),
                idempotency_key=idempotency_key
            ))
        except Exception:
            # Non-fatal if logging fails; transaction continues
            logger.warning({'event': 'transfer_log_failed'})

        return {
            'from_user_id': from_user_id,
            'to_user_id': to_user_id,
            'card_id': card.id,
            'transferred_quantity': quantity,
            'is_credit': (card.set_name == 'CREDIT')
        }


def _lock_credit_items_for_user(user_id: int) -> List[InventoryItem]:
    # Order by denomination desc, id asc as required
    inv = _locked_user_inventory(user_id)
    items = (
        db.session.query(InventoryItem)
        .join(Card, Card.id == InventoryItem.card_id)
        .options(joinedload(InventoryItem.card))
        .filter(InventoryItem.inventory_id == inv.id, InventoryItem.quantity > 0, Card.set_name == 'CREDIT')
        .order_by(Card.price.desc(), InventoryItem.id.asc())
        .with_for_update()
        .all()
    )
    return items


def apply_credits(user_id: int, amount_due_vnd: int, mode: str = 'auto', breakdown: Optional[List[Dict[str, int]]] = None, idempotency_key: Optional[str] = None, related_order_id: Optional[int] = None, preview: bool = False) -> Dict[str, Any]:
    if not FEAT_REDEEM:
        raise ServiceError('FEATURE_DISABLED', 'Credit redeem disabled', http=403)
    remaining = _to_vnd_int(amount_due_vnd)
    applied: List[Dict[str, Any]] = []

    def do_compute(items: List[InventoryItem]):
        nonlocal remaining, applied

        def consume(item: InventoryItem, units: int) -> int:
            nonlocal remaining
            if units <= 0:
                return 0
            denom = int(item.card.price)
            max_units = min(item.quantity, remaining // denom)
            use_units = min(units, max_units)
            if use_units <= 0:
                return 0
            vnd = denom * use_units
            applied.append({'card_id': item.card_id, 'units': use_units, 'vnd': vnd, 'denomination': denom, 'inventory_item_id': item.id})
            remaining -= vnd
            if not preview:
                item.quantity -= use_units
                _safe_add_ledger(CreditLedger(
                    user_id=user_id,
                    amount_vnd=vnd,
                    direction='debit',
                    kind='redeem',
                    related_order_id=related_order_id,
                    related_inventory_item_id=item.id,
                    idempotency_key=(f"{idempotency_key}:{item.card_id}" if idempotency_key else None)
                ))
            return use_units

        if mode == 'manual' and breakdown:
            index = {it.card_id: it for it in items}
            for row in breakdown:
                card_id = int(row.get('card_id'))
                units = int(row.get('units', 0))
                it = index.get(card_id)
                if it:
                    consume(it, units)
        else:
            for it in items:
                denom = int(it.card.price)
                max_units = remaining // denom
                if max_units > 0:
                    consume(it, max_units)
                if remaining == 0:
                    break

    if preview:
        # Preview path: do not lock for update, do not write, only compute
        inv = UserInventory.query.filter_by(user_id=user_id).first()
        if not inv:
            return {'credits_applied_vnd': 0, 'remaining_vnd': remaining, 'applied_breakdown': []}
        items = (
            db.session.query(InventoryItem)
            .join(Card, Card.id == InventoryItem.card_id)
            .options(joinedload(InventoryItem.card))
            .filter(InventoryItem.inventory_id == inv.id, InventoryItem.quantity > 0, Card.set_name == 'CREDIT')
            .order_by(Card.price.desc(), InventoryItem.id.asc())
            .all()
        )
        do_compute(items)
        discount = _to_vnd_int(amount_due_vnd) - remaining
        return {'credits_applied_vnd': discount, 'remaining_vnd': remaining, 'applied_breakdown': applied}
    else:
        with _txn(request_id=None):
            _check_idempotency(idempotency_key, scope='credit_redeem')
            items = _lock_credit_items_for_user(user_id)
            do_compute(items)
            discount = _to_vnd_int(amount_due_vnd) - remaining
            return {'credits_applied_vnd': discount, 'remaining_vnd': remaining, 'applied_breakdown': applied}


def _safe_add_ledger(entry: CreditLedger) -> None:
    """Add a ledger row and work around SQLite PK autoincrement issues when table was created without proper autoincrement.
    If inserting fails due to NULL id, assign next id manually and try again.
    """
    dialect = db.session.get_bind().dialect.name
    if dialect == 'sqlite' and getattr(entry, 'id', None) is None:
        # proactively assign id for sqlite to avoid NOT NULL on PK when RETURNING is used
        next_id = db.session.execute(db.text('SELECT COALESCE(MAX(id), 0) + 1 FROM credit_ledger')).scalar() or 1
        entry.id = int(next_id)
    db.session.add(entry)
    db.session.flush()
