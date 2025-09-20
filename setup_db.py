import sqlite3

conn = sqlite3.connect("bank.db")
cursor = conn.cursor()

# Users table
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    pin INTEGER NOT NULL,
    balance REAL NOT NULL,
    email TEXT
    
)
""")

conn.commit()
conn.close()
print("✅ Database setup complete")
