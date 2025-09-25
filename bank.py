import sqlite3

DB_FILE = "bank.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        pin INTEGER,
        balance REAL
    )
    """)
    conn.commit()
    conn.close()

def signup(name, pin, balance):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (name, pin, balance) VALUES (?, ?, ?)", (name, pin, balance))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def login(name, pin):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE name=? AND pin=?", (name, pin))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def get_balance(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE id=?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None



def get_user_by_name(name: str):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email FROM users WHERE name=?", (name,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "name": row[1], "email": row[2]}
    return None

def set_reset_required(user_id):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET reset_required=1 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

def clear_reset_required(user_id):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET reset_required=0 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

def update_password(user_id, new_pin):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET pin=? WHERE id=?", (new_pin, user_id))
    conn.commit()
    conn.close()
def update_pin(name, new_pin):
    conn = sqlite3.connect("bank.db")
    c = conn.cursor()
    c.execute("UPDATE users SET pin=? WHERE name=?", (new_pin, name))
    conn.commit()
    conn.close()
import sqlite3
from datetime import datetime

DB_FILE = "bank.db"

def log_transaction(sender_id, receiver_id, amount):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO transactions (sender_id, receiver_id, amount, timestamp) VALUES (?, ?, ?, ?)",
        (sender_id, receiver_id, amount, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def transfer(sender_id, receiver_id, amount):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Check sender balance
    c.execute("SELECT balance FROM users WHERE id=?", (sender_id,))
    sender = c.fetchone()
    if not sender or sender[0] < amount:
        conn.close()
        return False

    # Check receiver exists
    c.execute("SELECT balance FROM users WHERE id=?", (receiver_id,))
    receiver = c.fetchone()
    if not receiver:
        conn.close()
        return False

    # Update balances
    c.execute("UPDATE users SET balance=? WHERE id=?", (sender[0]-amount, sender_id))
    c.execute("UPDATE users SET balance=? WHERE id=?", (receiver[0]+amount, receiver_id))
    conn.commit()
    conn.close()

    # Log transaction
    log_transaction(sender_id, receiver_id, amount)
    return True
def get_last_transaction(user_id: int):
    conn = sqlite3.connect("bank.db")
    c = conn.cursor()
    c.execute(
        "SELECT sender_id, receiver_id, amount, timestamp FROM transactions "
        "WHERE sender_id=? OR receiver_id=? ORDER BY timestamp DESC LIMIT 1",
        (user_id, user_id)
    )
    row = c.fetchone()
    conn.close()
    if row:
        return {"sender_id": row[0], "receiver_id": row[1], "amount": row[2], "timestamp": row[3]}
    return None
