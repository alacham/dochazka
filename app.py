# Import necessary libraries
from flask import Flask, render_template, request, redirect, url_for, g, make_response
from flask_httpauth import HTTPBasicAuth
import sqlite3
from datetime import datetime, timedelta
import pytz # Library to handle timezones
import csv
import io

# --- Configuration ---

import os
try:
    # Try to import local config file
    from config import USERNAME, PASSWORD, DATABASE_PATH, TIMEZONE_NAME, SECRET_KEY, DEBUG as CONFIG_DEBUG, PORT, HOST
    DATABASE = os.getenv('DATABASE', DATABASE_PATH)
    TIMEZONE = pytz.timezone(TIMEZONE_NAME)
    APP_PORT = int(os.getenv('PORT', PORT))
    APP_HOST = os.getenv('HOST', HOST)
except ImportError:
    # Fallback to environment variables or defaults
    USERNAME = os.getenv('ATTENDANCE_USERNAME', 'admin')
    PASSWORD = os.getenv('ATTENDANCE_PASSWORD', 'password')
    DATABASE = os.getenv('DATABASE', 'attendance.db')
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

# This function defines the simple authentication logic
@auth.verify_password
def verify_password(username, password):
    """Verifies the provided username and password."""
    if username == USERNAME and password == PASSWORD:
        return username
    return None

# --- Database Functions ---

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

@app.route('/')
@auth.login_required # This decorator protects the route
def home():
    """
    Home Page: Displays a list of active employees.
    """
    db = get_db()
    # Fetch all ACTIVE employees from the database
    employees = db.execute(
        'SELECT id, name FROM employees WHERE is_active = 1 ORDER BY name'
    ).fetchall()
    
    return render_template('home.html', employees=employees, current_user=auth.current_user())

@app.route('/action/<string:employee_name>')
@auth.login_required
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
@auth.login_required
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
    
    # Redirect back to home page after successful action
    return redirect(url_for('home'))

@app.route('/admin')
@auth.login_required
def admin_page():
    """
    Admin Page: For viewing reports and managing employees.
    """
    db = get_db()
    
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    employee_filter = request.args.get('employee_filter', '')
    show_daily_hours = request.args.get('show_daily_hours') == '1'
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
    
    # Fetch all employees for management and filter dropdown
    all_employees = db.execute(
        'SELECT id, name, is_active FROM employees ORDER BY name'
    ).fetchall()
    
    return render_template('admin.html',
                         attendance_records=attendance_records,
                         daily_hours_data=daily_hours_data,
                         all_employees=all_employees,
                         start_date=start_date,
                         end_date=end_date,
                         employee_filter=employee_filter,
                         show_daily_hours=show_daily_hours,
                         message=message)

@app.route('/add_employee', methods=['POST'])
@auth.login_required
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
@auth.login_required
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
@auth.login_required
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
@auth.login_required
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
