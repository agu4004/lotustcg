import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from sqlalchemy.orm import DeclarativeBase, load_only
from werkzeug.middleware.proxy_fix import ProxyFix

# Set up logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

# Initialize extensions
db = SQLAlchemy(model_class=Base)
migrate = Migrate()
login_manager = LoginManager()

# Create the app
app = Flask(__name__, static_folder='static', template_folder='templates', static_url_path='/static')

# Configuration
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize extensions with app
db.init_app(app)
migrate.init_app(app, db)

# Flask-Login setup
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# Proxy fix for Replit deployments
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Import model classes
from models import (
    User, Card, Order, OrderItem,
    UserInventory, InventoryItem, TradeOffer, TradeItem,
    CartSession, CartItem, CreditLedger, IdempotencyKey
)

# Inject feature flags into templates
@app.context_processor
def inject_feature_flags():
    def _truthy(v):
        if v is None:
            return True
        return str(v).lower() not in ('0', 'false', 'off', 'no', '')

    return dict(
        feat_credit_issue=_truthy(os.environ.get('FEAT_CREDIT_ISSUE', os.environ.get('feat.credit.issue', '1'))),
        feat_credit_transfer=_truthy(os.environ.get('FEAT_CREDIT_TRANSFER', os.environ.get('feat.credit.transfer', '1'))),
        feat_credit_redeem=_truthy(os.environ.get('FEAT_CREDIT_REDEEM', os.environ.get('feat.credit.redeem', '1'))),
    )

# User loader callback
@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception:
        # Fallback: select only base columns to avoid errors if new columns not migrated yet
        try:
            return (
                User.query.options(
                    load_only(
                        User.id,
                        User.username,
                        User.email,
                        User.password_hash,
                        User.role,
                        User.created_at,
                        User.account_status,
                    )
                ).get(int(user_id))
            )
        except Exception:
            return None

# Create tables and seed data
with app.app_context():
    db.create_all()
    # Initialize default users if they don't exist
    from models import initialize_default_users
    initialize_default_users()

# Import routes after app setup
import routes
