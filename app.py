from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session, g
import os, io, smtplib, hashlib, secrets
from datetime import datetime
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'velo-dev-secret-key')

# ── DATABASE ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras
    def get_db():
        if 'db' not in g:
            g.db = psycopg2.connect(DATABASE_URL)
            g.db.autocommit = False
        return g.db
    def db_cursor(db):
        return db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    def db_commit(db):
        db.commit()
    IS_POSTGRES = True
else:
    import sqlite3
    DB_PATH = os.path.join(os.path.dirname(__file__), 'velo.db')
    def get_db():
        if 'db' not in g:
            g.db = sqlite3.connect(DB_PATH)
            g.db.row_factory = sqlite3.Row
        return g.db
    def db_cursor(db):
        return db.cursor()
    def db_commit(db):
        db.commit()
    IS_POSTGRES = False

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()

def init_db():
    if IS_POSTGRES:
        db = psycopg2.connect(DATABASE_URL)
        cur = db.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password TEXT NOT NULL,
                gmail_address TEXT DEFAULT '',
                gmail_app_pass TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT DEFAULT '',
                address TEXT DEFAULT ''
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS invoices (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                invoice_num TEXT NOT NULL,
                client_id INTEGER NOT NULL REFERENCES clients(id),
                total_amount REAL DEFAULT 0,
                status TEXT DEFAULT 'Unpaid',
                date TEXT NOT NULL,
                due_date TEXT DEFAULT '',
                notes TEXT DEFAULT ''
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS invoice_items (
                id SERIAL PRIMARY KEY,
                invoice_id INTEGER NOT NULL REFERENCES invoices(id),
                description TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                line_total REAL NOT NULL
            )
        ''')
        db.commit()
        db.close()
    else:
        db = sqlite3.connect(DB_PATH)
        db.executescript(
            "CREATE TABLE IF NOT EXISTS users ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "email TEXT UNIQUE NOT NULL,"
            "name TEXT NOT NULL,"
            "password TEXT NOT NULL,"
            "gmail_address TEXT DEFAULT '',"
            "gmail_app_pass TEXT DEFAULT '',"
            "created_at TEXT DEFAULT (datetime('now')));"
            "CREATE TABLE IF NOT EXISTS clients ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "name TEXT NOT NULL,"
            "email TEXT NOT NULL,"
            "phone TEXT DEFAULT '',"
            "address TEXT DEFAULT '',"
            "FOREIGN KEY(user_id) REFERENCES users(id));"
            "CREATE TABLE IF NOT EXISTS invoices ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "invoice_num TEXT NOT NULL,"
            "client_id INTEGER NOT NULL,"
            "total_amount REAL DEFAULT 0,"
            "status TEXT DEFAULT 'Unpaid',"
            "date TEXT NOT NULL,"
            "due_date TEXT DEFAULT '',"
            "notes TEXT DEFAULT '',"
            "FOREIGN KEY(user_id) REFERENCES users(id),"
            "FOREIGN KEY(client_id) REFERENCES clients(id));"
            "CREATE TABLE IF NOT EXISTS invoice_items ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "invoice_id INTEGER NOT NULL,"
            "description TEXT NOT NULL,"
            "quantity REAL NOT NULL,"
            "price REAL NOT NULL,"
            "line_total REAL NOT NULL,"
            "FOREIGN KEY(invoice_id) REFERENCES invoices(id));"
        )
        try:
            db.execute("ALTER TABLE users ADD COLUMN gmail_address TEXT DEFAULT ''")
        except: pass
        try:
            db.execute("ALTER TABLE users ADD COLUMN gmail_app_pass TEXT DEFAULT ''")
        except: pass
        db.commit()
        db.close()

init_db()

# ── HELPERS ───────────────────────────────────────────────────────────────────

def hash_password(password):
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{h}"

def check_password(stored, provided):
    try:
        salt, h = stored.split(':')
        return hashlib.sha256((salt + provided).encode()).hexdigest() == h
    except:
        return False

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'info')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def uid():
    return session.get('user_id')

def fetchone(db, sql, params=()):
    cur = db_cursor(db)
    cur.execute(sql, params)
    return cur.fetchone()

def fetchall(db, sql, params=()):
    cur = db_cursor(db)
    cur.execute(sql, params)
    return cur.fetchall()

def execute(db, sql, params=()):
    cur = db_cursor(db)
    cur.execute(sql, params)
    db_commit(db)
    if IS_POSTGRES and 'RETURNING' in sql:
        return cur.fetchone()
    return cur

def scalar(db, sql, params=()):
    row = fetchone(db, sql, params)
    if row is None: return 0
    return list(row.values())[0] if IS_POSTGRES else row[0]

def ph():
    return '%s' if IS_POSTGRES else '?'

def P(n=1):
    p = ph()
    return ','.join([p]*n)

# ── AUTH ──────────────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET','POST'])
def register():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email    = request.form['email'].strip().lower()
        name     = request.form['name'].strip()
        password = request.form['password']
        if password != request.form['confirm']:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('register.html')
        db = get_db()
        if fetchone(db, f'SELECT id FROM users WHERE email={ph()}', (email,)):
            flash('An account with that email already exists.', 'error')
            return render_template('register.html')
        execute(db, f'INSERT INTO users (email,name,password) VALUES ({P(3)})', (email, name, hash_password(password)))
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        db    = get_db()
        user  = fetchone(db, f'SELECT * FROM users WHERE email={ph()}', (email,))
        if user and check_password(user['password'], request.form['password']):
            session['user_id']    = user['id']
            session['user_name']  = user['name']
            session['user_email'] = user['email']
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── DASHBOARD ─────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    db = get_db()
    total_revenue     = scalar(db, f"SELECT COALESCE(SUM(total_amount),0) FROM invoices WHERE user_id={ph()} AND status='Paid'",   (uid(),))
    total_outstanding = scalar(db, f"SELECT COALESCE(SUM(total_amount),0) FROM invoices WHERE user_id={ph()} AND status='Unpaid'", (uid(),))
    total_invoices    = scalar(db, f'SELECT COUNT(*) FROM invoices WHERE user_id={ph()}', (uid(),))
    total_clients     = scalar(db, f'SELECT COUNT(*) FROM clients  WHERE user_id={ph()}', (uid(),))
    rate   = (total_revenue / (total_revenue + total_outstanding) * 100) if (total_revenue + total_outstanding) > 0 else 0
    recent = fetchall(db, f'SELECT i.*,c.name FROM invoices i JOIN clients c ON i.client_id=c.id WHERE i.user_id={ph()} ORDER BY i.date DESC LIMIT 5', (uid(),))
    return render_template('dashboard.html', total_revenue=total_revenue, total_outstanding=total_outstanding,
        total_invoices=total_invoices, total_clients=total_clients, collection_rate=round(rate,1), recent_invoices=recent)

# ── SETTINGS ──────────────────────────────────────────────────────────────────

@app.route('/settings', methods=['GET','POST'])
@login_required
def settings():
    db = get_db()
    if request.method == 'POST':
        gmail   = request.form.get('gmail_address','').strip()
        apppass = request.form.get('gmail_app_pass','').strip()
        execute(db, f'UPDATE users SET gmail_address={ph()}, gmail_app_pass={ph()} WHERE id={ph()}',
                (gmail, apppass, uid()))
        flash('Settings saved!', 'success')
        return redirect(url_for('settings'))
    user = fetchone(db, f'SELECT * FROM users WHERE id={ph()}', (uid(),))
    return render_template('settings.html', user=user)

# ── CLIENTS ───────────────────────────────────────────────────────────────────

@app.route('/clients')
@login_required
def clients():
    db   = get_db()
    rows = fetchall(db, f'''SELECT c.*, COUNT(i.id) as invoice_count, COALESCE(SUM(i.total_amount),0) as total_billed
        FROM clients c LEFT JOIN invoices i ON c.id=i.client_id AND i.user_id={ph()}
        WHERE c.user_id={ph()} GROUP BY c.id''', (uid(), uid()))
    return render_template('clients.html', clients=rows)

@app.route('/clients/add', methods=['GET','POST'])
@login_required
def add_client():
    if request.method == 'POST':
        db = get_db()
        execute(db, f'INSERT INTO clients (user_id,name,email,phone,address) VALUES ({P(5)})',
                (uid(), request.form['name'], request.form['email'],
                 request.form.get('phone',''), request.form.get('address','')))
        flash('Client added!', 'success')
        return redirect(url_for('clients'))
    return render_template('client_form.html', client=None)

@app.route('/clients/edit/<int:client_id>', methods=['GET','POST'])
@login_required
def edit_client(client_id):
    db = get_db()
    client = fetchone(db, f'SELECT * FROM clients WHERE id={ph()} AND user_id={ph()}', (client_id, uid()))
    if not client: return redirect(url_for('clients'))
    if request.method == 'POST':
        execute(db, f'UPDATE clients SET name={ph()},email={ph()},phone={ph()},address={ph()} WHERE id={ph()} AND user_id={ph()}',
                (request.form['name'], request.form['email'], request.form.get('phone',''),
                 request.form.get('address',''), client_id, uid()))
        flash('Client updated!', 'success')
        return redirect(url_for('clients'))
    return render_template('client_form.html', client=client)

@app.route('/clients/delete/<int:client_id>', methods=['POST'])
@login_required
def delete_client(client_id):
    db = get_db()
    execute(db, f'DELETE FROM clients WHERE id={ph()} AND user_id={ph()}', (client_id, uid()))
    flash('Client deleted.', 'info')
    return redirect(url_for('clients'))

# ── INVOICES ──────────────────────────────────────────────────────────────────

@app.route('/invoices')
@login_required
def invoices():
    db = get_db()
    sf = request.args.get('status','all')
    q  = f'SELECT i.*,c.name as client_name FROM invoices i JOIN clients c ON i.client_id=c.id WHERE i.user_id={ph()}'
    p  = [uid()]
    if sf != 'all':
        q += f' AND i.status={ph()}'
        p.append(sf)
    rows = fetchall(db, q + ' ORDER BY i.date DESC', p)
    return render_template('invoices.html', invoices=rows, status_filter=sf)

@app.route('/invoices/create', methods=['GET','POST'])
@login_required
def create_invoice():
    db = get_db()
    client_list = fetchall(db, f'SELECT * FROM clients WHERE user_id={ph()} ORDER BY name', (uid(),))
    if request.method == 'POST':
        count   = scalar(db, f'SELECT COUNT(*) FROM invoices WHERE user_id={ph()}', (uid(),))
        inv_num = f"INV-{int(count) + 101}"
        if IS_POSTGRES:
            row = execute(db, f"INSERT INTO invoices (user_id,invoice_num,client_id,total_amount,status,date,due_date,notes) VALUES ({P(8)}) RETURNING id",
                       (uid(), inv_num, int(request.form['client_id']), 0, 'Unpaid',
                        datetime.now().strftime('%Y-%m-%d'),
                        request.form.get('due_date',''), request.form.get('notes','')))
            inv_id = row['id']
        else:
            cur = execute(db, f"INSERT INTO invoices (user_id,invoice_num,client_id,total_amount,status,date,due_date,notes) VALUES ({P(8)})",
                       (uid(), inv_num, int(request.form['client_id']), 0, 'Unpaid',
                        datetime.now().strftime('%Y-%m-%d'),
                        request.form.get('due_date',''), request.form.get('notes','')))
            inv_id = cur.lastrowid
        flash(f'{inv_num} created!', 'success')
        return redirect(url_for('invoice_detail', invoice_id=inv_id))
    return render_template('invoice_form.html', clients=client_list)

@app.route('/invoices/<int:invoice_id>')
@login_required
def invoice_detail(invoice_id):
    db  = get_db()
    inv = fetchone(db, f'SELECT i.*,c.name as client_name,c.email as client_email,c.phone as client_phone FROM invoices i JOIN clients c ON i.client_id=c.id WHERE i.id={ph()} AND i.user_id={ph()}', (invoice_id, uid()))
    if not inv: return redirect(url_for('invoices'))
    items = fetchall(db, f'SELECT * FROM invoice_items WHERE invoice_id={ph()}', (invoice_id,))
    return render_template('invoice_detail.html', invoice=inv, items=items)

@app.route('/invoices/<int:invoice_id>/add_item', methods=['POST'])
@login_required
def add_item(invoice_id):
    db    = get_db()
    qty   = float(request.form['quantity'])
    price = float(request.form['price'])
    execute(db, f'INSERT INTO invoice_items (invoice_id,description,quantity,price,line_total) VALUES ({P(5)})',
            (invoice_id, request.form['description'], qty, price, qty*price))
    total = scalar(db, f'SELECT COALESCE(SUM(line_total),0) FROM invoice_items WHERE invoice_id={ph()}', (invoice_id,))
    execute(db, f'UPDATE invoices SET total_amount={ph()} WHERE id={ph()} AND user_id={ph()}', (total, invoice_id, uid()))
    flash('Item added!', 'success')
    return redirect(url_for('invoice_detail', invoice_id=invoice_id))

@app.route('/invoices/<int:invoice_id>/delete_item/<int:item_id>', methods=['POST'])
@login_required
def delete_item(invoice_id, item_id):
    db = get_db()
    execute(db, f'DELETE FROM invoice_items WHERE id={ph()} AND invoice_id={ph()}', (item_id, invoice_id))
    total = scalar(db, f'SELECT COALESCE(SUM(line_total),0) FROM invoice_items WHERE invoice_id={ph()}', (invoice_id,))
    execute(db, f'UPDATE invoices SET total_amount={ph()} WHERE id={ph()} AND user_id={ph()}', (total, invoice_id, uid()))
    flash('Item removed.', 'info')
    return redirect(url_for('invoice_detail', invoice_id=invoice_id))

@app.route('/invoices/<int:invoice_id>/mark_paid', methods=['POST'])
@login_required
def mark_paid(invoice_id):
    db = get_db()
    execute(db, f"UPDATE invoices SET status='Paid' WHERE id={ph()} AND user_id={ph()}", (invoice_id, uid()))
    flash('Marked as Paid!', 'success')
    return redirect(url_for('invoice_detail', invoice_id=invoice_id))

@app.route('/invoices/<int:invoice_id>/mark_unpaid', methods=['POST'])
@login_required
def mark_unpaid(invoice_id):
    db = get_db()
    execute(db, f"UPDATE invoices SET status='Unpaid' WHERE id={ph()} AND user_id={ph()}", (invoice_id, uid()))
    flash('Marked as Unpaid.', 'info')
    return redirect(url_for('invoice_detail', invoice_id=invoice_id))

@app.route('/invoices/<int:invoice_id>/delete', methods=['POST'])
@login_required
def delete_invoice(invoice_id):
    db = get_db()
    execute(db, f'DELETE FROM invoice_items WHERE invoice_id={ph()}', (invoice_id,))
    execute(db, f'DELETE FROM invoices WHERE id={ph()} AND user_id={ph()}', (invoice_id, uid()))
    flash('Invoice deleted.', 'info')
    return redirect(url_for('invoices'))

# ── PDF ───────────────────────────────────────────────────────────────────────

def build_pdf(invoice_id):
    db    = get_db()
    inv   = fetchone(db, f'SELECT i.*,c.name as client_name,c.email as client_email,c.phone as client_phone FROM invoices i JOIN clients c ON i.client_id=c.id WHERE i.id={ph()} AND i.user_id={ph()}', (invoice_id, uid()))
    items = fetchall(db, f'SELECT * FROM invoice_items WHERE invoice_id={ph()}', (invoice_id,))
    user  = fetchone(db, f'SELECT name FROM users WHERE id={ph()}', (uid(),))

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_fill_color(15,15,15)
    pdf.rect(0,0,210,6,'F')
    pdf.set_y(14)
    pdf.set_font("helvetica",'B',32)
    pdf.set_text_color(15,15,15)
    pdf.cell(0,14,text="VELO",align='L',new_x=XPos.LMARGIN,new_y=YPos.NEXT)
    pdf.set_font("helvetica",size=9)
    pdf.set_text_color(140,140,140)
    pdf.cell(0,6,text=user['name'],align='L',new_x=XPos.LMARGIN,new_y=YPos.NEXT)
    pdf.ln(4)
    pdf.set_draw_color(220,220,220)
    pdf.line(10,pdf.get_y(),200,pdf.get_y())
    pdf.ln(6)
    pdf.set_font("helvetica",'B',10)
    pdf.set_text_color(15,15,15)
    pdf.cell(100,7,text=f"Invoice: {inv['invoice_num']}")
    pdf.cell(90,7,text=f"Date: {inv['date']}",align='R',new_x=XPos.LMARGIN,new_y=YPos.NEXT)
    if inv['due_date']:
        pdf.set_font("helvetica",size=9)
        pdf.set_text_color(140,140,140)
        pdf.cell(100,6,text="")
        pdf.cell(90,6,text=f"Due: {inv['due_date']}",align='R',new_x=XPos.LMARGIN,new_y=YPos.NEXT)
    pdf.ln(8)
    pdf.set_font("helvetica",size=8)
    pdf.set_text_color(140,140,140)
    pdf.cell(0,6,text="BILL TO",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
    pdf.set_font("helvetica",'B',12)
    pdf.set_text_color(15,15,15)
    pdf.cell(0,7,text=inv['client_name'],new_x=XPos.LMARGIN,new_y=YPos.NEXT)
    pdf.set_font("helvetica",size=10)
    pdf.set_text_color(80,80,80)
    pdf.cell(0,6,text=inv['client_email'],new_x=XPos.LMARGIN,new_y=YPos.NEXT)
    if inv['client_phone']:
        pdf.cell(0,6,text=inv['client_phone'],new_x=XPos.LMARGIN,new_y=YPos.NEXT)
    pdf.ln(10)
    pdf.set_fill_color(15,15,15)
    pdf.set_text_color(255,255,255)
    pdf.set_font("helvetica",'B',9)
    pdf.cell(95,9,text="DESCRIPTION",border=0,fill=True)
    pdf.cell(25,9,text="QTY",border=0,fill=True,align='C')
    pdf.cell(35,9,text="UNIT PRICE",border=0,fill=True,align='C')
    pdf.cell(35,9,text="TOTAL",border=0,fill=True,align='R',new_x=XPos.LMARGIN,new_y=YPos.NEXT)
    pdf.set_text_color(15,15,15)
    pdf.set_font("helvetica",size=10)
    fill = False
    for row in items:
        if fill:
            pdf.set_fill_color(248,248,248)
        else:
            pdf.set_fill_color(255,255,255)
        pdf.cell(95,9,text=str(row['description']),border=0,fill=fill)
        pdf.cell(25,9,text=str(int(row['quantity'])),border=0,fill=fill,align='C')
        pdf.cell(35,9,text=f"EUR {row['price']:.2f}",border=0,fill=fill,align='R')
        pdf.cell(35,9,text=f"EUR {row['line_total']:.2f}",border=0,fill=fill,align='R',new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        fill = not fill
    pdf.ln(2)
    pdf.line(10,pdf.get_y(),200,pdf.get_y())
    pdf.ln(4)
    pdf.set_font("helvetica",'B',13)
    pdf.cell(155,10,text="TOTAL DUE",align='R')
    pdf.cell(35,10,text=f"EUR {inv['total_amount']:.2f}",align='R',new_x=XPos.LMARGIN,new_y=YPos.NEXT)
    if inv['notes']:
        pdf.ln(10)
        pdf.set_font("helvetica",size=8)
        pdf.set_text_color(140,140,140)
        pdf.cell(0,6,text="NOTES",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        pdf.set_text_color(80,80,80)
        pdf.set_font("helvetica",size=10)
        pdf.cell(0,6,text=str(inv['notes']),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
    pdf.set_y(-40)
    pdf.set_font("helvetica",'B',26)
    if inv['status'] == 'Paid':
        pdf.set_text_color(0,180,90)
    else:
        pdf.set_text_color(210,60,60)
    pdf.cell(0,14,text=inv['status'].upper(),align='R')
    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf, inv

@app.route('/invoices/<int:invoice_id>/pdf')
@login_required
def generate_pdf(invoice_id):
    buf, inv = build_pdf(invoice_id)
    return send_file(buf, download_name=f"{inv['invoice_num']}.pdf", as_attachment=True, mimetype='application/pdf')

@app.route('/invoices/<int:invoice_id>/send_email', methods=['POST'])
@login_required
def send_email(invoice_id):
    to_email = request.form.get('to_email','').strip()
    if not to_email:
        flash('Enter a recipient email.', 'error')
        return redirect(url_for('invoice_detail', invoice_id=invoice_id))
    db   = get_db()
    user = fetchone(db, f'SELECT * FROM users WHERE id={ph()}', (uid(),))
    gmail_address  = user['gmail_address'] or ''
    gmail_app_pass = user['gmail_app_pass'] or ''
    if not gmail_address or not gmail_app_pass:
        flash('Please set up your Gmail credentials in Settings first.', 'error')
        return redirect(url_for('invoice_detail', invoice_id=invoice_id))
    try:
        buf, inv = build_pdf(invoice_id)
        msg = MIMEMultipart()
        msg['From']    = f"{user['name']} <{gmail_address}>"
        msg['To']      = to_email
        msg['Subject'] = f"Invoice {inv['invoice_num']} from {user['name']}"
        msg.attach(MIMEText(f"Hi,\n\nPlease find attached invoice {inv['invoice_num']}.\n\nThanks,\n{user['name']}", 'plain'))
        part = MIMEBase('application','octet-stream')
        part.set_payload(buf.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename=\"{inv['invoice_num']}.pdf\"")
        msg.attach(part)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(gmail_address, gmail_app_pass)
            s.sendmail(gmail_address, to_email, msg.as_string())
        flash(f'Invoice sent to {to_email}!', 'success')
    except smtplib.SMTPAuthenticationError as e:
        flash(f'Gmail error: {str(e)}', 'error')
    except Exception as e:
        flash(f'Failed to send: {str(e)}', 'error')
    return redirect(url_for('invoice_detail', invoice_id=invoice_id))

if __name__ == '__main__':
    app.run(debug=True)
