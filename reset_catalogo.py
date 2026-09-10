import sys
import os

# Entriamo nella cartella corretta del progetto
CARTELLA_PROGETTO = os.path.dirname(os.path.abspath(__file__))
os.chdir(CARTELLA_PROGETTO)
if CARTELLA_PROGETTO not in sys.path:
    sys.path.append(CARTELLA_PROGETTO)

from app import app
from database.models import db, Articolo, VarianteArticolo, Vendita, DettaglioVendita

if __name__ == "__main__":
    with app.app_context():
        print(
            "⚠️ ATTENZIONE: Stai per eliminare TUTTI gli articoli, le varianti e le vendite di prova."
        )
        print("I fornitori e le scadenze NON verranno toccati.")
        conferma = input(
            "Vuoi procedere? Scrivi 'SI' (tutto maiuscolo) per confermare: "
        )

        if conferma == "SI":
            try:
                print("🔄 Cancellazione in corso...")

                # Ordine di cancellazione obbligatorio per non violare i vincoli (Foreign Keys)
                # Prima eliminiamo i dettagli delle vendite e le vendite stesse
                DettaglioVendita.query.delete()
                Vendita.query.delete()

                # Poi eliminiamo le varianti (taglie/colori)
                VarianteArticolo.query.delete()

                # Infine eliminiamo i modelli "padre"
                Articolo.query.delete()

                # Confermiamo le modifiche sul database
                db.session.commit()

                print(
                    "✅ Pulizia completata! Catalogo e vendite azzerati con successo."
                )
            except Exception as e:
                db.session.rollback()
                print(f"❌ Errore durante la cancellazione: {e}")
        else:
            print("🛑 Operazione annullata. Non è stato cancellato nulla.")
