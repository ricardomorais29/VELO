"""
Velo Bootstrap Script
Run once:  python bootstrap_velo.py
Creates the full invoice_app/ folder on your Desktop.
"""

import os

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE    = os.path.join(DESKTOP, "velo")
TMPL    = os.path.join(BASE, "templates")
DATA    = os.path.join(BASE, "data")

os.makedirs(TMPL, exist_ok=True)
os.makedirs(DATA, exist_ok=True)

files = {}

# ── app.py ────────────────────────────────────────────────────────────────────
files["app.py"] = r'''from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import pandas as pd
import os
from datetime import datetime
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

app = Flask(__name__)
app.secret_key = 'velo-secret-key'
app.jinja_env.globals['enumerate'] = enumerate

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

# ── EMAIL CONFIG ──────────────────────────────────────────────────────────────
# 1. Go to myaccount.google.com → Security → 2-Step Verification → App Passwords
# 2. Generate a password for "Mail"
# 3. Paste your Gmail and that 16-char app password below
GMAIL_ADDRESS  = "your_email@gmail.com"   # <-- change this
GMAIL_APP_PASS = "xxxx xxxx xxxx xxxx"    # <-- change this (Gmail App Password)
YOUR_NAME      = "Velo"                   # <-- your name or business name
# ─────────────────────────────────────────────────────────────────────────────

def get_path(f): return os.path.join(DATA_DIR, f)

def initialize_system():
    os.makedirs(DATA_DIR, exist_ok=True)
    schema = {
        'clients.csv':       ['client_id','name','email','phone','address'],
        'invoices.csv':      ['invoice_id','client_id','total_amount','status','date','due_date','notes'],
        'invoice_items.csv': ['invoice_id','description','quantity','price','line_total']
    }
    for file, cols in schema.items():
        path = get_path(file)
        if not os.path.exists(path):
            pd.DataFrame(columns=cols).to_csv(path, index=False)

initialize_system()

def read_csv(n):  return pd.read_csv(get_path(n))
def write_csv(df, n): df.to_csv(get_path(n), index=False)

def build_pdf_bytes(invoice_id):
    invoices  = read_csv('invoices.csv')
    items     = read_csv('invoice_items.csv')
    clients   = read_csv('clients.csv')
    inv_data      = invoices[invoices['invoice_id'] == invoice_id].iloc[0]
    client_data   = clients[clients['client_id'] == inv_data['client_id']].iloc[0]
    invoice_items = items[items['invoice_id'] == invoice_id]

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Top accent bar
    pdf.set_fill_color(15, 15, 15)
    pdf.rect(0, 0, 210, 6, 'F')

    pdf.set_y(14)
    pdf.set_font("helvetica", 'B', 32)
    pdf.set_text_color(15, 15, 15)
    pdf.cell(0, 14, text="VELO", align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("helvetica", size=9)
    pdf.set_text_color(140, 140, 140)
    pdf.cell(0, 6, text="Invoice & Billing", align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)

    # Divider
    pdf.set_draw_color(220, 220, 220)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    # Meta row
    pdf.set_font("helvetica", 'B', 10)
    pdf.set_text_color(15, 15, 15)
    pdf.cell(100, 7, text=f"Invoice #: {invoice_id}")
    pdf.cell(90, 7, text=f"Date: {inv_data['date']}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if str(inv_data.get('due_date', '')) not in ['', 'nan']:
        pdf.set_font("helvetica", size=10)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(100, 6, text="")
        pdf.cell(90, 6, text=f"Due: {inv_data['due_date']}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(8)

    # Bill to
    pdf.set_font("helvetica", size=8)
    pdf.set_text_color(140, 140, 140)
    pdf.cell(0, 6, text="BILL TO", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("helvetica", 'B', 12)
    pdf.set_text_color(15, 15, 15)
    pdf.cell(0, 7, text=str(client_data['name']), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("helvetica", size=10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 6, text=str(client_data['email']), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if str(client_data.get('phone', '')) not in ['', 'nan']:
        pdf.cell(0, 6, text=str(client_data['phone']), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(10)

    # Table header
    pdf.set_fill_color(15, 15, 15)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", 'B', 9)
    pdf.cell(95, 9, text="DESCRIPTION", border=0, fill=True, padding=3)
    pdf.cell(25, 9, text="QTY",         border=0, fill=True, align='C')
    pdf.cell(35, 9, text="UNIT PRICE",  border=0, fill=True, align='C')
    pdf.cell(35, 9, text="TOTAL",       border=0, fill=True, align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_text_color(15, 15, 15)
    pdf.set_font("helvetica", size=10)
    fill = False
    for _, row in invoice_items.iterrows():
        pdf.set_fill_color(248, 248, 248) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.cell(95, 9, text=str(row['description']),              border=0, fill=fill)
        pdf.cell(25, 9, text=str(int(row['quantity'])),            border=0, fill=fill, align='C')
        pdf.cell(35, 9, text=f"${float(row['price']):.2f}",        border=0, fill=fill, align='R')
        pdf.cell(35, 9, text=f"${float(row['line_total']):.2f}",   border=0, fill=fill, align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        fill = not fill

    # Bottom line + total
    pdf.ln(2)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)
    pdf.set_font("helvetica", 'B', 13)
    pdf.cell(155, 10, text="TOTAL DUE", align='R')
    pdf.cell(35, 10, text=f"${float(inv_data['total_amount']):.2f}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if str(inv_data.get('notes', '')) not in ['', 'nan']:
        pdf.ln(10)
        pdf.set_font("helvetica", size=8)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(0, 6, text="NOTES", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(80, 80, 80)
        pdf.set_font("helvetica", size=10)
        pdf.cell(0, 6, text=str(inv_data['notes']), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Status watermark
    pdf.set_y(-40)
    pdf.set_font("helvetica", 'B', 26)
    pdf.set_text_color(0, 180, 90) if inv_data['status'] == 'Paid' else pdf.set_text_color(210, 60, 60)
    pdf.cell(0, 14, text=f"● {inv_data['status'].upper()}", align='R')

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf

# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    invoices = read_csv('invoices.csv')
    clients  = read_csv('clients.csv')
    total_revenue     = float(invoices[invoices['status'] == 'Paid']['total_amount'].sum())
    total_outstanding = float(invoices[invoices['status'] == 'Unpaid']['total_amount'].sum())
    total_invoices    = len(invoices)
    total_clients     = len(clients)
    rate = (total_revenue / (total_revenue + total_outstanding) * 100) if (total_revenue + total_outstanding) > 0 else 0
    recent = invoices.merge(clients[['client_id','name']], on='client_id', how='left') if len(invoices) > 0 and len(clients) > 0 else invoices
    if 'name' not in recent.columns: recent['name'] = ''
    recent = recent.sort_values('date', ascending=False).head(5).to_dict('records') if len(recent) > 0 else []
    return render_template('dashboard.html',
        total_revenue=total_revenue, total_outstanding=total_outstanding,
        total_invoices=total_invoices, total_clients=total_clients,
        collection_rate=round(rate, 1), recent_invoices=recent)

@app.route('/clients')
def clients():
    df = read_csv('clients.csv')
    invoices = read_csv('invoices.csv')
    client_list = df.to_dict('records')
    for c in client_list:
        inv = invoices[invoices['client_id'] == c['client_id']]
        c['invoice_count'] = len(inv)
        c['total_billed']  = float(inv['total_amount'].sum())
    return render_template('clients.html', clients=client_list)

@app.route('/clients/add', methods=['GET','POST'])
def add_client():
    if request.method == 'POST':
        df = read_csv('clients.csv')
        new_id = int(df['client_id'].max() + 1) if len(df) > 0 else 1
        row = pd.DataFrame([[new_id, request.form['name'], request.form['email'],
                              request.form.get('phone',''), request.form.get('address','')]],
                           columns=['client_id','name','email','phone','address'])
        write_csv(pd.concat([df, row], ignore_index=True), 'clients.csv')
        flash(f"Client '{request.form['name']}' added!", 'success')
        return redirect(url_for('clients'))
    return render_template('client_form.html', client=None)

@app.route('/clients/edit/<int:client_id>', methods=['GET','POST'])
def edit_client(client_id):
    df = read_csv('clients.csv')
    if request.method == 'POST':
        for col in ['name','email','phone','address']:
            df.loc[df['client_id'] == client_id, col] = request.form.get(col, '')
        write_csv(df, 'clients.csv')
        flash('Client updated!', 'success')
        return redirect(url_for('clients'))
    return render_template('client_form.html', client=df[df['client_id'] == client_id].iloc[0].to_dict())

@app.route('/clients/delete/<int:client_id>', methods=['POST'])
def delete_client(client_id):
    df = read_csv('clients.csv')
    write_csv(df[df['client_id'] != client_id], 'clients.csv')
    flash('Client deleted.', 'info')
    return redirect(url_for('clients'))

@app.route('/invoices')
def invoices():
    inv = read_csv('invoices.csv')
    clients = read_csv('clients.csv')
    sf = request.args.get('status', 'all')
    if sf != 'all': inv = inv[inv['status'] == sf]
    if len(inv) > 0 and len(clients) > 0:
        merged = inv.merge(clients[['client_id','name']], on='client_id', how='left')
    else:
        merged = inv
        if 'name' not in merged.columns: merged['name'] = ''
    merged = merged.sort_values('date', ascending=False) if len(merged) > 0 else merged
    return render_template('invoices.html', invoices=merged.to_dict('records'), status_filter=sf)

@app.route('/invoices/create', methods=['GET','POST'])
def create_invoice():
    clients = read_csv('clients.csv')
    if request.method == 'POST':
        inv_df = read_csv('invoices.csv')
        inv_id = f"INV-{len(inv_df) + 101}"
        row = pd.DataFrame([[inv_id, int(request.form['client_id']), 0.0, 'Unpaid',
                              datetime.now().strftime('%Y-%m-%d'),
                              request.form.get('due_date',''),
                              request.form.get('notes','')]],
                           columns=['invoice_id','client_id','total_amount','status','date','due_date','notes'])
        write_csv(pd.concat([inv_df, row], ignore_index=True), 'invoices.csv')
        flash(f'Invoice {inv_id} created!', 'success')
        return redirect(url_for('invoice_detail', invoice_id=inv_id))
    return render_template('invoice_form.html', clients=clients.to_dict('records'))

@app.route('/invoices/<invoice_id>')
def invoice_detail(invoice_id):
    inv_df   = read_csv('invoices.csv')
    clients  = read_csv('clients.csv')
    items_df = read_csv('invoice_items.csv')
    inv    = inv_df[inv_df['invoice_id'] == invoice_id].iloc[0].to_dict()
    client = clients[clients['client_id'] == inv['client_id']].iloc[0].to_dict()
    items  = items_df[items_df['invoice_id'] == invoice_id].to_dict('records')
    return render_template('invoice_detail.html', invoice=inv, client=client, items=items)

@app.route('/invoices/<invoice_id>/add_item', methods=['POST'])
def add_item(invoice_id):
    qty, price = float(request.form['quantity']), float(request.form['price'])
    items_df = read_csv('invoice_items.csv')
    row = pd.DataFrame([[invoice_id, request.form['description'], qty, price, qty*price]],
                       columns=['invoice_id','description','quantity','price','line_total'])
    items_df = pd.concat([items_df, row], ignore_index=True)
    write_csv(items_df, 'invoice_items.csv')
    inv_df = read_csv('invoices.csv')
    inv_df.loc[inv_df['invoice_id'] == invoice_id, 'total_amount'] = \
        items_df[items_df['invoice_id'] == invoice_id]['line_total'].sum()
    write_csv(inv_df, 'invoices.csv')
    flash('Item added!', 'success')
    return redirect(url_for('invoice_detail', invoice_id=invoice_id))

@app.route('/invoices/<invoice_id>/delete_item/<int:item_index>', methods=['POST'])
def delete_item(invoice_id, item_index):
    items_df = read_csv('invoice_items.csv')
    inv_items = items_df[items_df['invoice_id'] == invoice_id]
    items_df = items_df.drop(inv_items.index[item_index]).reset_index(drop=True)
    write_csv(items_df, 'invoice_items.csv')
    inv_df = read_csv('invoices.csv')
    inv_df.loc[inv_df['invoice_id'] == invoice_id, 'total_amount'] = \
        items_df[items_df['invoice_id'] == invoice_id]['line_total'].sum()
    write_csv(inv_df, 'invoices.csv')
    flash('Item removed.', 'info')
    return redirect(url_for('invoice_detail', invoice_id=invoice_id))

@app.route('/invoices/<invoice_id>/mark_paid', methods=['POST'])
def mark_paid(invoice_id):
    inv_df = read_csv('invoices.csv')
    inv_df.loc[inv_df['invoice_id'] == invoice_id, 'status'] = 'Paid'
    write_csv(inv_df, 'invoices.csv')
    flash(f'{invoice_id} marked as Paid!', 'success')
    return redirect(url_for('invoice_detail', invoice_id=invoice_id))

@app.route('/invoices/<invoice_id>/mark_unpaid', methods=['POST'])
def mark_unpaid(invoice_id):
    inv_df = read_csv('invoices.csv')
    inv_df.loc[inv_df['invoice_id'] == invoice_id, 'status'] = 'Unpaid'
    write_csv(inv_df, 'invoices.csv')
    flash(f'{invoice_id} marked as Unpaid.', 'info')
    return redirect(url_for('invoice_detail', invoice_id=invoice_id))

@app.route('/invoices/<invoice_id>/delete', methods=['POST'])
def delete_invoice(invoice_id):
    inv_df = read_csv('invoices.csv')
    write_csv(inv_df[inv_df['invoice_id'] != invoice_id], 'invoices.csv')
    items_df = read_csv('invoice_items.csv')
    write_csv(items_df[items_df['invoice_id'] != invoice_id], 'invoice_items.csv')
    flash(f'{invoice_id} deleted.', 'info')
    return redirect(url_for('invoices'))

@app.route('/invoices/<invoice_id>/pdf')
def generate_pdf(invoice_id):
    buf = build_pdf_bytes(invoice_id)
    return send_file(buf, download_name=f"{invoice_id}.pdf", as_attachment=True, mimetype='application/pdf')

@app.route('/invoices/<invoice_id>/send_email', methods=['POST'])
def send_email(invoice_id):
    to_email = request.form.get('to_email', '').strip()
    if not to_email:
        flash('Please enter a recipient email.', 'error')
        return redirect(url_for('invoice_detail', invoice_id=invoice_id))

    try:
        pdf_buf = build_pdf_bytes(invoice_id)

        msg = MIMEMultipart()
        msg['From']    = f"{YOUR_NAME} <{GMAIL_ADDRESS}>"
        msg['To']      = to_email
        msg['Subject'] = f"Invoice {invoice_id} from {YOUR_NAME}"

        body = f"""Hi,

Please find attached invoice {invoice_id}.

If you have any questions, feel free to reply to this email.

Thanks,
{YOUR_NAME}
"""
        msg.attach(MIMEText(body, 'plain'))

        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_buf.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{invoice_id}.pdf"')
        msg.attach(part)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
            server.sendmail(GMAIL_ADDRESS, to_email, msg.as_string())

        flash(f'Invoice sent to {to_email}!', 'success')
    except smtplib.SMTPAuthenticationError:
        flash('Gmail authentication failed. Check your App Password in app.py.', 'error')
    except Exception as e:
        flash(f'Failed to send email: {str(e)}', 'error')

    return redirect(url_for('invoice_detail', invoice_id=invoice_id))

if __name__ == '__main__':
    app.run(debug=True)
'''

