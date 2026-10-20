from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import database

app = Flask(__name__)
app.secret_key = 'bayisa_chance_super_secret_key_2026'

# Ensure database tables and sample data are initialized
database.init_db()
database.seed_sample_data()

CONTACT_PHONE = "0952458502"
CBE_ACCOUNT = "1000607576584"
TELEBIRR_ACCOUNT = "0906619022"
ADMIN_DEFAULT_PIN = "1234"

@app.context_processor
def inject_global_data():
    """Make common stats, deadline, pricing, payment accounts, and user available in all templates."""
    stats = database.get_lottery_stats()
    current_user = None
    if 'user_id' in session:
        current_user = database.get_user_by_id(session['user_id'])

    return dict(
        stats=stats,
        contact_phone=CONTACT_PHONE,
        cbe_account=CBE_ACCOUNT,
        telebirr_account=TELEBIRR_ACCOUNT,
        base_price=database.TICKET_BASE_PRICE,
        service_fee=database.SERVICE_FEE,
        ticket_price=database.TOTAL_TICKET_PRICE,
        deadline=stats['deadline'],
        current_user=current_user,
        is_admin_logged_in=session.get('is_admin', False)
    )

# -------------------------------------------------------------
# Home & Public Pages
# -------------------------------------------------------------
@app.route('/')
def index():
    """Home dashboard with 16-day countdown, 3-rank winners podium, and live boxes."""
    auto_result = database.check_auto_draw_conditions()
    if auto_result:
        flash(f"🎉 Round #{auto_result['round']} completed! The 3 Lucky Spins have chosen our Rank 1, 2, and 3 winners!", 'success')

    tickets = database.get_all_tickets()
    latest_draw = database.get_latest_draw()
    stats = database.get_lottery_stats()
    boxes = database.get_all_boxes()

    winning_balls = []
    if latest_draw and latest_draw['winning_numbers']:
        winning_balls = [b.strip() for b in latest_draw['winning_numbers'].split(',')]

    return render_template(
        'index.html',
        tickets=tickets,
        latest_draw=latest_draw,
        winning_balls=winning_balls,
        boxes=boxes,
        stats=stats
    )

@app.route('/boxes')
def boxes_grid():
    """Interactive 200-box visualizer grid showing available vs taken boxes."""
    boxes = database.get_all_boxes()
    stats = database.get_lottery_stats()
    return render_template('boxes.html', boxes=boxes, stats=stats)

# -------------------------------------------------------------
# User Authentication (Register & Login)
# -------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page for returning users."""
    if 'user_id' in session:
        flash('You are already logged in!', 'info')
        return redirect(url_for('my_tickets'))

    next_url = request.args.get('next', '')
    selected_box = request.args.get('box', type=int)

    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()

        if not phone or not password:
            flash('Please enter both phone number and password.', 'error')
            return render_template('login.html', phone=phone, next=next_url, selected_box=selected_box)

        user = database.authenticate_user(phone, password)
        if user:
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_phone'] = user['phone']
            flash(f"👋 Welcome back, {user['name']}!", 'success')

            if selected_box:
                return redirect(url_for('register', box=selected_box))
            if next_url:
                return redirect(next_url)
            return redirect(url_for('my_tickets'))
        else:
            flash('Invalid phone number or password. If you are new, please register below.', 'error')

    return render_template('login.html', next=next_url, selected_box=selected_box)

@app.route('/logout')
def logout():
    """Log out the current user session."""
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('user_phone', None)
    flash('You have logged out successfully.', 'info')
    return redirect(url_for('index'))

