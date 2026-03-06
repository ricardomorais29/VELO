"""
InvoiceFlow Bootstrap Script
Run this once from anywhere:  python bootstrap_invoiceflow.py
It will create the full invoice_app/ folder on your Desktop.
"""

import os

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE    = os.path.join(DESKTOP, "invoice_app")
TMPL    = os.path.join(BASE, "templates")
DATA    = os.path.join(BASE, "data")

os.makedirs(TMPL, exist_ok=True)
os.makedirs(DATA, exist_ok=True)

# ── Write each file ────────────────────────────────────────────────────────────

files = {}

# ── app.py ────────────────────────────────────────────────────────────────────
files["app.py"] = '''from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import pandas as pd
import os
from datetime import datetime
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import io

app = Flask(__name__)
app.secret_key = \'invoice-tracker-secret-key\'
app.jinja_env.globals[\'enumerate\'] = enumerate

DATA_DIR = os.path.join(os.path.dirname(__file__), \'data\')

def get_path(filename):
    return os.path.join(DATA_DIR, filename)

def initialize_system():
    os.makedirs(DATA_DIR, exist_ok=True)
    files = {
        \'clients.csv\':       [\'client_id\', \'name\', \'email\', \'phone\', \'address\'],
        \'invoices.csv\':      [\'invoice_id\', \'client_id\', \'total_amount\', \'status\', \'date\', \'due_date\', \'notes\'],
        \'invoice_items.csv\': [\'invoice_id\', \'description\', \'quantity\', \'price\', \'line_total\']
    }
    for file, columns in files.items():
        path = get_path(file)
        if not os.path.exists(path):
            pd.DataFrame(columns=columns).to_csv(path, index=False)

initialize_system()

def read_csv(name):
    return pd.read_csv(get_path(name))

def write_csv(df, name):
    df.to_csv(get_path(name), index=False)

@app.route(\'/\')
def dashboard():
    invoices = read_csv(\'invoices.csv\')
    clients  = read_csv(\'clients.csv\')
    total_revenue     = float(invoices[invoices[\'status\'] == \'Paid\'][\'total_amount\'].sum())
    total_outstanding = float(invoices[invoices[\'status\'] == \'Unpaid\'][\'total_amount\'].sum())
    total_invoices    = len(invoices)
    total_clients     = len(clients)
    collection_rate   = (total_revenue / (total_revenue + total_outstanding) * 100) if (total_revenue + total_outstanding) > 0 else 0
    recent = invoices.merge(clients[[\'client_id\', \'name\']], on=\'client_id\', how=\'left\') if len(invoices) > 0 and len(clients) > 0 else invoices
    recent = recent.sort_values(\'date\', ascending=False).head(5).to_dict(\'records\') if len(recent) > 0 else []
    return render_template(\'dashboard.html\',
        total_revenue=total_revenue, total_outstanding=total_outstanding,
        total_invoices=total_invoices, total_clients=total_clients,
        collection_rate=round(collection_rate, 1), recent_invoices=recent)

@app.route(\'/clients\')
def clients():
    df = read_csv(\'clients.csv\')
    invoices = read_csv(\'invoices.csv\')
    client_list = df.to_dict(\'records\')
    for c in client_list:
        inv = invoices[invoices[\'client_id\'] == c[\'client_id\']]
        c[\'invoice_count\'] = len(inv)
        c[\'total_billed\']  = float(inv[\'total_amount\'].sum())
    return render_template(\'clients.html\', clients=client_list)

@app.route(\'/clients/add\', methods=[\'GET\', \'POST\'])
def add_client():
    if request.method == \'POST\':
        df = read_csv(\'clients.csv\')
        new_id = int(df[\'client_id\'].max() + 1) if len(df) > 0 else 1
        new_row = pd.DataFrame([[new_id, request.form[\'name\'], request.form[\'email\'],
                                  request.form.get(\'phone\', \'\'), request.form.get(\'address\', \'\')]],
                               columns=[\'client_id\', \'name\', \'email\', \'phone\', \'address\'])
        df = pd.concat([df, new_row], ignore_index=True)
        write_csv(df, \'clients.csv\')
        flash(f"Client \'{request.form[\'name\']}\' added!", \'success\')
        return redirect(url_for(\'clients\'))
    return render_template(\'client_form.html\', client=None)

@app.route(\'/clients/edit/<int:client_id>\', methods=[\'GET\', \'POST\'])
def edit_client(client_id):
    df = read_csv(\'clients.csv\')
    if request.method == \'POST\':
        for col, key in [(\'name\', \'name\'), (\'email\', \'email\'), (\'phone\', \'phone\'), (\'address\', \'address\')]:
            df.loc[df[\'client_id\'] == client_id, col] = request.form.get(key, \'\')
        write_csv(df, \'clients.csv\')
        flash(\'Client updated!\', \'success\')
        return redirect(url_for(\'clients\'))
    client = df[df[\'client_id\'] == client_id].iloc[0].to_dict()
    return render_template(\'client_form.html\', client=client)

@app.route(\'/clients/delete/<int:client_id>\', methods=[\'POST\'])
def delete_client(client_id):
    df = read_csv(\'clients.csv\')
    df = df[df[\'client_id\'] != client_id]
    write_csv(df, \'clients.csv\')
    flash(\'Client deleted.\', \'info\')
    return redirect(url_for(\'clients\'))

@app.route(\'/invoices\')
def invoices():
    inv = read_csv(\'invoices.csv\')
    clients = read_csv(\'clients.csv\')
    status_filter = request.args.get(\'status\', \'all\')
    if status_filter != \'all\':
        inv = inv[inv[\'status\'] == status_filter]
    if len(inv) > 0 and len(clients) > 0:
        merged = inv.merge(clients[[\'client_id\', \'name\']], on=\'client_id\', how=\'left\')
    else:
        merged = inv
        if \'name\' not in merged.columns:
            merged[\'name\'] = \'\'
    merged = merged.sort_values(\'date\', ascending=False) if len(merged) > 0 else merged
    return render_template(\'invoices.html\', invoices=merged.to_dict(\'records\'), status_filter=status_filter)

@app.route(\'/invoices/create\', methods=[\'GET\', \'POST\'])
def create_invoice():
    clients = read_csv(\'clients.csv\')
    if request.method == \'POST\':
        inv_df = read_csv(\'invoices.csv\')
        inv_id = f"INV-{len(inv_df) + 101}"
        new_inv = pd.DataFrame([[inv_id, int(request.form[\'client_id\']), 0.0, \'Unpaid\',
                                  datetime.now().strftime(\'%Y-%m-%d\'),
                                  request.form.get(\'due_date\', \'\'),
                                  request.form.get(\'notes\', \'\')]],
                               columns=[\'invoice_id\', \'client_id\', \'total_amount\', \'status\', \'date\', \'due_date\', \'notes\'])
        inv_df = pd.concat([inv_df, new_inv], ignore_index=True)
        write_csv(inv_df, \'invoices.csv\')
        flash(f\'Invoice {inv_id} created! Add line items below.\', \'success\')
        return redirect(url_for(\'invoice_detail\', invoice_id=inv_id))
    return render_template(\'invoice_form.html\', clients=clients.to_dict(\'records\'))

@app.route(\'/invoices/<invoice_id>\')
def invoice_detail(invoice_id):
    inv_df   = read_csv(\'invoices.csv\')
    clients  = read_csv(\'clients.csv\')
    items_df = read_csv(\'invoice_items.csv\')
    inv    = inv_df[inv_df[\'invoice_id\'] == invoice_id].iloc[0].to_dict()
    client = clients[clients[\'client_id\'] == inv[\'client_id\']].iloc[0].to_dict()
    items  = items_df[items_df[\'invoice_id\'] == invoice_id].to_dict(\'records\')
    return render_template(\'invoice_detail.html\', invoice=inv, client=client, items=items)

@app.route(\'/invoices/<invoice_id>/add_item\', methods=[\'POST\'])
def add_item(invoice_id):
    qty, price = float(request.form[\'quantity\']), float(request.form[\'price\'])
    items_df = read_csv(\'invoice_items.csv\')
    new_item = pd.DataFrame([[invoice_id, request.form[\'description\'], qty, price, qty*price]],
                            columns=[\'invoice_id\', \'description\', \'quantity\', \'price\', \'line_total\'])
    items_df = pd.concat([items_df, new_item], ignore_index=True)
    write_csv(items_df, \'invoice_items.csv\')
    inv_df = read_csv(\'invoices.csv\')
    inv_df.loc[inv_df[\'invoice_id\'] == invoice_id, \'total_amount\'] = items_df[items_df[\'invoice_id\'] == invoice_id][\'line_total\'].sum()
    write_csv(inv_df, \'invoices.csv\')
    flash(\'Item added!\', \'success\')
    return redirect(url_for(\'invoice_detail\', invoice_id=invoice_id))

@app.route(\'/invoices/<invoice_id>/delete_item/<int:item_index>\', methods=[\'POST\'])
def delete_item(invoice_id, item_index):
    items_df = read_csv(\'invoice_items.csv\')
    inv_items = items_df[items_df[\'invoice_id\'] == invoice_id]
    items_df = items_df.drop(inv_items.index[item_index]).reset_index(drop=True)
    write_csv(items_df, \'invoice_items.csv\')
    inv_df = read_csv(\'invoices.csv\')
    inv_df.loc[inv_df[\'invoice_id\'] == invoice_id, \'total_amount\'] = items_df[items_df[\'invoice_id\'] == invoice_id][\'line_total\'].sum()
    write_csv(inv_df, \'invoices.csv\')
    flash(\'Item removed.\', \'info\')
    return redirect(url_for(\'invoice_detail\', invoice_id=invoice_id))

@app.route(\'/invoices/<invoice_id>/mark_paid\', methods=[\'POST\'])
def mark_paid(invoice_id):
    inv_df = read_csv(\'invoices.csv\')
    inv_df.loc[inv_df[\'invoice_id\'] == invoice_id, \'status\'] = \'Paid\'
    write_csv(inv_df, \'invoices.csv\')
    flash(f\'{invoice_id} marked as Paid!\', \'success\')
    return redirect(url_for(\'invoice_detail\', invoice_id=invoice_id))

@app.route(\'/invoices/<invoice_id>/mark_unpaid\', methods=[\'POST\'])
def mark_unpaid(invoice_id):
    inv_df = read_csv(\'invoices.csv\')
    inv_df.loc[inv_df[\'invoice_id\'] == invoice_id, \'status\'] = \'Unpaid\'
    write_csv(inv_df, \'invoices.csv\')
    flash(f\'{invoice_id} marked as Unpaid.\', \'info\')
    return redirect(url_for(\'invoice_detail\', invoice_id=invoice_id))

@app.route(\'/invoices/<invoice_id>/delete\', methods=[\'POST\'])
def delete_invoice(invoice_id):
    inv_df = read_csv(\'invoices.csv\')
    inv_df = inv_df[inv_df[\'invoice_id\'] != invoice_id]
    write_csv(inv_df, \'invoices.csv\')
    items_df = read_csv(\'invoice_items.csv\')
    items_df = items_df[items_df[\'invoice_id\'] != invoice_id]
    write_csv(items_df, \'invoice_items.csv\')
    flash(f\'{invoice_id} deleted.\', \'info\')
    return redirect(url_for(\'invoices\'))

@app.route(\'/invoices/<invoice_id>/pdf\')
def generate_pdf(invoice_id):
    invoices  = read_csv(\'invoices.csv\')
    items     = read_csv(\'invoice_items.csv\')
    clients   = read_csv(\'clients.csv\')
    inv_data      = invoices[invoices[\'invoice_id\'] == invoice_id].iloc[0]
    client_data   = clients[clients[\'client_id\'] == inv_data[\'client_id\']].iloc[0]
    invoice_items = items[items[\'invoice_id\'] == invoice_id]
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_fill_color(30, 30, 80)
    pdf.rect(0, 0, 210, 40, \'F\')
    pdf.set_font("helvetica", \'B\', 28)
    pdf.set_text_color(255, 255, 255)
    pdf.set_y(10)
    pdf.cell(0, 20, text="INVOICE", align=\'R\', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(50)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", \'B\', 11)
    pdf.cell(100, 8, text=f"Invoice #: {invoice_id}")
    pdf.cell(90, 8, text=f"Date: {inv_data[\'date\']}", align=\'R\', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if str(inv_data.get(\'due_date\', \'\')) not in [\'\', \'nan\']:
        pdf.cell(100, 8, text="")
        pdf.cell(90, 8, text=f"Due: {inv_data[\'due_date\']}", align=\'R\', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)
    pdf.set_font("helvetica", \'B\', 12)
    pdf.cell(0, 8, text="BILL TO:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("helvetica", size=11)
    pdf.cell(0, 7, text=str(client_data[\'name\']), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 7, text=str(client_data[\'email\']), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if str(client_data.get(\'phone\', \'\')) not in [\'\', \'nan\']:
        pdf.cell(0, 7, text=str(client_data[\'phone\']), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(8)
    pdf.set_fill_color(30, 30, 80)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", \'B\', 11)
    pdf.cell(95, 10, text="Description", border=1, fill=True)
    pdf.cell(25, 10, text="Qty",        border=1, fill=True, align=\'C\')
    pdf.cell(35, 10, text="Unit Price", border=1, fill=True, align=\'C\')
    pdf.cell(35, 10, text="Total",      border=1, fill=True, align=\'C\', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", size=10)
    fill = False
    for _, row in invoice_items.iterrows():
        pdf.set_fill_color(245, 245, 250)
        pdf.cell(95, 9, text=str(row[\'description\']),         border=1, fill=fill)
        pdf.cell(25, 9, text=str(int(row[\'quantity\'])),       border=1, fill=fill, align=\'C\')
        pdf.cell(35, 9, text=f"${float(row[\'price\']):.2f}",   border=1, fill=fill, align=\'R\')
        pdf.cell(35, 9, text=f"${float(row[\'line_total\']):.2f}", border=1, fill=fill, align=\'R\', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        fill = not fill
    pdf.ln(4)
    pdf.set_font("helvetica", \'B\', 12)
    pdf.cell(155, 10, text="GRAND TOTAL:", align=\'R\')
    pdf.set_fill_color(30, 30, 80)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(35, 10, text=f"${float(inv_data[\'total_amount\']):.2f}", border=1, fill=True, align=\'R\', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if str(inv_data.get(\'notes\', \'\')) not in [\'\', \'nan\']:
        pdf.ln(8)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", \'I\', 10)
        pdf.cell(0, 7, text=f"Notes: {inv_data[\'notes\']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(-50)
    pdf.set_font("helvetica", \'B\', 30)
    pdf.set_text_color(0, 160, 80) if inv_data[\'status\'] == \'Paid\' else pdf.set_text_color(200, 50, 50)
    pdf.cell(0, 20, text=inv_data[\'status\'].upper(), align=\'R\')
    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return send_file(buf, download_name=f"{invoice_id}.pdf", as_attachment=True, mimetype=\'application/pdf\')

if __name__ == \'__main__\':
    app.run(debug=True)
'''

