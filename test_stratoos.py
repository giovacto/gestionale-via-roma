import requests

API_KEY = "pd6ShL8fD3Q9TfbUTcsV0domKu00nkcJ"
BASE_URL = "https://app.stratoos.com/api/v1"

print("🔑 STEP 1: Autenticazione...")
res_auth = requests.post(
    f"{BASE_URL}/auth",
    json={"apiKey": API_KEY},
    headers={"Content-Type": "application/json", "Accept": "application/json"},
)

if res_auth.status_code == 200:
    token = res_auth.json().get("data", {}).get("accessToken")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    print("✅ Autenticato! Cerco la sincronizzazione attiva (sync_id)...")

    # Chiediamo a Stratoos la lista dei canali di sincronizzazione
    res_sync = requests.get(f"{BASE_URL}/syncs", headers=headers)
    print(f"\nRisposta Syncs Status: {res_sync.status_code}")
    print(f"Dati Syncs trovati: {res_sync.text}\n")

else:
    print(f"❌ Errore Auth: {res_auth.status_code}")
