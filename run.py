# Point d'entrée de TBI Pro (utilisé aussi par PyInstaller)
import sys

from tbipro.app import main

if __name__ == "__main__":
    sys.exit(main())
