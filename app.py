# app.py
from fastapi import FastAPI, Form, Request, Body, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import bank
import joblib
import pandas as pd
from datetime import datetime
import json
import os
import requests
from email_utils import send_email
import secrets, sqlite3, time
from passlib.context import CryptContext
import plotly.express as px
import plotly.io as pio

# --- Session timeout globals ---
SESSION_TIMEOUT = 120  # seconds; adjust as needed
active_sessions = {}   # maps user_id -> last_active_timestamp

# --- Helper functions for session ---
def is_session_active(user_id: int):
    ts = active_sessions.get(user_id)
    if not ts:
        return False
    # session active if within timeout
    if time.time() - ts <= SESSION_TIMEOUT:
        return True
    # expired -> remove
    try:
        del active_sessions[user_id]
    except KeyError:
        pass
    return False

def remaining_session_time(user_id: int):
    ts = active_sessions.get(user_id)
    if not ts:
        return 0
    remaining = SESSION_TIMEOUT - (time.time() - ts)
    return max(0, int(remaining))

# --- Password hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Templates & DB ---
templates = Jinja2Templates(directory="templates")
DB_PATH = "bank.db"
OFFLINE_FILE = "offline_transactions.json"
login_attempts = {}
MAX_ATTEMPTS = 3
reset_tokens = {}

# --- Initialize DB ---
bank.init_db()

# --- Load fraud model ---
try:
    fraud_model = joblib.load("fraud_model.pkl")
except:
    fraud_model = None

# --- Helper functions ---
def verify_pin(plain_pin, hashed_pin):
    return pwd_context.verify(str(plain_pin), hashed_pin)

def generate_token(user):
    token = secrets.token_urlsafe(16)
    reset_tokens[user] = token
    return token

def check_fraud(user_id, amount):
    if not fraud_model:
        return False
    now = datetime.now()
    df = pd.DataFrame([[user_id, amount, now.hour, now.weekday()]],
                      columns=['user_id','amount','hour','day_of_week'])
    pred = fraud_model.predict(df)
    return bool(pred[0])

def get_transactions(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM transactions WHERE sender_id=? OR receiver_id=?",
        conn, params=(user_id, user_id)
    )
    conn.close()
    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

def get_user_transactions(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, sender_id, receiver_id, amount, timestamp FROM transactions "
        "WHERE sender_id=? OR receiver_id=? ORDER BY timestamp DESC",
        (user_id, user_id)
    )
    transactions = c.fetchall()
    conn.close()
    tx_list = [
        {"id": t[0], "sender_id": t[1], "receiver_id": t[2], "amount": t[3], "timestamp": t[4]}
        for t in transactions
    ]
    return tx_list

def get_last_transaction(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, sender_id, receiver_id, amount, timestamp FROM transactions "
        "WHERE sender_id=? OR receiver_id=? ORDER BY timestamp DESC LIMIT 1",
        (user_id, user_id)
    )
    txn = c.fetchone()
    conn.close()
    if txn:
        return {"id": txn[0], "sender_id": txn[1], "receiver_id": txn[2], "amount": txn[3], "timestamp": txn[4]}
    return None

# --- FastAPI app ---
app = FastAPI()

# --- Routes ---
@app.get("/")
def root_redirect():
    return RedirectResponse(url="/signup")

# Signup page
@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

# Handle signup form
@app.post("/signup_form")
def signup_form(name: str = Form(...), pin: int = Form(...), balance: float = Form(0)):
    success = bank.signup(name, pin, balance)
    if success:
        return RedirectResponse(url=f"/login", status_code=303)
    return {"status": "error", "message": "Username already exists"}

