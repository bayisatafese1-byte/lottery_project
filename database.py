import sqlite3
import random
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lottery.db')
TOTAL_BOXES = 200
ROUND_DURATION_DAYS = 16

# Payment & Pricing configuration
CBE_ACCOUNT = "1000607576584"
TELEBIRR_ACCOUNT = "0906619022"

# Exact Pricing breakdown requested
TICKET_BASE_PRICE = "100.00 Birr"
SERVICE_FEE = "0.05 Birr"
TOTAL_TICKET_PRICE = "100.05 Birr"

# Default Rank Prizes
PRIZE_RANK1 = "100,000 ETB"
PRIZE_RANK2 = "30,000 ETB"
PRIZE_RANK3 = "15,000 ETB"

def get_db_connection():
    """Establish and return a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables with users, 200 boxes, payments, 3-spin ranks, and 16-day deadline."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Table for registered users / accounts
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            email TEXT,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')

    # Table for registered tickets
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ticket_number TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            box_number INTEGER,
            lucky_numbers TEXT,
            payment_method TEXT,
            payment_reference TEXT,
            payment_status TEXT DEFAULT 'Pending',
            base_price TEXT DEFAULT '100.00 Birr',
            service_fee TEXT DEFAULT '0.05 Birr',
            total_price TEXT DEFAULT '100.05 Birr',
            amount_paid TEXT DEFAULT '100.05 Birr',
            registered_at TEXT NOT NULL,
            is_winner INTEGER DEFAULT 0,
            rank INTEGER,
            prize TEXT,
            round INTEGER DEFAULT 1
        )
    ''')

    # Upgrade columns if table already exists without newer columns
    cursor.execute("PRAGMA table_info(tickets)")
    columns = [row['name'] for row in cursor.fetchall()]
    for col, col_type in [
        ('user_id', 'INTEGER'),
        ('box_number', 'INTEGER'),
        ('round', 'INTEGER DEFAULT 1'),
        ('payment_method', 'TEXT'),
        ('payment_reference', 'TEXT'),
        ('payment_status', "TEXT DEFAULT 'Pending'"),
        ('base_price', "TEXT DEFAULT '100.00 Birr'"),
        ('service_fee', "TEXT DEFAULT '0.05 Birr'"),
        ('total_price', "TEXT DEFAULT '100.05 Birr'"),
        ('amount_paid', "TEXT DEFAULT '100.05 Birr'"),
        ('rank', 'INTEGER'),
        ('prize', 'TEXT')
    ]:
        if col not in columns:
            cursor.execute(f"ALTER TABLE tickets ADD COLUMN {col} {col_type}")

    # Table for draw history supporting 3 ranks
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS draws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round INTEGER DEFAULT 1,
            draw_time TEXT NOT NULL,
            winning_numbers TEXT,
            trigger_type TEXT DEFAULT 'manual',
            
            rank1_box INTEGER,
            rank1_name TEXT,
            rank1_ticket TEXT,
            rank1_prize TEXT,
            
            rank2_box INTEGER,
            rank2_name TEXT,
            rank2_ticket TEXT,
            rank2_prize TEXT,
            
            rank3_box INTEGER,
            rank3_name TEXT,
            rank3_ticket TEXT,
            rank3_prize TEXT,
            
            winning_box INTEGER,
            winner_ticket_number TEXT,
            winner_name TEXT,
            prize_amount TEXT
        )
    ''')

    cursor.execute("PRAGMA table_info(draws)")
    draw_cols = [row['name'] for row in cursor.fetchall()]
    for col, col_type in [
        ('rank1_box', 'INTEGER'),
        ('rank1_name', 'TEXT'),
        ('rank1_ticket', 'TEXT'),
        ('rank1_prize', 'TEXT'),
        ('rank2_box', 'INTEGER'),
        ('rank2_name', 'TEXT'),
        ('rank2_ticket', 'TEXT'),
        ('rank2_prize', 'TEXT'),
        ('rank3_box', 'INTEGER'),
        ('rank3_name', 'TEXT'),
        ('rank3_ticket', 'TEXT'),
        ('rank3_prize', 'TEXT'),
        ('trigger_type', "TEXT DEFAULT 'manual'"),
        ('winning_box', 'INTEGER'),
        ('winner_ticket_number', 'TEXT'),
        ('winner_name', 'TEXT'),
        ('prize_amount', 'TEXT')
    ]:
        if col not in draw_cols:
            cursor.execute(f"ALTER TABLE draws ADD COLUMN {col} {col_type}")

    # Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')

    now_dt = datetime.now()
    deadline_dt = now_dt + timedelta(days=ROUND_DURATION_DAYS)

    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('admin_pin', '1234')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('active_round', '1')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('contact_phone', '0952458502')")
    cursor.execute(f"INSERT OR IGNORE INTO settings (key, value) VALUES ('cbe_account', '{CBE_ACCOUNT}')")
    cursor.execute(f"INSERT OR IGNORE INTO settings (key, value) VALUES ('telebirr_account', '{TELEBIRR_ACCOUNT}')")
    cursor.execute(f"INSERT OR IGNORE INTO settings (key, value) VALUES ('round_start_time', '{now_dt.strftime('%Y-%m-%d %H:%M:%S')}')")
    cursor.execute(f"INSERT OR IGNORE INTO settings (key, value) VALUES ('round_deadline', '{deadline_dt.strftime('%Y-%m-%d %H:%M:%S')}')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_drawn', '0')")
    cursor.execute(f"INSERT OR IGNORE INTO settings (key, value) VALUES ('prize_rank1', '{PRIZE_RANK1}')")
    cursor.execute(f"INSERT OR IGNORE INTO settings (key, value) VALUES ('prize_rank2', '{PRIZE_RANK2}')")
    cursor.execute(f"INSERT OR IGNORE INTO settings (key, value) VALUES ('prize_rank3', '{PRIZE_RANK3}')")

    conn.commit()
    conn.close()

# -------------------------------------------------------------
# User Account Management (Register & Login)
# -------------------------------------------------------------
def register_user(name, phone, password, email=None):
    """Register a new user account with secure hashed password."""
    phone_clean = phone.strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE phone = ?", (phone_clean,))
    if cursor.fetchone():
        conn.close()
        raise ValueError(f"Phone number {phone_clean} is already registered! Please log in to your account.")

    pwd_hash = generate_password_hash(password)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute('''
        INSERT INTO users (name, phone, email, password_hash, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (name.strip(), phone_clean, email.strip() if email else '', pwd_hash, created_at))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "id": user_id,
        "name": name.strip(),
        "phone": phone_clean,
        "email": email.strip() if email else ''
    }

def authenticate_user(phone, password):
    """Authenticate a returning user by phone number and password."""
    phone_clean = phone.strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE phone = ?", (phone_clean,))
    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user['password_hash'], password):
        return dict(user)
    return None

def get_user_by_id(user_id):
    """Fetch user account by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, phone, email, created_at FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_phone(phone):
    """Fetch user account by Phone."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, phone, email, created_at FROM users WHERE phone = ?", (phone.strip(),))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_tickets(phone_or_user_id):
    """Retrieve all tickets belonging to a specific user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if isinstance(phone_or_user_id, int):
        cursor.execute("SELECT * FROM tickets WHERE user_id = ? ORDER BY id DESC", (phone_or_user_id,))
    else:
        cursor.execute("SELECT * FROM tickets WHERE phone = ? ORDER BY id DESC", (str(phone_or_user_id).strip(),))
    tickets = cursor.fetchall()
    conn.close()
    return tickets

