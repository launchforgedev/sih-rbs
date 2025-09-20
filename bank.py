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
