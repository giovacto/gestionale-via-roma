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


def aggiorna_giacenza_stratoos(
    barcode, nuova_giacenza, product_id=None, product_child_id=None
):
    """Sincronizza la giacenza di un barcode reale sul canale 17."""
    token = ottieni_access_token()
    if not token:
        return False

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
        payload["product_id"] = product_id
    if product_child_id:
        payload["product_child_id"] = product_child_id

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


def crea_prodotto_stratoos(codice_modello, nome_articolo, prezzo_listino):
    """Crea la scheda modello principale su Stratoos."""
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
            print(f"✅ [STRATOOS MODELLO CREATO] ID: {data.get('id')}")
            return data.get("id")
        print(
            f"⚠️ [STRATOOS MODELLO EXISTS/ERROR]: {response.status_code} - {response.text}"
        )
        return None
    except Exception as e:
        print(f"❌ [STRATOOS EXCEPTION Prodotto]: {e}")
        return None
