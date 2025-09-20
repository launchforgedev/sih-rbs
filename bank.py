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

def transfer(sender_id, receiver_id, amount):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # check sender balance
    cursor.execute("SELECT balance FROM users WHERE id=?", (sender_id,))
    sender_balance = cursor.fetchone()[0]
    if sender_balance < amount:
        conn.close()
        return False
    # update balances
    cursor.execute("UPDATE users SET balance = balance - ? WHERE id=?", (amount, sender_id))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, receiver_id))
    conn.commit()
    conn.close()
    return True
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
