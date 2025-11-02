# Import necessary libraries
from flask import Flask, render_template, request, redirect, url_for, g, make_response, session
from flask_httpauth import HTTPBasicAuth
import sqlite3
from datetime import datetime, timedelta
import pytz # Library to handle timezones
import csv
import io
import secrets
import hashlib
from functools import wraps
import requests
import threading
import json

# --- Configuration ---

import os
try:
    # Try to import local config file
    from config import USERNAME, PASSWORD, DATABASE_PATH, TIMEZONE_NAME, SECRET_KEY, DEBUG as CONFIG_DEBUG, PORT, HOST,\
        TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    DATABASE = os.getenv('DATABASE', DATABASE_PATH)
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', TELEGRAM_BOT_TOKEN)
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID)
    TIMEZONE = pytz.timezone(TIMEZONE_NAME)
    APP_PORT = int(os.getenv('PORT', PORT))
    APP_HOST = os.getenv('HOST', HOST)
except ImportError:
    # Fallback to environment variables or defaults
    USERNAME = os.getenv('ATTENDANCE_USERNAME', 'admin')
    PASSWORD = os.getenv('ATTENDANCE_PASSWORD', 'password')
    DATABASE = os.getenv('DATABASE', 'attendance.db')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
    TIMEZONE = pytz.timezone(os.getenv('TIMEZONE', 'Europe/Prague'))
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    CONFIG_DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    APP_PORT = int(os.getenv('PORT', '5000'))
    APP_HOST = os.getenv('HOST', '127.0.0.1')


# --- Application Setup ---

app = Flask(__name__)
app.secret_key = SECRET_KEY
auth = HTTPBasicAuth()

# --- Security ---

# This function defines the simple authentication logic (kept for compatibility)
@auth.verify_password
def verify_password(username, password):
    """Verifies the provided username and password."""
    if username == USERNAME and password == PASSWORD:
        return username
    return None

# --- Token-based Authentication ---

def generate_auth_token():
    """Generate a secure random token for authentication."""
    return secrets.token_urlsafe(32)

def hash_token(token):
    """Create a hash of the token for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()

def create_auth_token():
    """Create and store a new authentication token."""
    token = generate_auth_token()
    token_hash = hash_token(token)
    
    # Store token in database with expiration (e.g., 365 days)
    db = get_db()
    expiry_date = datetime.now(TIMEZONE) + timedelta(days=365)
    
    # Initialize auth_tokens table if it doesn't exist
    db.execute('''CREATE TABLE IF NOT EXISTS auth_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_hash TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        is_active INTEGER DEFAULT 1
    )''')
    
    db.execute(
        'INSERT INTO auth_tokens (token_hash, created_at, expires_at) VALUES (?, ?, ?)',
        (token_hash, datetime.now(TIMEZONE).isoformat(), expiry_date.isoformat())
    )
    db.commit()
    
    return token

def validate_auth_token(token):
    """Validate if the provided token is valid and not expired."""
    if not token:
        return False
    
    token_hash = hash_token(token)
    db = get_db()
    
    # Check if token exists and is not expired
    result = db.execute('''
        SELECT id FROM auth_tokens 
        WHERE token_hash = ? AND is_active = 1 AND datetime(expires_at) > datetime(?)
    ''', (token_hash, datetime.now(TIMEZONE).isoformat())).fetchone()
    
    return result is not None

def invalidate_all_tokens():
    """Invalidate all authentication tokens (for logout all)."""
    db = get_db()
    db.execute('UPDATE auth_tokens SET is_active = 0')
    db.commit()

def login_required(f):
    """Custom decorator to check for valid authentication token in cookies."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for auth token in cookies
        auth_token = request.cookies.get('auth_token')
        
        if not auth_token or not validate_auth_token(auth_token):
            # Redirect to login page if not authenticated
            return redirect(url_for('login_page'))
        
        return f(*args, **kwargs)
    return decorated_function

# --- Telegram Notifications ---

