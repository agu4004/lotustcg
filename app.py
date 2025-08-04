import os
import logging
from flask import Flask
from flask_login import LoginManager

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # type: ignore
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# User loader callback
@login_manager.user_loader
def load_user(user_id):
    from models import user_manager
    return user_manager.get_user(user_id)

# Import routes after app creation to avoid circular imports
from routes import *