# -------------------------------------------------------------
# Settings & Deadline Helpers
# -------------------------------------------------------------
def get_setting(key, default=None):
    """Retrieve a value from the settings table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    """Set or update a value in the settings table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    ''', (key, str(value)))
    conn.commit()
    conn.close()

def get_active_round():
    """Get the currently active lottery round number."""
    val = get_setting('active_round', '1')
    return int(val)

def get_deadline_info():
    """Get 16-day deadline information and countdown metrics."""
    deadline_str = get_setting('round_deadline')
    if not deadline_str:
        deadline_dt = datetime.now() + timedelta(days=ROUND_DURATION_DAYS)
        set_setting('round_deadline', deadline_dt.strftime("%Y-%m-%d %H:%M:%S"))
    else:
        try:
            deadline_dt = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            deadline_dt = datetime.now() + timedelta(days=ROUND_DURATION_DAYS)

    now = datetime.now()
    remaining = (deadline_dt - now).total_seconds()
    is_expired = remaining <= 0

    if remaining < 0:
        remaining = 0

    days = int(remaining // 86400)
    hours = int((remaining % 86400) // 3600)
    minutes = int((remaining % 3600) // 60)
    seconds = int(remaining % 60)

    total_seconds = ROUND_DURATION_DAYS * 86400
    elapsed_seconds = max(0, total_seconds - remaining)
    percent_time = round((elapsed_seconds / total_seconds) * 100, 1) if total_seconds > 0 else 100.0

    return {
        "deadline_iso": deadline_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "deadline_display": deadline_dt.strftime("%b %d, %Y at %I:%M %p"),
        "days": days,
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds,
        "is_expired": is_expired,
        "percent_time": min(100.0, percent_time),
        "total_days": ROUND_DURATION_DAYS
    }

def generate_ticket_number():
    """Generate a unique 6-digit ticket code like LOT-782914."""
    prefix = "LOT"
    random_digits = "".join(random.choices("0123456789", k=6))
    return f"{prefix}-{random_digits}"

def get_all_boxes(round_num=None):
    """Return status of all 200 boxes (1 to 200) for the active round."""
    if round_num is None:
        round_num = get_active_round()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM tickets WHERE round = ? AND box_number IS NOT NULL AND box_number > 0",
        (round_num,)
    )
    booked_rows = cursor.fetchall()
    conn.close()

    booked_map = {}
    for row in booked_rows:
        booked_map[row['box_number']] = row

    boxes = []
    for i in range(1, TOTAL_BOXES + 1):
        if i in booked_map:
            t = booked_map[i]
            boxes.append({
                "box_number": i,
                "is_taken": True,
                "ticket_id": t['id'],
                "ticket_number": t['ticket_number'],
                "name": t['name'],
                "phone": t['phone'],
                "payment_method": t['payment_method'],
                "payment_reference": t['payment_reference'],
                "payment_status": t['payment_status'] if t['payment_status'] else 'Pending',
                "is_winner": t['is_winner'],
                "rank": t['rank'],
                "prize": t['prize']
            })
        else:
            boxes.append({
                "box_number": i,
                "is_taken": False,
                "ticket_id": None,
                "ticket_number": None,
                "name": None,
                "phone": None,
                "payment_method": None,
                "payment_reference": None,
                "payment_status": None,
                "is_winner": 0,
                "rank": None,
                "prize": None
            })

    return boxes

def get_available_box_numbers(round_num=None):
    """Return list of integers from 1 to 200 that are currently unreserved."""
    all_boxes = get_all_boxes(round_num)
    return [b['box_number'] for b in all_boxes if not b['is_taken']]

def is_box_available(box_number, round_num=None):
    """Check if a specific box number (1..200) is available."""
    try:
        box_num = int(box_number)
    except (ValueError, TypeError):
        return False

    if box_num < 1 or box_num > TOTAL_BOXES:
        return False

    if round_num is None:
        round_num = get_active_round()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM tickets WHERE round = ? AND box_number = ?",
        (round_num, box_num)
    )
    row = cursor.fetchone()
    conn.close()
    return row is None

def register_ticket(name, phone, email, lucky_numbers=None, box_number=None, payment_method=None, payment_ref=None, user_id=None):
    """Register a new participant and generate their ticket with fee breakdown (100.00 Birr + 0.05 Birr = 100.05 Birr)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    active_round = get_active_round()

    while True:
        ticket_number = generate_ticket_number()
        cursor.execute("SELECT id FROM tickets WHERE ticket_number = ?", (ticket_number,))
        if not cursor.fetchone():
            break

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    box_num_val = None
    if box_number is not None and str(box_number).strip().isdigit():
        candidate = int(box_number)
        if 1 <= candidate <= TOTAL_BOXES and is_box_available(candidate, active_round):
            box_num_val = candidate

    lucky_str = ""
    if lucky_numbers:
        if isinstance(lucky_numbers, list):
            lucky_str = ", ".join(f"{n:02d}" if isinstance(n, int) else str(n) for n in sorted(lucky_numbers))
        else:
            lucky_str = str(lucky_numbers).strip()

    payment_status = 'Pending' if payment_method else 'Unpaid'

    cursor.execute('''
        INSERT INTO tickets (user_id, ticket_number, name, phone, email, box_number, lucky_numbers, 
                             payment_method, payment_reference, payment_status, 
                             base_price, service_fee, total_price, amount_paid, 
                             registered_at, is_winner, round)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
    ''', (user_id, ticket_number, name.strip(), phone.strip(), email.strip() if email else '', 
          box_num_val, lucky_str, payment_method, payment_ref, payment_status, 
          TICKET_BASE_PRICE, SERVICE_FEE, TOTAL_TICKET_PRICE, TOTAL_TICKET_PRICE, 
          created_at, active_round))

    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()

    check_auto_draw_conditions()

    return {
        "id": ticket_id,
        "user_id": user_id,
        "ticket_number": ticket_number,
        "name": name,
        "phone": phone,
        "email": email,
        "box_number": box_num_val,
        "lucky_numbers": lucky_str,
        "payment_method": payment_method,
        "payment_reference": payment_ref,
        "payment_status": payment_status,
        "base_price": TICKET_BASE_PRICE,
        "service_fee": SERVICE_FEE,
        "total_price": TOTAL_TICKET_PRICE,
        "registered_at": created_at,
        "round": active_round
    }

def assign_box_to_ticket(ticket_id, box_number):
    """Assign or change the box number of an existing ticket."""
    box_num = int(box_number)
    if box_num < 1 or box_num > TOTAL_BOXES:
        raise ValueError(f"Box number must be between 1 and {TOTAL_BOXES}.")

    active_round = get_active_round()
    if not is_box_available(box_num, active_round):
        raise ValueError(f"Box #{box_num} is already taken! Please pick another box.")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tickets SET box_number = ? WHERE id = ? AND round = ?",
        (box_num, ticket_id, active_round)
    )
    conn.commit()
    conn.close()

    check_auto_draw_conditions()
    return True

def submit_ticket_payment(ticket_id, payment_method, payment_reference, amount=TOTAL_TICKET_PRICE):
    """Record payment details and reference code for a ticket."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE tickets 
        SET payment_method = ?, payment_reference = ?, amount_paid = ?, total_price = ?, payment_status = 'Pending'
        WHERE id = ?
    ''', (payment_method, payment_reference.strip(), amount, amount, ticket_id))
    conn.commit()
    conn.close()
    return True

