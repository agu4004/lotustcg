"""
Database-backed storage for TCG cards using SQLAlchemy
"""
import csv
import io
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy import or_, and_
from app import db
# storage_db.py (thêm ở đầu file)
import re

def _norm_header(s: str) -> str:
    if s is None: return ""
    s = s.replace("\ufeff", "")   # remove BOM nếu có
    s = s.strip().lower()
    return re.sub(r"\s+", "_", s) # "Image URL" -> "image_url"

logger = logging.getLogger(__name__)

_IMAGE_URL_KEYS = {"image_url", "image", "img_url", "imageurl", "thumbnail", "thumb_url"}

class DatabaseStorage:
    """Database-backed storage for cards"""
    
    def add_card(self, card_data: Dict[str, Any]) -> str:
        """Add a card to the database and return its ID"""
        # Import Card here to avoid circular imports
        from models import Card
        
        try:
            # Create new card instance
            card = Card(
                name=card_data.get('name', 'Unknown Card'),
                set_name=card_data.get('set_name', 'Unknown'),
                rarity=card_data.get('rarity', 'Common'),
                condition=card_data.get('condition', 'Near Mint'),
                price=float(card_data.get('price', 0.0)),
                quantity=int(card_data.get('quantity', 0)),
                description=card_data.get('description', ''),
                image_url=card_data.get('image_url', ''),
                foiling=card_data.get('foiling', 'NF'),
                art_style=card_data.get('art_style', 'normal')
            )
            
            db.session.add(card)
            db.session.commit()
            
            logger.debug(f"Added card: {card.name} (ID: {card.id})")
            return str(card.id)
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding card: {e}")
            raise
    
    def get_card(self, card_id: str) -> Optional[Dict[str, Any]]:
        """Get a card by ID"""
        from models import Card
        try:
            card = Card.query.get(int(card_id))
            return card.to_dict() if card else None
        except (ValueError, TypeError):
            return None
    
    def get_all_cards(self) -> List[Dict[str, Any]]:
        """Get all non-deleted cards"""
        from models import Card
        cards = Card.query.filter(Card.is_deleted == False).all()
        return [card.to_dict() for card in cards]
    
    def search_cards(self, query: str = "", set_filter: str = "", rarity_filter: str = "", 
                    min_price: Optional[float] = None, max_price: Optional[float] = None) -> List[Dict[str, Any]]:
        """Search cards with filters"""
        from models import Card
        # Start with base query
        card_query = Card.query
        
        # Apply filters
        filters = []
        
        # Text search
        if query:
            filters.append(Card.name.ilike(f'%{query}%'))
        
        # Set filter
        if set_filter:
            filters.append(Card.set_name == set_filter)
        
        # Rarity filter
        if rarity_filter:
            filters.append(Card.rarity == rarity_filter)
        
        # Price range filters
        if min_price is not None:
            filters.append(Card.price >= min_price)
        if max_price is not None:
            filters.append(Card.price <= max_price)
        
        # Apply all filters
        if filters:
            card_query = card_query.filter(and_(*filters))

        # Always filter out deleted cards
        card_query = card_query.filter(Card.is_deleted == False)

        cards = card_query.all()
        return [card.to_dict() for card in cards]
    
    def get_unique_sets(self) -> List[str]:
        """Get unique set names from non-deleted cards"""
        from models import Card
        result = db.session.query(Card.set_name).filter(Card.is_deleted == False).distinct().all()
        return [row[0] for row in result if row[0]]

    def get_unique_rarities(self) -> List[str]:
        """Get unique rarities from non-deleted cards"""
        from models import Card
        result = db.session.query(Card.rarity).filter(Card.is_deleted == False).distinct().all()
        return [row[0] for row in result if row[0]]
    
    def update_card_quantity(self, card_id: str, new_quantity: int) -> bool:
        """Update card quantity"""
        from models import Card
        try:
            card = Card.query.get(int(card_id))
            if card:
                card.quantity = new_quantity
                db.session.commit()
                return True
            return False
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating card quantity: {e}")
            return False

    def find_existing_card(self, name: str, set_name: str, rarity: str, condition: str,
                          foiling: str, art_style: str) -> Optional[Dict[str, Any]]:
        """Find existing non-deleted card by matching criteria"""
        from models import Card
        try:
            card = Card.query.filter(
                Card.name == name,
                Card.set_name == set_name,
                Card.rarity == rarity,
                Card.condition == condition,
                Card.foiling == foiling,
                Card.art_style == art_style,
                Card.is_deleted == False
            ).first()

            return card.to_dict() if card else None
        except Exception as e:
            logger.error(f"Error finding existing card: {e}")
            return None

    def soft_delete_card(self, card_id: str) -> bool:
        """Soft delete a card by marking it as deleted"""
        from models import Card
        try:
            card = Card.query.get(int(card_id))
            if card and not card.is_deleted:
                card.soft_delete()
                db.session.commit()
                logger.debug(f"Soft deleted card: {card.name} (ID: {card_id})")
                return True
            return False
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error soft deleting card: {e}")
            return False

    def update_existing_card_quantity(self, card_id: str, additional_quantity: int,
                                     card_data: Optional[Dict[str, Any]] = None) -> bool:
        """Update existing card by adding to current quantity and optionally updating other fields"""
        from models import Card
        try:
            card = Card.query.get(int(card_id))
            if card:
                # Update quantity
                card.quantity += additional_quantity

                # Update other fields if provided and different
                if card_data:
                    if 'price' in card_data and card_data['price'] != float(card.price):
                        card.price = card_data['price']
                        logger.debug(f"Updated price for {card.name}: {card.price}")

                    if 'description' in card_data and card_data['description'] != (card.description or ''):
                        card.description = card_data['description']
                        logger.debug(f"Updated description for {card.name}")

                    if 'image_url' in card_data and card_data['image_url'] != (card.image_url or ''):
                        card.image_url = card_data['image_url']
                        logger.debug(f"Updated image_url for {card.name}")

                db.session.commit()
                logger.debug(f"Updated card: {card.name} (ID: {card.id}) - Added {additional_quantity}, Total: {card.quantity}")
                return True
            return False
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating existing card: {e}")
            return False
    
    def clear_all_cards(self):
        """Soft delete all cards from storage"""
        from models import Card
        try:
            # Soft delete all non-deleted cards
            cards_to_delete = Card.query.filter(Card.is_deleted == False).all()
            for card in cards_to_delete:
                card.soft_delete()

            db.session.commit()
            logger.info(f"Soft deleted {len(cards_to_delete)} cards from database")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error soft deleting cards: {e}")
            raise
    
    def process_csv_upload(self, csv_content: str) -> Dict[str, Any]:
        """Process CSV upload and return results"""
        results = {'success': 0, 'created': 0, 'updated': 0, 'errors': [], 'total': 0}
        
        if not csv_content.strip():
            results['errors'].append('Empty CSV content')
            return results
        
        try:
            csv_file = io.StringIO(csv_content)
            reader = csv.DictReader(csv_file)
            
            # Check if CSV has headers
            if not reader.fieldnames:
                results['errors'].append('CSV must have headers')
                return results
            
            row_num = 1  # Start from 1 for header
            for row in reader:
                row_num += 1
                results['total'] += 1
                
                try:
                    # Validate required fields
                    name = row.get('name', '').strip()
                    if not name:
                        results['errors'].append(f'Row {row_num}: missing card name')
                        continue
                    
                    # Parse price
                    try:
                        price = float(row.get('price', 0))
                    except (ValueError, TypeError):
                        results['errors'].append(f'Row {row_num}: invalid price "{row.get("price", "")}"')
                        continue
                    
                    # Parse quantity
                    try:
                        quantity = int(row.get('quantity', 0))
                    except (ValueError, TypeError):
                        results['errors'].append(f'Row {row_num}: invalid quantity "{row.get("quantity", "")}"')
                        
                    image_url = None
                    for k in _IMAGE_URL_KEYS:
                        if row.get(k):
                            image_url = row[k]
                            break
                    
                    # Create card data
                    card_data = {
                        'name': name,
                        'set_name': row.get('set_name', 'Unknown').strip(),
                        'rarity': row.get('rarity', 'Common').strip(),
                        'condition': row.get('condition', 'Near Mint').strip(),
                        'price': price,
                        'quantity': quantity,
                        'description': row.get('description', '').strip(),
                        'image_url': image_url or '',
                        'foiling': row.get('foiling', 'NF').strip(),
                        'art_style': row.get('art_style', 'normal').strip()
                    }

                    # Check if card already exists
                    existing_card = self.find_existing_card(
                        name=card_data['name'],
                        set_name=card_data['set_name'],
                        rarity=card_data['rarity'],
                        condition=card_data['condition'],
                        foiling=card_data['foiling'],
                        art_style=card_data['art_style']
                    )

                    if existing_card:
                        # Update existing card quantity and other fields if provided
                        success = self.update_existing_card_quantity(existing_card['id'], quantity, card_data)
                        if success:
                            results['success'] += 1
                            results['updated'] += 1
                            logger.debug(f"Updated existing card: {name} - Added {quantity} to existing quantity")
                        else:
                            results['errors'].append(f'Row {row_num}: failed to update existing card')
                    else:
                        # Add new card to database
                        self.add_card(card_data)
                        results['success'] += 1
                        results['created'] += 1
                    
                except Exception as e:
                    results['errors'].append(f'Row {row_num}: {str(e)}')
                    continue
            
        except Exception as e:
            results['errors'].append(f'CSV parsing error: {str(e)}')
        
        return results


# Global storage instance
storage = DatabaseStorage()