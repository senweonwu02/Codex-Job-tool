"""
Authentication system for Career Coach application.
Handles user registration, login, session management, and usage tracking.
"""

from flask import jsonify
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import database as db


class User(UserMixin):
    """User class for Flask-Login integration."""

    def __init__(self, user_id, email):
        self.id = user_id
        self.email = email


def register_user(email: str, password: str) -> dict:
    """
    Register a new user.

    Args:
        email: User email address
        password: Plain text password (will be hashed)

    Returns:
        Dict with user_id and message

    Raises:
        ValueError: If email already exists
    """
    # Check if user already exists
    existing_user = db.get_user_by_email(email)
    if existing_user:
        raise ValueError("Email already registered")

    # Hash password
    password_hash = generate_password_hash(password)

    # Create user
    user_id = db.create_user(email, password_hash)

    # Initialize user settings
    db.create_user_settings(user_id)

    return {"user_id": user_id, "email": email}


def verify_user(email: str, password: str) -> dict:
    """
    Verify user credentials.

    Args:
        email: User email
        password: Plain text password

    Returns:
        Dict with user_id and email if valid

    Raises:
        ValueError: If credentials invalid
    """
    user = db.get_user_by_email(email)

    if not user or not check_password_hash(user['password_hash'], password):
        raise ValueError("Invalid email or password")

    return {"user_id": user['id'], "email": user['email']}


def get_user_info(user_id: int) -> dict:
    """Get user information."""
    user = db.get_user_by_id(user_id)
    if not user:
        raise ValueError("User not found")

    return {
        "id": user['id'],
        "email": user['email'],
        "created_at": user['created_at']
    }


def get_usage_info(user_id: int) -> dict:
    """
    Get current month API usage for user.

    Args:
        user_id: User ID

    Returns:
        Dict with usage count, limit, and remaining
    """
    current_month = datetime.now().strftime("%Y-%m")
    count = db.get_api_usage_count(user_id, current_month)
    limit = 25

    return {
        "used": count,
        "limit": limit,
        "remaining": max(0, limit - count),
        "month": current_month
    }


def check_api_quota(f):
    """
    Decorator to check if user has exceeded API quota.
    Returns 429 if limit reached.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask_login import current_user

        if not current_user.is_authenticated:
            return jsonify({"error": "Unauthorized"}), 401

        current_month = datetime.now().strftime("%Y-%m")
        count = db.get_api_usage_count(current_user.id, current_month)

        if count >= 25:
            return jsonify({
                "error": "Monthly API limit (25) exceeded",
                "usage": get_usage_info(current_user.id)
            }), 429

        return f(*args, **kwargs)

    return decorated_function


def record_api_usage(user_id: int, endpoint: str, tokens_used: int = None):
    """Record API call usage."""
    db.add_api_usage(user_id, endpoint, tokens_used)
