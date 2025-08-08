"""
Database-backed storage for TCG cards using SQLAlchemy
"""
import csv
import io
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy import or_, and_
from app import db

logger = logging.getLogger(__name__)


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
                image_url=card_data.get('image_url', '')
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
        """Get all cards"""
        from models import Card
        cards = Card.query.all()
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
        
        cards = card_query.all()
        return [card.to_dict() for card in cards]
    
    def get_unique_sets(self) -> List[str]:
        """Get unique set names"""
        from models import Card
        result = db.session.query(Card.set_name).distinct().all()
        return [row[0] for row in result if row[0]]
    
    def get_unique_rarities(self) -> List[str]:
        """Get unique rarities"""
        from models import Card
        result = db.session.query(Card.rarity).distinct().all()
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
    
    def clear_all_cards(self):
        """Clear all cards from storage"""
        from models import Card
        try:
            Card.query.delete()
            db.session.commit()
            logger.info("Cleared all cards from database")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error clearing cards: {e}")
            raise
    
    def process_csv_upload(self, csv_content: str) -> Dict[str, Any]:
        """Process CSV upload and return results"""
        results = {'success': 0, 'errors': [], 'total': 0}
        
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
                        continue
                    
                    # Create card data
                    card_data = {
                        'name': name,
                        'set_name': row.get('set_name', 'Unknown').strip(),
                        'rarity': row.get('rarity', 'Common').strip(),
                        'condition': row.get('condition', 'Near Mint').strip(),
                        'price': price,
                        'quantity': quantity,
                        'description': row.get('description', '').strip()
                    }
                    
                    # Add card to database
                    self.add_card(card_data)
                    results['success'] += 1
                    
                except Exception as e:
                    results['errors'].append(f'Row {row_num}: {str(e)}')
                    continue
            
        except Exception as e:
            results['errors'].append(f'CSV parsing error: {str(e)}')
        
        return results


# Global storage instance
storage = DatabaseStorage()