# ── requirements.txt ──────────────────────────────────────────────────────────
files["requirements.txt"] = """flask>=3.0.0
pandas>=2.0.0
fpdf2>=2.7.0
gunicorn>=21.0.0
"""

# ── templates/base.html ───────────────────────────────────────────────────────
files["templates/base.html"] = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{% block title %}InvoiceFlow{% endblock %}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    :root{--ink:#0f0f1a;--paper:#f7f6f2;--accent:#1e1e50;--gold:#c9a84c;--green:#1a7a4a;--red:#b83232;--muted:#8a8a9a;--border:#e0dfd8;--card:#ffffff;--shadow:0 2px 12px rgba(15,15,26,0.08);}
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:'DM Sans',sans-serif;background:var(--paper);color:var(--ink);min-height:100vh;display:flex;}
    .sidebar{width:240px;min-height:100vh;background:var(--accent);display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;z-index:100;}
    .sidebar-brand{padding:28px 24px 20px;border-bottom:1px solid rgba(255,255,255,0.1);}
    .sidebar-brand h1{font-family:'DM Serif Display',serif;font-size:1.5rem;color:#fff;}
    .sidebar-brand h1 span{color:var(--gold);}
    .sidebar-brand p{font-size:0.72rem;color:rgba(255,255,255,0.45);margin-top:2px;text-transform:uppercase;letter-spacing:1.5px;}
    .sidebar nav{padding:20px 12px;flex:1;}
    .nav-label{font-size:0.65rem;text-transform:uppercase;letter-spacing:2px;color:rgba(255,255,255,0.3);padding:0 12px;margin:16px 0 6px;}
    .nav-link{display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:8px;color:rgba(255,255,255,0.7);text-decoration:none;font-size:0.9rem;font-weight:500;transition:all .15s;margin-bottom:2px;}
    .nav-link:hover,.nav-link.active{background:rgba(255,255,255,0.12);color:#fff;}
    .nav-link.active{background:rgba(201,168,76,0.2);color:var(--gold);}
    .nav-icon{font-size:1.1rem;width:20px;text-align:center;}
    .main{margin-left:240px;flex:1;display:flex;flex-direction:column;min-height:100vh;}
    .topbar{background:var(--card);border-bottom:1px solid var(--border);padding:16px 32px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:50;}
    .topbar h2{font-family:'DM Serif Display',serif;font-size:1.4rem;font-weight:400;}
    .topbar-actions{display:flex;gap:10px;flex-wrap:wrap;}
    .content{padding:32px;}
    .flash-list{list-style:none;margin-bottom:20px;}
    .flash-list li{padding:12px 18px;border-radius:8px;font-size:0.88rem;font-weight:500;margin-bottom:8px;}
    .flash-success{background:#e8f5ee;color:var(--green);border:1px solid #b8dfc9;}
    .flash-info{background:#eef2ff;color:var(--accent);border:1px solid #c8d0f0;}
    .flash-error{background:#fdecea;color:var(--red);border:1px solid #f2bcba;}
    .stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;margin-bottom:32px;}
    .stat-card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:22px 24px;box-shadow:var(--shadow);position:relative;overflow:hidden;}
    .stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--gold);}
    .stat-card.green::before{background:var(--green);}
    .stat-card.accent::before{background:var(--accent);}
    .stat-card.red::before{background:var(--red);}
    .stat-label{font-size:0.72rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--muted);margin-bottom:8px;}
    .stat-value{font-family:'DM Serif Display',serif;font-size:2rem;color:var(--ink);line-height:1;}
    .stat-sub{font-size:0.78rem;color:var(--muted);margin-top:6px;}
    .table-card{background:var(--card);border:1px solid var(--border);border-radius:14px;overflow:hidden;box-shadow:var(--shadow);}
    .table-header{padding:18px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;}
    .table-header h3{font-family:'DM Serif Display',serif;font-size:1.1rem;font-weight:400;}
    table{width:100%;border-collapse:collapse;}
    th{text-align:left;padding:10px 24px;font-size:0.7rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--muted);background:#fafaf8;border-bottom:1px solid var(--border);}
    td{padding:13px 24px;font-size:0.88rem;border-bottom:1px solid var(--border);vertical-align:middle;}
    tr:last-child td{border-bottom:none;}
    tr:hover td{background:#fafaf8;}
    .badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;}
    .badge-paid{background:#e8f5ee;color:var(--green);}
    .badge-unpaid{background:#fdecea;color:var(--red);}
    .btn{display:inline-flex;align-items:center;gap:6px;padding:9px 18px;border-radius:8px;font-family:'DM Sans',sans-serif;font-size:0.86rem;font-weight:500;cursor:pointer;border:none;text-decoration:none;transition:all .15s;}
    .btn-primary{background:var(--accent);color:#fff;}
    .btn-primary:hover{background:#2a2a70;}
    .btn-gold{background:var(--gold);color:#fff;}
    .btn-gold:hover{background:#b8963c;}
    .btn-outline{background:transparent;color:var(--ink);border:1px solid var(--border);}
    .btn-outline:hover{background:var(--paper);}
    .btn-danger{background:#fdecea;color:var(--red);border:1px solid #f2bcba;}
    .btn-danger:hover{background:#fbd9d7;}
    .btn-sm{padding:5px 12px;font-size:0.78rem;}
    .btn-green{background:var(--green);color:#fff;}
    .btn-green:hover{background:#155e38;}
    .form-card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:32px;box-shadow:var(--shadow);max-width:600px;}
    .form-group{margin-bottom:20px;}
    label{display:block;font-size:0.78rem;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:7px;}
    input,select,textarea{width:100%;padding:10px 14px;border:1px solid var(--border);border-radius:8px;font-family:'DM Sans',sans-serif;font-size:0.9rem;background:var(--paper);color:var(--ink);transition:border .15s;}
    input:focus,select:focus,textarea:focus{outline:none;border-color:var(--accent);background:#fff;}
    textarea{resize:vertical;min-height:80px;}
    .form-row{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
    .detail-grid{display:grid;grid-template-columns:2fr 1fr;gap:24px;}
    .detail-meta{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:24px;box-shadow:var(--shadow);}
    .meta-row{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);font-size:0.88rem;}
    .meta-row:last-child{border-bottom:none;}
    .meta-key{color:var(--muted);}
    .meta-val{font-weight:600;}
    .total-row td{font-family:'DM Serif Display',serif;font-size:1.1rem;background:#fafaf8;}
    .filter-tabs{display:flex;gap:8px;margin-bottom:20px;}
    .filter-tab{padding:7px 16px;border-radius:20px;font-size:0.82rem;font-weight:500;text-decoration:none;color:var(--muted);border:1px solid var(--border);transition:all .15s;}
    .filter-tab:hover{border-color:var(--accent);color:var(--accent);}
    .filter-tab.active{background:var(--accent);color:#fff;border-color:var(--accent);}
    .empty-state{text-align:center;padding:60px 20px;color:var(--muted);}
    .empty-state p{font-size:0.9rem;margin-top:8px;}
  </style>
</head>
<body>
  <aside class="sidebar">
    <div class="sidebar-brand">
      <h1>Invoice<span>Flow</span></h1>
      <p>Billing & Tracking</p>
    </div>
    <nav>
      <div class="nav-label">Main</div>
      <a href="{{ url_for('dashboard') }}" class="nav-link {% if request.endpoint == 'dashboard' %}active{% endif %}">
        <span class="nav-icon">◈</span> Dashboard
      </a>
      <div class="nav-label">Manage</div>
      <a href="{{ url_for('invoices') }}" class="nav-link {% if 'invoice' in request.endpoint %}active{% endif %}">
        <span class="nav-icon">◧</span> Invoices
      </a>
      <a href="{{ url_for('clients') }}" class="nav-link {% if 'client' in request.endpoint %}active{% endif %}">
        <span class="nav-icon">◉</span> Clients
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
        {% if messages %}
          <ul class="flash-list">
            {% for category, message in messages %}
              <li class="flash-{{ category }}">{{ message }}</li>
            {% endfor %}
          </ul>
        {% endif %}
      {% endwith %}
      {% block content %}{% endblock %}
    </div>
  </div>
</body>
</html>
"""

# ── templates/dashboard.html ──────────────────────────────────────────────────
files["templates/dashboard.html"] = """{% extends "base.html" %}
{% block title %}Dashboard — InvoiceFlow{% endblock %}
{% block page_title %}Dashboard{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('create_invoice') }}" class="btn btn-primary">＋ New Invoice</a>{% endblock %}
{% block content %}
<div class="stats-grid">
  <div class="stat-card green"><div class="stat-label">Cash Collected</div><div class="stat-value">${{ "%.2f"|format(total_revenue) }}</div><div class="stat-sub">From paid invoices</div></div>
  <div class="stat-card red"><div class="stat-label">Outstanding</div><div class="stat-value">${{ "%.2f"|format(total_outstanding) }}</div><div class="stat-sub">Awaiting payment</div></div>
  <div class="stat-card accent"><div class="stat-label">Collection Rate</div><div class="stat-value">{{ collection_rate }}%</div><div class="stat-sub">Paid vs total billed</div></div>
  <div class="stat-card"><div class="stat-label">Total Invoices</div><div class="stat-value">{{ total_invoices }}</div><div class="stat-sub">{{ total_clients }} active clients</div></div>
</div>
<div class="table-card">
  <div class="table-header"><h3>Recent Invoices</h3><a href="{{ url_for('invoices') }}" class="btn btn-outline btn-sm">View All</a></div>
  {% if recent_invoices %}
  <table>
    <thead><tr><th>Invoice</th><th>Client</th><th>Date</th><th>Amount</th><th>Status</th><th></th></tr></thead>
    <tbody>
      {% for inv in recent_invoices %}
      <tr>
        <td><strong>{{ inv.invoice_id }}</strong></td>
        <td>{{ inv.get('name', '—') }}</td>
        <td>{{ inv.date }}</td>
        <td>${{ "%.2f"|format(inv.total_amount) }}</td>
        <td><span class="badge badge-{{ inv.status|lower }}">{{ inv.status }}</span></td>
        <td><a href="{{ url_for('invoice_detail', invoice_id=inv.invoice_id) }}" class="btn btn-outline btn-sm">Open</a></td>
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

# ── templates/clients.html ────────────────────────────────────────────────────
files["templates/clients.html"] = """{% extends "base.html" %}
{% block title %}Clients — InvoiceFlow{% endblock %}
{% block page_title %}Clients{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('add_client') }}" class="btn btn-primary">＋ Add Client</a>{% endblock %}
{% block content %}
<div class="table-card">
  <div class="table-header"><h3>All Clients</h3><span style="color:var(--muted);font-size:0.85rem;">{{ clients|length }} total</span></div>
  {% if clients %}
  <table>
    <thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Phone</th><th>Invoices</th><th>Total Billed</th><th>Actions</th></tr></thead>
    <tbody>
      {% for c in clients %}
      <tr>
        <td style="color:var(--muted)">#{{ c.client_id }}</td>
        <td><strong>{{ c.name }}</strong></td>
        <td>{{ c.email }}</td>
        <td>{{ c.phone if c.phone and c.phone != 'nan' else '—' }}</td>
        <td>{{ c.invoice_count }}</td>
        <td>${{ "%.2f"|format(c.total_billed) }}</td>
        <td>
          <a href="{{ url_for('edit_client', client_id=c.client_id) }}" class="btn btn-outline btn-sm">Edit</a>
          <form action="{{ url_for('delete_client', client_id=c.client_id) }}" method="post" style="display:inline" onsubmit="return confirm('Delete this client?')">
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

# ── templates/client_form.html ────────────────────────────────────────────────
files["templates/client_form.html"] = """{% extends "base.html" %}
{% block title %}{{ 'Edit' if client else 'Add' }} Client — InvoiceFlow{% endblock %}
{% block page_title %}{{ 'Edit' if client else 'Add' }} Client{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('clients') }}" class="btn btn-outline">← Back to Clients</a>{% endblock %}
{% block content %}
<div class="form-card">
  <form method="post">
    <div class="form-group"><label>Full Name / Company</label><input type="text" name="name" value="{{ client.name if client else '' }}" required placeholder="e.g. Acme Corporation"></div>
    <div class="form-row">
      <div class="form-group"><label>Email Address</label><input type="email" name="email" value="{{ client.email if client else '' }}" required placeholder="billing@company.com"></div>
      <div class="form-group"><label>Phone (optional)</label><input type="text" name="phone" value="{{ client.phone if client and client.phone != 'nan' else '' }}" placeholder="+1 555 000 0000"></div>
    </div>
    <div class="form-group"><label>Address (optional)</label><textarea name="address" placeholder="123 Main Street, City, State">{{ client.address if client and client.address != 'nan' else '' }}</textarea></div>
    <div style="display:flex;gap:10px;margin-top:8px;">
      <button type="submit" class="btn btn-primary">{{ 'Save Changes' if client else 'Add Client' }}</button>
      <a href="{{ url_for('clients') }}" class="btn btn-outline">Cancel</a>
    </div>
  </form>
</div>
{% endblock %}
"""

# ── templates/invoices.html ───────────────────────────────────────────────────
files["templates/invoices.html"] = """{% extends "base.html" %}
{% block title %}Invoices — InvoiceFlow{% endblock %}
{% block page_title %}Invoices{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('create_invoice') }}" class="btn btn-primary">＋ New Invoice</a>{% endblock %}
{% block content %}
<div class="filter-tabs">
  <a href="{{ url_for('invoices') }}" class="filter-tab {% if status_filter == 'all' %}active{% endif %}">All</a>
  <a href="{{ url_for('invoices', status='Unpaid') }}" class="filter-tab {% if status_filter == 'Unpaid' %}active{% endif %}">Unpaid</a>
  <a href="{{ url_for('invoices', status='Paid') }}" class="filter-tab {% if status_filter == 'Paid' %}active{% endif %}">Paid</a>
</div>
<div class="table-card">
  <div class="table-header"><h3>{{ status_filter|capitalize if status_filter != 'all' else 'All' }} Invoices</h3><span style="color:var(--muted);font-size:0.85rem;">{{ invoices|length }} total</span></div>
  {% if invoices %}
  <table>
    <thead><tr><th>Invoice #</th><th>Client</th><th>Date</th><th>Due Date</th><th>Amount</th><th>Status</th><th>Actions</th></tr></thead>
    <tbody>
      {% for inv in invoices %}
      <tr>
        <td><strong>{{ inv.invoice_id }}</strong></td>
        <td>{{ inv.get('name', '—') }}</td>
        <td>{{ inv.date }}</td>
        <td>{{ inv.due_date if inv.due_date and inv.due_date != 'nan' else '—' }}</td>
        <td>${{ "%.2f"|format(inv.total_amount) }}</td>
        <td><span class="badge badge-{{ inv.status|lower }}">{{ inv.status }}</span></td>
        <td>
          <a href="{{ url_for('invoice_detail', invoice_id=inv.invoice_id) }}" class="btn btn-outline btn-sm">Open</a>
          <a href="{{ url_for('generate_pdf', invoice_id=inv.invoice_id) }}" class="btn btn-gold btn-sm">PDF</a>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty-state"><strong>No invoices found</strong><p>{% if status_filter != 'all' %}No {{ status_filter|lower }} invoices.{% else %}Create your first invoice to get started.{% endif %}</p></div>
  {% endif %}
</div>
{% endblock %}
"""

# ── templates/invoice_form.html ───────────────────────────────────────────────
files["templates/invoice_form.html"] = """{% extends "base.html" %}
{% block title %}New Invoice — InvoiceFlow{% endblock %}
{% block page_title %}New Invoice{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('invoices') }}" class="btn btn-outline">← Back</a>{% endblock %}
{% block content %}
<div class="form-card">
  <form method="post">
    <div class="form-group">
      <label>Client</label>
      <select name="client_id" required>
        <option value="">— Select a client —</option>
        {% for c in clients %}<option value="{{ c.client_id }}">{{ c.name }}</option>{% endfor %}
      </select>
      {% if not clients %}<p style="color:var(--red);font-size:0.82rem;margin-top:6px;">No clients yet. <a href="{{ url_for('add_client') }}">Add one first →</a></p>{% endif %}
    </div>
    <div class="form-group"><label>Due Date (optional)</label><input type="date" name="due_date"></div>
    <div class="form-group"><label>Notes (optional)</label><textarea name="notes" placeholder="Payment terms, project details, etc."></textarea></div>
    <div style="display:flex;gap:10px;margin-top:8px;">
      <button type="submit" class="btn btn-primary" {% if not clients %}disabled{% endif %}>Create Invoice</button>
      <a href="{{ url_for('invoices') }}" class="btn btn-outline">Cancel</a>
    </div>
  </form>
</div>
{% endblock %}
"""

# ── templates/invoice_detail.html ────────────────────────────────────────────
files["templates/invoice_detail.html"] = """{% extends "base.html" %}
{% block title %}{{ invoice.invoice_id }} — InvoiceFlow{% endblock %}
{% block page_title %}{{ invoice.invoice_id }}{% endblock %}
{% block topbar_actions %}
  <a href="{{ url_for('invoices') }}" class="btn btn-outline">← All Invoices</a>
  <a href="{{ url_for('generate_pdf', invoice_id=invoice.invoice_id) }}" class="btn btn-gold">⬇ Download PDF</a>
  {% if invoice.status == 'Unpaid' %}
    <form action="{{ url_for('mark_paid', invoice_id=invoice.invoice_id) }}" method="post" style="display:inline">
      <button class="btn btn-green">✓ Mark as Paid</button>
    </form>
  {% else %}
    <form action="{{ url_for('mark_unpaid', invoice_id=invoice.invoice_id) }}" method="post" style="display:inline">
      <button class="btn btn-outline">↩ Mark as Unpaid</button>
    </form>
  {% endif %}
  <form action="{{ url_for('delete_invoice', invoice_id=invoice.invoice_id) }}" method="post" style="display:inline" onsubmit="return confirm('Delete this invoice permanently?')">
    <button class="btn btn-danger">Delete</button>
  </form>
{% endblock %}
{% block content %}
<div class="detail-grid">
  <div>
    <div class="table-card" style="margin-bottom:24px;">
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
              <form action="{{ url_for('delete_item', invoice_id=invoice.invoice_id, item_index=loop.index0) }}" method="post" onsubmit="return confirm('Remove this item?')">
                <button class="btn btn-danger btn-sm">✕</button>
              </form>
            </td>
          </tr>
          {% else %}
          <tr><td colspan="5" style="text-align:center;color:var(--muted);padding:32px;">No items yet — add one below.</td></tr>
          {% endfor %}
          {% if items %}
          <tr class="total-row">
            <td colspan="3" style="text-align:right;padding-right:24px;">Grand Total</td>
            <td><strong>${{ "%.2f"|format(invoice.total_amount) }}</strong></td>
            <td></td>
          </tr>
          {% endif %}
        </tbody>
      </table>
    </div>
    <div class="form-card">
      <h3 style="font-family:'DM Serif Display',serif;font-weight:400;margin-bottom:20px;">Add Line Item</h3>
      <form method="post" action="{{ url_for('add_item', invoice_id=invoice.invoice_id) }}">
        <div class="form-group"><label>Description</label><input type="text" name="description" required placeholder="e.g. Web Design Services"></div>
        <div class="form-row">
          <div class="form-group"><label>Quantity</label><input type="number" name="quantity" min="1" step="1" value="1" required></div>
          <div class="form-group"><label>Unit Price ($)</label><input type="number" name="price" min="0" step="0.01" required placeholder="0.00"></div>
        </div>
        <button type="submit" class="btn btn-primary">＋ Add Item</button>
      </form>
    </div>
  </div>
  <div>
    <div class="detail-meta">
      <h3 style="font-family:'DM Serif Display',serif;font-weight:400;margin-bottom:16px;">Invoice Details</h3>
      <div class="meta-row"><span class="meta-key">Invoice #</span><span class="meta-val">{{ invoice.invoice_id }}</span></div>
      <div class="meta-row"><span class="meta-key">Status</span><span class="meta-val"><span class="badge badge-{{ invoice.status|lower }}">{{ invoice.status }}</span></span></div>
      <div class="meta-row"><span class="meta-key">Date</span><span class="meta-val">{{ invoice.date }}</span></div>
      <div class="meta-row"><span class="meta-key">Due Date</span><span class="meta-val">{{ invoice.due_date if invoice.due_date and invoice.due_date != 'nan' else 'N/A' }}</span></div>
      <div class="meta-row"><span class="meta-key">Total</span><span class="meta-val" style="font-size:1.1rem">${{ "%.2f"|format(invoice.total_amount) }}</span></div>
    </div>
    <div class="detail-meta" style="margin-top:20px;">
      <h3 style="font-family:'DM Serif Display',serif;font-weight:400;margin-bottom:16px;">Bill To</h3>
      <div class="meta-row"><span class="meta-key">Name</span><span class="meta-val">{{ client.name }}</span></div>
      <div class="meta-row"><span class="meta-key">Email</span><span class="meta-val">{{ client.email }}</span></div>
      {% if client.phone and client.phone != 'nan' %}<div class="meta-row"><span class="meta-key">Phone</span><span class="meta-val">{{ client.phone }}</span></div>{% endif %}
      {% if client.address and client.address != 'nan' %}<div class="meta-row"><span class="meta-key">Address</span><span class="meta-val" style="text-align:right;max-width:180px;">{{ client.address }}</span></div>{% endif %}
    </div>
    {% if invoice.notes and invoice.notes != 'nan' %}
    <div class="detail-meta" style="margin-top:20px;">
      <h3 style="font-family:'DM Serif Display',serif;font-weight:400;margin-bottom:12px;">Notes</h3>
      <p style="font-size:0.88rem;color:var(--muted);line-height:1.6;">{{ invoice.notes }}</p>
    </div>
    {% endif %}
  </div>
</div>
{% endblock %}
"""

# ── Write all files ────────────────────────────────────────────────────────────
for rel_path, content in files.items():
    full_path = os.path.join(BASE, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

print("=" * 55)
print("  ✅  InvoiceFlow created at:")
print(f"      {BASE}")
print("=" * 55)
print()
print("  Next steps:")
print()
print("  1.  pip install flask pandas fpdf2")
print()
print("  2.  cd ~/Desktop/invoice_app")
print("      python app.py")
print()
print("  3.  Open http://127.0.0.1:5000")
print("=" * 55)
