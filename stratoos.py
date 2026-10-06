import logging
import requests

# Configurazione API Stratoos
API_KEY = "pd6ShL8fD3Q9TfbUTcsV0domKu00nkcJ"
SYNC_ID = 17
BASE_URL = "https://app.stratoos.com/api/v1"


def ottieni_access_token():
    """Richiede il token di accesso a Stratoos via API Key."""
    url = f"{BASE_URL}/auth"
    payload = {"apiKey": API_KEY}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "data" in data and "accessToken" in data["data"]:
                return data["data"]["accessToken"]
            return data.get("access_token") or data.get("token")

        logging.error(
            f"[STRATOOS AUTH ERROR]: {response.status_code} - {response.text}"
        )
        return None
    except Exception as e:
        logging.error(f"[STRATOOS AUTH EXCEPTION]: {e}")
        return None


def ottieni_mappa_prodotti_stratoos(token):
    """
    Recupera l'elenco dei prodotti associati al canale SYNC_ID
    e crea una mappa per trovare subito product_id e product_child_id
    tramite Barcode/EAN o Riferimento/Modello.
    """
    url = f"{BASE_URL}/syncs/{SYNC_ID}/products"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            logging.error(
                f"[STRATOOS GET PRODUCTS ERROR]: {response.status_code} - {response.text}"
            )
            return {}

        risposta_json = response.json()
        lista_prodotti = risposta_json.get("data", [])

        # Mappa chiave -> (product_id, product_child_id)
        mappa = {}

        for p in lista_prodotti:
            p_id = p.get("id")
            ref_modello = p.get("reference")
            ean_padre = p.get("ean13")

            if ref_modello:
                mappa[str(ref_modello).strip().lower()] = (p_id, None)
            if ean_padre:
                mappa[str(ean_padre).strip()] = (p_id, None)

            # Se ci sono varianti (figli)
            for child in p.get("children", []):
                child_id = child.get("id")
                child_ean = child.get("ean13")
                child_ref = child.get("reference")

                if child_ean:
                    mappa[str(child_ean).strip()] = (p_id, child_id)
                if child_ref:
                    mappa[str(child_ref).strip().lower()] = (p_id, child_id)

        return mappa

    except Exception as e:
        logging.error(f"[STRATOOS GET PRODUCTS EXCEPTION]: {e}")
        return {}


def aggiorna_giacenza_stratoos(barcode, codice_modello, nuova_giacenza):
    """
    Invia l'aggiornamento della giacenza a Stratoos.
    Cerca prima per Barcode, altrimenti per Codice Modello.
    """
    token = ottieni_access_token()
    if not token:
        print("[STRATOOS UPDATE STOCK]: Token non ottenuto.")
        return False

    mappa = ottieni_mappa_prodotti_stratoos(token)
    if not mappa:
        print("[STRATOOS UPDATE STOCK]: Mappatura prodotti vuota o fallita.")
        return False

    chiave_barcode = str(barcode).strip() if barcode else ""
    chiave_modello = str(codice_modello).strip().lower() if codice_modello else ""

    ids = mappa.get(chiave_barcode) or mappa.get(chiave_modello)

    if not ids:
        print(
            f"[STRATOOS UPDATE STOCK]: Prodotto non trovato per Barcode '{barcode}' o Modello '{codice_modello}'."
        )
        return False

    product_id, product_child_id = ids

    url = f"{BASE_URL}/syncs/{SYNC_ID}/stocks"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    payload = {
        "product_id": product_id,
        "quantity": int(nuova_giacenza),
    }

    if product_child_id:
        payload["product_child_id"] = product_child_id

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code in [200, 201, 204]:
            print(
                f"[STRATOOS SUCCESS]: Giacenza aggiornata per ID {product_id} (Qta: {nuova_giacenza})"
            )
            return True
        else:
            print(f"[STRATOOS ERROR]: {res.status_code} - {res.text}")
            return False
    except Exception as e:
        print(f"[STRATOOS EXCEPTION]: {e}")
        return False
