from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import bank
import joblib
import pandas as pd
from datetime import datetime
import json
import os
from datetime import datetime
import requests
from email_utils import send_email
import secrets, datetime
from fastapi.responses import RedirectResponse
import traceback
import secrets
from fastapi import Query
from fastapi import Form
from fastapi.responses import RedirectResponse
reset_tokens = {} 
import sqlite3
from passlib.context import CryptContext
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from fastapi import Request
from fastapi.templating import Jinja2Templates
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.io as pio
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
templates = Jinja2Templates(directory="templates")
DB_PATH = "bank.db"

def verify_pin(plain_pin, hashed_pin):
    return pwd_context.verify(str(plain_pin), hashed_pin)
def generate_token(user):
    token = secrets.token_urlsafe(16)
    reset_tokens[user] = token
    return token

OFFLINE_FILE = "offline_transactions.json"
login_attempts = {}
MAX_ATTEMPTS = 3

bank.init_db()
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Load fraud model if exists
try:
    fraud_model = joblib.load("fraud_model.pkl")
except:
    fraud_model = None

def check_fraud(user_id, amount):
    if not fraud_model:
        return False
    now = datetime.now()
    df = pd.DataFrame([[user_id, amount, now.hour, now.weekday()]],
                      columns=['user_id','amount','hour','day_of_week'])
    pred = fraud_model.predict(df)
    return bool(pred[0])
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
def login_form( name: str = Form(...), pin: int = Form(...)):
    

    # 1) initialize attempts for new user
    if name not in login_attempts:
        login_attempts[name] = MAX_ATTEMPTS

    # 2) fetch user info from DB
    user_info = bank.get_user_by_name(name)

    # 3) check if account is locked
    if login_attempts[name] <= 0:
        if user_info and user_info.get("email"):
            try:
                
               

                # token + reset link
                token = generate_token(name)
                reset_link = f"http://127.0.0.1:8000/reset_password?user={name}&token={token}"

                # send reset email
                send_email(
                    user_info["email"],
                    "Reset Your Bank PIN",
                    f"Your account has been locked due to repeated failed logins.\n\n"
                    
                    f"Reset your PIN here (link valid for a short time):\n\n{reset_link}"
                )
            except Exception as e:
                print("Email failed:", e)

        # optional: mark user for reset in DB
        try:
            if user_info:
                bank.set_reset_required(user_info["id"])
        except Exception:
            pass

        return {"status": "error", "message": "Account locked. Reset link sent to your email if available."}

    # 4) check credentials
    user_id = bank.login(name, pin)
    if user_id:
        # reset attempts on success
        login_attempts[name] = MAX_ATTEMPTS
        return RedirectResponse(url=f"/dashboard/{user_id}", status_code=303)

    # 5) wrong credentials -> reduce attempts
    login_attempts[name] -= 1
    return {
        "status": "error",
        "message": f"Invalid credentials. {login_attempts[name]} attempts remaining."
    }

    

# Dashboard page
@app.get("/dashboard/{user_id}", response_class=HTMLResponse)
def dashboard(request: Request, user_id: int):
    balance = bank.get_balance(user_id)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user_id": user_id, "balance": balance})

# Transfer page
@app.get("/transfer/{user_id}", response_class=HTMLResponse)
def transfer_page(request: Request, user_id: int):
    return templates.TemplateResponse("transfer.html", {"request": request, "user_id": user_id})

# Handle transfer form
@app.post("/transfer_form")
def transfer_form(
    sender_id: int = Form(...),
    receiver_id: int = Form(...),
    amount: float = Form(...),
    
):
    try:
        
        

        # Fraud detection (optional)
        if check_fraud(sender_id, amount):
            return {"status": "error", "message": "Transaction flagged as fraud"}

        # Execute transfer
        success = bank.transfer(sender_id, receiver_id, amount)

        if success:
            return {"status": "success", "message": "Transfer complete"}
        return {"status": "error", "message": "Insufficient funds or invalid user"}

    except Exception as e:
        # Queue transaction if server is down
        transaction = {
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "amount": amount,
            "timestamp": datetime.now().isoformat()
        }
        if os.path.exists(OFFLINE_FILE):
            with open(OFFLINE_FILE, "r") as f:
                data = json.load(f)
        else:
            data = []
        data.append(transaction)
        with open(OFFLINE_FILE, "w") as f:
            json.dump(data, f, indent=4)
        return {"status": "queued", "message": "Server offline, transaction queued locally"}
@app.get("/reset_password/{token}")
def reset_password_form(token: str):
    # Serve HTML form
    return templates.TemplateResponse("reset_password.html", {"request": {}, "token": token})

@app.post("/reset_password/{token}")
def reset_password(token: str, new_pin: int = Form(...)):
    user_id = bank.verify_reset_token(token)
    if not user_id:
        return {"status": "error", "message": "Invalid or expired token"}

    bank.update_pin(user_id, new_pin)
    return {"status": "success", "message": "PIN updated. You can log in now."}