# Login page
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# Handle login form
@app.post("/login_form")
def login_form(name: str = Form(...), pin: int = Form(...)):
    if name not in login_attempts:
        login_attempts[name] = MAX_ATTEMPTS

    user_info = bank.get_user_by_name(name)

    if login_attempts[name] <= 0:
        if user_info and user_info.get("email"):
            try:
                token = generate_token(name)
                reset_link = f"http://127.0.0.1:8000/reset_password?user={name}&token={token}"
                send_email(user_info["email"], "Reset Your Bank PIN",
                           f"Your account has been locked due to repeated failed logins.\n\nReset your PIN here:\n{reset_link}")
            except Exception as e:
                print("Email failed:", e)
        try:
            if user_info:
                bank.set_reset_required(user_info["id"])
        except:
            pass
        return {"status": "error", "message": "Account locked. Reset link sent to email if available."}

    user_id = bank.login(name, pin)
    if user_id:
        login_attempts[name] = MAX_ATTEMPTS
        active_sessions[user_id] = time.time()
        return RedirectResponse(url=f"/dashboard/{user_id}", status_code=303)

    login_attempts[name] -= 1
    return {"status": "error", "message": f"Invalid credentials. {login_attempts[name]} attempts remaining."}

# Logout
@app.get("/logout/{user_id}")
def logout(user_id: int):
    active_sessions.pop(user_id, None)
    return RedirectResponse(url="/login", status_code=303)

# Dashboard
@app.get("/dashboard/{user_id}", response_class=HTMLResponse)
def dashboard(request: Request, user_id: int):
    if not is_session_active(user_id):
        return RedirectResponse(url="/login", status_code=303)
    balance = bank.get_balance(user_id)
    transactions = get_user_transactions(user_id)
    remaining_time = remaining_session_time(user_id)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user_id": user_id,
        "balance": balance,
        "transactions": transactions,
        "session_timeout": remaining_time
    })

# Transfer page
@app.get("/transfer/{user_id}", response_class=HTMLResponse)
def transfer_page(request: Request, user_id: int):
    if not is_session_active(user_id):
        return RedirectResponse(url="/login", status_code=303)
    remaining_time = remaining_session_time(user_id)
    return templates.TemplateResponse("transfer.html", {
        "request": request,
        "user_id": user_id,
        "session_timeout": remaining_time
    })

# Handle transfer form
@app.post("/transfer_form")
def transfer_form(sender_id: int = Form(...), receiver_id: int = Form(...), amount: float = Form(...)):
    if not is_session_active(sender_id):
        return RedirectResponse(url="/login", status_code=303)
    try:
        if check_fraud(sender_id, amount):
            return {"status": "error", "message": "Transaction flagged as fraud"}
        success = bank.transfer(sender_id, receiver_id, amount)
        if success:
            active_sessions[sender_id] = time.time()
            return {"status": "success", "message": "Transfer complete"}
        return {"status": "error", "message": "Insufficient funds or invalid user"}
    except Exception:
        transaction = {"sender_id": sender_id, "receiver_id": receiver_id,
                       "amount": amount, "timestamp": datetime.now().isoformat()}
        if os.path.exists(OFFLINE_FILE):
            with open(OFFLINE_FILE, "r") as f:
                data = json.load(f)
        else:
            data = []
        data.append(transaction)
        with open(OFFLINE_FILE, "w") as f:
            json.dump(data, f, indent=4)
        return {"status": "queued", "message": "Server offline, transaction queued"}

# Transactions
@app.get("/transactions/{user_id}", response_class=HTMLResponse)
def transaction_history(request: Request, user_id: int):
    if not is_session_active(user_id):
        return RedirectResponse(url="/login", status_code=303)

    transactions = get_user_transactions(user_id)
    remaining_time = int(remaining_session_time(user_id))  # <- exact seconds remaining

    return templates.TemplateResponse(
        "transactions.html",
        {"request": request, "transactions": transactions, "user_id": user_id, "session_timeout": remaining_time}
    )


