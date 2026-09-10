import sys
import os

# Entriamo nella cartella corretta del progetto
CARTELLA_PROGETTO = os.path.dirname(os.path.abspath(__file__))
os.chdir(CARTELLA_PROGETTO)
if CARTELLA_PROGETTO not in sys.path:
    sys.path.append(CARTELLA_PROGETTO)

from app import app
from database.models import db, Articolo, VarianteArticolo, Vendita, DettaglioVendita

# NOTA: Se hai altre tabelle (es. Categoria, Fornitore, MovimentoMagazzino)
# importale qui sopra e aggiungi il comando di `.delete()` sotto.

if __name__ == "__main__":
    with app.app_context():
        print(
            "ATTENZIONE: Stai per eliminare TUTTI gli articoli, le varianti e le vendite dal database."
        )
        conferma = input(
            "Vuoi procedere? Scrivi 'SI' (tutto maiuscolo) per confermare: "
        )

        if conferma == "SI":
            try:
                print("🔄 Cancellazione in corso...")

                # Eliminiamo prima i "figli" (vendite e varianti) per non violare le chiavi esterne
                DettaglioVendita.query.delete()
                Vendita.query.delete()
                VarianteArticolo.query.delete()

                # Poi eliminiamo i "padri" (gli articoli)
                Articolo.query.delete()

                # Confermiamo le modifiche sul database
                db.session.commit()

                print(
                    "✅ Pulizia completata! Il database è tornato vuoto e pronto per i dati reali."
                )
            except Exception as e:
                db.session.rollback()
                print(f"❌ Errore durante la cancellazione: {e}")
        else:
            print("🛑 Operazione annullata. Non è stato cancellato nulla.")
