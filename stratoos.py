import logging
import requests

# Configurazione API Stratoos
API_KEY = "pd6ShL8fD3Q9TfbUTcsV0domKu00nkcJ"
SYNC_ID = 17
BASE_URL = "https://app.stratoos.com/api/v1"

_modelli_sincronizzati_cache = set()


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
        return None
    except Exception as e:
        logging.error(f"[STRATOOS AUTH EXCEPTION]: {e}")
        return None


def ottieni_mappa_prodotti_stratoos(token):
    """Mappa i prodotti esistenti per identificare i prodotti padre."""
    url = f"{BASE_URL}/syncs/{SYNC_ID}/products"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return {}
        risposta_json = response.json()
        lista_prodotti = risposta_json.get("data", [])
        mappa = {}
        for p in lista_prodotti:
            p_id = p.get("id")
            ref_modello = p.get("reference")
            ean_padre = p.get("ean13")
            if ref_modello:
                mappa[str(ref_modello).strip().lower()] = p_id
            if ean_padre:
                mappa[str(ean_padre).strip()] = p_id
        return mappa
    except Exception as e:
        logging.error(f"[STRATOOS GET PRODUCTS EXCEPTION]: {e}")
        return {}


def _gestisci_entita(token, endpoint_name, nome_entita):
    """Gestisce Brand e Categorie sotto /syncs/17/manufacturers e /syncs/17/categories."""
    if not nome_entita:
        return None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"{BASE_URL}/syncs/{SYNC_ID}/{endpoint_name}"

    # 1. Cerca se l'entità esiste già
    try:
        res_get = requests.get(url, headers=headers, timeout=10)
        if res_get.status_code == 200:
            dati = res_get.json().get("data", [])
            for item in dati:
                for lang in item.get("langs", []):
                    if (
                        str(lang.get("name", "")).strip().lower()
                        == str(nome_entita).strip().lower()
                    ):
                        return item.get("id")
    except Exception:
        pass

    # 2. Crea l'entità se non trovata
    try:
        payload = {"langs": [{"lang_id": 1, "name": str(nome_entita)}]}
        res_post = requests.post(url, json=payload, headers=headers, timeout=10)
        if res_post.status_code in [200, 201]:
            return res_post.json().get("data", {}).get("id")
    except Exception:
        pass
    return None


def sincronizza_anagrafica_articolo(articolo, token, mappa):
    """Invia il Prodotto Padre con il Brand associato tramite manufacturer_id."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    brand_nome = articolo.fornitore.nome if articolo.fornitore else articolo.brand
    brand_id = _gestisci_entita(token, "manufacturers", brand_nome or "Via Roma")

    payload_padre = {
        "price": float(articolo.prezzo_listino or 0.0),
        "reference": str(articolo.codice_modello),
        "langs": [{"lang_id": 1, "name": str(articolo.nome)}],
    }

    if brand_id:
        payload_padre["manufacturer_id"] = int(brand_id)

    chiave_modello = str(articolo.codice_modello).strip().lower()

    try:
        if chiave_modello in mappa:
            product_id = mappa[chiave_modello]
            res = requests.put(
                f"{BASE_URL}/syncs/{SYNC_ID}/products/{product_id}",
                json=payload_padre,
                headers=headers,
                timeout=10,
            )
        else:
            res = requests.post(
                f"{BASE_URL}/syncs/{SYNC_ID}/products",
                json=payload_padre,
                headers=headers,
                timeout=10,
            )

        return res.status_code in [200, 201, 204]
    except Exception as e:
        logging.error(f"[STRATOOS PRODUCT SYNC ERROR] {e}")
        return False


def aggiorna_giacenza_stratoos(barcode, codice_modello, nuova_giacenza):
    """Sincronizza anagrafica e poi aggiorna le quantità su Stratoos."""
    global _modelli_sincronizzati_cache

    token = ottieni_access_token()
    if not token:
        print("[STRATOOS UPDATE STOCK]: Token non ottenuto.")
        return False

    chiave_modello = str(codice_modello).strip().lower() if codice_modello else ""

    # 1. Sincronizzazione anagrafica se non ancora eseguita in questa sessione
    try:
        if chiave_modello and chiave_modello not in _modelli_sincronizzati_cache:
            from database.models import VarianteArticolo

            variante = VarianteArticolo.query.filter_by(
                barcode=str(barcode).strip()
            ).first()
            if variante and variante.articolo:
                mappa_temp = ottieni_mappa_prodotti_stratoos(token)
                sincronizza_anagrafica_articolo(variante.articolo, token, mappa_temp)
                _modelli_sincronizzati_cache.add(chiave_modello)
    except Exception as e:
        print(f"[STRATOOS ANAGRAFICA EXCEPTION]: {e}")

    # 2. Sincronizzazione Stock
    url_products = f"{BASE_URL}/syncs/{SYNC_ID}/products"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    try:
        res = requests.get(url_products, headers=headers, timeout=10)
        if res.status_code != 200:
            return False
        lista_prodotti = res.json().get("data", [])

        product_id = None
        product_child_id = None
        chiave_barcode = str(barcode).strip()

        for p in lista_prodotti:
            p_ref = str(p.get("reference", "")).strip().lower()
            if p_ref == chiave_modello:
                product_id = p.get("id")
            for child in p.get("children", []):
                if str(child.get("ean13", "")).strip() == chiave_barcode:
                    product_id = p.get("id")
                    product_child_id = child.get("id")
                    break
            if product_child_id:
                break

        if not product_id:
            print(
                f"[STRATOOS UPDATE STOCK]: Prodotto non trovato per Barcode '{barcode}' o Modello '{codice_modello}'."
            )
            return False

        url_stock = f"{BASE_URL}/syncs/{SYNC_ID}/stocks"
        headers_post = {
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

        res_stock = requests.post(
            url_stock, json=payload, headers=headers_post, timeout=10
        )
        if res_stock.status_code in [200, 201, 204]:
            print(f"[STRATOOS SUCCESS]: Giacenza aggiornata (Qta: {nuova_giacenza})")
            return True
        else:
            print(f"[STRATOOS ERROR]: {res_stock.status_code} - {res_stock.text}")
            return False
    except Exception as e:
        print(f"[STRATOOS EXCEPTION]: {e}")
        return False