@app.route('/my-tickets')
def my_tickets():
    """Dashboard showing tickets purchased by the logged-in user."""
    if 'user_id' not in session:
        flash('Please log in to view your tickets.', 'info')
        return redirect(url_for('login', next=url_for('my_tickets')))

    user = database.get_user_by_id(session['user_id'])
    tickets = database.get_user_tickets(session['user_phone'])
    return render_template('my_tickets.html', user=user, tickets=tickets)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Registration page:
    - If user is already logged in, automatically pre-fills their profile.
    - If user is new, creates their account (with password) and ticket.
    - If user already has an account, prompts them to log in!
    """
    selected_box = request.args.get('box', type=int)
    logged_user = None
    if 'user_id' in session:
        logged_user = database.get_user_by_id(session['user_id'])

    if request.method == 'POST':
        # If user is already logged in, use their credentials
        if logged_user:
            name = logged_user['name']
            phone = logged_user['phone']
            email = logged_user['email']
            user_id = logged_user['id']
        else:
            name = request.form.get('name', '').strip()
            phone = request.form.get('phone', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()

            if not name or not phone or not password:
                flash('Please enter your full name, phone number, and a password to create your account!', 'error')
                return render_template('register.html', name=name, phone=phone, email=email, selected_box=selected_box)

            # Check if phone already registered
            existing_user = database.get_user_by_phone(phone)
            if existing_user:
                flash('An account with this phone number already exists! Please log in above.', 'error')
                return redirect(url_for('login', box=selected_box))

            try:
                new_user = database.register_user(name, phone, password, email)
                user_id = new_user['id']
                session['user_id'] = user_id
                session['user_name'] = name
                session['user_phone'] = phone
            except Exception as e:
                flash(str(e), 'error')
                return render_template('register.html', name=name, phone=phone, email=email, selected_box=selected_box)

        lucky_numbers = request.form.get('lucky_numbers', '').strip()
        box_number_input = request.form.get('box_number', '').strip()

        # Validate box number if specified
        box_num = None
        if box_number_input:
            try:
                box_num = int(box_number_input)
                if not (1 <= box_num <= 200):
                    flash('Box number must be between 1 and 200!', 'error')
                    return render_template('register.html', selected_box=selected_box)
                if not database.is_box_available(box_num):
                    flash(f'Box #{box_num} is already taken! Please choose another box.', 'error')
                    return render_template('register.html', selected_box=selected_box)
            except ValueError:
                flash('Invalid box number entered.', 'error')
                return render_template('register.html', selected_box=selected_box)

        try:
            ticket = database.register_ticket(name, phone, email, lucky_numbers, box_number=box_num, user_id=user_id)
            
            # If box was selected, take straight to payment!
            if box_num:
                flash(f"Box #{box_num} reserved! Please transfer the 100.05 Birr fee to finalize.", 'info')
                return redirect(url_for('payment', ticket_id=ticket['id']))

            # Otherwise, proceed to 200 boxes selection
            flash(f"🎉 Account ready! Now select your Lucky Box from the 200 boxes below.", 'info')
            return redirect(url_for('select_box', ticket_id=ticket['id']))
        except Exception as e:
            flash(f"Error during registration: {str(e)}", 'error')

    return render_template('register.html', selected_box=selected_box, logged_user=logged_user)

@app.route('/select-box/<int:ticket_id>', methods=['GET', 'POST'])
def select_box(ticket_id):
    """The 200-box selection screen shown after registration."""
    ticket = database.get_ticket_by_id(ticket_id)
    if not ticket:
        flash('Ticket not found.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        chosen_box = request.form.get('box_number', type=int)
        if not chosen_box or not (1 <= chosen_box <= 200):
            flash('Please select a valid box between 1 and 200.', 'error')
            return redirect(url_for('select_box', ticket_id=ticket_id))

        try:
            database.assign_box_to_ticket(ticket_id, chosen_box)
            flash(f"🎉 Box #{chosen_box} chosen! Now finalize by submitting the 100.05 Birr payment.", 'success')
            return redirect(url_for('payment', ticket_id=ticket_id))
        except Exception as e:
            flash(str(e), 'error')
            return redirect(url_for('select_box', ticket_id=ticket_id))

    boxes = database.get_all_boxes()
    return render_template('select_box.html', ticket=ticket, boxes=boxes)

@app.route('/payment/<int:ticket_id>', methods=['GET', 'POST'])
def payment(ticket_id):
    """Payment page: user transfers exactly 100.05 Birr (100.00 ticket + 0.05 fee) via CBE or Telebirr."""
    ticket = database.get_ticket_by_id(ticket_id)
    if not ticket:
        flash('Ticket not found.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        payment_method = request.form.get('payment_method', '').strip()
        payment_reference = request.form.get('payment_reference', '').strip()

        if payment_method not in ['CBE', 'Telebirr']:
            flash('Please select a valid payment method (CBE or Telebirr)!', 'error')
            return render_template('payment.html', ticket=ticket)

        if not payment_reference:
            flash('Please enter your Transaction Reference Number / Confirmation Code!', 'error')
            return render_template('payment.html', ticket=ticket, payment_method=payment_method)

        try:
            database.submit_ticket_payment(ticket_id, payment_method, payment_reference, amount=database.TOTAL_TICKET_PRICE)
            flash(f"🎉 Payment of {database.TOTAL_TICKET_PRICE} submitted! Your Box #{ticket['box_number']} is confirmed.", 'success')
            return redirect(url_for('view_ticket', ticket_id=ticket_id))
        except Exception as e:
            flash(f"Error submitting payment: {str(e)}", 'error')

    return render_template('payment.html', ticket=ticket)

@app.route('/ticket/<int:ticket_id>')
def view_ticket(ticket_id):
    """Digital Ticket Receipt slip with exact price breakdown and rank award status."""
    ticket = database.get_ticket_by_id(ticket_id)
    if not ticket:
        flash('Ticket not found.', 'error')
        return redirect(url_for('index'))
    return render_template('ticket.html', ticket=ticket)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    """Contact & Support page featuring phone 0952458502 and customer service."""
    if request.method == 'POST':
        c_name = request.form.get('name', '').strip()
        c_phone = request.form.get('phone', '').strip()
        c_message = request.form.get('message', '').strip()
        flash(f"Thank you {c_name}! Your message has been received. Our team will contact you at {c_phone}.", 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html', contact_phone=CONTACT_PHONE)

@app.route('/check', methods=['GET', 'POST'])
def check_ticket():
    """Ticket verification and status lookup by phone, ticket code, or box number."""
    search_query = request.args.get('q', '').strip()
    results = []
    if search_query:
        results = database.search_tickets(search_query)
    return render_template('check.html', query=search_query, results=results)

@app.route('/api/status')
def api_status():
    """API endpoint for live countdown clock and auto-draw poll."""
    stats = database.get_lottery_stats()
    return jsonify({
        "boxes_booked": stats["boxes_booked"],
        "total_boxes": stats["total_boxes"],
        "auto_drawn": stats["auto_drawn"],
        "deadline": stats["deadline"]
    })

# -------------------------------------------------------------
# Admin Area
# -------------------------------------------------------------
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    """Admin Dashboard for managing boxes, verifying payments, and draws."""
    if not session.get('is_admin'):
        if request.method == 'POST':
            pin = request.form.get('pin', '').strip()
            if pin == ADMIN_DEFAULT_PIN:
                session['is_admin'] = True
                flash('Welcome to Bayisa Chance Admin Dashboard!', 'success')
                return redirect(url_for('admin'))
            else:
                flash('Invalid Admin PIN. Please try again.', 'error')
        return render_template('admin_login.html')

    boxes = database.get_all_boxes()
    tickets = database.get_all_tickets()
    stats = database.get_lottery_stats()
    draws = database.get_all_draws()
    return render_template('admin.html', boxes=boxes, tickets=tickets, stats=stats, draws=draws)

@app.route('/admin/approve-payment/<int:ticket_id>', methods=['POST'])
def admin_approve_payment(ticket_id):
    """Admin approves and confirms payment for a ticket."""
    if not session.get('is_admin'):
        return redirect(url_for('admin'))

    ticket = database.get_ticket_by_id(ticket_id)
    if ticket:
        database.approve_ticket_payment(ticket_id)
        flash(f"✅ Payment for Ticket {ticket['ticket_number']} (Box #{ticket['box_number']}) approved!", 'success')
    return redirect(url_for('admin'))

@app.route('/admin/draw', methods=['POST'])
def admin_draw():
    """Admin triggers the 3-spin draw for Rank 1, Rank 2, and Rank 3."""
    if not session.get('is_admin'):
        flash('Unauthorized. Please log in as admin.', 'error')
        return redirect(url_for('admin'))

    prize1 = request.form.get('prize1', '100,000 ETB')
    prize2 = request.form.get('prize2', '30,000 ETB')
    prize3 = request.form.get('prize3', '15,000 ETB')

    try:
        draw_result = database.conduct_3spin_draw(trigger_type="manual_admin", prize1=prize1, prize2=prize2, prize3=prize3)
        r1 = draw_result['rank1']
        r2 = draw_result['rank2']
        r3 = draw_result['rank3']
        flash(
            f"🏆 3-SPIN DRAW COMPLETE! "
            f"🥇 Rank 1: {r1['name']} (Box #{r1['box']} - {r1['prize']}) | "
            f"🥈 Rank 2: {r2['name']} (Box #{r2['box']} - {r2['prize']}) | "
            f"🥉 Rank 3: {r3['name']} (Box #{r3['box']} - {r3['prize']})",
            'success'
        )
    except Exception as e:
        flash(f"Error executing draw: {str(e)}", 'error')

    return redirect(url_for('admin'))

@app.route('/admin/release-box', methods=['POST'])
def admin_release_box():
    """Admin frees up a box so someone else can claim it."""
    if not session.get('is_admin'):
        return redirect(url_for('admin'))

    box_number = request.form.get('box_number', type=int)
    if box_number:
        database.release_box(box_number)
        flash(f"Box #{box_number} has been released and is now available on the grid.", 'info')
    return redirect(url_for('admin'))

@app.route('/admin/new-round', methods=['POST'])
def admin_new_round():
    """Admin starts a brand new round with fresh 200 boxes and new 16-day deadline."""
    if not session.get('is_admin'):
        return redirect(url_for('admin'))

    new_round = database.start_new_round()
    flash(f"🎉 Round #{new_round} has officially started! Fresh 200 boxes opened and 16-day countdown reset.", 'success')
    return redirect(url_for('admin'))

@app.route('/admin/logout')
def admin_logout():
    """Log out of the admin panel."""
    session.pop('is_admin', None)
    flash('Admin logged out successfully.', 'info')
    return redirect(url_for('index'))

if __name__ == '__main__':
    print(f"🚀 Bayisa Chance Lottery running at http://127.0.0.1:5000 (Contact: {CONTACT_PHONE})")
    app.run(debug=True, host='127.0.0.1', port=5000)
