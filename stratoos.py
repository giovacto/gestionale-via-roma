import requests

API_KEY = "pd6ShL8fD3Q9TfbUTcsV0domKu00nkcJ"
BASE_URL = "https://app.stratoos.com/api/v1"


def ottieni_access_token():
    """Richiede il pass temporaneo (accessToken) a Stratoos usando la API Key."""
    url = f"{BASE_URL}/auth"
    payload = {"apiKey": API_KEY}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Estrae l'accessToken dalla risposta JSON
            return data.get("data", {}).get("accessToken")
        else:
            print(f"[STRATOOS ERROR Auth]: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"[STRATOOS EXCEPTION Auth]: {e}")
        return None


def aggiorna_giacenza_stratoos(barcode, nuova_giacenza):
    """Sincronizza la giacenza di un singolo barcode su Stratoos."""
    token = ottieni_access_token()
    if not token:
        print("[STRATOOS] Impossibile aggiornare la giacenza: Token non valido.")
        return False

    # L'endpoint di aggiornamento stock (da documentazione Stratoos)
    url = f"{BASE_URL}/stock"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Struttura del messaggio corrispondente a UpdateStockRequest
    payload = {
        "reference": str(barcode),
        "quantity_available": int(nuova_giacenza),
        "quantity_physical": int(nuova_giacenza),
        "quantity_reserved": 0,
    }

    try:
        response = requests.put(url, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201, 204]:
            print(
                f" [STRATOOS SYNC OK] Barcode {barcode} aggiornato a giacenza: {nuova_giacenza}"
            )
            return True
        else:
            print(f"❌ [STRATOOS SYNC ERROR]: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ [STRATOOS EXCEPTION Stock]: {e}")
        return False
