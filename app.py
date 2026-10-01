from flask import Flask, render_template, request, redirect, flash, jsonify, session
from database.models import (
    db,
    Fornitore,
    Articolo,
    VarianteArticolo,
    Vendita,
    DettaglioVendita,
    Scadenza,
)
from datetime import datetime, date
from sqlalchemy import func
import os

try:
    from stratoos import aggiorna_giacenza_stratoos, crea_prodotto_stratoos
except ImportError:

    def aggiorna_giacenza_stratoos(
        barcode, giacenza, product_id=None, product_child_id=None
    ):
        pass

    def crea_prodotto_stratoos(codice_modello, nome_articolo, prezzo_listino):
        pass


app = Flask(__name__)
app.secret_key = "chiave_segreta_via_roma_2026"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"sqlite:///{os.path.join(BASE_DIR, 'magazzino.db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()


@app.before_request
def blinda_pagine():
    rotte_libere = ["login", "static"]
    if request.endpoint in rotte_libere or request.path.startswith("/static/"):
        return
    if not session.get("loggato"):
        return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        if username == "admin" and password == "Loredanalo":
            session["loggato"] = True
            return redirect("/")
        else:
            flash("❌ Nome utente o Password errati!", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("loggato", None)
    flash("🚪 Sessione chiusa. Alla prossima!", "info")
    return redirect("/login")


@app.route("/")
def dashboard():
    scadenze_attive = Scadenza.query.filter_by(pagato=False).count()
    oggi = date.today()

    stat_oggi = (
        db.session.query(
            func.coalesce(func.sum(DettaglioVendita.quantita), 0),
            func.coalesce(func.sum(Vendita.importo_totale_incassato), 0.0),
            func.coalesce(func.sum(Vendita.importo_totale_guadagnato), 0.0),
        )
        .select_from(Vendita)
        .join(DettaglioVendita)
        .filter(func.date(Vendita.data_vendita) == oggi)
        .first()
    )

    return render_template(
        "dashboard.html",
        totale_pezzi=stat_oggi[0],
        totale_incassato=stat_oggi[1],
        totale_guadagnato=stat_oggi[2],
        scadenze_attive=scadenze_attive,
    )


@app.route("/cassa")
def cassa():
    return render_template("cassa.html")


@app.route("/carico", methods=["GET", "POST"])
def carico_merci():
    if request.method == "POST":
        codice_modello = request.form["codice_modello"].strip()
        nome = request.form["nome"].strip()
        fornitore_id = int(request.form["fornitore_id"])
        tipologia = request.form["tipologia"]
        prezzo_acquisto = float(request.form["prezzo_acquisto"])
        ricarico_percentuale = float(request.form.get("ricarico_percentuale", 100))

        prezzo_listino_input = request.form.get("prezzo_listino", "").strip()
        if prezzo_listino_input:
            prezzo_listino = float(prezzo_listino_input)
            if prezzo_acquisto > 0:
                ricarico_percentuale = (
                    (prezzo_listino - prezzo_acquisto) / prezzo_acquisto
                ) * 100
        else:
            prezzo_listino = prezzo_acquisto + (
                prezzo_acquisto * (ricarico_percentuale / 100.0)
            )

        colori = request.form.getlist("colore[]")
        taglie_numeri = request.form.getlist("taglia_numero[]")
        giacenze = request.form.getlist("giacenza[]")
        barcodes = request.form.getlist("barcode[]")

        articolo = Articolo.query.filter_by(codice_modello=codice_modello).first()

        if not articolo:
            articolo = Articolo(
                codice_modello=codice_modello,
                nome=nome,
                fornitore_id=fornitore_id,
                tipologia=tipologia,
                prezzo_acquisto=prezzo_acquisto,
                ricarico_percentuale=ricarico_percentuale,
                prezzo_listino=prezzo_listino,
            )
            db.session.add(articolo)
            db.session.commit()

            p_id = crea_prodotto_stratoos(codice_modello, nome, prezzo_listino)
            if p_id:
                articolo.stratoos_id = p_id
                db.session.commit()

            msg_successo = (
                f"Nuovo modello '{nome}' registrato su Gestionale e Stratoos! "
            )
        else:
            msg_successo = (
                f"Aggiunte nuove varianti al modello esistente '{articolo.nome}'! "
            )

        conteggio_inseriti = 0
        varianti_caricate = []

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
                varianti_caricate.append(variante_esistente)
            else:
                nuova_variante = VarianteArticolo(
                    articolo_id=articolo.id,
                    barcode=bcode,
                    colore=col,
                    taglia_numero=num,
                    giacenza=qta,
                )
                db.session.add(nuova_variante)
                conteggio_inseriti += qta
                varianti_caricate.append(nuova_variante)

        db.session.commit()

        for v in varianti_caricate:
            aggiorna_giacenza_stratoos(
                v.barcode,
                v.giacenza,
                product_id=articolo.stratoos_id,
                product_child_id=v.stratoos_child_id,
            )

        flash(f"⚓ {msg_successo} Movimentati {conteggio_inseriti} pezzi.", "success")
        return redirect("/carico")

    lista_fornitori = Fornitore.query.order_by(Fornitore.nome.asc()).all()
    return render_template("carico.html", fornitori=lista_fornitori)


@app.route("/api/check_modello/<codice>")
def check_modello(codice):
    articolo = Articolo.query.filter_by(codice_modello=codice.strip()).first()
    if not articolo:
        return jsonify({"esiste": False})

    lista_varianti = []
    for v in articolo.varianti:
        lista_varianti.append(
            {
                "colore": v.colore,
                "taglia_numero": v.taglia_numero,
                "giacenza": v.giacenza,
                "barcode": v.barcode,
            }
        )

    return jsonify(
        {
            "esiste": True,
            "nome": articolo.nome,
            "fornitore_id": articolo.fornitore_id,
            "tipologia": articolo.tipologia,
            "prezzo_acquisto": articolo.prezzo_acquisto,
            "ricarico_percentuale": articolo.ricarico_percentuale,
            "prezzo_listino": articolo.prezzo_listino,
            "varianti": lista_varianti,
        }
    )


@app.route("/api/articolo/<barcode>")
def cerca_articolo(barcode):
    variante = VarianteArticolo.query.filter_by(barcode=barcode).first()
    if not variante:
        return jsonify({"errore": "Articolo non trovato"}), 404

    articolo = variante.articolo
    brand_nome = (
        articolo.fornitore.nome
        if articolo.fornitore
        else (articolo.brand or "Sconosciuto")
    )

    return jsonify(
        {
            "variante_id": variante.id,
            "nome": articolo.nome,
            "brand": brand_nome,
            "codice_modello": articolo.codice_modello,
            "colore": variante.colore,
            "taglia_numero": variante.taglia_numero,
            "prezzo_listino": articolo.prezzo_listino,
            "giacenza": variante.giacenza,
        }
    )


@app.route("/api/cerca_prodotti_cassa")
def cerca_prodotti_cassa():
    query = request.args.get("q", "").strip()
    if not query or len(query) < 2:
        return jsonify([])

    varianti = (
        VarianteArticolo.query.join(Articolo)
        .outerjoin(Fornitore)
        .filter(
            (Articolo.nome.ilike(f"%{query}%"))
            | (Articolo.codice_modello.ilike(f"%{query}%"))
            | (Fornitore.nome.ilike(f"%{query}%"))
            | (VarianteArticolo.colore.ilike(f"%{query}%"))
            | (VarianteArticolo.barcode.ilike(f"%{query}%"))
        )
        .limit(25)
        .all()
    )

    risultati = []
    for v in varianti:
        art = v.articolo
        brand_nome = (
            art.fornitore.nome if art.fornitore else (art.brand or "Sconosciuto")
        )
        risultati.append(
            {
                "variante_id": v.id,
                "nome": art.nome,
                "brand": brand_nome,
                "codice_modello": art.codice_modello,
                "colore": v.colore,
                "taglia_numero": v.taglia_numero,
                "prezzo_listino": art.prezzo_listino,
                "giacenza": v.giacenza,
                "barcode": v.barcode,
            }
        )

    return jsonify(risultati)


@app.route("/api/vendi", methods=["POST"])
def elabora_vendita():
    dati_carrello = request.json
    if not dati_carrello:
        return jsonify({"errore": "Carrello vuoto"}), 400

    importo_totale_incassato = 0.0
    importo_totale_guadagnato = 0.0
    dettagli_da_salvare = []
    varianti_da_sincronizzare = []

    for item in dati_carrello:
        variante = VarianteArticolo.query.get(item["variante_id"])
        if not variante:
            continue

        articolo = variante.articolo
        prezzo_venduto = float(item["prezzo_finale"])
        guadagno_singolo = prezzo_venduto - articolo.prezzo_acquisto

        importo_totale_incassato += prezzo_venduto
        importo_totale_guadagnato += guadagno_singolo

        variante.giacenza -= 1
        varianti_da_sincronizzare.append(variante)

        dettaglio = DettaglioVendita(
            variante_id=variante.id, quantita=1, prezzo_singolo_venduto=prezzo_venduto
        )
        dettagli_da_salvare.append(dettaglio)

    nuova_vendita = Vendita(
        importo_totale_incassato=importo_totale_incassato,
        importo_totale_guadagnato=importo_totale_guadagnato,
        dettagli=dettagli_da_salvare,
    )

    db.session.add(nuova_vendita)
    db.session.commit()

    for v in varianti_da_sincronizzare:
        aggiorna_giacenza_stratoos(
            v.barcode,
            v.giacenza,
            product_id=v.articolo.stratoos_id,
            product_child_id=v.stratoos_child_id,
        )

    return jsonify({"successo": True, "totale": importo_totale_incassato})


@app.route("/scadenziario", methods=["GET", "POST"])
def scadenziario():
    if request.method == "POST":
        fornitore_id = int(request.form["fornitore_id"])
        descrizione = request.form["descrizione"]
        importo = float(request.form["importo"])
        data_scadenza = datetime.strptime(
            request.form["data_scadenza"], "%Y-%m-%d"
        ).date()

        nuova_scadenza = Scadenza(
            fornitore_id=fornitore_id,
            descrizione=descrizione,
            importo=importo,
            data_scadenza=data_scadenza,
            pagato=False,
        )
        db.session.add(nuova_scadenza)
        db.session.commit()
        return redirect("/scadenziario")

    scadenze_da_pagare = (
        Scadenza.query.filter_by(pagato=False)
        .order_by(Scadenza.data_scadenza.asc())
        .all()
    )
    lista_fornitori = Fornitore.query.order_by(Fornitore.nome.asc()).all()
    return render_template(
        "scadenziario.html", scadenze=scadenze_da_pagare, fornitori=lista_fornitori
    )


@app.route("/scadenziario/paga/<int:id>", methods=["POST"])
def paga_scadenza(id):
    scadenza = Scadenza.query.get(id)
    if scadenza:
        scadenza.pagato = True
        db.session.commit()
    return redirect("/scadenziario")


@app.route("/tools")
def tools():
    tutte_varianti = (
        VarianteArticolo.query.join(Articolo)
        .outerjoin(Fornitore)
        .order_by(Fornitore.nome, Articolo.nome)
        .all()
    )
    lista_fornitori = Fornitore.query.order_by(Fornitore.nome.asc()).all()
    return render_template(
        "tools.html", varianti=tutte_varianti, fornitori=lista_fornitori
    )


@app.route("/tools/modifica/<int:id>", methods=["POST"])
def modifica_variante(id):
    variante = VarianteArticolo.query.get_or_404(id)
    articolo = variante.articolo

    articolo.nome = request.form["nome"].strip()
    articolo.fornitore_id = int(request.form["fornitore_id"])
    articolo.tipologia = request.form["tipologia"]
    articolo.prezzo_acquisto = float(request.form["prezzo_acquisto"])
    articolo.prezzo_listino = float(request.form["prezzo_listino"])

    if articolo.prezzo_acquisto > 0:
        articolo.ricarico_percentuale = (
            (articolo.prezzo_listino - articolo.prezzo_acquisto)
            / articolo.prezzo_acquisto
        ) * 100

    variante.colore = request.form["colore"].strip()
    variante.taglia_numero = request.form["taglia_numero"].strip()
    variante.barcode = request.form["barcode"].strip()
    variante.giacenza = int(request.form["giacenza"])

    db.session.commit()
    aggiorna_giacenza_stratoos(
        variante.barcode,
        variante.giacenza,
        product_id=articolo.stratoos_id,
        product_child_id=variante.stratoos_child_id,
    )

    flash(
        f"✏️ Prodotto '{articolo.nome}' (Taglia {variante.taglia_numero}) aggiornato correttamente!",
        "success",
    )
    return redirect("/tools")


@app.route("/tools/regola/<int:id>/<string:azione>", methods=["POST"])
def regola_magazzino(id, azione):
    variante = VarianteArticolo.query.get_or_404(id)
    barcode_temp = variante.barcode

    if azione == "piu":
        variante.giacenza += 1
        db.session.commit()
        aggiorna_giacenza_stratoos(
            barcode_temp,
            variante.giacenza,
            product_id=variante.articolo.stratoos_id,
            product_child_id=variante.stratoos_child_id,
        )
        flash(f"➕ Giacenza aumentata per il barcode {variante.barcode}.", "success")

    elif azione == "meno" and variante.giacenza > 0:
        variante.giacenza -= 1
        db.session.commit()
        aggiorna_giacenza_stratoos(
            barcode_temp,
            variante.giacenza,
            product_id=variante.articolo.stratoos_id,
            product_child_id=variante.stratoos_child_id,
        )
        flash(f"➖ Giacenza ridotta per il barcode {variante.barcode}.", "info")

    elif azione == "elimina":
        ha_vendite = DettaglioVendita.query.filter_by(variante_id=variante.id).first()

        if ha_vendite:
            variante.giacenza = 0
            db.session.commit()
            aggiorna_giacenza_stratoos(
                barcode_temp,
                0,
                product_id=variante.articolo.stratoos_id,
                product_child_id=variante.stratoos_child_id,
            )
            flash(
                "⚠️ Questo articolo fa parte dello storico vendite: la giacenza è stata azzerata a 0 pz.",
                "warning",
            )
        else:
            try:
                db.session.delete(variante)
                db.session.commit()
                aggiorna_giacenza_stratoos(
                    barcode_temp,
                    0,
                    product_id=variante.articolo.stratoos_id,
                    product_child_id=variante.stratoos_child_id,
                )
                flash("🗑️ Articolo eliminato definitivamente dal magazzino.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"❌ Errore durante l'eliminazione: {e}", "danger")

    return redirect("/tools")


@app.route("/fornitori", methods=["GET", "POST"])
def gestione_fornitori():
    if request.method == "POST":
        nome = request.form["nome"].strip()
        telefono = request.form["telefono"].strip()
        email = request.form["email"].strip()

        nuovo_f = Fornitore(nome=nome, telefono=telefono, email=email)
        db.session.add(nuovo_f)
        db.session.commit()
        return redirect("/fornitori")

    tutti_fornitori = Fornitore.query.order_by(Fornitore.nome.asc()).all()
    return render_template("fornitori.html", fornitori=tutti_fornitori)


@app.route("/fornitori/elimina/<int:id>", methods=["POST"])
def elimina_fornitore(id):
    f = Fornitore.query.get_or_404(id)
    db.session.delete(f)
    db.session.commit()
    return redirect("/fornitori")


@app.route("/report", methods=["GET", "POST"])
def report_vendite():
    data_inizio_str = date.today().strftime("%Y-%m-%d")
    data_fine_str = date.today().strftime("%Y-%m-%d")

    if request.method == "POST":
        data_inizio_str = request.form["data_inizio"]
        data_fine_str = request.form["data_fine"]

    vendite_periodo = Vendita.query.filter(
        func.date(Vendita.data_vendita) >= data_inizio_str,
        func.date(Vendita.data_vendita) <= data_fine_str,
    ).all()

    rep_incasso = sum(v.importo_totale_incassato for v in vendite_periodo)
    rep_guadagno = sum(v.importo_totale_guadagnato for v in vendite_periodo)

    dettagli_periodo = (
        DettaglioVendita.query.join(Vendita)
        .filter(
            func.date(Vendita.data_vendita) >= data_inizio_str,
            func.date(Vendita.data_vendita) <= data_fine_str,
        )
        .order_by(Vendita.data_vendita.desc())
        .all()
    )

    rep_pezzi = sum(d.quantita for d in dettagli_periodo)

    return render_template(
        "report.html",
        data_inizio=data_inizio_str,
        data_fine=data_fine_str,
        rep_pezzi=rep_pezzi,
        rep_incasso=rep_incasso,
        rep_guadagno=rep_guadagno,
        dettagli=dettagli_periodo,
    )


if __name__ == "__main__":
    app.run(debug=True)
