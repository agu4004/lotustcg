"""
Authentication decorators and utilities
"""
from functools import wraps
from flask import redirect, url_for, flash, request
from flask_login import current_user, login_required


def admin_required(f):
    """Decorator to require admin role for access"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


def guest_or_user_required(f):
    """Decorator that allows both guests and authenticated users"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function


def get_redirect_target():
    """Get the URL to redirect to after login"""
    for target in request.values.get('next'), request.referrer:
        if not target:
            continue
        # Basic security check - ensure redirect is relative
        if target.startswith('/') and not target.startswith('//'):
            return target
    return None