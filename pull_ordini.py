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


def risolvi_variante_da_stratoos(product_id, product_child_id, token):
    """Recupera EAN o Reference da Stratoos per individuare la variante nel DB locale."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # 1. Se è una variante figlia (scarpa con taglia)
    if product_child_id:
        url_child = f"{stratoos.BASE_URL}/syncs/{stratoos.SYNC_ID}/products/{product_id}/productChildren"
        try:
            res = requests.get(url_child, headers=headers, timeout=10)
            if res.status_code == 200:
                for ch in res.json().get("data", []):
                    if ch.get("id") == int(product_child_id):
                        ean = ch.get("ean13")
                        ref = ch.get("reference")
                        if ean:
                            v = VarianteArticolo.query.filter_by(
                                barcode=str(ean).strip()
                            ).first()
                            if v:
                                return v
                        if ref and "-" in str(ref):
                            parti = str(ref).strip().rsplit("-", 1)
                            art = Articolo.query.filter_by(
                                codice_modello=parti[0]
                            ).first()
                            if art:
                                return VarianteArticolo.query.filter(
                                    VarianteArticolo.articolo_id == art.id,
                                    (VarianteArticolo.taglia_numero == parti[1])
                                    | (VarianteArticolo.taglia == parti[1]),
                                ).first()
        except Exception as e:
            print(f"⚠️ Errore risoluzione variante figlia: {e}")

    # 2. Se è un prodotto senza varianti (es. accessorio/borsa)
    if product_id:
        url_parent = (
            f"{stratoos.BASE_URL}/syncs/{stratoos.SYNC_ID}/products/{product_id}"
        )
        try:
            res = requests.get(url_parent, headers=headers, timeout=10)
            if res.status_code == 200:
                p_data = res.json().get("data", {})
                ean = p_data.get("ean13")
                ref = p_data.get("reference")
                if ean:
                    v = VarianteArticolo.query.filter_by(
                        barcode=str(ean).strip()
                    ).first()
                    if v:
                        return v
                if ref:
                    art = Articolo.query.filter_by(
                        codice_modello=str(ref).strip()
                    ).first()
                    if art and art.varianti:
                        return art.varianti[0]
        except Exception as e:
            print(f"⚠️ Errore risoluzione prodotto padre: {e}")

    return None


def controlla_nuovi_ordini_web():
    """Controlla gli ordini web su Stratoos e aggiorna il DB locale."""
    print("🔄 Avvio controllo ordini online...")

    token = stratoos.ottieni_access_token()
    if not token:
        print("❌ Impossibile autenticarsi su Stratoos.")
        return

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # Richiediamo esplicitamente le righe (rows), lo stato e il riferimento cliente
    params = [
        ("fields[]", "id"),
        ("fields[]", "reference"),
        ("fields[]", "status"),
        ("fields[]", "created_at"),
        ("fields[]", "rows"),
        ("fields[]", "customer"),
    ]

    try:
        url = f"{stratoos.BASE_URL}/syncs/{stratoos.SYNC_ID}/orders"
        res_orders = requests.get(url, headers=headers, params=params, timeout=10)
    except Exception as e:
        print(f"❌ Errore di connessione a Stratoos: {e}")
        return

    if res_orders.status_code != 200:
        print(f"ℹ️ Errore consultazione ordini (HTTP {res_orders.status_code}).")
        return

    ordini = res_orders.json().get("data", [])
    if not ordini:
        print("✅ Nessun nuovo ordine presente su Stratoos.")
        return

    with app.app_context():
        for ordine in ordini:
            ordine_id = ordine.get("id")
            ordine_ref = ordine.get("reference") or f"ID-{ordine_id}"
            marcatura_ordine = f"Web Stratoos #{ordine_id}"

            # Controllo anti-duplicazione: verifica se l'ordine è già stato importato
            gia_registrato = Vendita.query.filter(
                (Vendita.tipo_pagamento == marcatura_ordine)
                | (Vendita.note.like(f"%{marcatura_ordine}%"))
            ).first()

            if gia_registrato:
                continue

            righe = ordine.get("rows", [])
            if not righe:
                continue

            totale_incassato = 0.0
            totale_guadagnato = 0.0
            dettagli_da_salvare = []

            for row in righe:
                qta = int(row.get("quantity") or 1)
                product_id = row.get("product_id")
                product_child_id = row.get("product_child_id")

                variante = risolvi_variante_da_stratoos(
                    product_id, product_child_id, token
                )

                if variante:
                    articolo = variante.articolo
                    prezzo_unitario = float(
                        row.get("price") or articolo.prezzo_listino or 0.0
                    )
                    costo_acquisto = float(articolo.prezzo_acquisto or 0.0)

                    # Decrementa magazzino locale per la quantità venduta
                    variante.giacenza = max(0, variante.giacenza - qta)

                    subtotale = prezzo_unitario * qta
                    totale_incassato += subtotale
                    totale_guadagnato += (prezzo_unitario - costo_acquisto) * qta

                    dettaglio = DettaglioVendita(
                        variante_id=variante.id,
                        quantita=qta,
                        prezzo_singolo_venduto=prezzo_unitario,
                    )
                    dettagli_da_salvare.append(dettaglio)
                else:
                    print(
                        f"   ⚠️ Variante non trovata nel gestionale: ProdID={product_id}, ChildID={product_child_id}"
                    )

            if dettagli_da_salvare:
                nuova_vendita = Vendita(
                    importo_totale_incassato=totale_incassato,
                    importo_totale_guadagnato=totale_guadagnato,
                    tipo_pagamento=marcatura_ordine,
                    note=f"Ordine Web Ref: {ordine_ref}",
                    dettagli=dettagli_da_salvare,
                )
                db.session.add(nuova_vendita)
                db.session.commit()
                print(
                    f"🎉 Ordine Web #{ordine_id} (Ref: {ordine_ref}) registrato con successo nel DB locale!"
                )


if __name__ == "__main__":
    controlla_nuovi_ordini_web()
