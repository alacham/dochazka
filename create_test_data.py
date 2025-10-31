#!/usr/bin/env python3
"""
Skript pro vytvoření testovacích dat pro systém docházky.
Vytvoří různé scénáře pro testování exportu párů příchod-odchod.
"""

import sqlite3
from datetime import datetime, timedelta
import pytz

# Konfigurace
DATABASE = 'data/attendance.db'
TIMEZONE = pytz.timezone('Europe/Prague')

def create_test_data():
    """Vytvoří testovací data s různými scénáři."""
    
    # Připojení k databázi
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    print("Vytvářím testovací data...")
    
    # 1. Přidání testovacích zaměstnanců
    employees = [
        "Jan Novák",
        "Marie Svobodová", 
        "Pavel Dvořák"
    ]
    
    for name in employees:
        try:
            cursor.execute('INSERT INTO employees (name, is_active) VALUES (?, 1)', (name,))
            print(f"✓ Přidán zaměstnanec: {name}")
        except sqlite3.IntegrityError:
            print(f"- Zaměstnanec {name} již existuje")
    
    conn.commit()
    
    # Získání ID zaměstnanců
    emp_ids = {}
    for name in employees:
        result = cursor.execute('SELECT id FROM employees WHERE name = ?', (name,)).fetchone()
        if result:
            emp_ids[name] = result[0]
    
    # 2. Vytvoření testovacích záznamů docházky
    base_date = datetime.now(TIMEZONE).date() - timedelta(days=7)  # Před týdnem
    
    # Scénář 1: Jan Novák - normální pracovní dny s různými časy
    jan_id = emp_ids["Jan Novák"]
    test_records = [
        # Den 1: 8:05 - 16:25 (8:20 hodin, má se zaokrouhlit na 8:15)
        (jan_id, 'Enter', (base_date + timedelta(days=0)).strftime('%Y-%m-%d') + ' 08:05:00'),
        (jan_id, 'Leave', (base_date + timedelta(days=0)).strftime('%Y-%m-%d') + ' 16:25:00'),
        
        # Den 2: 7:58 - 16:12 (8:14 hodin, má se zaokrouhlit na 8:15 s přenosem z předchozího dne)
        (jan_id, 'Enter', (base_date + timedelta(days=1)).strftime('%Y-%m-%d') + ' 07:58:00'),
        (jan_id, 'Leave', (base_date + timedelta(days=1)).strftime('%Y-%m-%d') + ' 16:12:00'),
        
        # Den 3: 8:00 - 16:30 (8:30 hodin)
        (jan_id, 'Enter', (base_date + timedelta(days=2)).strftime('%Y-%m-%d') + ' 08:00:00'),
        (jan_id, 'Leave', (base_date + timedelta(days=2)).strftime('%Y-%m-%d') + ' 16:30:00'),
    ]
    
    # Scénář 2: Marie Svobodová - chybějící odchod
    marie_id = emp_ids["Marie Svobodová"]
    test_records.extend([
        # Den 1: Normální den
        (marie_id, 'Enter', (base_date + timedelta(days=0)).strftime('%Y-%m-%d') + ' 08:15:00'),
        (marie_id, 'Leave', (base_date + timedelta(days=0)).strftime('%Y-%m-%d') + ' 16:45:00'),
        
        # Den 2: Chybějící odchod
        (marie_id, 'Enter', (base_date + timedelta(days=1)).strftime('%Y-%m-%d') + ' 08:10:00'),
        # Žádný odchod!
        
        # Den 3: Další normální den
        (marie_id, 'Enter', (base_date + timedelta(days=2)).strftime('%Y-%m-%d') + ' 08:00:00'),
        (marie_id, 'Leave', (base_date + timedelta(days=2)).strftime('%Y-%m-%d') + ' 17:00:00'),
    ])
    
    # Scénář 3: Pavel Dvořák - více příchodů/odchodů v jednom dni (přestávka)
    pavel_id = emp_ids["Pavel Dvořák"]
    test_records.extend([
        # Den 1: S obědovou přestávkou
        (pavel_id, 'Enter', (base_date + timedelta(days=0)).strftime('%Y-%m-%d') + ' 08:00:00'),
        (pavel_id, 'Leave', (base_date + timedelta(days=0)).strftime('%Y-%m-%d') + ' 12:00:00'),  # Odchod na oběd
        (pavel_id, 'Enter', (base_date + timedelta(days=0)).strftime('%Y-%m-%d') + ' 13:00:00'),  # Návrat z oběda
        (pavel_id, 'Leave', (base_date + timedelta(days=0)).strftime('%Y-%m-%d') + ' 17:00:00'),  # Konec dne
        
        # Den 2: Krátká práce
        (pavel_id, 'Enter', (base_date + timedelta(days=1)).strftime('%Y-%m-%d') + ' 09:00:00'),
        (pavel_id, 'Leave', (base_date + timedelta(days=1)).strftime('%Y-%m-%d') + ' 13:30:00'),  # 4:30 hodin
    ])
    
    # Vložení všech záznamů
    for employee_id, status, timestamp in test_records:
        cursor.execute(
            'INSERT INTO attendance (employee_id, status, timestamp) VALUES (?, ?, ?)',
            (employee_id, status, timestamp)
        )
        print(f"✓ Přidán záznam: {status} v {timestamp}")
    
    conn.commit()
    conn.close()
    
    print(f"\n🎉 Testovací data byla úspěšně vytvořena!")
    print(f"📊 Zahrnují různé scénáře:")
    print(f"   - Normální pracovní dny s různými časy")
    print(f"   - Chybějící odchody") 
    print(f"   - Více příchodů/odchodů v jednom dni")
    print(f"   - Různé délky pracovní doby")
    print(f"\n🔗 Otevřete http://localhost:5000/admin pro zobrazení dat")

if __name__ == '__main__':
    create_test_data()