def _send_telegram_message_async(employee_name, action, timestamp):
    """Internal function to send Telegram message in background thread."""
    try:
        # Format timestamp
        dt = datetime.strptime(f"{timestamp['date']} {timestamp['time']}", "%Y-%m-%d %H:%M:%S")
        formatted_time = dt.strftime("%d.%m.%Y %H:%M")
        
        # Create message
        action_text = "příchod" if action == "in" else "odchod"
        message = f"{employee_name}:\n {formatted_time} - {action_text}"
        
        # Send to Telegram
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }
        
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            pass
        else:
            print(f"Failed to send Telegram notification: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"Error sending Telegram notification: {e}")

def send_telegram_notification(employee_name, action, timestamp):
    """Send notification to Telegram group asynchronously if token and chat ID are configured."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return  # Skip if Telegram is not configured
    
    # Start background thread for Telegram notification
    telegram_thread = threading.Thread(
        target=_send_telegram_message_async,
        args=(employee_name, action, timestamp),
        daemon=True  # Thread will die when main program exits
    )
    telegram_thread.start()

# --- Database Functions ---

def calculate_entry_exit_pairs(records):
    """
    Calculate entry-exit pairs with quarter-hour logic and carry-over.
    Returns list of dictionaries with paired entries/exits and accumulated minutes.
    """
    from collections import defaultdict
    
    # Group records by employee
    employee_data = defaultdict(list)
    
    for record in records:
        employee_data[record['employee_name']].append(record)
    
    result = []
    
    for employee_name, emp_records in employee_data.items():
        # Sort by timestamp
        emp_records.sort(key=lambda x: (x['date'], x['time']))
        
        accumulated_minutes = 0  # Running total for quarter-hour logic
        i = 0
        
        # Process each Enter record and look for matching Exit on the same day
        processed_exits = set()  # Track which exit records we've already used
        
        for i, record in enumerate(emp_records):
            if record['status'] == 'Enter':
                entry_record = record
                exit_record = None
                
                # Look for matching exit on the same day that hasn't been used yet
                for j in range(i + 1, len(emp_records)):
                    if (emp_records[j]['status'] == 'Leave' and 
                        emp_records[j]['date'] == entry_record['date'] and
                        j not in processed_exits):
                        exit_record = emp_records[j]
                        processed_exits.add(j)  # Mark this exit as used
                        break
                    elif emp_records[j]['date'] != entry_record['date']:
                        # Different date - stop looking for exits on this day
                        break
                
                if exit_record:
                    # Calculate worked minutes
                    entry_time = datetime.strptime(f"{entry_record['date']} {entry_record['time']}", '%Y-%m-%d %H:%M:%S')
                    exit_time = datetime.strptime(f"{exit_record['date']} {exit_record['time']}", '%Y-%m-%d %H:%M:%S')
                    
                    worked_minutes = int((exit_time - entry_time).total_seconds() / 60)
                    
                    # Apply quarter-hour logic with accumulation
                    total_minutes = worked_minutes + accumulated_minutes
                    
                    # Round to nearest quarter
                    remainder = total_minutes % 15
                    if remainder <= 7:
                        rounded_minutes = total_minutes - remainder
                    else:
                        rounded_minutes = total_minutes + (15 - remainder)
                    
                    # Ensure non-negative
                    rounded_minutes = max(0, rounded_minutes)
                    
                    # Update accumulated difference for next pair
                    accumulated_minutes = total_minutes - rounded_minutes
                    
                    # Format hours
                    actual_hours = worked_minutes // 60
                    actual_mins = worked_minutes % 60
                    actual_time_str = f"{actual_hours}:{actual_mins:02d}"
                    
                    quarter_hours = rounded_minutes // 60
                    quarter_mins = rounded_minutes % 60
                    quarter_time_str = f"{quarter_hours}:{quarter_mins:02d}"
                    
                    result.append({
                        'employee_name': employee_name,
                        'entry_date': entry_record['date'],
                        'entry_time': entry_record['time'],
                        'exit_date': exit_record['date'],
                        'exit_time': exit_record['time'],
                        'actual_hours': actual_time_str,
                        'quarter_hours': quarter_time_str,
                        'carry_over_minutes': accumulated_minutes
                    })
                else:
                    # No matching exit found - show entry with missing exit
                    result.append({
                        'employee_name': employee_name,
                        'entry_date': entry_record['date'],
                        'entry_time': entry_record['time'],
                        'exit_date': '-',
                        'exit_time': '-',
                        'actual_hours': '-',
                        'quarter_hours': '-',
                        'carry_over_minutes': accumulated_minutes
                    })
    
    return result

def calculate_daily_hours_with_quarters(records):
    """
    Calculate daily worked hours with quarter-hour rounding logic.
    Returns list of dictionaries with employee data including quarter-hour adjustments.
    """
    from collections import defaultdict
    
    # Group records by employee
    employee_data = defaultdict(list)
    
    for record in records:
        employee_data[record['employee_name']].append(record)
    
    # Calculate hours for each employee
    result = []
    
    for employee_name, emp_records in employee_data.items():
        # Group by date for this employee
        daily_records = defaultdict(list)
        for record in emp_records:
            daily_records[record['date']].append(record)
        
        # Sort dates to process in chronological order
        sorted_dates = sorted(daily_records.keys())
        accumulated_minutes = 0  # Running total of minute differences
        
        for i, date in enumerate(sorted_dates):
            day_records = daily_records[date]
            day_records.sort(key=lambda x: x['time'])
            
            # Calculate worked hours for this day
            total_minutes = 0
            enter_time = None
            
            for record in day_records:
                time_obj = datetime.strptime(record['time'], '%H:%M:%S').time()
                minutes_since_midnight = time_obj.hour * 60 + time_obj.minute
                
                if record['status'] == 'Enter':
                    enter_time = minutes_since_midnight
                elif record['status'] == 'Leave' and enter_time is not None:
                    total_minutes += minutes_since_midnight - enter_time
                    enter_time = None
            
            # Convert to hours and minutes
            hours = total_minutes // 60
            minutes = total_minutes % 60
            actual_hours = f"{hours}:{minutes:02d}"
            
            # Apply quarter-hour logic
            is_last_day = (i == len(sorted_dates) - 1)
            
            if is_last_day:
                # Last day - apply accumulated difference but don't round
                final_minutes = total_minutes + accumulated_minutes
                # Ensure non-negative result
                final_minutes = max(0, final_minutes)
                final_hours = final_minutes // 60
                final_mins = final_minutes % 60
                quarter_hours = f"{final_hours}:{final_mins:02d}"
            else:
                # Not last day - round to nearest quarter
                adjusted_minutes = total_minutes + accumulated_minutes
                
                # Round to nearest quarter (0, 15, 30, 45)
                remainder = adjusted_minutes % 15
                if remainder <= 7:
                    rounded_minutes = adjusted_minutes - remainder
                else:
                    rounded_minutes = adjusted_minutes + (15 - remainder)
                
                # Ensure non-negative
                rounded_minutes = max(0, rounded_minutes)
                
                # Update accumulated difference for next day
                accumulated_minutes = adjusted_minutes - rounded_minutes
                
                # Format quarter hours
                q_hours = rounded_minutes // 60
                q_mins = rounded_minutes % 60
                quarter_hours = f"{q_hours}:{q_mins:02d}"
            
            result.append({
                'employee_name': employee_name,
                'date': date,
                'actual_hours': actual_hours,
                'quarter_hours': quarter_hours
            })
    
    # Sort by employee name, then by date
    result.sort(key=lambda x: (x['employee_name'], x['date']))
    return result

def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        # Using a Row factory makes it easier to work with results (access columns by name)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    """Closes the database again at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

# You will need a one-time function to initialize the database schema
def init_db():
    """Initializes the database with the required tables."""
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
    print("Databáze byla inicializována.")

# --- Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    """Login page with form authentication."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember_me = request.form.get('remember_me') == '1'
        
        # Verify credentials
        if username == USERNAME and password == PASSWORD:
            # Create auth token
            token = create_auth_token()
            
            # Redirect to home page
            response = make_response(redirect(url_for('home')))
            
            # Set cookie with long expiration if remember_me is checked
            if remember_me:
                # 1 year expiration
                response.set_cookie('auth_token', token, max_age=365*24*60*60, httponly=True, secure=False)
            else:
                # Session cookie (until browser closes)
                response.set_cookie('auth_token', token, httponly=True, secure=False)
            
            return response
        else:
            # Invalid credentials
            return render_template('login.html', 
                                 error_message="Nesprávné uživatelské jméno nebo heslo.",
                                 username=username)
    
    # GET request - show login form
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout route - clears the auth token cookie."""
    response = make_response(redirect(url_for('login_page')))
    response.set_cookie('auth_token', '', expires=0)
    return response

@app.route('/logout-all')
@login_required
def logout_all():
    """Logout from all devices - invalidates all tokens."""
    invalidate_all_tokens()
    response = make_response(redirect(url_for('login_page')))
    response.set_cookie('auth_token', '', expires=0)
    return response

@app.route('/')
@login_required # Using new token-based decorator
def home():
    """
    Home Page: Displays a list of active employees.
    """
    db = get_db()
    # Fetch all ACTIVE employees from the database
    employees = db.execute(
        'SELECT id, name FROM employees WHERE is_active = 1 ORDER BY name'
    ).fetchall()
    
    return render_template('home.html', employees=employees, current_user=USERNAME)

@app.route('/action/<string:employee_name>')
@login_required
def action_page(employee_name):
    """
    Action Page: Shows 'Enter' or 'Leave' button for a specific employee.
    """
    db = get_db()
    
    # Get employee ID and verify the employee exists and is active
    employee = db.execute(
        'SELECT id, name FROM employees WHERE name = ? AND is_active = 1', 
        (employee_name,)
    ).fetchone()
    
    if not employee:
        return redirect(url_for('home'))
    
    # Check the last status of this employee today
    today = datetime.now(TIMEZONE).date()
    last_record = db.execute(
        'SELECT status FROM attendance WHERE employee_id = ? AND date(timestamp) = ? ORDER BY timestamp DESC LIMIT 1',
        (employee['id'], today)
    ).fetchone()
    
    # Determine next action
    if last_record is None or last_record['status'] == 'Leave':
        next_action = 'Enter'
    else:
        next_action = 'Leave'

    return render_template('action.html', 
                         employee_name=employee_name, 
                         next_action=next_action)

@app.route('/record/<string:employee_name>', methods=['POST'])
@login_required
def record_action(employee_name):
    """
    Records the attendance action (Enter/Leave) for an employee.
    """
    db = get_db()
    
    # Get employee ID
    employee = db.execute(
        'SELECT id FROM employees WHERE name = ? AND is_active = 1', 
        (employee_name,)
    ).fetchone()
    
    if not employee:
        return redirect(url_for('home'))
    
    action = request.form.get('action')
    if action not in ['Enter', 'Leave']:
        return redirect(url_for('action_page', employee_name=employee_name))
    
    # Record the action with Prague timezone
    now = datetime.now(TIMEZONE)
    timestamp = now.isoformat()
    
    db.execute(
        'INSERT INTO attendance (employee_id, status, timestamp) VALUES (?, ?, ?)',
        (employee['id'], action, timestamp)
    )
    db.commit()
    
    # Send Telegram notification if configured
    telegram_action = "in" if action == "Enter" else "out"
    send_telegram_notification(
        employee_name,
        telegram_action,
        {'date': now.strftime('%Y-%m-%d'), 'time': now.strftime('%H:%M:%S')}
    )
    
    # Redirect back to home page after successful action
    return redirect(url_for('home'))

@app.route('/admin')
@login_required
def admin_page():
    """
    Admin Page: For viewing reports and managing employees.
    """
    db = get_db()
    
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    employee_filter = request.args.get('employee_filter', '')
    view_type = request.args.get('view_type', 'basic')  # basic, daily_hours, entry_exit_pairs
    show_daily_hours = view_type == 'daily_hours'
    show_entry_exit_pairs = view_type == 'entry_exit_pairs'
    message = request.args.get('message')
    
    # Default to previous month if no dates provided
    if not start_date or not end_date:
        today = datetime.now(TIMEZONE).date()
        # Get first day of previous month
        first_of_current_month = today.replace(day=1)
        last_month = first_of_current_month - timedelta(days=1)
        start_date = last_month.replace(day=1).strftime('%Y-%m-%d')
        end_date = last_month.strftime('%Y-%m-%d')
    
    # Fetch attendance records with filters
    query = '''
        SELECT e.name as employee_name, a.status, 
               date(a.timestamp) as date, 
               time(a.timestamp) as time
        FROM attendance a 
        JOIN employees e ON a.employee_id = e.id 
        WHERE date(a.timestamp) >= ? AND date(a.timestamp) <= ?
    '''
    params = [start_date, end_date]
    
    if employee_filter:
        query += ' AND e.name = ?'
        params.append(employee_filter)
    
    query += ' ORDER BY a.timestamp DESC'
    
    attendance_records = db.execute(query, params).fetchall()
    
    # Calculate daily hours data if requested
    daily_hours_data = None
    if show_daily_hours and attendance_records:
        daily_hours_data = calculate_daily_hours_with_quarters(attendance_records)
    
    # Calculate entry-exit pairs if requested
    pairs_data = None
    if show_entry_exit_pairs and attendance_records:
        pairs_data = calculate_entry_exit_pairs(attendance_records)
    
    # Fetch all employees for management and filter dropdown
    all_employees = db.execute(
        'SELECT id, name, is_active FROM employees ORDER BY name'
    ).fetchall()
    
    return render_template('admin.html',
                         attendance_records=attendance_records,
                         daily_hours_data=daily_hours_data,
                         pairs_data=pairs_data,
                         all_employees=all_employees,
                         start_date=start_date,
                         end_date=end_date,
                         employee_filter=employee_filter,
                         view_type=view_type,
                         show_daily_hours=show_daily_hours,
                         show_entry_exit_pairs=show_entry_exit_pairs,
                         message=message)

@app.route('/add_employee', methods=['POST'])
@login_required
def add_employee():
    """
    Adds a new employee to the database.
    """
    db = get_db()
    employee_name = request.form.get('employee_name', '').strip()
    
    if not employee_name:
        return redirect(url_for('admin_page'))
    
    try:
        db.execute(
            'INSERT INTO employees (name, is_active) VALUES (?, 1)',
            (employee_name,)
        )
        db.commit()
        message = f"Zaměstnanec '{employee_name}' byl úspěšně přidán!"
    except sqlite3.IntegrityError:
        message = f"Zaměstnanec '{employee_name}' již existuje!"
    
    # Redirect back to admin with message
    return redirect(url_for('admin_page') + f'?message={message}')

@app.route('/toggle_employee/<int:employee_id>', methods=['POST'])
@login_required
def toggle_employee(employee_id):
    """
    Toggles employee active/inactive status.
    """
    db = get_db()
    action = request.form.get('action')
    
    if action == 'disable':
        new_status = 0
        status_text = 'deaktivován'
    elif action == 'enable':
        new_status = 1
        status_text = 'aktivován'
    else:
        return redirect(url_for('admin_page'))
    
    # Get employee name for message
    employee = db.execute('SELECT name FROM employees WHERE id = ?', (employee_id,)).fetchone()
    
    if employee:
        db.execute(
            'UPDATE employees SET is_active = ? WHERE id = ?',
            (new_status, employee_id)
        )
        db.commit()
        message = f"Zaměstnanec '{employee['name']}' byl úspěšně {status_text}!"
    else:
        message = "Zaměstnanec nebyl nalezen!"
    
    return redirect(url_for('admin_page') + f'?message={message}')

@app.route('/export_csv')
@login_required
def export_csv():
    """
    Exports attendance records to CSV based on filters.
    """
    db = get_db()
    
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    employee_filter = request.args.get('employee_filter', '')
    
    # Build query with same logic as admin page
    query = '''
        SELECT e.name as employee_name, a.status, 
               date(a.timestamp) as date, 
               time(a.timestamp) as time
        FROM attendance a 
        JOIN employees e ON a.employee_id = e.id 
        WHERE date(a.timestamp) >= ? AND date(a.timestamp) <= ?
    '''
    params = [start_date, end_date]
    
    if employee_filter:
        query += ' AND e.name = ?'
        params.append(employee_filter)
    
    query += ' ORDER BY a.timestamp'
    
    records = db.execute(query, params).fetchall()
    
    # Create CSV content
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Jméno zaměstnance', 'Stav (Příchod/Odchod)', 'Datum', 'Čas'])
    
    # Write data
    for record in records:
        status_czech = 'Příchod' if record['status'] == 'Enter' else 'Odchod'
        writer.writerow([record['employee_name'], status_czech, record['date'], record['time']])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=dochazka_report_{start_date}_do_{end_date}.csv'
    
    return response

@app.route('/export_quarters_csv')
@login_required
def export_quarters_csv():
    """
    Exports attendance data with quarter-hour calculations to CSV.
    """
    db = get_db()
    
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    employee_filter = request.args.get('employee_filter', '')
    
    # Build query to get attendance records
    query = '''
        SELECT e.name as employee_name, a.status, 
               date(a.timestamp) as date, 
               time(a.timestamp) as time
        FROM attendance a 
        JOIN employees e ON a.employee_id = e.id 
        WHERE date(a.timestamp) >= ? AND date(a.timestamp) <= ?
    '''
    params = [start_date, end_date]
    
    if employee_filter:
        query += ' AND e.name = ?'
        params.append(employee_filter)
    
    query += ' ORDER BY e.name, a.timestamp'
    
    records = db.execute(query, params).fetchall()
    
    # Calculate daily hours with quarter-hour logic
    daily_hours = calculate_daily_hours_with_quarters(records)
    
    # Create CSV content
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Jméno', 'Datum', 'Počet odpracovaných hodin', 'Počet na čtvrthodiny'])
    
    # Write data
    for record in daily_hours:
        writer.writerow([
            record['employee_name'], 
            record['date'], 
            record['actual_hours'], 
            record['quarter_hours']
        ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=dochazka_ctvrthod_{start_date}_do_{end_date}.csv'
    
    return response

@app.route('/export_pairs_csv')
@login_required
def export_pairs_csv():
    """
    Exports entry-exit pairs with quarter-hour calculations to CSV.
    """
    db = get_db()
    
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    employee_filter = request.args.get('employee_filter', '')
    
    # Build query to get attendance records
    query = '''
        SELECT e.name as employee_name, a.status, 
               date(a.timestamp) as date, 
               time(a.timestamp) as time
        FROM attendance a 
        JOIN employees e ON a.employee_id = e.id 
        WHERE date(a.timestamp) >= ? AND date(a.timestamp) <= ?
    '''
    params = [start_date, end_date]
    
    if employee_filter:
        query += ' AND e.name = ?'
        params.append(employee_filter)
    
    query += ' ORDER BY e.name, a.timestamp'
    
    records = db.execute(query, params).fetchall()
    
    # Calculate entry-exit pairs
    pairs = calculate_entry_exit_pairs(records)
    
    # Create CSV content
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Jméno', 
        'Datum a čas příchodu', 
        'Datum a čas odchodu', 
        'Přesný počet hodin', 
        'Přenos minut do dalšího',
        'Počet hodin na čtvrthodiny',
    ])
    
    # Write data
    for pair in pairs:
        # Format entry datetime
        if pair['entry_date'] != '-' and pair['entry_time'] != '-':
            entry_datetime = f"{pair['entry_date']} {pair['entry_time']}"
        else:
            entry_datetime = '-'
        
        # Format exit datetime
        if pair['exit_date'] != '-' and pair['exit_time'] != '-':
            exit_datetime = f"{pair['exit_date']} {pair['exit_time']}"
        else:
            exit_datetime = '-'
        
        writer.writerow([
            pair['employee_name'],
            entry_datetime,
            exit_datetime,
            pair['actual_hours'],
            f"{pair['carry_over_minutes']} min" if pair['carry_over_minutes'] != 0 else "0 min",
            pair['quarter_hours'],
        ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=dochazka_pary_{start_date}_do_{end_date}.csv'
    
    return response

# --- Main Execution ---

if __name__ == '__main__':
    # Check if running in Docker or production
    is_production = os.getenv('FLASK_ENV') == 'production'
    
    if is_production:
        # Production settings for Docker - use environment variables for host/port
        app.run(host=APP_HOST, port=APP_PORT, debug=False)
    else:
        # Development settings - use config file settings
        app.run(host=APP_HOST, port=APP_PORT, debug=CONFIG_DEBUG)
