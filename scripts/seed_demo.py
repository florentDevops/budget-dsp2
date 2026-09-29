"""Charge le relevé fictif sans passer par l'interface : python -m scripts.seed_demo"""
from app import classifier, db, demo

if __name__ == "__main__":
    db.init_db()
    print(f"{demo.load_demo()} opérations importées, {classifier.classify_pending()} classées.")
