"""Allow ``python3 -m hydra_fix``."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
