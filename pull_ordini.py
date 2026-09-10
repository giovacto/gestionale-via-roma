import sys
import os
import time
import requests

# Imposta automaticamente la cartella di lavoro corrente sul percorso dello script
CARTELLA_PROGETTO = os.path.dirname(os.path.abspath(__file__))
os.chdir(CARTELLA_PROGETTO)
if CARTELLA_PROGETTO not in sys.path:
    sys.path.append(CARTELLA_PROGETTO)

from app import app
from database.models import db, VarianteArticolo, Vendita, DettaglioVendita

API_KEY = "pd6ShL8fD3Q9TfbUTcsV0domKu00nkcJ"
SYNC_ID = 17
BASE_URL = "https://app.stratoos.com/api/v1"


def controlla_nuovi_ordini_web():
    """Controlla gli ordini web su Stratoos e aggiorna il DB locale."""
    print("🔄 Avvio controllo ordini online...")

    # 1. Autenticazione
    res_auth = requests.post(
        f"{BASE_URL}/auth",
        json={"apiKey": API_KEY},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=10,
    )
    if res_auth.status_code != 200:
        print("❌ Impossibile autenticarsi su Stratoos.")
        return

    token = res_auth.json().get("data", {}).get("accessToken")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # 2. Richiesta ordini pendenti
    res_orders = requests.get(
        f"{BASE_URL}/syncs/{SYNC_ID}/orders?status=pending", headers=headers, timeout=10
    )
    if res_orders.status_code != 200:
        print(
            f"ℹ️ Nessun nuovo ordine o endpoint non ancora attivo ({res_orders.status_code})."
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
                barcode = item.get("reference")
                variante = VarianteArticolo.query.filter_by(barcode=barcode).first()

                if variante and variante.giacenza > 0:
                    articolo = variante.articolo
                    prezzo_vendita = float(item.get("price", articolo.prezzo_listino))
                    guadagno = prezzo_vendita - articolo.prezzo_acquisto

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
    print("🚀 Servizio di Polling Ordini Avviato in Background...")
    while True:
        try:
            controlla_nuovi_ordini_web()
        except Exception as e:
            print(f"⚠️ Errore imprevisto durante il controllo ordini: {e}")

        # Mette il demone in pausa per 15 minuti (900 secondi)
        print("💤 Attesa 15 minuti prima del prossimo controllo...\n")
        time.sleep(900)
