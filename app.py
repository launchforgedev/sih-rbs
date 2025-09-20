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
OFFLINE_FILE = "offline_transactions.json"

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
    user_id = bank.login(name, pin)
    if user_id:
        return RedirectResponse(url=f"/dashboard/{user_id}", status_code=303)
    return {"status": "error", "message": "Invalid credentials"}

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
