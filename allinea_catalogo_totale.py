import os
import sys
import time
import requests

basedir = os.path.abspath(os.path.dirname(__file__))
sys.path.append(basedir)

from app import app
from database.models import Articolo, VarianteArticolo
import stratoos


def esegui():
    with app.app_context():
        print("1. Richiesta token a Stratoos...")
        token = stratoos.ottieni_access_token()
        if not token:
            print("❌ Errore autenticazione Stratoos")
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        print("2. Recupero mappa prodotti...")
        mappa = stratoos.ottieni_mappa_prodotti_stratoos(token)

        articoli = Articolo.query.all()
        tot = len(articoli)
        print(f"3. Inizio invio di {tot} modelli con relative varianti e stock...\n")

        for idx, art in enumerate(articoli, start=1):
            codice = art.codice_modello
            print(f"[{idx}/{tot}] Allineamento: {codice} - {art.nome}...")

            # 1. Anagrafica, Brand, Categoria e Varianti
            product_id = stratoos.sincronizza_anagrafica_articolo(art, token, mappa)
            if not product_id:
                print(f"   ⚠️ Errore creazione/aggiornamento padre {codice}")
                continue

            # 2. Elenco varianti su Stratoos per agganciare le quantità corrette
            url_children = f"{stratoos.BASE_URL}/syncs/{stratoos.SYNC_ID}/products/{product_id}/productChildren"
            mappa_figli = {}
            try:
                res_ch = requests.get(url_children, headers=headers, timeout=10)
                if res_ch.status_code == 200:
                    for ch in res_ch.json().get("data", []):
                        ref = str(ch.get("reference", "")).strip().lower()
                        ean = str(ch.get("ean13", "")).strip()
                        if ref:
                            mappa_figli[ref] = ch.get("id")
                        if ean:
                            mappa_figli[ean] = ch.get("id")
            except Exception:
                pass

            # 3. Invio scorte per ogni taglia
            for v in art.varianti:
                taglia = (
                    getattr(v, "taglia_numero", None)
                    or getattr(v, "taglia", None)
                    or "TU"
                )
                ref_target = f"{art.codice_modello}-{taglia}"[:40].strip().lower()
                ean_target = str(v.barcode).strip() if v.barcode else ""

                child_id = mappa_figli.get(ref_target) or (
                    mappa_figli.get(ean_target) if ean_target else None
                )

                payload_stock = {
                    "product_id": int(product_id),
                    "quantity_available": int(v.giacenza),
                    "quantity_physical": int(v.giacenza),
                    "quantity_reserved": 0,
                }
                if child_id:
                    payload_stock["product_child_id"] = int(child_id)

                try:
                    res_stk = requests.post(
                        f"{stratoos.BASE_URL}/syncs/{stratoos.SYNC_ID}/stocks",
                        json=payload_stock,
                        headers=headers,
                        timeout=10,
                    )
                    if res_stk.status_code not in [200, 201, 204]:
                        print(
                            f"      Errore stock tg.{taglia}: HTTP {res_stk.status_code}"
                        )
                except Exception as e:
                    print(f"      Eccezione stock tg.{taglia}: {e}")

            time.sleep(0.05)

        print("\n✅ ALLINEAMENTO TOTALE COMPLETATO CON SUCCESSO!")


if __name__ == "__main__":
    esegui()
