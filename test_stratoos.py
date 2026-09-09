import requests

API_KEY = "pd6ShL8fD3Q9TfbUTcsV0domKu00nkcJ"
SYNC_ID = 17
BASE_URL = "https://app.stratoos.com/api/v1"


def ottieni_access_token():
    """Richiede l'accessToken a Stratoos usando la API Key."""
    url = f"{BASE_URL}/auth"
    payload = {"apiKey": API_KEY}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get("data", {}).get("accessToken")
        else:
            print(f"[STRATOOS ERROR Auth]: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"[STRATOOS EXCEPTION Auth]: {e}")
        return None


def aggiorna_giacenza_stratoos(
    barcode, nuova_giacenza, product_id=None, product_child_id=None
):
    """Sincronizza la giacenza di un barcode reale sul canale 17 di Stratoos."""
    token = ottieni_access_token()
    if not token:
        print("[STRATOOS] Impossibile aggiornare la giacenza: Token non valido.")
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
                f"✅ [STRATOOS SYNC OK] Barcode {barcode} aggiornato a giacenza: {nuova_giacenza}"
            )
            return True
        else:
            print(f"❌ [STRATOOS SYNC ERROR]: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ [STRATOOS EXCEPTION Stock]: {e}")
        return False
