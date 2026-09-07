import os
import sys
import logging
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# IMPORT DOTENV TO READ THE .env FILE
from dotenv import load_dotenv

# 1. Load the hidden .env file into the environment
load_dotenv()

# 2. CloudWatch-friendly structured logging
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
)
logger = logging.getLogger("finpulze-engine")

# 3. STRICT SECRET PULLING (NO HARDCODING ALLOWED)
DATABASE_URL = os.getenv("DATABASE_URL")
PAYMENT_GATEWAY_SECRET = os.getenv("PAYMENT_GATEWAY_SECRET")

# If the .env file is missing or empty, kill the app instantly!
if not DATABASE_URL or not PAYMENT_GATEWAY_SECRET:
    logger.error("CRITICAL FATAL ERROR: Missing environment variables.")
    logger.error("You MUST create a .env file with DATABASE_URL and PAYMENT_GATEWAY_SECRET to run this application securely.")
    sys.exit(1)

app = FastAPI(title="FinPulze Global Payments", version="1.2.0")

# 4. In-memory storage & 13 Global Exchange Rates (Base NGN)
EXCHANGE_RATES = {
    "NGN": 1.0,       # Nigerian Naira
    "USD": 1500.0,    # US Dollar
    "EUR": 1600.0,    # Euro
    "GBP": 1900.0,    # British Pound
    "GHS": 115.0,     # Ghanaian Cedi
    "CAD": 1100.0,    # Canadian Dollar
    "AUD": 980.0,     # Australian Dollar
    "ZAR": 80.0,      # South African Rand
    "KRW": 1.1,       # South Korean Won
    "CNY": 200.0,     # Chinese Yuan
    "JPY": 10.0,      # Japanese Yen
    "KES": 11.0,      # Kenyan Shilling
    "INR": 18.0       # Indian Rupee
} 

CURRENCY_SYMBOLS = {
    "NGN": "₦", "USD": "$", "EUR": "€", "GBP": "£", "GHS": "GH₵",
    "CAD": "C$", "AUD": "A$", "ZAR": "R", "KRW": "₩", "CNY": "¥",
    "JPY": "¥", "KES": "KSh", "INR": "₹"
}

USERS_DB = {}
TRANSACTIONS_DB = []

# --- STRICT PYDANTIC SCHEMAS ---
class AuthRequest(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = "Demo User"
    currency: Optional[str] = "USD"

class ProfileUpdateRequest(BaseModel):
    email: str
    full_name: str
    currency: str

class FundWalletRequest(BaseModel):
    email: str
    amount: float = Field(..., gt=0, description="Amount must be a valid number")

class TransferRequest(BaseModel):
    sender_email: str
    recipient_account: str = Field(..., min_length=4, max_length=20)
    recipient_bank: str
    amount: float = Field(..., gt=0)
    narration: Optional[str] = "FinPulze Transfer"

# --- API ENDPOINTS ---
@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "finpulze-engine", "secrets_injected": PAYMENT_GATEWAY_SECRET != "dummy_secret_key"}

@app.post("/api/v1/auth/signup")
def signup(payload: AuthRequest):
    if payload.email in USERS_DB:
        raise HTTPException(status_code=400, detail="Account already exists. Please sign in.")
    
    account_no = f"01{uuid.uuid4().int % 100000000:08d}"
    # Standardize welcome bonus to $100 equivalent
    welcome_bonus_ngn = 150000.0
    starting_balance = welcome_bonus_ngn / EXCHANGE_RATES.get(payload.currency, 1.0)

    new_user = {
        "full_name": payload.full_name,
        "email": payload.email,
        "password": payload.password,
        "account_number": account_no,
        "balance": starting_balance,  
        "currency": payload.currency
    }
    USERS_DB[payload.email] = new_user
    logger.info(f"New international account created: {payload.email} | Currency: {payload.currency}")
    return new_user

@app.post("/api/v1/auth/login")
def login(payload: AuthRequest):
    user = USERS_DB.get(payload.email)
    if not user or user["password"] != payload.password:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return user

