from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from barcode import Code128
from barcode.writer import ImageWriter
from io import BytesIO
from PIL import ImageFont
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import sqlite3
import base64
from fpdf import FPDF
import webbrowser  # Import para abrir o navegador
from threading import Timer  # Para abrir o navegador de forma não bloqueante

app = Flask(__name__)
app.secret_key = 'ViaCores'

DATABASE = 'estoque.db'	



def get_db():
    conn = sqlite3.connect(DATABASE)
    return conn

def create_table():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS estoque (
                codigo TEXT PRIMARY KEY,
                quantidade INTEGER NOT NULL DEFAULT 0,
                caixa TEXT
            )
        ''')

create_table()

@app.route('/')
def index():
    items = get_items()
    return render_template('index.html', items=items)

def get_items():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT codigo, quantidade, caixa FROM estoque ORDER BY codigo ASC")
        return cursor.fetchall()

@app.route('/add_remove_item', methods=['POST'])
def add_remove_item():
    sku = request.form['barcode']
    quantity = int(request.form['quantity'])
    action = request.form['action']
    caixa = request.form.get('caixa')  # Obtém a caixa selecionada

    # Prefixos que precisam de seleção de caixa
    skus_que_precisam_caixa_prefixos = ["PV", "PH", "FF", "FH", "RV", "PR"]
    skus_sem_caixa = ["PC", "CL", "KD", "KC", "VC"]

    # Obtém os dois primeiros caracteres do SKU
    sku_prefixo = sku[:2]

    with get_db() as conn:
        cursor = conn.cursor()
        
        if action == 'add':
            # Verifica se o prefixo requer seleção de caixa
            if sku_prefixo in skus_que_precisam_caixa_prefixos and not caixa:
                flash('Por favor, selecione uma caixa para este SKU.', 'error')
                return redirect(url_for('index'))

            # Se o SKU não exige caixa, adiciona normalmente
            if sku_prefixo in skus_sem_caixa:
                cursor.execute("""
                    INSERT INTO estoque (codigo, quantidade) 
                    VALUES (?, ?) 
                    ON CONFLICT(codigo) DO UPDATE SET quantidade = quantidade + ?
                """, (sku, quantity, quantity))
            else:
                # Adiciona com caixa selecionada
                cursor.execute("""
                    INSERT INTO estoque (codigo, quantidade, caixa) 
                    VALUES (?, ?, ?) 
                    ON CONFLICT(codigo) DO UPDATE SET quantidade = quantidade + ?
                """, (sku, quantity, caixa, quantity))
            flash(f'Item {sku} adicionado com sucesso!')

        elif action == 'remove':
            if sku_prefixo in skus_que_precisam_caixa_prefixos:
                cursor.execute("UPDATE estoque SET quantidade = quantidade - ? WHERE codigo = ? AND caixa = ? AND quantidade >= ?", (quantity, sku, caixa, quantity))
            else:
                cursor.execute("UPDATE estoque SET quantidade = quantidade - ? WHERE codigo = ? AND quantidade >= ?", (quantity, sku, quantity))

            if cursor.rowcount == 0:
                flash(f'Não foi possível remover {quantity} de {sku} (quantidade insuficiente).', 'error')
            else:
                # Verifica se a quantidade é zero ou menor, e remove o item do estoque
                cursor.execute("SELECT quantidade FROM estoque WHERE codigo = ?", (sku,))
                result = cursor.fetchone()
                if result and result[0] <= 0:
                    cursor.execute("DELETE FROM estoque WHERE codigo = ?", (sku,))
                    flash(f'O item {sku} foi removido do estoque por não ter mais quantidade disponível.', 'info')
                else:
                    flash(f'Item {sku} removido com sucesso!')

    return redirect(url_for('index'))

@app.route('/print_barcode', methods=['GET', 'POST'])
def print_barcode():
    sku = request.args.get('sku') or request.form.get('sku')
    quantity = int(request.args.get('quantity') or request.form.get('quantity'))

    # Gerar os códigos de barras com base na quantidade solicitada
    codes = []
    for _ in range(quantity):
        code128 = Code128(sku, writer=ImageWriter())
        buffer = BytesIO()
        code128.write(buffer)
        buffer.seek(0)
        image_data = buffer.getvalue()
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        image_uri = f"data:image/png;base64,{image_base64}"
        codes.append(image_uri)

    return render_template('print_barcode.html', codes=codes, sku=sku, quantity=quantity)

@app.route('/search_item', methods=['GET'])
def search_item():
    sku = request.args.get('sku')
    item = get_item_by_sku(sku)
    items = get_items()  # Mantém a lista de todos os itens no estoque
    return render_template('index.html', search_result=item, items=items)

def get_item_by_sku(sku):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT codigo, quantidade, caixa FROM estoque WHERE codigo = ?", (sku,))
        return cursor.fetchone()

@app.route('/download_pdf')
def download_pdf():
    items = get_items()
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, txt="Estoque", ln=True, align='C')
    pdf.cell(200, 10, txt="Código | Quantidade | Caixa", ln=True)

    for item in items:
        codigo, quantidade, caixa = item
        pdf.cell(200, 10, txt=f"{codigo} | {quantidade} | {caixa if caixa else 'N/A'}", ln=True)

    pdf_file_path = 'estoque.pdf'
    pdf.output(pdf_file_path)

    flash('PDF gerado com sucesso!', 'info')
    return redirect(url_for('index'))


# Função para abrir o navegador automaticamente
def open_browser():
    webbrowser.open_new('http://127.0.0.1:5000/')

if __name__ == '__main__':
    # Iniciar o servidor Flask e abrir o navegador automaticamente
    Timer(0, open_browser).start()  # Aguarda 1 segundo antes de abrir o navegador
    app.run(host='127.0.0.1', port=5000)

