"""Allow ``python -m autospine_workbench serve``."""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())

