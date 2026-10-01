import requests

API_KEY = "pd6ShL8fD3Q9TfbUTcsV0domKu00nkcJ"
SYNC_ID = 17
BASE_URL = "https://app.stratoos.com/api/v1"


def ottieni_access_token():
    """Richiede il token di accesso a Stratoos."""
    url = f"{BASE_URL}/auth"
    payload = {"apiKey": API_KEY}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get("data", {}).get("accessToken")
        print(f"[STRATOOS AUTH ERROR]: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        print(f"[STRATOOS AUTH EXCEPTION]: {e}")
        return None


def cerca_prodotto_stratoos(reference_o_barcode):
    """Recupera gli ID di Stratoos (product_id e product_child_id) tramite ricerca API."""
    token = ottieni_access_token()
    if not token:
        return None, None

    url = f"{BASE_URL}/syncs/{SYNC_ID}/products"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            params={"search": str(reference_o_barcode)},
            timeout=10,
        )
        if response.status_code == 200:
            prodotti = response.json().get("data", [])
            for prod in prodotti:
                p_id = prod.get("id") or prod.get("product_id")
                children = prod.get("children", []) or prod.get("variants", [])
                for child in children:
                    c_ref = str(child.get("reference") or child.get("barcode") or "")
                    c_id = child.get("id") or child.get("product_child_id")
                    if c_ref == str(reference_o_barcode):
                        return p_id, c_id
                if str(prod.get("reference")) == str(reference_o_barcode):
                    first_child = children[0].get("id") if children else None
                    return p_id, first_child
        return None, None
    except Exception as e:
        print(f"❌ [STRATOOS EXCEPTION Lookup]: {e}")
        return None, None


def crea_prodotto_stratoos(codice_modello, nome_articolo, prezzo_listino):
    """Crea la scheda modello su Stratoos e restituisce l'ID del prodotto padre."""
    token = ottieni_access_token()
    if not token:
        return None

    url = f"{BASE_URL}/syncs/{SYNC_ID}/products"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "reference": str(codice_modello),
        "price": float(prezzo_listino),
        "langs": [
            {
                "lang_id": 1,
                "name": str(nome_articolo),
                "description_short": str(nome_articolo),
                "description": str(nome_articolo),
            }
        ],
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201]:
            data = response.json().get("data", {})
            p_id = data.get("id") or data.get("product_id")
            print(f"✅ [STRATOOS MODELLO CREATO] ID: {p_id}")
            return p_id

        # Se il modello esiste già su Stratoos, recuperiamo il suo ID
        p_id, _ = cerca_prodotto_stratoos(codice_modello)
        if p_id:
            print(f"ℹ️ [STRATOOS MODELLO RECUPERATO] ID: {p_id}")
            return p_id

        print(
            f"⚠️ [STRATOOS MODELLO EXISTS/ERROR]: {response.status_code} - {response.text}"
        )
        return None
    except Exception as e:
        print(f"❌ [STRATOOS EXCEPTION Prodotto]: {e}")
        return None


def aggiorna_giacenza_stratoos(
    barcode, nuova_giacenza, product_id=None, product_child_id=None
):
    """Sincronizza la giacenza inoltrando anche product_id e product_child_id."""
    token = ottieni_access_token()
    if not token:
        return False

    # Se gli ID non sono salvati localmente, tenta la ricerca al volo tramite API
    if not product_id or not product_child_id:
        p_id, c_id = cerca_prodotto_stratoos(barcode)
        product_id = product_id or p_id
        product_child_id = product_child_id or c_id

    url = f"{BASE_URL}/syncs/{SYNC_ID}/stocks"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "reference": str(barcode),
        "quantity_available": int(nuova_giacenza),
        "quantity_physical": int(nuova_giacenza),
        "quantity_reserved": 0,
    }

    if product_id:
        payload["product_id"] = int(product_id)
    if product_child_id:
        payload["product_child_id"] = int(product_child_id)

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201, 204]:
            print(
                f"✅ [STRATOOS SYNC OK] Barcode {barcode} -> Giacenza: {nuova_giacenza}"
            )
            return True
        print(f"❌ [STRATOOS SYNC ERROR]: {response.status_code} - {response.text}")
        return False
    except Exception as e:
        print(f"❌ [STRATOOS EXCEPTION Stock]: {e}")
        return False
