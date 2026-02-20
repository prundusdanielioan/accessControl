import sqlite3
import datetime

DB_NAME = "access_control.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    with conn:
        # Users table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                phone TEXT UNIQUE,
                rfid_tag TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Subscription Types
        conn.execute('''
            CREATE TABLE IF NOT EXISTS subscription_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                entries_per_week INTEGER,
                duration_days INTEGER NOT NULL,
                price REAL
            )
        ''')

        # Active Subscriptions
        conn.execute('''
            CREATE TABLE IF NOT EXISTS active_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type_id INTEGER,
                start_date DATE,
                end_date DATE,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (type_id) REFERENCES subscription_types (id)
            )
        ''')

        # Access Logs
        conn.execute('''
            CREATE TABLE IF NOT EXISTS access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                allowed BOOLEAN,
                reason TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Seed some data if empty
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM subscription_types")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO subscription_types (name, entries_per_week, duration_days, price) VALUES (?, ?, ?, ?)",
                        ('Unlimited Monthly', None, 30, 200.0))
            cur.execute("INSERT INTO subscription_types (name, entries_per_week, duration_days, price) VALUES (?, ?, ?, ?)",
                        ('3 Sessions / Week', 3, 30, 150.0))
            cur.execute("INSERT INTO subscription_types (name, entries_per_week, duration_days, price) VALUES (?, ?, ?, ?)",
                        ('One Year Full', None, 365, 2000.0))
            print("Seeded subscription types.")

    conn.close()

def get_user_by_rfid(rfid_tag):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE rfid_tag = ?', (rfid_tag,)).fetchone()
    conn.close()
    return user

def create_user(name, phone, rfid_tag):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute('INSERT INTO users (name, phone, rfid_tag) VALUES (?, ?, ?)', (name, phone, rfid_tag))
        user_id = cur.lastrowid
        conn.commit()
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def assign_subscription(user_id, type_id):
    conn = get_db_connection()
    sub_type = conn.execute('SELECT * FROM subscription_types WHERE id = ?', (type_id,)).fetchone()
    
    if not sub_type:
        conn.close()
        return False
        
    start_date = datetime.date.today()
    end_date = start_date + datetime.timedelta(days=sub_type['duration_days'])
    
    conn.execute('INSERT INTO active_subscriptions (user_id, type_id, start_date, end_date) VALUES (?, ?, ?, ?)',
                 (user_id, type_id, start_date, end_date))
    conn.commit()
    conn.close()
    return True

def log_access(user_id, allowed, reason):
    conn = get_db_connection()
    conn.execute('INSERT INTO access_logs (user_id, allowed, reason) VALUES (?, ?, ?)',
                 (user_id, allowed, reason))
    conn.commit()
    conn.close()

def check_access(user_id):
    conn = get_db_connection()
    today = datetime.date.today()
    
    # Get active subscription
    subscription = conn.execute('''
        SELECT s.*, t.entries_per_week, t.name as sub_name
        FROM active_subscriptions s
        JOIN subscription_types t ON s.type_id = t.id
        WHERE s.user_id = ? AND s.start_date <= ? AND s.end_date >= ?
        ORDER BY s.end_date DESC LIMIT 1
    ''', (user_id, today, today)).fetchone()

    # Calculate start of week (Monday) globally for this function
    start_of_week = today - datetime.timedelta(days=today.weekday())
    count = conn.execute('''
        SELECT COUNT(*) FROM access_logs 
        WHERE user_id = ? AND allowed = 1 AND timestamp >= ?
    ''', (user_id, start_of_week)).fetchone()[0]

    if not subscription:
        conn.close()
        return False, "No active subscription found.", "denied", None, count
        
    # Check weekly limits
    if subscription['entries_per_week']:
        if count >= subscription['entries_per_week']:
            conn.close()
            return False, f"Weekly limit reached ({count}/{subscription['entries_per_week']}).", "denied", subscription['sub_name'], count

    # Check for expiration warning (within 7 days)
    end_date = datetime.datetime.strptime(subscription['end_date'], '%Y-%m-%d').date()
    days_left = (end_date - today).days
    
    if days_left <= 7:
        conn.close()
        return True, f"Access Granted. Expires in {days_left} days ({subscription['end_date']})", "warning", subscription['sub_name'], count

    conn.close()
    return True, "Access Granted", "allowed", subscription['sub_name'], count

def get_all_users():
    conn = get_db_connection()
    users = conn.execute('''
        SELECT u.*, s.end_date, t.name as sub_name 
        FROM users u
        LEFT JOIN active_subscriptions s ON u.id = s.user_id AND s.end_date >= DATE('now')
        LEFT JOIN subscription_types t ON s.type_id = t.id
        ORDER BY u.name
    ''').fetchall()
    conn.close()
    return users

def get_user_by_id(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user

def get_active_subscription(user_id):
    conn = get_db_connection()
    today = datetime.date.today()
    sub = conn.execute('''
        SELECT s.*, t.name as type_name
        FROM active_subscriptions s
        JOIN subscription_types t ON s.type_id = t.id
        WHERE s.user_id = ? AND s.end_date >= ?
        ORDER BY s.end_date DESC LIMIT 1
    ''', (user_id, today)).fetchone()
    conn.close()
    return sub

def update_user(user_id, name, phone, rfid_tag):
    conn = get_db_connection()
    try:
        conn.execute('UPDATE users SET name = ?, phone = ?, rfid_tag = ? WHERE id = ?',
                     (name, phone, rfid_tag, user_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def extend_current_subscription(user_id, days):
    conn = get_db_connection()
    today = datetime.date.today()
    
    # Get current active sub
    current = conn.execute('''
        SELECT * FROM active_subscriptions 
        WHERE user_id = ? AND end_date >= ?
        ORDER BY end_date DESC LIMIT 1
    ''', (user_id, today)).fetchone()
    
    if current:
        # Extend existing
        new_end_date = datetime.datetime.strptime(current['end_date'], '%Y-%m-%d').date() + datetime.timedelta(days=days)
        conn.execute('UPDATE active_subscriptions SET end_date = ? WHERE id = ?', (new_end_date, current['id']))
    else:
        conn.close()
        return False
        
    conn.commit()
    conn.close()
    return True

def delete_user(user_id):
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM access_logs WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM active_subscriptions WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error deleting user: {e}")
        return False
    finally:
        conn.close()

def delete_log(log_id):
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM access_logs WHERE id = ?', (log_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error deleting log: {e}")
        return False
    finally:
        conn.close()