@app.put("/api/v1/profile")
def update_profile(payload: ProfileUpdateRequest):
    user = USERS_DB.get(payload.email)
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    
    old_curr = user["currency"]
    new_curr = payload.currency
    if old_curr != new_curr and new_curr in EXCHANGE_RATES:
        base_ngn_balance = user["balance"] * EXCHANGE_RATES[old_curr]
        user["balance"] = base_ngn_balance / EXCHANGE_RATES[new_curr]
        user["currency"] = new_curr

    user["full_name"] = payload.full_name
    logger.info(f"Profile updated for {payload.email} to currency {new_curr}")
    return user

@app.get("/api/v1/wallet")
def get_wallet(email: str):
    user = USERS_DB.get(email)
    if not user:
        raise HTTPException(status_code=404, detail="User account not found")
    return {"user": user, "symbol": CURRENCY_SYMBOLS.get(user["currency"], "")}

@app.get("/api/v1/transactions")
def get_transactions(email: str):
    return [tx for tx in TRANSACTIONS_DB if tx["owner"] == email]

@app.post("/api/v1/wallet/fund")
def fund_wallet(payload: FundWalletRequest):
    user = USERS_DB.get(payload.email)
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    
    user["balance"] += payload.amount
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    record = {
        "id": tx_id,
        "owner": payload.email,
        "type": "credit",
        "description": "Card Deposit",
        "amount": payload.amount,
        "currency": user["currency"],
        "symbol": CURRENCY_SYMBOLS.get(user["currency"], ""),
        "counterparty": "Payment Gateway",
        "timestamp": datetime.now().strftime("%d %b, %I:%M %p"),
        "status": "SUCCESSFUL"
    }
    TRANSACTIONS_DB.insert(0, record)
    return {"message": "Wallet funded", "new_balance": user["balance"], "transaction": record}

@app.post("/api/v1/wallet/transfer")
def transfer_funds(payload: TransferRequest):
    sender = USERS_DB.get(payload.sender_email)
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")
    
    if sender["balance"] < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient wallet balance")
    
    sender["balance"] -= payload.amount
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    record = {
        "id": tx_id,
        "owner": payload.sender_email,
        "type": "debit",
        "description": payload.narration,
        "amount": payload.amount,
        "currency": sender["currency"],
        "symbol": CURRENCY_SYMBOLS.get(sender["currency"], ""),
        "counterparty": f"{payload.recipient_account} ({payload.recipient_bank})",
        "timestamp": datetime.now().strftime("%d %b, %I:%M %p"),
        "status": "SUCCESSFUL"
    }
    TRANSACTIONS_DB.insert(0, record)
    return {"message": "Transfer successful", "new_balance": sender["balance"]}

