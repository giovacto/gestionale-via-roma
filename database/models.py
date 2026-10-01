from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Fornitore(db.Model):
    __tablename__ = "fornitore"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(50))
    email = db.Column(db.String(100))
    articoli = db.relationship("Articolo", backref="fornitore", lazy=True)


class Articolo(db.Model):
    __tablename__ = "articolo"
    id = db.Column(db.Integer, primary_key=True)
    codice_modello = db.Column(db.String(50), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(100))
    fornitore_id = db.Column(db.Integer, db.ForeignKey("fornitore.id"), nullable=True)
    tipologia = db.Column(db.String(50), nullable=False)
    prezzo_acquisto = db.Column(db.Float, nullable=False)
    ricarico_percentuale = db.Column(db.Float, nullable=False)
    prezzo_listino = db.Column(db.Float, nullable=False)
    stratoos_id = db.Column(db.Integer, nullable=True)  # ID Modello Padre Stratoos
    varianti = db.relationship(
        "VarianteArticolo", backref="articolo", lazy=True, cascade="all, delete-orphan"
    )


class VarianteArticolo(db.Model):
    __tablename__ = "variante_articolo"
    id = db.Column(db.Integer, primary_key=True)
    articolo_id = db.Column(db.Integer, db.ForeignKey("articolo.id"), nullable=False)
    barcode = db.Column(db.String(50), unique=True, nullable=False)
    colore = db.Column(db.String(50), nullable=False)
    taglia_numero = db.Column(db.String(20), nullable=False)
    giacenza = db.Column(db.Integer, nullable=False, default=0)
    stratoos_child_id = db.Column(
        db.Integer, nullable=True
    )  # ID Variante Figlio Stratoos


class Vendita(db.Model):
    __tablename__ = "vendita"
    id = db.Column(db.Integer, primary_key=True)
    data_vendita = db.Column(db.DateTime, default=db.func.now())
    importo_totale_incassato = db.Column(db.Float, nullable=False)
    importo_totale_guadagnato = db.Column(db.Float, nullable=False)
    dettagli = db.relationship("DettaglioVendita", backref="vendita", lazy=True)


class DettaglioVendita(db.Model):
    __tablename__ = "dettaglio_vendita"
    id = db.Column(db.Integer, primary_key=True)
    vendita_id = db.Column(db.Integer, db.ForeignKey("vendita.id"), nullable=False)
    variante_id = db.Column(
        db.Integer, db.ForeignKey("variante_articolo.id"), nullable=False
    )
    quantita = db.Column(db.Integer, nullable=False)
    prezzo_singolo_venduto = db.Column(db.Float, nullable=False)
    variante = db.relationship("VarianteArticolo")


class Scadenza(db.Model):
    __tablename__ = "scadenza"
    id = db.Column(db.Integer, primary_key=True)
    fornitore_id = db.Column(db.Integer, db.ForeignKey("fornitore.id"), nullable=False)
    descrizione = db.Column(db.String(200), nullable=False)
    importo = db.Column(db.Float, nullable=False)
    data_scadenza = db.Column(db.Date, nullable=False)
    pagato = db.Column(db.Boolean, default=False)
    fornitore = db.relationship("Fornitore")