# ── requirements.txt ──────────────────────────────────────────────────────────
files["requirements.txt"] = """flask>=3.0.0
pandas>=2.0.0
fpdf2>=2.7.0
gunicorn>=21.0.0
"""

# ── base.html ─────────────────────────────────────────────────────────────────
files["templates/base.html"] = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{% block title %}Velo{% endblock %}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg:       #fafafa;
      --surface:  #ffffff;
      --border:   #e8e8e8;
      --border2:  #f0f0f0;
      --ink:      #111111;
      --ink2:     #555555;
      --ink3:     #999999;
      --accent:   #111111;
      --green:    #16a34a;
      --green-bg: #f0fdf4;
      --red:      #dc2626;
      --red-bg:   #fef2f2;
      --amber:    #d97706;
      --amber-bg: #fffbeb;
      --radius:   10px;
      --shadow:   0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { font-size: 15px; }
    body { font-family: 'Geist', -apple-system, sans-serif; background: var(--bg); color: var(--ink); min-height: 100vh; display: flex; }

    /* SIDEBAR */
    .sidebar { width: 220px; min-height: 100vh; background: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; position: fixed; top: 0; left: 0; bottom: 0; z-index: 100; }
    .sidebar-brand { padding: 24px 20px 20px; border-bottom: 1px solid var(--border2); }
    .sidebar-brand h1 { font-size: 1.35rem; font-weight: 600; letter-spacing: -0.5px; color: var(--ink); }
    .sidebar-brand h1 span { color: var(--ink3); font-weight: 300; }
    .sidebar-brand p { font-size: 0.7rem; color: var(--ink3); margin-top: 3px; letter-spacing: 0.5px; }
    .sidebar nav { padding: 16px 12px; flex: 1; }
    .nav-section { font-size: 0.62rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1.5px; color: var(--ink3); padding: 0 10px; margin: 14px 0 5px; }
    .nav-link { display: flex; align-items: center; gap: 9px; padding: 8px 10px; border-radius: 7px; color: var(--ink2); text-decoration: none; font-size: 0.875rem; font-weight: 450; transition: all 0.12s; margin-bottom: 1px; }
    .nav-link:hover { background: var(--bg); color: var(--ink); }
    .nav-link.active { background: var(--ink); color: #fff; }
    .nav-icon { font-size: 0.95rem; width: 18px; text-align: center; opacity: 0.7; }
    .nav-link.active .nav-icon { opacity: 1; }

    /* MAIN */
    .main { margin-left: 220px; flex: 1; display: flex; flex-direction: column; min-height: 100vh; }
    .topbar { background: var(--surface); border-bottom: 1px solid var(--border); padding: 14px 28px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 50; gap: 12px; }
    .topbar h2 { font-size: 1.05rem; font-weight: 600; letter-spacing: -0.3px; }
    .topbar-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .content { padding: 28px; }

    /* FLASH */
    .flash-list { list-style: none; margin-bottom: 18px; }
    .flash-list li { padding: 10px 16px; border-radius: var(--radius); font-size: 0.85rem; font-weight: 450; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
    .flash-success { background: var(--green-bg); color: var(--green); border: 1px solid #bbf7d0; }
    .flash-info    { background: #f5f5f5; color: var(--ink2); border: 1px solid var(--border); }
    .flash-error   { background: var(--red-bg); color: var(--red); border: 1px solid #fecaca; }

    /* STATS */
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px,1fr)); gap: 16px; margin-bottom: 28px; }
    .stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px 22px; box-shadow: var(--shadow); }
    .stat-label { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: var(--ink3); margin-bottom: 8px; }
    .stat-value { font-size: 1.8rem; font-weight: 600; letter-spacing: -1px; color: var(--ink); line-height: 1; }
    .stat-sub { font-size: 0.75rem; color: var(--ink3); margin-top: 5px; }
    .stat-card.highlight { background: var(--ink); }
    .stat-card.highlight .stat-label { color: rgba(255,255,255,0.5); }
    .stat-card.highlight .stat-value { color: #fff; }
    .stat-card.highlight .stat-sub { color: rgba(255,255,255,0.4); }

    /* TABLE */
    .table-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; box-shadow: var(--shadow); }
    .table-header { padding: 16px 22px; border-bottom: 1px solid var(--border2); display: flex; align-items: center; justify-content: space-between; }
    .table-header h3 { font-size: 0.95rem; font-weight: 600; }
    table { width: 100%; border-collapse: collapse; }
    th { text-align: left; padding: 9px 22px; font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: var(--ink3); background: var(--bg); border-bottom: 1px solid var(--border); }
    td { padding: 12px 22px; font-size: 0.865rem; border-bottom: 1px solid var(--border2); vertical-align: middle; }
    tr:last-child td { border-bottom: none; }
    tbody tr:hover td { background: #fafafa; }

    /* BADGES */
    .badge { display: inline-flex; align-items: center; gap: 5px; padding: 2px 9px; border-radius: 20px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }
    .badge::before { content: '●'; font-size: 0.5rem; }
    .badge-paid   { background: var(--green-bg); color: var(--green); }
    .badge-unpaid { background: var(--red-bg);   color: var(--red);   }

    /* BUTTONS */
    .btn { display: inline-flex; align-items: center; gap: 5px; padding: 8px 16px; border-radius: 7px; font-family: 'Geist', sans-serif; font-size: 0.84rem; font-weight: 500; cursor: pointer; border: none; text-decoration: none; transition: all 0.12s; white-space: nowrap; }
    .btn-primary  { background: var(--ink); color: #fff; }
    .btn-primary:hover  { background: #333; }
    .btn-outline  { background: transparent; color: var(--ink); border: 1px solid var(--border); }
    .btn-outline:hover  { background: var(--bg); }
    .btn-danger   { background: var(--red-bg); color: var(--red); border: 1px solid #fecaca; }
    .btn-danger:hover   { background: #fee2e2; }
    .btn-green    { background: var(--green); color: #fff; }
    .btn-green:hover    { background: #15803d; }
    .btn-sm { padding: 5px 11px; font-size: 0.78rem; }

    /* FORMS */
    .form-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 28px; box-shadow: var(--shadow); max-width: 580px; }
    .form-group { margin-bottom: 18px; }
    label { display: block; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px; color: var(--ink3); margin-bottom: 6px; }
    input, select, textarea { width: 100%; padding: 9px 12px; border: 1px solid var(--border); border-radius: 7px; font-family: 'Geist', sans-serif; font-size: 0.875rem; background: var(--bg); color: var(--ink); transition: border 0.12s, box-shadow 0.12s; }
    input:focus, select:focus, textarea:focus { outline: none; border-color: var(--ink); background: #fff; box-shadow: 0 0 0 3px rgba(0,0,0,0.06); }
    textarea { resize: vertical; min-height: 80px; }
    .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }

    /* INVOICE DETAIL */
    .detail-grid { display: grid; grid-template-columns: 1fr 300px; gap: 22px; }
    .detail-meta { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 22px; box-shadow: var(--shadow); }
    .meta-row { display: flex; justify-content: space-between; align-items: center; padding: 9px 0; border-bottom: 1px solid var(--border2); font-size: 0.865rem; }
    .meta-row:last-child { border-bottom: none; }
    .meta-key { color: var(--ink3); font-size: 0.8rem; }
    .meta-val { font-weight: 500; }
    .total-row td { font-weight: 600; font-size: 0.95rem; background: var(--bg); }

    /* EMAIL PANEL */
    .email-panel { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 22px; box-shadow: var(--shadow); margin-top: 18px; }
    .email-panel h4 { font-size: 0.9rem; font-weight: 600; margin-bottom: 14px; }
    .email-row { display: flex; gap: 8px; }
    .email-row input { flex: 1; }

    /* FILTER TABS */
    .filter-tabs { display: flex; gap: 6px; margin-bottom: 18px; }
    .filter-tab { padding: 6px 14px; border-radius: 20px; font-size: 0.8rem; font-weight: 500; text-decoration: none; color: var(--ink2); border: 1px solid var(--border); transition: all 0.12s; }
    .filter-tab:hover { border-color: var(--ink); color: var(--ink); }
    .filter-tab.active { background: var(--ink); color: #fff; border-color: var(--ink); }

    .empty-state { text-align: center; padding: 56px 20px; color: var(--ink3); }
    .empty-state strong { font-size: 0.95rem; color: var(--ink2); }
    .empty-state p { font-size: 0.85rem; margin-top: 6px; }

    .mono { font-family: 'Geist Mono', monospace; }
    .divider { border: none; border-top: 1px solid var(--border2); margin: 20px 0; }
  </style>
</head>
<body>
  <aside class="sidebar">
    <div class="sidebar-brand">
      <h1>Velo<span>.</span></h1>
      <p>Invoice Tracker</p>
    </div>
    <nav>
      <div class="nav-section">Main</div>
      <a href="{{ url_for('dashboard') }}" class="nav-link {% if request.endpoint == 'dashboard' %}active{% endif %}">
        <span class="nav-icon">⊞</span> Dashboard
      </a>
      <div class="nav-section">Manage</div>
      <a href="{{ url_for('invoices') }}" class="nav-link {% if 'invoice' in request.endpoint %}active{% endif %}">
        <span class="nav-icon">≡</span> Invoices
      </a>
      <a href="{{ url_for('clients') }}" class="nav-link {% if 'client' in request.endpoint %}active{% endif %}">
        <span class="nav-icon">○</span> Clients
      </a>
    </nav>
  </aside>
  <div class="main">
    <div class="topbar">
      <h2>{% block page_title %}Dashboard{% endblock %}</h2>
      <div class="topbar-actions">{% block topbar_actions %}{% endblock %}</div>
    </div>
    <div class="content">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}<ul class="flash-list">
          {% for cat, msg in messages %}<li class="flash-{{ cat }}">{{ msg }}</li>{% endfor %}
        </ul>{% endif %}
      {% endwith %}
      {% block content %}{% endblock %}
    </div>
  </div>
</body>
</html>
"""

# ── dashboard.html ────────────────────────────────────────────────────────────
files["templates/dashboard.html"] = """{% extends "base.html" %}
{% block title %}Dashboard — Velo{% endblock %}
{% block page_title %}Dashboard{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('create_invoice') }}" class="btn btn-primary">+ New Invoice</a>{% endblock %}
{% block content %}
<div class="stats-grid">
  <div class="stat-card highlight">
    <div class="stat-label">Collected</div>
    <div class="stat-value">${{ "%.2f"|format(total_revenue) }}</div>
    <div class="stat-sub">Paid invoices</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Outstanding</div>
    <div class="stat-value">${{ "%.2f"|format(total_outstanding) }}</div>
    <div class="stat-sub">Awaiting payment</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Collection Rate</div>
    <div class="stat-value">{{ collection_rate }}%</div>
    <div class="stat-sub">Of total billed</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Invoices</div>
    <div class="stat-value">{{ total_invoices }}</div>
    <div class="stat-sub">{{ total_clients }} clients</div>
  </div>
</div>
<div class="table-card">
  <div class="table-header">
    <h3>Recent Activity</h3>
    <a href="{{ url_for('invoices') }}" class="btn btn-outline btn-sm">View all</a>
  </div>
  {% if recent_invoices %}
  <table>
    <thead><tr><th>Invoice</th><th>Client</th><th>Date</th><th>Amount</th><th>Status</th><th></th></tr></thead>
    <tbody>
      {% for inv in recent_invoices %}
      <tr>
        <td class="mono" style="font-size:0.82rem">{{ inv.invoice_id }}</td>
        <td>{{ inv.get('name','—') }}</td>
        <td style="color:var(--ink3)">{{ inv.date }}</td>
        <td><strong>${{ "%.2f"|format(inv.total_amount) }}</strong></td>
        <td><span class="badge badge-{{ inv.status|lower }}">{{ inv.status }}</span></td>
        <td><a href="{{ url_for('invoice_detail', invoice_id=inv.invoice_id) }}" class="btn btn-outline btn-sm">Open →</a></td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty-state"><strong>No invoices yet</strong><p>Create your first invoice to get started.</p></div>
  {% endif %}
</div>
{% endblock %}
"""

# ── clients.html ──────────────────────────────────────────────────────────────
files["templates/clients.html"] = """{% extends "base.html" %}
{% block title %}Clients — Velo{% endblock %}
{% block page_title %}Clients{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('add_client') }}" class="btn btn-primary">+ Add Client</a>{% endblock %}
{% block content %}
<div class="table-card">
  <div class="table-header"><h3>All Clients</h3><span style="color:var(--ink3);font-size:0.82rem;">{{ clients|length }} total</span></div>
  {% if clients %}
  <table>
    <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Invoices</th><th>Billed</th><th></th></tr></thead>
    <tbody>
      {% for c in clients %}
      <tr>
        <td><strong>{{ c.name }}</strong><br><span style="color:var(--ink3);font-size:0.75rem;">#{{ c.client_id }}</span></td>
        <td>{{ c.email }}</td>
        <td>{{ c.phone if c.phone and c.phone != 'nan' else '—' }}</td>
        <td style="color:var(--ink3)">{{ c.invoice_count }}</td>
        <td><strong>${{ "%.2f"|format(c.total_billed) }}</strong></td>
        <td style="display:flex;gap:6px;padding:12px 22px;">
          <a href="{{ url_for('edit_client', client_id=c.client_id) }}" class="btn btn-outline btn-sm">Edit</a>
          <form action="{{ url_for('delete_client', client_id=c.client_id) }}" method="post" onsubmit="return confirm('Delete this client?')">
            <button class="btn btn-danger btn-sm">Delete</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty-state"><strong>No clients yet</strong><p>Add your first client to start creating invoices.</p></div>
  {% endif %}
</div>
{% endblock %}
"""

# ── client_form.html ──────────────────────────────────────────────────────────
files["templates/client_form.html"] = """{% extends "base.html" %}
{% block title %}{{ 'Edit' if client else 'New' }} Client — Velo{% endblock %}
{% block page_title %}{{ 'Edit' if client else 'New' }} Client{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('clients') }}" class="btn btn-outline">← Back</a>{% endblock %}
{% block content %}
<div class="form-card">
  <form method="post">
    <div class="form-group"><label>Name</label><input type="text" name="name" value="{{ client.name if client else '' }}" required placeholder="Client or company name"></div>
    <div class="form-row">
      <div class="form-group"><label>Email</label><input type="email" name="email" value="{{ client.email if client else '' }}" required placeholder="email@example.com"></div>
      <div class="form-group"><label>Phone</label><input type="text" name="phone" value="{{ client.phone if client and client.phone != 'nan' else '' }}" placeholder="+1 555 000 0000"></div>
    </div>
    <div class="form-group"><label>Address</label><textarea name="address" placeholder="Street, City, State">{{ client.address if client and client.address != 'nan' else '' }}</textarea></div>
    <div style="display:flex;gap:8px;">
      <button type="submit" class="btn btn-primary">{{ 'Save Changes' if client else 'Add Client' }}</button>
      <a href="{{ url_for('clients') }}" class="btn btn-outline">Cancel</a>
    </div>
  </form>
</div>
{% endblock %}
"""

# ── invoices.html ─────────────────────────────────────────────────────────────
files["templates/invoices.html"] = """{% extends "base.html" %}
{% block title %}Invoices — Velo{% endblock %}
{% block page_title %}Invoices{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('create_invoice') }}" class="btn btn-primary">+ New Invoice</a>{% endblock %}
{% block content %}
<div class="filter-tabs">
  <a href="{{ url_for('invoices') }}" class="filter-tab {% if status_filter=='all' %}active{% endif %}">All</a>
  <a href="{{ url_for('invoices',status='Unpaid') }}" class="filter-tab {% if status_filter=='Unpaid' %}active{% endif %}">Unpaid</a>
  <a href="{{ url_for('invoices',status='Paid') }}" class="filter-tab {% if status_filter=='Paid' %}active{% endif %}">Paid</a>
</div>
<div class="table-card">
  <div class="table-header"><h3>{{ status_filter|capitalize if status_filter!='all' else 'All' }} Invoices</h3><span style="color:var(--ink3);font-size:0.82rem;">{{ invoices|length }}</span></div>
  {% if invoices %}
  <table>
    <thead><tr><th>Invoice</th><th>Client</th><th>Date</th><th>Due</th><th>Amount</th><th>Status</th><th></th></tr></thead>
    <tbody>
      {% for inv in invoices %}
      <tr>
        <td class="mono" style="font-size:0.82rem">{{ inv.invoice_id }}</td>
        <td>{{ inv.get('name','—') }}</td>
        <td style="color:var(--ink3)">{{ inv.date }}</td>
        <td style="color:var(--ink3)">{{ inv.due_date if inv.due_date and inv.due_date!='nan' else '—' }}</td>
        <td><strong>${{ "%.2f"|format(inv.total_amount) }}</strong></td>
        <td><span class="badge badge-{{ inv.status|lower }}">{{ inv.status }}</span></td>
        <td style="display:flex;gap:6px;padding:12px 22px;">
          <a href="{{ url_for('invoice_detail',invoice_id=inv.invoice_id) }}" class="btn btn-outline btn-sm">Open</a>
          <a href="{{ url_for('generate_pdf',invoice_id=inv.invoice_id) }}" class="btn btn-outline btn-sm">PDF</a>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty-state"><strong>No invoices</strong><p>{% if status_filter!='all' %}No {{ status_filter|lower }} invoices found.{% else %}Create your first invoice.{% endif %}</p></div>
  {% endif %}
</div>
{% endblock %}
"""

# ── invoice_form.html ─────────────────────────────────────────────────────────
files["templates/invoice_form.html"] = """{% extends "base.html" %}
{% block title %}New Invoice — Velo{% endblock %}
{% block page_title %}New Invoice{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('invoices') }}" class="btn btn-outline">← Back</a>{% endblock %}
{% block content %}
<div class="form-card">
  <form method="post">
    <div class="form-group">
      <label>Client</label>
      <select name="client_id" required>
        <option value="">Select a client</option>
        {% for c in clients %}<option value="{{ c.client_id }}">{{ c.name }}</option>{% endfor %}
      </select>
      {% if not clients %}<p style="color:var(--red);font-size:0.8rem;margin-top:5px;">No clients yet. <a href="{{ url_for('add_client') }}" style="color:var(--red)">Add one first →</a></p>{% endif %}
    </div>
    <div class="form-group"><label>Due Date</label><input type="date" name="due_date"></div>
    <div class="form-group"><label>Notes</label><textarea name="notes" placeholder="Payment terms, project details…"></textarea></div>
    <div style="display:flex;gap:8px;">
      <button type="submit" class="btn btn-primary" {% if not clients %}disabled{% endif %}>Create Invoice</button>
      <a href="{{ url_for('invoices') }}" class="btn btn-outline">Cancel</a>
    </div>
  </form>
</div>
{% endblock %}
"""

# ── invoice_detail.html ───────────────────────────────────────────────────────
files["templates/invoice_detail.html"] = """{% extends "base.html" %}
{% block title %}{{ invoice.invoice_id }} — Velo{% endblock %}
{% block page_title %}<span class="mono">{{ invoice.invoice_id }}</span>{% endblock %}
{% block topbar_actions %}
  <a href="{{ url_for('invoices') }}" class="btn btn-outline">← Back</a>
  <a href="{{ url_for('generate_pdf', invoice_id=invoice.invoice_id) }}" class="btn btn-outline">↓ PDF</a>
  {% if invoice.status == 'Unpaid' %}
    <form action="{{ url_for('mark_paid', invoice_id=invoice.invoice_id) }}" method="post" style="display:inline">
      <button class="btn btn-green">✓ Mark Paid</button>
    </form>
  {% else %}
    <form action="{{ url_for('mark_unpaid', invoice_id=invoice.invoice_id) }}" method="post" style="display:inline">
      <button class="btn btn-outline">↩ Mark Unpaid</button>
    </form>
  {% endif %}
  <form action="{{ url_for('delete_invoice', invoice_id=invoice.invoice_id) }}" method="post" style="display:inline" onsubmit="return confirm('Delete this invoice?')">
    <button class="btn btn-danger">Delete</button>
  </form>
{% endblock %}
{% block content %}
<div class="detail-grid">
  <div>
    <!-- Line Items -->
    <div class="table-card" style="margin-bottom:20px;">
      <div class="table-header"><h3>Line Items</h3><span class="badge badge-{{ invoice.status|lower }}">{{ invoice.status }}</span></div>
      <table>
        <thead><tr><th>Description</th><th>Qty</th><th>Unit Price</th><th>Total</th><th></th></tr></thead>
        <tbody>
          {% for item in items %}
          <tr>
            <td>{{ item.description }}</td>
            <td>{{ item.quantity|int }}</td>
            <td>${{ "%.2f"|format(item.price) }}</td>
            <td>${{ "%.2f"|format(item.line_total) }}</td>
            <td>
              <form action="{{ url_for('delete_item', invoice_id=invoice.invoice_id, item_index=loop.index0) }}" method="post" onsubmit="return confirm('Remove item?')">
                <button class="btn btn-danger btn-sm">✕</button>
              </form>
            </td>
          </tr>
          {% else %}
          <tr><td colspan="5" style="text-align:center;color:var(--ink3);padding:28px;font-size:0.85rem;">No items yet — add one below.</td></tr>
          {% endfor %}
          {% if items %}
          <tr class="total-row">
            <td colspan="3" style="text-align:right;">Total</td>
            <td>${{ "%.2f"|format(invoice.total_amount) }}</td>
            <td></td>
          </tr>
          {% endif %}
        </tbody>
      </table>
    </div>

    <!-- Add Item -->
    <div class="form-card">
      <h4 style="font-size:0.9rem;font-weight:600;margin-bottom:16px;">Add Line Item</h4>
      <form method="post" action="{{ url_for('add_item', invoice_id=invoice.invoice_id) }}">
        <div class="form-group"><label>Description</label><input type="text" name="description" required placeholder="e.g. Design work — 3 hours"></div>
        <div class="form-row">
          <div class="form-group"><label>Quantity</label><input type="number" name="quantity" min="1" step="1" value="1" required></div>
          <div class="form-group"><label>Unit Price ($)</label><input type="number" name="price" min="0" step="0.01" required placeholder="0.00"></div>
        </div>
        <button type="submit" class="btn btn-primary">+ Add Item</button>
      </form>
    </div>

    <!-- Send Email -->
    <div class="email-panel">
      <h4>Send Invoice by Email</h4>
      <p style="font-size:0.82rem;color:var(--ink3);margin-bottom:12px;">The PDF will be attached automatically. You can send to any email — not just the client's saved one.</p>
      <form method="post" action="{{ url_for('send_email', invoice_id=invoice.invoice_id) }}">
        <div class="email-row">
          <input type="email" name="to_email" placeholder="recipient@example.com" value="{{ client.email }}" required>
          <button type="submit" class="btn btn-primary">Send ↗</button>
        </div>
      </form>
    </div>
  </div>

  <!-- Right sidebar -->
  <div>
    <div class="detail-meta">
      <h4 style="font-size:0.88rem;font-weight:600;margin-bottom:14px;">Invoice Details</h4>
      <div class="meta-row"><span class="meta-key">Number</span><span class="meta-val mono" style="font-size:0.82rem">{{ invoice.invoice_id }}</span></div>
      <div class="meta-row"><span class="meta-key">Status</span><span class="badge badge-{{ invoice.status|lower }}">{{ invoice.status }}</span></div>
      <div class="meta-row"><span class="meta-key">Created</span><span class="meta-val">{{ invoice.date }}</span></div>
      <div class="meta-row"><span class="meta-key">Due</span><span class="meta-val">{{ invoice.due_date if invoice.due_date and invoice.due_date!='nan' else '—' }}</span></div>
      <div class="meta-row"><span class="meta-key">Total</span><span class="meta-val" style="font-size:1rem">${{ "%.2f"|format(invoice.total_amount) }}</span></div>
    </div>

    <div class="detail-meta" style="margin-top:16px;">
      <h4 style="font-size:0.88rem;font-weight:600;margin-bottom:14px;">Bill To</h4>
      <div class="meta-row"><span class="meta-key">Name</span><span class="meta-val">{{ client.name }}</span></div>
      <div class="meta-row"><span class="meta-key">Email</span><span class="meta-val" style="font-size:0.82rem">{{ client.email }}</span></div>
      {% if client.phone and client.phone != 'nan' %}
      <div class="meta-row"><span class="meta-key">Phone</span><span class="meta-val">{{ client.phone }}</span></div>
      {% endif %}
    </div>

    {% if invoice.notes and invoice.notes != 'nan' %}
    <div class="detail-meta" style="margin-top:16px;">
      <h4 style="font-size:0.88rem;font-weight:600;margin-bottom:10px;">Notes</h4>
      <p style="font-size:0.84rem;color:var(--ink2);line-height:1.6;">{{ invoice.notes }}</p>
    </div>
    {% endif %}
  </div>
</div>
{% endblock %}
"""

# ── Write everything ───────────────────────────────────────────────────────────
for rel_path, content in files.items():
    full_path = os.path.join(BASE, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

print("=" * 55)
print("  ✅  Velo created at:")
print(f"      {BASE}")
print("=" * 55)
print()
print("  BEFORE running, open velo/app.py and set:")
print("    GMAIL_ADDRESS  = 'your_email@gmail.com'")
print("    GMAIL_APP_PASS = 'xxxx xxxx xxxx xxxx'")
print("    YOUR_NAME      = 'Your Name'")
print()
print("  Then:")
print("  1. pip install flask pandas fpdf2")
print("  2. cd ~/Desktop/velo && python app.py")
print("  3. Open http://127.0.0.1:5000")
print("=" * 55)
