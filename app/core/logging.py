"""Application logging configuration."""

from __future__ import annotations

import logging
import sys


def configure_logging(debug: bool = False) -> None:
    """Configure root logging once. Console-only; no secrets are ever logged."""

    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(logging.DEBUG if debug else logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(handler)
