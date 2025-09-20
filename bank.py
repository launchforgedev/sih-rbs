import sqlite3

def signup(name, pin, balance=0):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (name, pin, balance) VALUES (?, ?, ?)", (name, pin, balance))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def login(name, pin):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE name=? AND pin=?", (name, pin))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def get_balance(user_id):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE id=?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def transfer(sender_id, receiver_id, amount):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE id=?", (sender_id,))
    sender = cursor.fetchone()
    if not sender or sender[0] < amount:
        conn.close()
        return False
    cursor.execute("UPDATE users SET balance=balance-? WHERE id=?", (amount, sender_id))
    cursor.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, receiver_id))
    conn.commit()
    conn.close()
    return True
