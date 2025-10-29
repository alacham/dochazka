#!/usr/bin/env python3
"""
Generate a secure secret key for the Flask application.
Usage: python generate_secret_key.py
"""

import secrets

if __name__ == "__main__":
    secret_key = secrets.token_hex(32)
    print("Generated SECRET_KEY:")
    print(secret_key)
    print("\nAdd this to your config.py or .env file:")
    print(f'SECRET_KEY = "{secret_key}"')
    print("or")
    print(f'SECRET_KEY={secret_key}')