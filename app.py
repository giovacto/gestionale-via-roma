from flask import Flask, render_template, request, redirect, flash, jsonify
from database.models import db, Fornitore, Articolo, VarianteArticolo, Vendita, DettaglioVendita, Scadenza
from datetime import datetime, date
from sqlalchemy import func
import os

app = Flask(__name__)
app.secret_key = 'chiave_segreta_via_roma_2026'

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(BASE_DIR, 'magazzino.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()

# 1. DASHBOARD PRINCIPALE
@app.route('/')
def dashboard():
    scadenze_attive = Scadenza.query.filter_by(pagato=False).count()
    oggi = date.today()
    
    stat_oggi = db.session.query(
        func.coalesce(func.sum(DettaglioVendita.quantita), 0),
        func.coalesce(func.sum(Vendita.importo_totale_incassato), 0.0),
        func.coalesce(func.sum(Vendita.importo_totale_guadagnato), 0.0)
    ).select_from(Vendita).join(DettaglioVendita).filter(func.date(Vendita.data_vendita) == oggi).first()

    return render_template('dashboard.html', 
                           totale_pezzi=stat_oggi[0],
                           totale_incassato=stat_oggi[1],
                           totale_guadagnato=stat_oggi[2],
                           scadenze_attive=scadenze_attive)

# 2. PUNTO CASSA
@app.route('/cassa')
def cassa():
    return render_template('cassa.html')

# 3. INTERFACCIA CARICO MERCI
@app.route('/carico', methods=['GET', 'POST'])
def carico_merci():
    if request.method == 'POST':
        codice_modello = request.form['codice_modello'].strip()
        nome = request.form['nome'].strip()
        fornitore_id = int(request.form['fornitore_id'])
        tipologia = request.form['tipologia']
        prezzo_acquisto = float(request.form['prezzo_acquisto'])
        ricarico_percentuale = float(request.form['ricarico_percentuale'])
        
        colori = request.form.getlist('colore[]')
        taglie_numeri = request.form.getlist('taglia_numero[]')
        giacenze = request.form.getlist('giacenza[]')
        barcodes = request.form.getlist('barcode[]')

        prezzo_listino = prezzo_acquisto + (prezzo_acquisto * (ricarico_percentuale / 100.0))

        articolo = Articolo.query.filter_by(codice_modello=codice_modello).first()
        
        if not articolo:
            articolo = Articolo(
                codice_modello=codice_modello, nome=nome, fornitore_id=fornitore_id,
                tipologia=tipologia, prezzo_acquisto=prezzo_acquisto,
                ricarico_percentuale=ricarico_percentuale, prezzo_listino=prezzo_listino
            )
            db.session.add(articolo)
            db.session.commit()
            msg_successo = f"Nuovo modello '{nome}' registrato! "
        else:
            articolo.nome = nome
            articolo.fornitore_id = fornitore_id
            articolo.tipologia = tipologia
            articolo.prezzo_acquisto = prezzo_acquisto
            articolo.ricarico_percentuale = ricarico_percentuale
            articolo.prezzo_listino = prezzo_listino
            msg_successo = f"Modello '{articolo.nome}' esistente aggiornato! "

        conteggio_inseriti = 0
        
        for i in range(len(taglie_numeri)):
            bcode = barcodes[i].strip()
            num = taglie_numeri[i].strip()
            col = colori[i].strip()
            qta = int(giacenze[i])

            if not bcode or not num:
                continue

            variante_esistente = VarianteArticolo.query.filter_by(barcode=bcode).first()
            
            if variante_esistente:
                variante_esistente.giacenza += qta
                conteggio_inseriti += qta
            else:
                nuova_variante = VarianteArticolo(
                    articolo_id=articolo.id, barcode=bcode, colore=col,
                    taglia_numero=num, giacenza=qta
                )
                db.session.add(nuova_variante)
                conteggio_inseriti += qta

        db.session.commit()
        flash(f"⚓ {msg_successo} Movimentati {conteggio_inseriti} pezzi.", "success")
        return redirect('/carico')

    lista_fornitori = Fornitore.query.order_by(Fornitore.nome.asc()).all()
    return render_template('carico.html', fornitori=lista_fornitori)

# 4. API VERIFICA MODELLO
@app.route('/api/check_modello/<codice>')
def check_modello(codice):
    articolo = Articolo.query.filter_by(codice_modello=codice.strip()).first()
    if not articolo:
        return jsonify({"esiste": False})
    
    lista_varianti = []
    for v in articolo.varianti:
        lista_varianti.append({
            "colore": v.colore,
            "taglia_numero": v.taglia_numero,
            "giacenza": v.giacenza,
            "barcode": v.barcode
        })
        
    return jsonify({
        "esiste": True,
        "nome": articolo.nome,
        "fornitore_id": articolo.fornitore_id,
        "tipologia": articolo.tipologia,
        "prezzo_acquisto": articolo.prezzo_acquisto,
        "ricarico_percentuale": articolo.ricarico_percentuale,
        "varianti": lista_varianti
    })

# 5. API RICERCA IN CASSA
@app.route('/api/articolo/<barcode>')
def cerca_articolo(barcode):
    variante = VarianteArticolo.query.filter_by(barcode=barcode).first()
    if not variante:
        return jsonify({"errore": "Articolo non trovato"}), 404
    
    articolo = variante.articolo
    return jsonify({
        "variante_id": variante.id,
        "nome": articolo.nome,
        "brand": articolo.fornitore.nome,
        "codice_modello": articolo.codice_modello,
        "colore": variante.colore,
        "taglia_numero": variante.taglia_numero,
        "prezzo_listino": articolo.prezzo_listino
    })

# 6. API CHIUDI VENDITA
@app.route('/api/vendi', methods=['POST'])
def elabora_vendita():
    dati_carrello = request.json
    if not dati_carrello:
        return jsonify({"errore": "Carrello vuoto"}), 400
        
    importo_totale_incassato = 0.0
    importo_totale_guadagnato = 0.0
    dettagli_da_salvare = []

    for item in dati_carrello:
        variante = VarianteArticolo.query.get(item['variante_id'])
        if not variante:
            continue
        
        articolo = variante.articolo
        prezzo_venduto = float(item['prezzo_finale'])
        guadagno_singolo = prezzo_venduto - articolo.prezzo_acquisto
        
        importo_totale_incassato += prezzo_venduto
        importo_totale_guadagnato += guadagno_singolo
        
        variante.giacenza -= 1
        
        dettaglio = DettaglioVendita(
            variante_id=variante.id,
            quantita=1,
            prezzo_singolo_venduto=prezzo_venduto
        )
        dettagli_da_salvare.append(dettaglio)

    nuova_vendita = Vendita(
        importo_totale_incassato=importo_totale_incassato,
        importo_totale_guadagnato=importo_totale_guadagnato,
        dettagli=dettagli_da_salvare
    )
    
    db.session.add(nuova_vendita)
    db.session.commit()

    return jsonify({"successo": True, "totale": importo_totale_incassato})

# 7. SCADENZIARIO
@app.route('/scadenziario', methods=['GET', 'POST'])
def scadenziario():
    if request.method == 'POST':
        fornitore_id = int(request.form['fornitore_id'])
        descrizione = request.form['descrizione']
        importo = float(request.form['importo'])
        data_scadenza = datetime.strptime(request.form['data_scadenza'], '%Y-%m-%d').date()

        nuova_scadenza = Scadenza(
            fornitore_id=fornitore_id, descrizione=descrizione,
            importo=importo, data_scadenza=data_scadenza, pagato=False
        )
        db.session.add(nuova_scadenza)
        db.session.commit()
        return redirect('/scadenziario')

    scadenze_da_pagare = Scadenza.query.filter_by(pagato=False).order_by(Scadenza.data_scadenza.asc()).all()
    lista_fornitori = Fornitore.query.order_by(Fornitore.nome.asc()).all()
    return render_template('scadenziario.html', scadenze=scadenze_da_pagare, fornitori=lista_fornitori)

# 8. MARCA SCADENZA PAGATA
@app.route('/scadenziario/paga/<int:id>', methods=['POST'])
def paga_scadenza(id):
    scadenza = Scadenza.query.get(id)
    if scadenza:
        scadenza.pagato = True
        db.session.commit()
    return redirect('/scadenziario')

# 9. INVENTARIO COMPLETO (TOOLS)
@app.route('/tools')
def tools():
    tutte_varianti = VarianteArticolo.query.join(Articolo).join(Fornitore).order_by(Fornitore.nome, Articolo.nome).all()
    return render_template('tools.html', varianti=tutte_varianti)

# 10. RETTIFICA RAPIDA VARIANTI
@app.route('/tools/regola/<int:id>/<string:azione>', methods=['POST'])
def regola_magazzino(id, azione):
    variante = VarianteArticolo.query.get_or_404(id)
    if azione == 'piu':
        variante.giacenza += 1
    elif azione == 'meno' and variante.giacenza > 0:
        variante.giacenza -= 1
    elif azione == 'elimina':
        db.session.delete(variante)
        
    db.session.commit()
    return redirect('/tools')

# 11. ANAGRAFICA FORNITORI
@app.route('/fornitori', methods=['GET', 'POST'])
def gestione_fornitori():
    if request.method == 'POST':
        nome = request.form['nome'].strip()
        telefono = request.form['telefono'].strip()
        email = request.form['email'].strip()
        
        nuovo_f = Fornitore(nome=nome, telephone=telefono, email=email) if hasattr(Fornitore, 'telephone') else Fornitore(nome=nome, telefono=telefono, email=email)
        db.session.add(nuovo_f)
        db.session.commit()
        return redirect('/fornitori')
        
    tutti_fornitori = Fornitore.query.order_by(Fornitore.nome.asc()).all()
    return render_template('fornitori.html', fornitori=tutti_fornitori)

# 12. RIMOZIONE FORNITORE
@app.route('/fornitori/elimina/<int:id>', methods=['POST'])
def elimina_fornitore(id):
    f = Fornitore.query.get_or_404(id)
    db.session.delete(f)
    db.session.commit()
    return redirect('/fornitori')

# 13. SCHEDA REPORT TEMPORALE (LAVORO DI SPRINT VENDITE)
@app.route('/report', methods=['GET', 'POST'])
def report_vendite():
    # Impostiamo le date di default su oggi se l'utente apre solo la pagina (GET)
    data_inizio_str = date.today().strftime('%Y-%m-%d')
    data_fine_str = date.today().strftime('%Y-%m-%d')
    
    if request.method == 'POST':
        data_inizio_str = request.form['data_inizio']
        data_fine_str = request.form['data_fine']
        
    # Estraiamo le vendite del periodo per fare i totali finanziari puliti
    vendite_periodo = Vendita.query.filter(
        func.date(Vendita.data_vendita) >= data_inizio_str,
        func.date(Vendita.data_vendita) <= data_fine_str
    ).all()
    
    rep_incasso = sum(v.importo_totale_incassato for v in vendite_periodo)
    rep_guadagno = sum(v.importo_totale_guadagnato for v in vendite_periodo)
    
    # Estraiamo i singoli pezzi usciti per popolare la tabella
    dettagli_periodo = DettaglioVendita.query.join(Vendita).filter(
        func.date(Vendita.data_vendita) >= data_inizio_str,
        func.date(Vendita.data_vendita) <= data_fine_str
    ).order_by(Vendita.data_vendita.desc()).all()
    
    rep_pezzi = sum(d.quantita for d in dettagli_periodo)
    
    return render_template('report.html',
                           data_inizio=data_inizio_str,
                           data_fine=data_fine_str,
                           rep_pezzi=rep_pezzi,
                           rep_incasso=rep_incasso,
                           rep_guadagno=rep_guadagno,
                           dettagli=dettagli_periodo)

if __name__ == '__main__':
    app.run(debug=True)