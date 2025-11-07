import sys
from typing import Tuple

from app import app, db
from models import UserInventory, InventoryItem, Card
from credit_service import get_or_create_credit_card


NEW_DENOMS = [100000, 10000, 1000]  # greedy order
ALLOWED_SET = set(NEW_DENOMS)


def _merge_inventory_item(inv_id: int, card_id: int, add_units: int) -> InventoryItem:
    item = (
        db.session.query(InventoryItem)
        .filter(InventoryItem.inventory_id == inv_id, InventoryItem.card_id == card_id)
        .with_for_update(of=InventoryItem)
        .first()
    )
    if item:
        item.quantity += add_units
        return item
    item = InventoryItem(
        inventory_id=inv_id,
        card_id=card_id,
        quantity=add_units,
        verification_status='verified',
        is_verified=True,
    )
    db.session.add(item)
    return item


def convert_inventory(inv: UserInventory) -> Tuple[int, int]:
    """Convert legacy CREDIT denominations (e.g., 50k/200k) into 1k/10k/100k.
    Returns (legacy_units, new_units_created_total).
    """
    legacy_items = (
        db.session.query(InventoryItem)
        .join(Card, Card.id == InventoryItem.card_id)
        .filter(
            InventoryItem.inventory_id == inv.id,
            Card.set_name == 'CREDIT',
        )
        .with_for_update(of=InventoryItem)
        .all()
    )

    total_legacy_vnd = 0
    legacy_units = 0
    for it in legacy_items:
        denom = int(it.card.price)
        if denom in ALLOWED_SET:
            continue  # already new-format
        if it.quantity <= 0:
            continue
        total_legacy_vnd += denom * it.quantity
        legacy_units += it.quantity
        it.quantity = 0  # zero out legacy units

    if total_legacy_vnd == 0:
        return (legacy_units, 0)

    # Allocate to new denominations greedily
    remaining = total_legacy_vnd
    new_units_created = 0
    for d in NEW_DENOMS:
        if remaining <= 0:
            break
        units = remaining // d
        if units <= 0:
            continue
        card = get_or_create_credit_card(d)
        _merge_inventory_item(inv.id, card.id, int(units))
        new_units_created += int(units)
        remaining -= int(units) * d

    if remaining != 0:
        # Should not happen if legacy amounts are multiples of 1000
        print(f"[WARN] Non-zero remainder {remaining} VND for inventory {inv.id}")

    return (legacy_units, new_units_created)


def main():
    count_inventories = 0
    total_legacy_units = 0
    total_new_units = 0
    with app.app_context():
        inventories = db.session.query(UserInventory).all()
        for inv in inventories:
            count_inventories += 1
            legacy_units, new_units = convert_inventory(inv)
            total_legacy_units += legacy_units
            total_new_units += new_units
        db.session.commit()

    print(f"Converted {total_legacy_units} legacy units into {total_new_units} new units across {count_inventories} inventories.")


if __name__ == '__main__':
    main()

