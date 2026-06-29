from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Fornitore(db.Model):
    __tablename__ = 'fornitori'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    telefono = db.Column(db.String(50))
    email = db.Column(db.String(100))
    
    # Relazioni automatiche verso le altre tabelle
    articoli = db.relationship('Articolo', backref='fornitore', lazy=True)
    scadenze = db.relationship('Scadenza', backref='fornitore', lazy=True)

class Articolo(db.Model):
    __tablename__ = 'articoli'
    id = db.Column(db.Integer, primary_key=True)
    codice_modello = db.Column(db.String(100), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(100))
    tipologia = db.Column(db.String(50))
    prezzo_acquisto = db.Column(db.Float, nullable=False)
    ricarico_percentuale = db.Column(db.Float, nullable=False)
    prezzo_listino = db.Column(db.Float, nullable=False)
    
    # Collegamento reale al Fornitore
    fornitore_id = db.Column(db.Integer, db.ForeignKey('fornitori.id'), nullable=False)
    
    varianti = db.relationship('VarianteArticolo', backref='articolo', lazy=True, cascade="all, delete-orphan")

class VarianteArticolo(db.Model):
    __tablename__ = 'varianti_articoli'
    id = db.Column(db.Integer, primary_key=True)
    articolo_id = db.Column(db.Integer, db.ForeignKey('articoli.id'), nullable=False)
    barcode = db.Column(db.String(100), unique=True, nullable=False)
    colore = db.Column(db.String(50), nullable=False)
    taglia_numero = db.Column(db.String(20), nullable=False)
    giacenza = db.Column(db.Integer, default=0)
    
    dettagli_vendita = db.relationship('DettaglioVendita', backref='variante', lazy=True)

class Vendita(db.Model):
    __tablename__ = 'vendite'
    id = db.Column(db.Integer, primary_key=True)
    data_vendita = db.Column(db.DateTime, default=datetime.now)
    importo_totale_incassato = db.Column(db.Float, nullable=False)
    importo_totale_guadagnato = db.Column(db.Float, nullable=False)
    
    dettagli = db.relationship('DettaglioVendita', backref='vendita', lazy=True)

class DettaglioVendita(db.Model):
    __tablename__ = 'dettagli_vendite'
    id = db.Column(db.Integer, primary_key=True)
    vendita_id = db.Column(db.Integer, db.ForeignKey('vendite.id'), nullable=False)
    variante_id = db.Column(db.Integer, db.ForeignKey('varianti_articoli.id'), nullable=False)
    quantita = db.Column(db.Integer, nullable=False)
    prezzo_singolo_venduto = db.Column(db.Float, nullable=False)

class Scadenza(db.Model):
    __tablename__ = 'scadenze'
    id = db.Column(db.Integer, primary_key=True)
    fornitore_id = db.Column(db.Integer, db.ForeignKey('fornitori.id'), nullable=False)
    descrizione = db.Column(db.String(200))
    importo = db.Column(db.Float, nullable=False)
    data_scadenza = db.Column(db.Date, nullable=False)
    pagato = db.Column(db.Boolean, default=False)