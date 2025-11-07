import os
from app import app, db
from credit_service import get_or_create_credit_card


def main():
    denoms = [1000, 10000, 100000]
    with app.app_context():
        for d in denoms:
            card = get_or_create_credit_card(d)
            print(f"Ensured CREDIT card: id={card.id} denom={int(card.price)} name={card.name}")
        db.session.commit()


if __name__ == '__main__':
    main()
