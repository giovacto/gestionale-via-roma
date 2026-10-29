import sys
import os
import requests

# Imposta automaticamente la cartella di lavoro corrente sul percorso dello script
CARTELLA_PROGETTO = os.path.dirname(os.path.abspath(__file__))
os.chdir(CARTELLA_PROGETTO)
if CARTELLA_PROGETTO not in sys.path:
    sys.path.append(CARTELLA_PROGETTO)

from app import app
from database.models import db, Articolo, VarianteArticolo, Vendita, DettaglioVendita
import stratoos


def controlla_nuovi_ordini_web():
    """Controlla gli ordini web su Stratoos e aggiorna il DB locale."""
    print("🔄 Avvio controllo ordini online...")

    # 1. Autenticazione centralizzata e robusta tramite stratoos.py
    token = stratoos.ottieni_access_token()
    if not token:
        print("❌ Impossibile autenticarsi su Stratoos.")
        return

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # 2. Richiesta ordini pendenti
    try:
        res_orders = requests.get(
            f"{stratoos.BASE_URL}/syncs/{stratoos.SYNC_ID}/orders?status=pending",
            headers=headers,
            timeout=10,
        )
    except Exception as e:
        print(f"❌ Errore di connessione a Stratoos: {e}")
        return

    if res_orders.status_code != 200:
        print(
            f"ℹ️ Nessun ordine o endpoint non pronto (HTTP {res_orders.status_code})."
        )
        return

    ordini = res_orders.json().get("data", [])
    if not ordini:
        print("✅ Nessun nuovo ordine da elaborare.")
        return

    # 3. Processamento all'interno del contesto dell'applicazione Flask
    with app.app_context():
        for ordine in ordini:
            totale_incassato = 0.0
            totale_guadagnato = 0.0
            dettagli_da_salvare = []

            for item in ordine.get("items", []):
                ean = item.get("ean13") or item.get("barcode")
                ref = item.get("reference")
                variante = None

                # Ricerca 1: tramite Barcode EAN13
                if ean:
                    variante = VarianteArticolo.query.filter_by(
                        barcode=str(ean).strip()
                    ).first()

                # Ricerca 2: se nel reference è finito il barcode a 13 cifre
                if not variante and ref and str(ref).strip().isdigit():
                    variante = VarianteArticolo.query.filter_by(
                        barcode=str(ref).strip()
                    ).first()

                # Ricerca 3: se il reference è nel formato MODELLO-TAGLIA (es. I617421D/613-38)
                if not variante and ref and "-" in str(ref):
                    parti = str(ref).strip().rsplit("-", 1)
                    if len(parti) == 2:
                        cod_modello, taglia = parti
                        art = Articolo.query.filter_by(
                            codice_modello=cod_modello
                        ).first()
                        if art:
                            variante = VarianteArticolo.query.filter(
                                VarianteArticolo.articolo_id == art.id,
                                (VarianteArticolo.taglia_numero == taglia)
                                | (VarianteArticolo.taglia == taglia),
                            ).first()

                if variante and variante.giacenza > 0:
                    articolo = variante.articolo
                    prezzo_listino = float(articolo.prezzo_listino or 0.0)
                    prezzo_acquisto = float(articolo.prezzo_acquisto or 0.0)
                    prezzo_vendita = float(item.get("price", prezzo_listino))
                    guadagno = prezzo_vendita - prezzo_acquisto

                    # Decrementa magazzino locale
                    variante.giacenza -= 1
                    totale_incassato += prezzo_vendita
                    totale_guadagnato += guadagno

                    dettaglio = DettaglioVendita(
                        variante_id=variante.id,
                        quantita=1,
                        prezzo_singolo_venduto=prezzo_vendita,
                    )
                    dettagli_da_salvare.append(dettaglio)
                else:
                    print(
                        f"   ⚠️ Variante non trovata o esaurita per l'articolo: Ref={ref}, EAN={ean}"
                    )

            if dettagli_da_salvare:
                nuova_vendita = Vendita(
                    importo_totale_incassato=totale_incassato,
                    importo_totale_guadagnato=totale_guadagnato,
                    dettagli=dettagli_da_salvare,
                )
                db.session.add(nuova_vendita)
                db.session.commit()
                print(
                    f"🎉 Ordine Web #{ordine.get('id')} registrato con successo nel DB locale!"
                )


if __name__ == "__main__":
    controlla_nuovi_ordini_web()
