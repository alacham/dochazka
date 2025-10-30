# Configuration file for Attendance System
# Copy this file to config.py and modify the values

# Authentication credentials
USERNAME = "admin"
PASSWORD = "password"

# Database settings
DATABASE_PATH = "attendance.db"

# Timezone setting (Prague timezone)
TIMEZONE_NAME = "Europe/Prague"

# Flask settings
DEBUG = True
SECRET_KEY = "your-secret-key-change-this-in-production"
PORT = 5000
HOST = "127.0.0.1"  # Use "0.0.0.0" for Docker or external access