def approve_ticket_payment(ticket_id):
    """Admin approves and confirms payment for a ticket."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE tickets SET payment_status = 'Confirmed' WHERE id = ?
    ''', (ticket_id,))
    conn.commit()
    conn.close()
    return True

def release_box(box_number, round_num=None):
    """Release a booked box back to the available pool."""
    if round_num is None:
        round_num = get_active_round()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tickets SET box_number = NULL WHERE round = ? AND box_number = ?",
        (round_num, int(box_number))
    )
    conn.commit()
    conn.close()

def get_ticket_by_id(ticket_id):
    """Fetch ticket record by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    ticket = cursor.fetchone()
    conn.close()
    return ticket

def get_ticket_by_number(ticket_number):
    """Fetch ticket record by Ticket Number."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tickets WHERE ticket_number = ?", (ticket_number.strip(),))
    ticket = cursor.fetchone()
    conn.close()
    return ticket

def search_tickets(query):
    """Search tickets by name, phone, ticket number, or box number."""
    conn = get_db_connection()
    cursor = conn.cursor()
    q = f"%{query.strip()}%"
    cursor.execute('''
        SELECT * FROM tickets 
        WHERE ticket_number LIKE ? 
           OR name LIKE ? 
           OR phone LIKE ? 
           OR payment_reference LIKE ? 
           OR CAST(box_number AS TEXT) = ?
        ORDER BY id DESC
    ''', (q, q, q, q, query.strip()))
    results = cursor.fetchall()
    conn.close()
    return results

def get_all_tickets(round_num=None):
    """Retrieve all tickets, optionally filtered by round."""
    if round_num is None:
        round_num = get_active_round()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tickets WHERE round = ? ORDER BY id DESC", (round_num,))
    tickets = cursor.fetchall()
    conn.close()
    return tickets

def conduct_3spin_draw(trigger_type="manual", prize1=None, prize2=None, prize3=None):
    """Conduct 3 spins to award Rank 1, Rank 2, and Rank 3."""
    active_round = get_active_round()
    prize1 = prize1 or get_setting('prize_rank1', PRIZE_RANK1)
    prize2 = prize2 or get_setting('prize_rank2', PRIZE_RANK2)
    prize3 = prize3 or get_setting('prize_rank3', PRIZE_RANK3)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM tickets WHERE round = ? AND box_number IS NOT NULL AND box_number > 0",
        (active_round,)
    )
    eligible = [dict(r) for r in cursor.fetchall()]

    balls = sorted(random.sample(range(1, 51), 5))
    winning_numbers_str = ", ".join(f"{b:02d}" for b in balls)

    winner_ranks = [
        {"rank": 1, "prize": prize1, "box": None, "name": None, "ticket": None, "id": None},
        {"rank": 2, "prize": prize2, "box": None, "name": None, "ticket": None, "id": None},
        {"rank": 3, "prize": prize3, "box": None, "name": None, "ticket": None, "id": None},
    ]

    available_pool = list(eligible)
    random.shuffle(available_pool)

    for i in range(3):
        if available_pool:
            chosen = available_pool.pop(0)
            winner_ranks[i]["box"] = chosen['box_number']
            winner_ranks[i]["name"] = chosen['name']
            winner_ranks[i]["ticket"] = chosen['ticket_number']
            winner_ranks[i]["id"] = chosen['id']

            cursor.execute('''
                UPDATE tickets 
                SET is_winner = 1, rank = ?, prize = ? 
                WHERE id = ?
            ''', (winner_ranks[i]["rank"], winner_ranks[i]["prize"], chosen['id']))
        else:
            rand_box = random.randint(1, TOTAL_BOXES)
            winner_ranks[i]["box"] = rand_box
            winner_ranks[i]["name"] = f"Box #{rand_box} (Unclaimed)"
            winner_ranks[i]["ticket"] = f"UNCLAIMED-{rand_box}"

    draw_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute('''
        INSERT INTO draws (
            round, draw_time, winning_numbers, trigger_type,
            rank1_box, rank1_name, rank1_ticket, rank1_prize,
            rank2_box, rank2_name, rank2_ticket, rank2_prize,
            rank3_box, rank3_name, rank3_ticket, rank3_prize,
            winning_box, winner_ticket_number, winner_name, prize_amount
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        active_round, draw_time, winning_numbers_str, trigger_type,
        winner_ranks[0]["box"], winner_ranks[0]["name"], winner_ranks[0]["ticket"], winner_ranks[0]["prize"],
        winner_ranks[1]["box"], winner_ranks[1]["name"], winner_ranks[1]["ticket"], winner_ranks[1]["prize"],
        winner_ranks[2]["box"], winner_ranks[2]["name"], winner_ranks[2]["ticket"], winner_ranks[2]["prize"],
        winner_ranks[0]["box"], winner_ranks[0]["ticket"], winner_ranks[0]["name"], winner_ranks[0]["prize"]
    ))

    cursor.execute("UPDATE settings SET value = '1' WHERE key = 'auto_drawn'")
    conn.commit()
    conn.close()

    return {
        "round": active_round,
        "draw_time": draw_time,
        "winning_numbers": winning_numbers_str,
        "trigger_type": trigger_type,
        "rank1": winner_ranks[0],
        "rank2": winner_ranks[1],
        "rank3": winner_ranks[2]
    }

def conduct_draw(prize_amount=None):
    """Alias for backwards compatibility: triggers the 3-spin draw."""
    return conduct_3spin_draw(trigger_type="manual", prize1=prize_amount)

def check_auto_draw_conditions():
    """Check if all 200 boxes booked or 16-day deadline passed."""
    auto_drawn = get_setting('auto_drawn', '0')
    if auto_drawn == '1':
        return None

    active_round = get_active_round()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM tickets WHERE round = ? AND box_number IS NOT NULL AND box_number > 0",
        (active_round,)
    )
    boxes_booked = cursor.fetchone()[0]
    conn.close()

    deadline_info = get_deadline_info()

    if boxes_booked >= TOTAL_BOXES:
        return conduct_3spin_draw(trigger_type="auto_200_boxes_completed")

    if deadline_info["is_expired"] and boxes_booked > 0:
        return conduct_3spin_draw(trigger_type="auto_16_day_deadline_reached")

    return None

def start_new_round():
    """Archive current round, start new round, reset 200 boxes, and reset 16-day clock."""
    conn = get_db_connection()
    cursor = conn.cursor()
    current_round = get_active_round()
    new_round = current_round + 1

    now_dt = datetime.now()
    new_deadline = now_dt + timedelta(days=ROUND_DURATION_DAYS)

    cursor.execute("UPDATE settings SET value = ? WHERE key = 'active_round'", (str(new_round),))
    cursor.execute("UPDATE settings SET value = '0' WHERE key = 'auto_drawn'")
    cursor.execute("UPDATE settings SET value = ? WHERE key = 'round_start_time'", (now_dt.strftime('%Y-%m-%d %H:%M:%S'),))
    cursor.execute("UPDATE settings SET value = ? WHERE key = 'round_deadline'", (new_deadline.strftime('%Y-%m-%d %H:%M:%S'),))

    conn.commit()
    conn.close()
    return new_round

def get_latest_draw():
    """Retrieve the most recent draw."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM draws ORDER BY id DESC LIMIT 1")
    draw = cursor.fetchone()
    conn.close()
    return draw

