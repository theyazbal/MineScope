"""Module entry point: ``python -m minescope``."""

import sys

from minescope.cli.app import main

if __name__ == "__main__":
    sys.exit(main())
