import logging
import requests
import threading

# Configurazione API Stratoos
API_KEY = "pd6ShL8fD3Q9TfbUTcsV0domKu00nkcJ"
SYNC_ID = 17
BASE_URL = "https://app.stratoos.com/api/v1"

_cache_gruppi_attributi = {}
_cache_attributi = {}
_cache_stocks = {}
_stocks_mappati = False
_sync_lock = threading.Lock()


def ottieni_access_token():
    """Richiede il token di accesso a Stratoos via Email, Password e API Key."""
    url = f"{BASE_URL}/auth"
    payload = {
        "email": "viaromacalzature.store@gmail.com",
        "password": "GPj#vm0$pf9Q",
        "apiKey": API_KEY,
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "data" in data and "accessToken" in data["data"]:
                return data["data"]["accessToken"]
            return data.get("access_token") or data.get("token")
        else:
            logging.error(
                f"[STRATOOS AUTH FAILED]: HTTP {response.status_code} - {response.text}"
            )
        return None
    except Exception as e:
        logging.error(f"[STRATOOS AUTH EXCEPTION]: {e}")
        return None


def ottieni_mappa_prodotti_stratoos(token):
    """Mappa i prodotti esistenti leggendo tutte le pagine per prevenire duplicati."""
    mappa = {}
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    page = 1
    while True:
        url = f"{BASE_URL}/syncs/{SYNC_ID}/products?page={page}"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                break
            risposta_json = response.json()
            lista_prodotti = risposta_json.get("data", [])
            if not lista_prodotti:
                break

            for p in lista_prodotti:
                p_id = p.get("id")
                ref_modello = p.get("reference")
                ean_padre = p.get("ean13")
                if ref_modello:
                    mappa[str(ref_modello).strip().lower()] = p_id
                if ean_padre:
                    mappa[str(ean_padre).strip()] = p_id

            if not risposta_json.get("links", {}).get("next"):
                break
            page += 1
        except Exception as e:
            logging.error(f"[STRATOOS GET PRODUCTS EXCEPTION]: {e}")
            break
    return mappa


def _ottieni_children_prodotto(product_id, headers_auth):
    """Legge tutte le varianti figlie direttamente dalla scheda prodotto (senza limiti di pagina)."""
    try:
        res = requests.get(
            f"{BASE_URL}/syncs/{SYNC_ID}/products/{product_id}",
            headers=headers_auth,
            timeout=10,
        )
        if res.status_code == 200:
            data = res.json().get("data", {})
            if isinstance(data.get("children"), list):
                return data["children"]
    except Exception:
        pass

    # Fallback paginato se children non fosse incluso nella scheda
    tutti = []
    page = 1
    while True:
        try:
            res_ch = requests.get(
                f"{BASE_URL}/syncs/{SYNC_ID}/products/{product_id}/productChildren?page={page}",
                headers=headers_auth,
                timeout=10,
            )
            if res_ch.status_code != 200:
                break
            js = res_ch.json()
            dati = js.get("data", [])
            if not dati:
                break
            tutti.extend(dati)
            if not js.get("links", {}).get("next"):
                break
            page += 1
        except Exception:
            break
    return tutti


def _gestisci_entita(token, endpoint_name, nome_entita):
    """Gestisce Brand e Categorie garantendo la presenza del campo reference."""
    if not nome_entita:
        return None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"{BASE_URL}/syncs/{SYNC_ID}/{endpoint_name}"
    reference_val = str(nome_entita).strip().upper().replace(" ", "_")

    page = 1
    found_id = None
    while True:
        try:
            res_get = requests.get(f"{url}?page={page}", headers=headers, timeout=10)
            if res_get.status_code == 200:
                data_json = res_get.json()
                dati = data_json.get("data", [])
                if not dati:
                    break

                for item in dati:
                    if item.get("reference") == reference_val:
                        found_id = item.get("id")
                        break
                    for lang in item.get("langs", []):
                        if (
                            str(lang.get("name", "")).strip().lower()
                            == str(nome_entita).strip().lower()
                        ):
                            found_id = item.get("id")
                            break

                if found_id or not data_json.get("links", {}).get("next"):
                    break
                page += 1
            else:
                break
        except Exception:
            break

    if found_id:
        return found_id

    try:
        payload = {
            "reference": reference_val,
            "langs": [{"lang_id": 1, "name": str(nome_entita)}],
        }

        if endpoint_name == "categories":
            payload["parent_id"] = None

        res_post = requests.post(url, json=payload, headers=headers, timeout=10)
        if res_post.status_code in [200, 201]:
            return res_post.json().get("data", {}).get("id")
    except Exception:
        pass
    return None


def _gestisci_gruppo_attributi(token, nome_gruppo="Taglia"):
    """Recupera o crea l'AttributeGroup specificato."""
    global _cache_gruppi_attributi
    chiave = nome_gruppo.strip().lower()
    if chiave in _cache_gruppi_attributi:
        return _cache_gruppi_attributi[chiave]

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"{BASE_URL}/syncs/{SYNC_ID}/attributeGroups"

    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            for g in res.json().get("data", []):
                for lang in g.get("langs", []):
                    if lang.get("name", "").strip().lower() == chiave:
                        _cache_gruppi_attributi[chiave] = g.get("id")
                        return g.get("id")
    except Exception:
        pass

    try:
        payload = {
            "group_type": "select",
            "reference": nome_gruppo.strip().upper(),
            "langs": [{"lang_id": 1, "name": nome_gruppo}],
        }
        res_post = requests.post(
            url,
            json=payload,
            headers={**headers, "Content-Type": "application/json"},
            timeout=10,
        )
        if res_post.status_code in [200, 201]:
            g_id = res_post.json().get("data", {}).get("id")
            _cache_gruppi_attributi[chiave] = g_id
            return g_id
    except Exception as e:
        logging.error(f"[STRATOOS ATTRIBUTE GROUP EXCEPTION]: {e}")
    return None


def _gestisci_attributo(token, group_id, valore_attributo):
    """Recupera o crea il singolo attributo all'interno di un AttributeGroup."""
    global _cache_attributi
    chiave = (group_id, str(valore_attributo).strip().lower())
    if chiave in _cache_attributi:
        return _cache_attributi[chiave]

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"{BASE_URL}/syncs/{SYNC_ID}/attributeGroups/{group_id}/attributes"

    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            for a in res.json().get("data", []):
                for lang in a.get("langs", []):
                    if lang.get("name", "").strip().lower() == chiave[1]:
                        _cache_attributi[chiave] = a.get("id")
                        return a.get("id")
    except Exception:
        pass

    try:
        payload = {
            "reference": f"ATTR_{group_id}_{valore_attributo}".strip()
            .upper()
            .replace(" ", "_"),
            "langs": [{"lang_id": 1, "name": str(valore_attributo)}],
        }
        res_post = requests.post(
            url,
            json=payload,
            headers={**headers, "Content-Type": "application/json"},
            timeout=10,
        )
        if res_post.status_code in [200, 201]:
            a_id = res_post.json().get("data", {}).get("id")
            _cache_attributi[chiave] = a_id
            return a_id
    except Exception as e:
        logging.error(f"[STRATOOS ATTRIBUTE EXCEPTION]: {e}")
    return None


def sincronizza_anagrafica_articolo(articolo, token, mappa):
    """Sincronizza Prodotto Padre, aggancia Brand/Categoria e crea le relative varianti figlie."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    brand_nome = articolo.fornitore.nome if articolo.fornitore else articolo.brand
    brand_id = _gestisci_entita(token, "manufacturers", brand_nome or "Via Roma")

    categoria_id = None
    if hasattr(articolo, "tipologia") and articolo.tipologia:
        categoria_id = _gestisci_entita(token, "categories", articolo.tipologia)

    payload_padre = {
        "price": float(articolo.prezzo_listino or 0.0),
        "reference": str(articolo.codice_modello),
        "langs": [{"lang_id": 1, "name": str(articolo.nome)}],
    }

    chiave_modello = str(articolo.codice_modello).strip().lower()
    product_id = mappa.get(chiave_modello)

    try:
        if product_id:
            requests.put(
                f"{BASE_URL}/syncs/{SYNC_ID}/products/{product_id}",
                json=payload_padre,
                headers=headers,
                timeout=10,
            )
        else:
            res_post = requests.post(
                f"{BASE_URL}/syncs/{SYNC_ID}/products",
                json=payload_padre,
                headers=headers,
                timeout=10,
            )
            if res_post.status_code in [200, 201]:
                product_id = res_post.json().get("data", {}).get("id")
                mappa[chiave_modello] = product_id

        if product_id:
            payload_assoc = {}
            if brand_id:
                payload_assoc["manufacturer"] = {"id": int(brand_id)}
            if categoria_id:
                payload_assoc["categories"] = [{"id": int(categoria_id)}]

            if payload_assoc:
                requests.put(
                    f"{BASE_URL}/syncs/{SYNC_ID}/products/{product_id}",
                    json=payload_assoc,
                    headers=headers,
                    timeout=10,
                )

        if product_id and hasattr(articolo, "varianti") and articolo.varianti:
            sincronizza_varianti_prodotto(articolo, product_id, token)

        return product_id
    except Exception as e:
        logging.error(f"[STRATOOS PRODUCT SYNC ERROR]: {e}")
        return None


def sincronizza_varianti_prodotto(articolo, product_id, token):
    """Crea o aggiorna le varianti (productChildren) associate al prodotto padre senza duplicati."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    headers_get = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url_children = f"{BASE_URL}/syncs/{SYNC_ID}/products/{product_id}/productChildren"

    children_esistenti = {}
    for ch in _ottieni_children_prodotto(product_id, headers_get):
        if ch.get("reference"):
            children_esistenti[str(ch.get("reference")).strip().lower()] = ch.get("id")
        if ch.get("ean13"):
            children_esistenti[str(ch.get("ean13")).strip()] = ch.get("id")

    group_taglia_id = _gestisci_gruppo_attributi(token, "Taglia")

    for v in articolo.varianti:
        taglia = getattr(v, "taglia_numero", None) or getattr(v, "taglia", None) or "TU"
        ref_variante = f"{articolo.codice_modello}-{taglia}"[:40]
        chiave_ref = ref_variante.strip().lower()
        chiave_ean = str(v.barcode).strip() if v.barcode else ""

        if chiave_ref in children_esistenti or (
            chiave_ean and chiave_ean in children_esistenti
        ):
            continue

        options = []
        if taglia and group_taglia_id:
            attr_id = _gestisci_attributo(token, group_taglia_id, str(taglia))
            if attr_id:
                options.append({"id": attr_id})

        payload_child = {
            "price": float(articolo.prezzo_listino or 0.0),
            "reference": ref_variante,
            "options": options if options else None,
        }
        if (
            v.barcode
            and len(str(v.barcode).strip()) == 13
            and str(v.barcode).strip().isdigit()
        ):
            payload_child["ean13"] = str(v.barcode).strip()

        try:
            res_ch = requests.post(
                url_children, json=payload_child, headers=headers, timeout=10
            )
            if res_ch.status_code in [200, 201]:
                new_id = res_ch.json().get("data", {}).get("id")
                children_esistenti[chiave_ref] = new_id
                if chiave_ean:
                    children_esistenti[chiave_ean] = new_id
        except Exception as e:
            logging.error(f"[STRATOOS CHILD SYNC ERROR]: {e}")


def sincronizza_brand_stratoos(nome_brand):
    """Crea o verifica immediatamente un Brand (Manufacturer) su Stratoos."""
    if not nome_brand:
        return None
    token = ottieni_access_token()
    if not token:
        return None
    return _gestisci_entita(token, "manufacturers", str(nome_brand).strip())


def _cerca_child_id(product_id, chiave_barcode, ref_attesa, headers_auth):
    """Cerca l'ID della variante su Stratoos per EAN13 oppure per riferimento MODELLO-TAGLIA."""
    for child in _ottieni_children_prodotto(product_id, headers_auth):
        ref_child = str(child.get("reference", "")).strip().lower()
        ean_child = str(child.get("ean13", "")).strip()
        if (
            (chiave_barcode and ean_child == chiave_barcode)
            or (ref_attesa and ref_child == ref_attesa)
            or (chiave_barcode and chiave_barcode in ref_child)
        ):
            return child.get("id")
    return None


def _carica_mappa_stocks(headers_auth):
    """Carica in cache la mappa (product_id, product_child_id) -> stock_id."""
    global _cache_stocks, _stocks_mappati
    if _stocks_mappati:
        return
    url_stocks = f"{BASE_URL}/syncs/{SYNC_ID}/stocks"
    page = 1
    while True:
        try:
            res = requests.get(
                f"{url_stocks}?page={page}", headers=headers_auth, timeout=10
            )
            if res.status_code != 200:
                break
            js = res.json()
            for st in js.get("data", []):
                chiave = (int(st.get("product_id") or 0), int(st.get("product_child_id") or 0))
                _cache_stocks[chiave] = st.get("id")
            if not js.get("links", {}).get("next"):
                break
            page += 1
        except Exception:
            break
    _stocks_mappati = True


def _invia_o_aggiorna_stock(product_id, product_child_id, nuova_giacenza, headers_auth):
    """Invia lo stock tramite POST o lo aggiorna tramite PUT se il record esiste già su Stratoos."""
    global _cache_stocks, _stocks_mappati
    url_stocks = f"{BASE_URL}/syncs/{SYNC_ID}/stocks"
    headers_json = {**headers_auth, "Content-Type": "application/json"}

    payload = {
        "product_id": int(product_id),
        "quantity_available": int(nuova_giacenza),
        "quantity_physical": int(nuova_giacenza),
        "quantity_reserved": 0,
    }
    if product_child_id:
        payload["product_child_id"] = int(product_child_id)

    chiave_stock = (int(product_id), int(product_child_id or 0))

    try:
        _carica_mappa_stocks(headers_auth)
        stock_id = _cache_stocks.get(chiave_stock)

        if stock_id:
            res_put = requests.put(
                f"{url_stocks}/{stock_id}",
                json=payload,
                headers=headers_json,
                timeout=10,
            )
            if res_put.status_code in [200, 201, 204]:
                return True

        res_post = requests.post(
            url_stocks, json=payload, headers=headers_json, timeout=10
        )
        if res_post.status_code in [200, 201, 204]:
            new_st_id = res_post.json().get("data", {}).get("id")
            if new_st_id:
                _cache_stocks[chiave_stock] = new_st_id
            return True

        # Se la cache non era allineata, forza un refresh della mappa e riprova PUT
        _stocks_mappati = False
        _cache_stocks.clear()
        _carica_mappa_stocks(headers_auth)
        stock_id = _cache_stocks.get(chiave_stock)
        if stock_id:
            res_put = requests.put(
                f"{url_stocks}/{stock_id}",
                json=payload,
                headers=headers_json,
                timeout=10,
            )
            return res_put.status_code in [200, 201, 204]

        print(
            f"⚠️ Errore stock Stratoos (HTTP {res_post.status_code}): {res_post.text[:150]}"
        )
        return False
    except Exception as e:
        logging.error(f"[STRATOOS STOCK EXCEPTION]: {e}")
        return False


def aggiorna_giacenza_stratoos(barcode, codice_modello, nuova_giacenza):
    """Aggiorna quantità su Stratoos garantendo l'esistenza di Brand, Prodotto e Variante."""
    with _sync_lock:
        token = ottieni_access_token()
        if not token:
            return False

        chiave_modello = str(codice_modello).strip().lower() if codice_modello else ""
        chiave_barcode = str(barcode).strip()

        variante = None
        ref_attesa = ""
        try:
            from database.models import VarianteArticolo

            variante = VarianteArticolo.query.filter_by(barcode=chiave_barcode).first()
            if variante and variante.articolo:
                taglia = (
                    getattr(variante, "taglia_numero", None)
                    or getattr(variante, "taglia", None)
                    or "TU"
                )
                ref_attesa = (
                    f"{variante.articolo.codice_modello}-{taglia}"[:40].strip().lower()
                )
        except Exception:
            pass

        headers_auth = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        mappa_prod = ottieni_mappa_prodotti_stratoos(token)
        product_id = mappa_prod.get(chiave_modello) or mappa_prod.get(chiave_barcode)

        if not product_id and variante and variante.articolo:
            product_id = sincronizza_anagrafica_articolo(
                variante.articolo, token, mappa_prod
            )

        if not product_id:
            return False

        product_child_id = _cerca_child_id(
            product_id, chiave_barcode, ref_attesa, headers_auth
        )

        if not product_child_id and variante and variante.articolo:
            sincronizza_varianti_prodotto(variante.articolo, product_id, token)
            product_child_id = _cerca_child_id(
                product_id, chiave_barcode, ref_attesa, headers_auth
            )

        return _invia_o_aggiorna_stock(
            product_id, product_child_id, nuova_giacenza, headers_auth
        )