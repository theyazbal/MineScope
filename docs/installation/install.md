# Installation

Requirements: Python 3.10+, Windows 10/11 or Linux. No third-party package is required.

1. Get the sources (`git clone` or unzip the release archive).
2. Optional but recommended: `python -m venv .venv` and activate it.
3. Either run in place with `python main.py`, or `python -m pip install -e ".[rich]"` to get the
   `minescope` command and the rich terminal interface.

Windows (CMD): `.venv\Scripts\activate`. Linux: `source .venv/bin/activate`.
Verify: `minescope --version` (or `python main.py --version`).