@app.get("/reset_password", response_class=HTMLResponse)
def reset_password_page(request: Request, user: str = Query(...), token: str = Query(...)):
    if user in reset_tokens and reset_tokens[user] == token:
        return templates.TemplateResponse("reset_password.html", {"request": request, "user": user, "token": token})
    return {"status": "error", "message": "Invalid or expired reset link."}


@app.post("/reset_password_form")
def reset_password_form(user: str = Form(...), token: str = Form(...), new_pin: int = Form(...)):
    if user in reset_tokens and reset_tokens[user] == token:
        # update password in DB
        bank.update_pin(user, new_pin)

        # unlock account
        login_attempts[user] = 3
        del reset_tokens[user]

        return {"status": "success", "message": "Password reset successful. You can now login."}
    return {"status": "error", "message": "Invalid or expired reset attempt."}
@app.get("/transactions/{user_id}", response_class=HTMLResponse)
def transaction_history(request: Request, user_id: int):
    conn = sqlite3.connect("bank.db")
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
    return templates.TemplateResponse("transactions.html", {"request": request, "transactions": tx_list})
def get_transactions(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM transactions WHERE sender_id=? OR receiver_id=?",
        conn, params=(user_id, user_id)
    )
    conn.close()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

@app.get("/analytics/{user_id}")
def analytics_page(request: Request, user_id: int):
    df = get_transactions(user_id)

    # --- Line chart: All transactions over time (sent + received) ---
    df_sorted = df.sort_values('timestamp')
    df_sorted['type'] = df_sorted.apply(lambda x: 'Sent' if x['sender_id'] == user_id else 'Received', axis=1)
    
    line_fig = px.line(
        df_sorted, 
        x='timestamp', 
        y='amount', 
        color='type',             # differentiate Sent vs Received
        title="Transaction Amounts Over Time",
        markers=True
    )
    line_html = pio.to_html(line_fig, full_html=False)

    # --- Pie chart: Top 5 recipients by amount ---
    outgoing = df[df['sender_id'] == user_id]
    top5 = outgoing.groupby('receiver_id')['amount'].sum().sort_values(ascending=False).head(5).reset_index()
    pie_fig = px.pie(top5, names='receiver_id', values='amount', title="Top 5 Recipients by Amount")
    pie_html = pio.to_html(pie_fig, full_html=False)

    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "line_chart": line_html,   # pass line chart
        "pie_chart": pie_html,
        "user_id": user_id
    })
from fastapi import Body
from fastapi.responses import JSONResponse
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
@app.get("/voice-assistant/{user_id}", response_class=HTMLResponse)
def voice_assistant_page(request: Request, user_id: int):
    # Render template and pass user_id so frontend knows the sender id
    return templates.TemplateResponse("voice_assistant.html", {"request": request, "user_id": user_id})
# Check balance
@app.post("/api/voice/check_balance")
def api_check_balance(payload: dict = Body(...)):
    user_id = int(payload.get("user_id"))
    bal = bank.get_balance(user_id)
    return {"status": "ok", "balance": bal}

# Get last transaction
@app.post("/api/voice/last_transaction")
def api_last_transaction(payload: dict = Body(...)):
    user_id = int(payload.get("user_id"))
    txn = get_last_transaction(user_id)
    if txn:
        return {"status": "ok", "transaction": txn}
    return {"status": "empty", "message": "No transactions found."}

# Transfer money
@app.post("/api/voice/transfer")
def api_transfer(payload: dict = Body(...)):
    try:
        sender_id = int(payload.get("sender_id"))
        receiver_id = int(payload.get("receiver_id"))
        amount = float(payload.get("amount"))
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid input"}, status_code=400)

    # Optional: verify sender has enough balance
    success = bank.transfer(sender_id, receiver_id, amount)
    if success:
        return {"status": "ok", "message": f"Transferred {amount} to user {receiver_id}"}
    else:
        return {"status": "error", "message": "Insufficient funds or invalid user"}
# Admin login page
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
            return {"status": "error", "message": "Invalid admin credentials"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/admin_dashboard/{admin_id}", response_class=HTMLResponse)
def admin_dashboard(request: Request, admin_id: int):
    conn = sqlite3.connect("bank.db")
    c = conn.cursor()
    c.execute("SELECT id, name, balance FROM users")
    users = c.fetchall()
    conn.close()
    return templates.TemplateResponse("admin_dashboard.html", {"request": request, "users": users})
# Admin dashboard
@app.get("/admin_dashboard/{admin_id}", response_class=HTMLResponse)
def admin_dashboard(request: Request, admin_id: int):
    conn = sqlite3.connect("bank.db")
    c = conn.cursor()
    c.execute("SELECT id, name, balance FROM users")
    users = c.fetchall()
    conn.close()
    return templates.TemplateResponse("admin_dashboard.html", {"request": request, "users": users})

# Admin add amount to user
@app.post("/admin_add_amount")
def admin_add_amount(user_id: int = Form(...), amount: float = Form(...)):
    conn = sqlite3.connect("bank.db")
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/admin_dashboard/1", status_code=303)  # assuming admin_id=1