# --- FULL STACK UI WITH DARK/LIGHT THEME ---
@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>FinPulze Global Payments</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            tailwind.config = {
                darkMode: 'class',
                theme: { extend: {} }
            }
        </script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');
            body { font-family: 'Plus Jakarta Sans', sans-serif; transition: background-color 0.3s, color 0.3s; }
            .glass-card { backdrop-filter: blur(12px); }
        </style>
    </head>
    <body class="bg-gray-50 text-gray-900 dark:bg-[#0b0f19] dark:text-gray-100 min-h-screen flex flex-col">

        <!-- AUTHENTICATION VIEW -->
        <div id="auth-view" class="flex-1 flex flex-col items-center justify-center p-4">
            <div class="glass-card bg-white/80 dark:bg-gray-900/80 border border-gray-200 dark:border-gray-800 rounded-2xl p-8 max-w-md w-full shadow-xl">
                <div class="text-center mb-8">
                    <div class="w-12 h-12 mx-auto rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 flex items-center justify-center text-gray-950 font-extrabold text-2xl shadow-lg shadow-emerald-500/20 mb-4">FZ</div>
                    <h2 class="text-2xl font-bold text-gray-900 dark:text-white">Welcome to FinPulze</h2>
                    <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Global infrastructure for modern teams</p>
                </div>

                <!-- Tabs -->
                <div class="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-1 mb-6 border border-gray-200 dark:border-gray-700">
                    <button id="tab-login" onclick="switchAuth('login')" class="flex-1 py-2 text-sm font-bold rounded-md bg-emerald-500 text-white dark:text-gray-950 shadow-sm transition">Log In</button>
                    <button id="tab-signup" onclick="switchAuth('signup')" class="flex-1 py-2 text-sm font-medium text-gray-500 dark:text-gray-400 rounded-md hover:text-gray-900 dark:hover:text-white transition">Sign Up</button>
                </div>

                <div id="auth-error" class="hidden mb-4 p-3 bg-rose-100 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 rounded-lg text-rose-600 dark:text-rose-400 text-xs font-semibold text-center"></div>

                <div class="space-y-4">
                    <div id="name-field" class="hidden">
                        <label class="text-xs font-medium text-gray-500 dark:text-gray-400">Full Name</label>
                        <input id="auth-name" type="text" class="w-full mt-1 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-2 text-gray-900 dark:text-white focus:border-emerald-500 focus:outline-none shadow-sm">
                    </div>
                    <div>
                        <label class="text-xs font-medium text-gray-500 dark:text-gray-400">Email Address</label>
                        <input id="auth-email" type="email" class="w-full mt-1 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-2 text-gray-900 dark:text-white focus:border-emerald-500 focus:outline-none shadow-sm">
                    </div>
                    <div>
                        <label class="text-xs font-medium text-gray-500 dark:text-gray-400">Password</label>
                        <input id="auth-password" type="password" class="w-full mt-1 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-2 text-gray-900 dark:text-white focus:border-emerald-500 focus:outline-none shadow-sm">
                    </div>
                    <div id="currency-field" class="hidden">
                        <label class="text-xs font-medium text-gray-500 dark:text-gray-400">Base Currency</label>
                        <select id="auth-currency" class="w-full mt-1 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-2 text-gray-900 dark:text-white focus:border-emerald-500 focus:outline-none shadow-sm">
                            <option value="USD">United States (USD $)</option>
                            <option value="NGN">Nigeria (NGN ₦)</option>
                            <option value="EUR">Eurozone (EUR €)</option>
                            <option value="GBP">British Pound (GBP £)</option>
                            <option value="GHS">Ghana (GHS GH₵)</option>
                            <option value="CAD">Canada (CAD C$)</option>
                            <option value="AUD">Australia (AUD A$)</option>
                            <option value="ZAR">South Africa (ZAR R)</option>
                            <option value="KRW">South Korea (KRW ₩)</option>
                            <option value="CNY">China (CNY ¥)</option>
                            <option value="JPY">Japan (JPY ¥)</option>
                            <option value="KES">Kenya (KES KSh)</option>
                            <option value="INR">India (INR ₹)</option>
                        </select>
                    </div>
                    <button onclick="executeAuth()" id="auth-btn" class="w-full bg-emerald-500 hover:bg-emerald-600 dark:hover:bg-emerald-400 text-white dark:text-gray-950 font-bold py-3 rounded-xl transition text-sm mt-4 shadow-lg shadow-emerald-500/20">
                        Log In
                    </button>
                </div>
            </div>
        </div>

        <!-- DASHBOARD VIEW -->
        <div id="dashboard-view" class="hidden flex-col min-h-screen">
            <header class="border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-[#0d1322]/80 sticky top-0 z-40 backdrop-blur">
                <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                    <div class="flex items-center space-x-3">
                        <div class="w-8 h-8 rounded-lg bg-gradient-to-tr from-emerald-500 to-teal-400 flex items-center justify-center text-white dark:text-gray-950 font-bold text-sm">FZ</div>
                        <span class="text-lg font-bold text-gray-900 dark:text-white hidden sm:block">FinPulze Global</span>
                    </div>
                    <div class="flex items-center space-x-4">
                        <button onclick="toggleTheme()" class="w-9 h-9 rounded-full bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:border-emerald-500 transition flex items-center justify-center text-gray-600 dark:text-gray-300">
                            <i id="theme-icon" class="fa-solid fa-moon text-sm"></i>
                        </button>
                        <div class="text-right hidden sm:block">
                            <p class="text-xs font-bold text-gray-900 dark:text-white" id="user-name">Loading...</p>
                            <p class="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono" id="user-account"></p>
                        </div>
                        <button onclick="toggleModal('profile-modal')" class="w-9 h-9 rounded-full bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:border-emerald-500 transition flex items-center justify-center text-gray-600 dark:text-gray-300">
                            <i class="fa-solid fa-gear text-sm"></i>
                        </button>
                        <button onclick="logout()" class="w-9 h-9 rounded-full bg-rose-100 dark:bg-rose-500/10 text-rose-600 dark:text-rose-400 hover:bg-rose-200 dark:hover:bg-rose-500/20 transition flex items-center justify-center">
                            <i class="fa-solid fa-arrow-right-from-bracket text-sm"></i>
                        </button>
                    </div>
                </div>
            </header>

            <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
                <!-- Balance Card -->
                <div class="glass-card rounded-2xl p-6 md:p-8 relative overflow-hidden bg-white dark:bg-gradient-to-br dark:from-gray-900 dark:to-[#0b1120] shadow-xl dark:shadow-2xl border border-gray-200 dark:border-gray-700/50">
                    <p class="text-sm font-medium text-gray-500 dark:text-gray-400">Available Balance</p>
                    <h2 class="text-4xl md:text-5xl font-extrabold text-gray-900 dark:text-white mt-2 font-mono tracking-tight" id="balance-display">
                        0.00
                    </h2>
                    <div class="mt-8 flex gap-3">
                        <button onclick="toggleModal('deposit-modal')" class="bg-emerald-500 hover:bg-emerald-600 dark:hover:bg-emerald-400 text-white dark:text-gray-950 font-bold px-5 py-2.5 rounded-xl text-sm flex items-center gap-2 shadow-lg shadow-emerald-500/20">
                            <i class="fa-solid fa-plus"></i> Add Money
                        </button>
                        <button onclick="toggleModal('transfer-modal')" class="bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-900 dark:text-white font-semibold px-5 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 text-sm flex items-center gap-2 shadow-sm">
                            <i class="fa-solid fa-paper-plane text-emerald-500 dark:text-emerald-400"></i> Send Money
                        </button>
                    </div>
                </div>

                <!-- Ledger -->
                <div class="glass-card rounded-2xl p-6 border border-gray-200 dark:border-gray-800 bg-white dark:bg-transparent shadow-sm">
                    <h3 class="text-lg font-bold text-gray-900 dark:text-white mb-4">Transaction History</h3>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-sm">
                            <thead class="text-[10px] text-gray-500 uppercase bg-gray-50 dark:bg-gray-900/50 border-b border-gray-200 dark:border-gray-800">
                                <tr>
                                    <th class="py-3 px-4 rounded-tl-lg">Ref</th>
                                    <th class="py-3 px-4">Details</th>
                                    <th class="py-3 px-4">Amount</th>
                                    <th class="py-3 px-4 rounded-tr-lg">Status</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-gray-100 dark:divide-gray-800/60" id="transactions-body"></tbody>
                        </table>
                    </div>
                </div>
            </main>
        </div>

        <!-- MODALS -->
        <!-- Deposit Modal -->
        <div id="deposit-modal" class="fixed inset-0 bg-black/60 dark:bg-black/80 z-50 hidden flex items-center justify-center p-4 backdrop-blur-sm">
            <div class="bg-white dark:bg-gray-900 rounded-2xl max-w-sm w-full p-6 border border-gray-200 dark:border-gray-700 shadow-2xl">
                <div class="flex justify-between mb-4"><h3 class="font-bold text-gray-900 dark:text-white">Add Funds</h3><button onclick="toggleModal('deposit-modal')" class="text-gray-400 hover:text-gray-600 dark:hover:text-white"><i class="fa-solid fa-xmark"></i></button></div>
                <input id="deposit-amount" type="number" step="0.01" min="1" placeholder="Amount (Numbers only)" class="w-full bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-3 text-gray-900 dark:text-white focus:border-emerald-500 outline-none mb-4 shadow-sm">
                <button onclick="submitDeposit()" class="w-full bg-emerald-500 hover:bg-emerald-600 dark:hover:bg-emerald-400 text-white dark:text-gray-950 font-bold py-3 rounded-xl shadow-lg shadow-emerald-500/20">Deposit</button>
            </div>
        </div>

        <!-- Transfer Modal -->
        <div id="transfer-modal" class="fixed inset-0 bg-black/60 dark:bg-black/80 z-50 hidden flex items-center justify-center p-4 backdrop-blur-sm">
            <div class="bg-white dark:bg-gray-900 rounded-2xl max-w-sm w-full p-6 border border-gray-200 dark:border-gray-700 shadow-2xl">
                <div class="flex justify-between mb-4"><h3 class="font-bold text-gray-900 dark:text-white">Send Money</h3><button onclick="toggleModal('transfer-modal')" class="text-gray-400 hover:text-gray-600 dark:hover:text-white"><i class="fa-solid fa-xmark"></i></button></div>
                <div class="space-y-3 mb-4">
                    <input id="transfer-acc" type="text" placeholder="Account Number / Phone" class="w-full bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-3 text-gray-900 dark:text-white outline-none focus:border-emerald-500 shadow-sm">
                    <input id="transfer-bank" type="text" placeholder="Bank Name or Network" class="w-full bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-3 text-gray-900 dark:text-white outline-none focus:border-emerald-500 shadow-sm">
                    <input id="transfer-amount" type="number" step="0.01" min="1" placeholder="Amount (Numbers only)" class="w-full bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-3 text-gray-900 dark:text-white outline-none focus:border-emerald-500 shadow-sm">
                    <input id="transfer-note" type="text" placeholder="Narration" class="w-full bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-3 text-gray-900 dark:text-white outline-none focus:border-emerald-500 shadow-sm">
                </div>
                <button onclick="submitTransfer()" class="w-full bg-emerald-500 hover:bg-emerald-600 dark:hover:bg-emerald-400 text-white dark:text-gray-950 font-bold py-3 rounded-xl shadow-lg shadow-emerald-500/20">Send Payment</button>
            </div>
        </div>

        <!-- Profile Modal -->
        <div id="profile-modal" class="fixed inset-0 bg-black/60 dark:bg-black/80 z-50 hidden flex items-center justify-center p-4 backdrop-blur-sm">
            <div class="bg-white dark:bg-gray-900 rounded-2xl max-w-sm w-full p-6 border border-gray-200 dark:border-gray-700 shadow-2xl">
                <div class="flex justify-between mb-4"><h3 class="font-bold text-gray-900 dark:text-white">Edit Profile</h3><button onclick="toggleModal('profile-modal')" class="text-gray-400 hover:text-gray-600 dark:hover:text-white"><i class="fa-solid fa-xmark"></i></button></div>
                <div class="space-y-3 mb-4">
                    <label class="text-xs text-gray-500 dark:text-gray-400">Full Name</label>
                    <input id="prof-name" type="text" class="w-full bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-2.5 text-gray-900 dark:text-white outline-none focus:border-emerald-500 shadow-sm">
                    <label class="text-xs text-gray-500 dark:text-gray-400">Base Currency</label>
                    <select id="prof-currency" class="w-full bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-2.5 text-gray-900 dark:text-white outline-none focus:border-emerald-500 shadow-sm">
                        <option value="USD">United States (USD $)</option>
                        <option value="NGN">Nigeria (NGN ₦)</option>
                        <option value="EUR">Eurozone (EUR €)</option>
                        <option value="GBP">British Pound (GBP £)</option>
                        <option value="GHS">Ghana (GHS GH₵)</option>
                        <option value="CAD">Canada (CAD C$)</option>
                        <option value="AUD">Australia (AUD A$)</option>
                        <option value="ZAR">South Africa (ZAR R)</option>
                        <option value="KRW">South Korea (KRW ₩)</option>
                        <option value="CNY">China (CNY ¥)</option>
                        <option value="JPY">Japan (JPY ¥)</option>
                        <option value="KES">Kenya (KES KSh)</option>
                        <option value="INR">India (INR ₹)</option>
                    </select>
                </div>
                <button onclick="updateProfile()" class="w-full bg-emerald-500 hover:bg-emerald-600 dark:hover:bg-emerald-400 text-white dark:text-gray-950 font-bold py-3 rounded-xl shadow-lg shadow-emerald-500/20">Save Changes</button>
            </div>
        </div>

        <script>
            // --- THEME LOGIC ---
            function toggleTheme() {
                document.documentElement.classList.toggle('dark');
                const isDark = document.documentElement.classList.contains('dark');
                localStorage.setItem('theme', isDark ? 'dark' : 'light');
                updateThemeIcon(isDark);
            }
            function updateThemeIcon(isDark) {
                const icon = document.getElementById('theme-icon');
                if (isDark) { icon.classList.replace('fa-moon', 'fa-sun'); } 
                else { icon.classList.replace('fa-sun', 'fa-moon'); }
            }
            if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                document.documentElement.classList.add('dark');
                updateThemeIcon(true);
            }

            // --- APP LOGIC ---
            let currentUserEmail = localStorage.getItem("finpulze_user") || null;
            let authMode = 'login';

            function toggleModal(id) { document.getElementById(id).classList.toggle('hidden'); }
            
            function switchAuth(mode) {
                authMode = mode;
                document.getElementById('name-field').classList.toggle('hidden', mode === 'login');
                document.getElementById('currency-field').classList.toggle('hidden', mode === 'login');
                
                const btnLog = document.getElementById('tab-login');
                const btnSign = document.getElementById('tab-signup');
                
                if(mode === 'login') {
                    btnLog.className = "flex-1 py-2 text-sm font-bold rounded-md bg-emerald-500 text-white dark:text-gray-950 shadow-sm transition";
                    btnSign.className = "flex-1 py-2 text-sm font-medium text-gray-500 dark:text-gray-400 rounded-md hover:text-gray-900 dark:hover:text-white transition";
                    document.getElementById('auth-btn').innerText = "Log In";
                } else {
                    btnSign.className = "flex-1 py-2 text-sm font-bold rounded-md bg-emerald-500 text-white dark:text-gray-950 shadow-sm transition";
                    btnLog.className = "flex-1 py-2 text-sm font-medium text-gray-500 dark:text-gray-400 rounded-md hover:text-gray-900 dark:hover:text-white transition";
                    document.getElementById('auth-btn').innerText = "Create Account";
                }
            }

            function logout() {
                localStorage.removeItem("finpulze_user");
                currentUserEmail = null;
                checkAuth();
            }

            async function executeAuth() {
                const email = document.getElementById('auth-email').value;
                const password = document.getElementById('auth-password').value;
                const name = document.getElementById('auth-name').value;
                const curr = document.getElementById('auth-currency').value;
                const errBox = document.getElementById('auth-error');
                errBox.classList.add('hidden');

                if (!email || !password) {
                    errBox.innerText = "Email and Password are required.";
                    errBox.classList.remove('hidden'); return;
                }

                const endpoint = authMode === 'login' ? '/api/v1/auth/login' : '/api/v1/auth/signup';
                const payload = { email, password, full_name: name, currency: curr };

                const res = await fetch(endpoint, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (res.ok) {
                    currentUserEmail = email;
                    localStorage.setItem("finpulze_user", email);
                    checkAuth();
                } else {
                    const error = await res.json();
                    errBox.innerText = error.detail || "Authentication failed.";
                    errBox.classList.remove('hidden');
                }
            }

            async function updateProfile() {
                const name = document.getElementById('prof-name').value;
                const curr = document.getElementById('prof-currency').value;
                const res = await fetch('/api/v1/profile', {
                    method: 'PUT', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: currentUserEmail, full_name: name, currency: curr })
                });
                if (res.ok) {
                    toggleModal('profile-modal');
                    syncDashboard();
                }
            }

            async function submitDeposit() {
                const amt = parseFloat(document.getElementById('deposit-amount').value);
                if (isNaN(amt) || amt <= 0) return alert("Strict Validation: Amount must be a valid number greater than 0.");

                const res = await fetch('/api/v1/wallet/fund', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: currentUserEmail, amount: amt })
                });
                
                if (res.ok) {
                    document.getElementById('deposit-amount').value = '';
                    toggleModal('deposit-modal');
                    syncDashboard();
                } else {
                    const err = await res.json();
                    alert(err.detail ? JSON.stringify(err.detail) : "Deposit failed");
                }
            }

            async function submitTransfer() {
                const amt = parseFloat(document.getElementById('transfer-amount').value);
                const acc = document.getElementById('transfer-acc').value;
                const bank = document.getElementById('transfer-bank').value;
                const note = document.getElementById('transfer-note').value;

                if (isNaN(amt) || amt <= 0) return alert("Strict Validation: Amount must be a valid number.");
                if (acc.length < 4) return alert("Validation: Account number must be at least 4 characters.");

                const res = await fetch('/api/v1/wallet/transfer', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        sender_email: currentUserEmail,
                        recipient_account: acc,
                        recipient_bank: bank || "External Bank",
                        amount: amt,
                        narration: note || "Transfer"
                    })
                });

                if (res.ok) {
                    document.getElementById('transfer-amount').value = '';
                    document.getElementById('transfer-acc').value = '';
                    toggleModal('transfer-modal');
                    syncDashboard();
                } else {
                    const err = await res.json();
                    alert(err.detail ? JSON.stringify(err.detail) : "Transfer failed");
                }
            }

            async function syncDashboard() {
                if (!currentUserEmail) return;
                
                // Fetch Wallet
                const walletRes = await fetch(`/api/v1/wallet?email=${currentUserEmail}`);
                if (!walletRes.ok) return logout();
                
                const data = await walletRes.json();
                const user = data.user;
                
                document.getElementById('balance-display').innerText = `${data.symbol} ${user.balance.toLocaleString('en-US', {minimumFractionDigits: 2})}`;
                document.getElementById('user-name').innerText = user.full_name;
                document.getElementById('user-account').innerText = `Acc: ${user.account_number} • ${user.currency}`;
                
                // Populate profile modal defaults
                document.getElementById('prof-name').value = user.full_name;
                document.getElementById('prof-currency').value = user.currency;

                // Fetch Transactions
                const txRes = await fetch(`/api/v1/transactions?email=${currentUserEmail}`);
                const transactions = await txRes.json();
                
                const tbody = document.getElementById('transactions-body');
                tbody.innerHTML = '';
                transactions.forEach(tx => {
                    const isCredit = tx.type === 'credit';
                    tbody.innerHTML += `
                        <tr class="hover:bg-gray-50 dark:hover:bg-gray-800/30 transition">
                            <td class="py-3 px-4 font-mono text-[10px] text-gray-500">${tx.id}</td>
                            <td class="py-3 px-4 text-gray-900 dark:text-white">${tx.description}<br><span class="text-[10px] text-gray-500">${tx.timestamp} • ${tx.counterparty}</span></td>
                            <td class="py-3 px-4 font-mono font-bold ${isCredit ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}">
                                ${isCredit ? '+' : '-'} ${tx.symbol}${tx.amount.toLocaleString('en-US', {minimumFractionDigits: 2})}
                            </td>
                            <td class="py-3 px-4"><span class="text-[9px] font-bold px-2 py-0.5 rounded border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 uppercase">${tx.status}</span></td>
                        </tr>`;
                });
            }

            function checkAuth() {
                if (currentUserEmail) {
                    document.getElementById('auth-view').classList.add('hidden');
                    document.getElementById('dashboard-view').classList.remove('hidden');
                    document.getElementById('dashboard-view').classList.add('flex');
                    syncDashboard();
                } else {
                    document.getElementById('auth-view').classList.remove('hidden');
                    document.getElementById('dashboard-view').classList.add('hidden');
                    document.getElementById('dashboard-view').classList.remove('flex');
                }
            }

            // Init
            checkAuth();
        </script>
    </body>
    </html>
    """