import os
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import func

# Import modelli database
from database.models import (
    db,
    Fornitore,
    Articolo,
    VarianteArticolo,
    Vendita,
    DettaglioVendita,
    Scadenza,
)

# Import integrazione Stratoos
from stratoos import aggiorna_giacenza_stratoos

app = Flask(__name__)
app.config["SECRET_KEY"] = "chiave-segreta-gestionale-via-roma"

basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(
    basedir, "magazzino.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()


# -------------------------------------------------------------------
# ROUTE PRINCIPALI
# -------------------------------------------------------------------


@app.route("/")
@app.route("/dashboard")
def dashboard():
    oggi = date.today()

    # Preleva le vendite effettuate nella giornata di oggi
    vendite_oggi = Vendita.query.filter(
        db.func.date(Vendita.data_vendita) == oggi
    ).all()

    totale_incassato = sum(v.importo_totale_incassato or 0.0 for v in vendite_oggi)
    totale_guadagnato = sum(v.importo_totale_guadagnato or 0.0 for v in vendite_oggi)

    pezzi_oggi = 0
    for v in vendite_oggi:
        if hasattr(v, "dettagli") and v.dettagli:
            pezzi_oggi += sum(d.quantita for d in v.dettagli)

    scadenze_attive = 0

    return render_template(
        "dashboard.html",
        totale_incassato=totale_incassato,
        totale_guadagnato=totale_guadagnato,
        pezzi_oggi=pezzi_oggi,
        scadenze_attive=scadenze_attive,
    )


@app.route("/cassa")
def cassa():
    return render_template("cassa.html")


@app.route("/carico", methods=["GET", "POST"])
def carico():
    if request.method == "POST":
        codice_modello = request.form.get("codice_modello", "").strip()
        nome = request.form.get("nome", "").strip()
        fornitore_id = request.form.get("fornitore_id")
        tipologia = request.form.get("tipologia", "").strip()

        prezzo_acquisto = float(request.form.get("prezzo_acquisto") or 0)
        ricarico_percentuale = float(request.form.get("ricarico_percentuale") or 0)
        prezzo_listino = float(request.form.get("prezzo_listino") or 0)

        if not codice_modello or not nome:
            flash("⚠️ Codice Modello e Nome Prodotto sono obbligatori!", "danger")
            return redirect("/carico")

        # Cerca se il modello esiste già (ricerca case-insensitive)
        articolo = Articolo.query.filter(
            func.lower(Articolo.codice_modello) == codice_modello.lower()
        ).first()

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

        colori = request.form.getlist("colore[]")
        taglie_numeri = request.form.getlist("taglia_numero[]")
        giacenze = request.form.getlist("giacenza[]")
        barcodes = request.form.getlist("barcode[]")

        conteggio_inseriti = 0

        for i in range(len(colori)):
            bcode = barcodes[i].strip() if i < len(barcodes) else ""
            num = taglie_numeri[i].strip() if i < len(taglie_numeri) else ""
            col = colori[i].strip() if i < len(colori) else "Nero"
            qta = int(giacenze[i]) if (i < len(giacenze) and giacenze[i]) else 1

            # Se la taglia è vuota (es. per le borse/accessori), imposta automaticamente "TU"
            if not num:
                num = "TU"

            if not bcode:
                continue

            variante_esistente = VarianteArticolo.query.filter_by(barcode=bcode).first()

            if variante_esistente:
                variante_esistente.giacenza += qta
                var_target = variante_esistente
            else:
                var_target = VarianteArticolo(
                    articolo_id=articolo.id,
                    barcode=bcode,
                    colore=col,
                    taglia_numero=num,
                    giacenza=qta,
                )
                db.session.add(var_target)

            conteggio_inseriti += qta
            db.session.commit()

            # Sincronizzazione automatica giacenza su Stratoos
            try:
                aggiorna_giacenza_stratoos(
                    barcode=var_target.barcode,
                    codice_modello=articolo.codice_modello,
                    nuova_giacenza=var_target.giacenza,
                )
            except Exception as e:
                print(f"Errore sincronizzazione Stratoos: {e}")

        flash(f"⚓ Movimentati {conteggio_inseriti} pezzi con successo!", "success")
        return redirect("/carico")

    lista_fornitori = Fornitore.query.order_by(Fornitore.nome.asc()).all()
    return render_template("carico.html", fornitori=lista_fornitori)


# -------------------------------------------------------------------
# ENDPOINT API (AUTOCOMPILAZIONE E VERIFICHE)
# -------------------------------------------------------------------


@app.route("/api/check_modello")
@app.route("/api/check_modello/<path:codice>")
def check_modello(codice=None):
    if not codice:
        codice = request.args.get("q", "").strip()
    else:
        codice = codice.strip()

    if not codice:
        return jsonify({"esiste": False})

    articolo = Articolo.query.filter(
        func.lower(Articolo.codice_modello) == codice.lower()
    ).first()

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
def check_barcode(barcode):
    variante = VarianteArticolo.query.filter_by(barcode=barcode.strip()).first()
    if variante:
        articolo = variante.articolo
        return jsonify(
            {
                "esiste": True,
                "nome": articolo.nome,
                "colore": variante.colore,
                "taglia_numero": variante.taglia_numero,
            }
        )
    return jsonify({"esiste": False}), 404


@app.route("/fornitori")
def fornitori():
    lista_fornitori = Fornitore.query.all()
    return render_template("fornitori.html", fornitori=lista_fornitori)


@app.route("/report", methods=["GET", "POST"])
def report():
    rep_incasso = 0.0
    rep_vendite = 0
    rep_guadagno = 0.0
    rep_margine = 0.0

    data_inizio = request.form.get("data_inizio") or request.args.get("data_inizio")
    data_fine = request.form.get("data_fine") or request.args.get("data_fine")

    query = Vendita.query

    if data_inizio:
        d_inizio = datetime.strptime(data_inizio, "%Y-%m-%d")
        query = query.filter(Vendita.data_vendita >= d_inizio)
    if data_fine:
        d_fine = datetime.strptime(data_fine + " 23:59:59", "%Y-%m-%d %H:%M:%S")
        query = query.filter(Vendita.data_vendita <= d_fine)

    vendite_filtrate = query.all()

    for v in vendite_filtrate:
        rep_incasso += v.importo_totale_incassato or 0.0
        rep_guadagno += v.importo_totale_guadagnato or 0.0
        if hasattr(v, "dettagli") and v.dettagli:
            rep_vendite += sum(d.quantita for d in v.dettagli)

    if rep_incasso > 0:
        rep_margine = (rep_guadagno / rep_incasso) * 100.0

    return render_template(
        "report.html",
        rep_incasso=rep_incasso,
        rep_vendite=rep_vendite,
        rep_guadagno=rep_guadagno,
        rep_margine=rep_margine,
        data_inizio=data_inizio or "",
        data_fine=data_fine or "",
    )


@app.route("/scadenziario")
def scadenziario():
    return render_template("scadenziario.html")


@app.route("/tools")
def tools():
    return render_template("tools.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
