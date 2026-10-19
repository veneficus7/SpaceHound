"""Entry point used by PyInstaller (and handy for `python run_spacehound.py`)."""

import sys

from spacehound.app import main

if __name__ == "__main__":
    sys.exit(main())
