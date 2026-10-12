import logging
import requests

# Configurazione API Stratoos
API_KEY = "pd6ShL8fD3Q9TfbUTcsV0domKu00nkcJ"
SYNC_ID = 17
BASE_URL = "https://app.stratoos.com/api/v1"

# Cache per evitare di inviare la stessa anagrafica 10 volte se si caricano 10 taglie insieme
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
    """Mappa i prodotti esistenti per evitare doppioni."""
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
                mappa[str(ref_modello).strip().lower()] = (p_id, None)
            if ean_padre:
                mappa[str(ean_padre).strip()] = (p_id, None)
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


def _gestisci_entita(token, endpoint, nome_entita):
    """Cerca Brand o Categorie su Stratoos. Se non esistono, li crea e restituisce l'ID."""
    if not nome_entita:
        return None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # 1. Cerca se esiste già
    try:
        res_get = requests.get(f"{BASE_URL}/{endpoint}", headers=headers, timeout=10)
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

    # 2. Crealo se non esiste
    try:
        payload = {"langs": [{"lang_id": 1, "name": str(nome_entita)}]}
        res_post = requests.post(
            f"{BASE_URL}/{endpoint}", json=payload, headers=headers, timeout=10
        )
        if res_post.status_code in [200, 201]:
            return res_post.json().get("data", {}).get("id")
    except Exception:
        pass
    return None


def sincronizza_anagrafica_articolo(articolo, token, mappa):
    """Invia Brand, Categoria, Prodotto Padre e Varianti Figlio a Stratoos."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    brand_nome = articolo.fornitore.nome if articolo.fornitore else articolo.brand
    brand_id = _gestisci_entita(token, "manufacturers", brand_nome or "Via Roma")
    cat_id = _gestisci_entita(token, "categories", articolo.tipologia or "Generico")

    payload_padre = {
        "price": float(articolo.prezzo_listino or 0.0),
        "reference": str(articolo.codice_modello),
        "langs": [{"lang_id": 1, "name": str(articolo.nome)}],
    }

    if brand_id:
        payload_padre["manufacturer"] = {"id": brand_id}
    if cat_id:
        payload_padre["categories"] = [{"id": cat_id}]

    chiave_modello = str(articolo.codice_modello).strip().lower()
    product_id = None

    try:
        # Crea o aggiorna il Modello Principale (Padre)
        if chiave_modello in mappa:
            product_id = mappa[chiave_modello][0]
            requests.put(
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
            if res.status_code in [200, 201]:
                product_id = res.json().get("data", {}).get("id")
    except Exception as e:
        logging.error(f"[STRATOOS PADRE ERROR] {e}")

    if not product_id:
        return False

    # Crea o aggiorna le singole Varianti (Colori/Taglie)
    for var in articolo.varianti:
        payload_figlio = {
            "product_id": product_id,
            "ean13": str(var.barcode),
            "price": float(articolo.prezzo_listino or 0.0),
            "reference": f"{articolo.codice_modello}-{var.taglia_numero}",
            "langs": [
                {
                    "lang_id": 1,
                    "name": f"{articolo.nome} - Colore: {var.colore} - Taglia: {var.taglia_numero}",
                }
            ],
        }
        chiave_barcode = str(var.barcode).strip()
        try:
            if chiave_barcode in mappa and mappa[chiave_barcode][1] is not None:
                child_id = mappa[chiave_barcode][1]
                requests.put(
                    f"{BASE_URL}/syncs/{SYNC_ID}/product-children/{child_id}",
                    json=payload_figlio,
                    headers=headers,
                    timeout=10,
                )
            else:
                requests.post(
                    f"{BASE_URL}/syncs/{SYNC_ID}/product-children",
                    json=payload_figlio,
                    headers=headers,
                    timeout=10,
                )
        except Exception as e:
            logging.error(f"[STRATOOS CHILD ERROR] {e}")

    return True


def aggiorna_giacenza_stratoos(barcode, codice_modello, nuova_giacenza):
    """Sincronizza anagrafica (una tantum) e poi aggiorna le quantità."""
    global _modelli_sincronizzati_cache

    token = ottieni_access_token()
    if not token:
        print("[STRATOOS UPDATE STOCK]: Token non ottenuto.")
        return False

    chiave_modello = str(codice_modello).strip().lower() if codice_modello else ""

    # 1. SINCRONIZZA ANAGRAFICA COMPLETA (Solo la prima volta che si tocca il modello in questa sessione)
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

    # 2. SINCRONIZZA GIACENZE
    mappa = ottieni_mappa_prodotti_stratoos(token)
    if not mappa:
        return False

    chiave_barcode = str(barcode).strip() if barcode else ""
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
            print(f"[STRATOOS SUCCESS]: Giacenza aggiornata (Qta: {nuova_giacenza})")
            return True
        else:
            print(f"[STRATOOS ERROR]: {res.status_code} - {res.text}")
            return False
    except Exception as e:
        print(f"[STRATOOS EXCEPTION]: {e}")
        return False