# Analytics
@app.get("/analytics/{user_id}", response_class=HTMLResponse)
def analytics_page(request: Request, user_id: int):
    if not is_session_active(user_id):
        return RedirectResponse(url="/login", status_code=303)
    df = get_transactions(user_id)
    df_sorted = df.sort_values('timestamp')
    df_sorted['type'] = df_sorted.apply(lambda x: 'Sent' if x['sender_id']==user_id else 'Received', axis=1)
    line_fig = px.line(df_sorted, x='timestamp', y='amount', color='type', title="Transaction Amounts Over Time", markers=True)
    line_html = pio.to_html(line_fig, full_html=False)
    outgoing = df[df['sender_id']==user_id]
    top5 = outgoing.groupby('receiver_id')['amount'].sum().sort_values(ascending=False).head(5).reset_index()
    pie_fig = px.pie(top5, names='receiver_id', values='amount', title="Top 5 Recipients by Amount")
    pie_html = pio.to_html(pie_fig, full_html=False)
    remaining_time = remaining_session_time(user_id)
    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "line_chart": line_html,
        "pie_chart": pie_html,
        "user_id": user_id,
        "session_timeout": remaining_time
    })

# Voice assistant
@app.get("/voice-assistant/{user_id}", response_class=HTMLResponse)
def voice_assistant_page(request: Request, user_id: int):
    if not is_session_active(user_id):
        return RedirectResponse(url="/login", status_code=303)
    remaining_time = remaining_session_time(user_id)
    return templates.TemplateResponse("voice_assistant.html", {
        "request": request,
        "user_id": user_id,
        "session_timeout": remaining_time
    })

# APIs for voice assistant
@app.post("/api/voice/check_balance")
def api_check_balance(payload: dict = Body(...)):
    user_id = int(payload.get("user_id"))
    if not is_session_active(user_id):
        return JSONResponse({"status":"error","message":"Session expired"}, status_code=401)
    bal = bank.get_balance(user_id)
    return {"status":"ok","balance":bal}

@app.post("/api/voice/last_transaction")
def api_last_transaction(payload: dict = Body(...)):
    user_id = int(payload.get("user_id"))
    if not is_session_active(user_id):
        return JSONResponse({"status":"error","message":"Session expired"}, status_code=401)
    txn = get_last_transaction(user_id)
    if txn:
        return {"status":"ok","transaction":txn}
    return {"status":"empty","message":"No transactions found."}

@app.post("/api/voice/transfer")
def api_transfer(payload: dict = Body(...)):
    try:
        sender_id = int(payload.get("sender_id"))
        receiver_id = int(payload.get("receiver_id"))
        amount = float(payload.get("amount"))
    except:
        return JSONResponse({"status":"error","message":"Invalid input"}, status_code=400)
    if not is_session_active(sender_id):
        return JSONResponse({"status":"error","message":"Session expired"}, status_code=401)
    success = bank.transfer(sender_id, receiver_id, amount)
    if success:
        active_sessions[sender_id] = time.time()
        return {"status":"ok","message":f"Transferred {amount} to user {receiver_id}"}
    else:
        return {"status":"error","message":"Insufficient funds or invalid user"}

# Admin routes (unchanged)
@app.get("/admin_login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})

@app.post("/admin_login_form")
def admin_login_form(username: str = Form(...), password: int = Form(...)):
    try:
        conn = sqlite3.connect("bank.db")
        c = conn.cursor()
        c.execute("SELECT id FROM admin WHERE username=? AND password=?", (username, password))
        admin = c.fetchone()
        conn.close()
        if admin:
            return RedirectResponse(url=f"/admin_dashboard/{admin[0]}", status_code=303)
        else:
            return {"status":"error","message":"Invalid admin credentials"}
    except Exception as e:
        return {"status":"error","message":str(e)}

@app.get("/admin_dashboard/{admin_id}", response_class=HTMLResponse)
def admin_dashboard(request: Request, admin_id: int):
    conn = sqlite3.connect("bank.db")
    c = conn.cursor()
    c.execute("SELECT id, name, balance FROM users")
    users = c.fetchall()
    conn.close()
    return templates.TemplateResponse("admin_dashboard.html", {"request": request, "users": users})

@app.post("/admin_add_amount")
def admin_add_amount(user_id: int = Form(...), amount: float = Form(...)):
    conn = sqlite3.connect("bank.db")
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/admin_dashboard/1", status_code=303)