def get_all_draws():
    """Retrieve all past draws."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM draws ORDER BY id DESC")
    draws = cursor.fetchall()
    conn.close()
    return draws

def get_lottery_stats():
    """Calculate summary statistics for dashboard, countdown timer, and admin."""
    check_auto_draw_conditions()

    active_round = get_active_round()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM tickets WHERE round = ?", (active_round,))
    total_tickets = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM tickets WHERE round = ? AND box_number IS NOT NULL", (active_round,))
    boxes_booked = cursor.fetchone()[0]

    boxes_available = TOTAL_BOXES - boxes_booked

    cursor.execute("SELECT COUNT(*) FROM tickets WHERE round = ? AND is_winner > 0", (active_round,))
    total_winners = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM draws WHERE round = ?", (active_round,))
    total_draws = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM tickets WHERE round = ? AND payment_status = 'Pending'", (active_round,))
    pending_payments = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM tickets WHERE round = ? AND payment_status = 'Confirmed'", (active_round,))
    confirmed_payments = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    conn.close()

    percent_booked = round((boxes_booked / TOTAL_BOXES) * 100, 1) if TOTAL_BOXES > 0 else 0
    deadline_info = get_deadline_info()
    auto_drawn = (get_setting('auto_drawn', '0') == '1')

    return {
        "active_round": active_round,
        "total_boxes": TOTAL_BOXES,
        "boxes_booked": boxes_booked,
        "boxes_available": max(0, boxes_available),
        "percent_booked": percent_booked,
        "total_tickets": total_tickets,
        "total_winners": total_winners,
        "total_draws": total_draws,
        "total_users": total_users,
        "pending_payments": pending_payments,
        "confirmed_payments": confirmed_payments,
        "contact_phone": "0952458502",
        "cbe_account": CBE_ACCOUNT,
        "telebirr_account": TELEBIRR_ACCOUNT,
        "base_price": TICKET_BASE_PRICE,
        "service_fee": SERVICE_FEE,
        "ticket_price": TOTAL_TICKET_PRICE,
        "deadline": deadline_info,
        "auto_drawn": auto_drawn,
        "prize_rank1": get_setting('prize_rank1', PRIZE_RANK1),
        "prize_rank2": get_setting('prize_rank2', PRIZE_RANK2),
        "prize_rank3": get_setting('prize_rank3', PRIZE_RANK3)
    }

def seed_sample_data():
    """Add initial sample participants with assigned boxes and payments."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM tickets")
    count = cursor.fetchone()[0]
    conn.close()

    if count == 0:
        # Create a sample user account
        u1 = register_user("Abebe Kebede", "+251911223344", "pass123", "abebe@example.com")
        u2 = register_user("Almaz Tadesse", "+251922334455", "pass123", "almaz@example.com")
        u3 = register_user("Dawit Haile", "+251933445566", "pass123", "dawit@example.com")

        samples = [
            ("Abebe Kebede", "+251911223344", "abebe@example.com", "07, 14, 22, 35, 48", 7, "CBE", "FT26109923", "Confirmed", u1['id']),
            ("Almaz Tadesse", "+251922334455", "almaz@example.com", "03, 11, 29, 31, 50", 25, "Telebirr", "TX99482711", "Confirmed", u2['id']),
            ("Dawit Haile", "+251933445566", "dawit@example.com", "05, 18, 24, 38, 42", 88, "Telebirr", "TX11029384", "Pending", u3['id']),
        ]
        for name, phone, email, numbers, box, pay_method, pay_ref, pay_status, uid in samples:
            t = register_ticket(name, phone, email, numbers, box_number=box, payment_method=pay_method, payment_ref=pay_ref, user_id=uid)
            if pay_status == "Confirmed":
                approve_ticket_payment(t['id'])
