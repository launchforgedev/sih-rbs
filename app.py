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
from fastapi_utils.tasks import repeat_every
from email_utils import send_email
import secrets, datetime
from fastapi.responses import RedirectResponse
import traceback
import secrets
from fastapi import Query
from fastapi import Form
from fastapi.responses import RedirectResponse
reset_tokens = {}  # store temporary tokens in memory
import sqlite3
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
def login_form(name: str = Form(...), pin: int = Form(...)):
    # 1) initialize attempts for new user
    if name not in login_attempts:
        login_attempts[name] = MAX_ATTEMPTS

    # 2) If already locked, tell the user to check email
    if login_attempts[name] <= 0:
        return {"status": "error", "message": "Account locked. Check your email for reset instructions."}

    # 3) fetch user info (used for email & id)
    user_info = bank.get_user_by_name(name)  # should return dict or None

    # 4) attempt login
    user_id = bank.login(name, pin)
    if user_id:
        # success -> reset attempts and proceed
        login_attempts[name] = MAX_ATTEMPTS

        # optional: if user requires reset flag, redirect to reset page
        if user_info and user_info.get("reset_required"):
            return RedirectResponse(url=f"/reset_password/{user_id}", status_code=303)

        return RedirectResponse(url=f"/dashboard/{user_id}", status_code=303)

    # 5) failed login -> decrement attempts
    login_attempts[name] -= 1

    # 6) if now locked, generate token + email
    if login_attempts[name] <= 0:
        if user_info and user_info.get("email"):
            try:
                token = generate_token(name)
                reset_link = f"http://127.0.0.1:8000/reset_password?user={name}&token={token}"
                send_email(
                    user_info["email"],
                    "Reset Your Bank PIN",
                    f"Your account has been locked due to repeated failed logins.\n\n"
                    f"Reset your PIN here (link valid for a short time):\n\n{reset_link}"
                )
            except Exception as e:
                # don't crash the route when email sending fails; log and continue
                print("Email failed:", e)

        # optional: set DB flag that reset is required (if you implemented it)
        try:
            if user_info:
                bank.set_reset_required(user_info["id"])
        except Exception:
            pass

        return {"status": "error", "message": "Account locked. Reset link sent to your email if available."}

    # 7) still has attempts left -> inform remaining attempts
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
def transfer_form(sender_id: int = Form(...), receiver_id: int = Form(...), amount: float = Form(...)):
    try:
        # Fraud check (optional)
        if check_fraud(sender_id, amount):
            return {"status":"error","message":"Transaction flagged as fraud"}
        
        success = bank.transfer(sender_id, receiver_id, amount)
        if success:
            return {"status":"success","message":"Transfer complete"}
        return {"status":"error","message":"Insufficient funds or invalid user"}
    
    except Exception as e:
        # Server offline / error → queue transaction
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
        return {"status":"queued","message":"Server offline, transaction queued locally"}
@app.on_event("startup")
@repeat_every(seconds=60)  # every 60 seconds
def process_offline_queue():
    if not os.path.exists(OFFLINE_FILE):
        return
    with open(OFFLINE_FILE, "r") as f:
        transactions = json.load(f)
    success_list = []
    for tx in transactions:
        try:
            success = bank.transfer(tx["sender_id"], tx["receiver_id"], tx["amount"])
            if success:
                success_list.append(tx)
        except:
            continue
    transactions = [tx for tx in transactions if tx not in success_list]
    with open(OFFLINE_FILE, "w") as f:
        json.dump(transactions, f, indent=4)
    if success_list:
        print(f"Processed {len(success_list)} queued transactions ✅")

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
