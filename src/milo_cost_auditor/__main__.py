"""Module entry: `python -m milo_cost_auditor`."""

import sys

from milo_cost_auditor.server import main


def _main_entry() -> int:
    return main()


# Re-export for the console script in pyproject.toml.
def main_entry() -> int:  # pragma: no cover - thin wrapper
    return _main_entry()


# Console script in pyproject points at this name.
main = main


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main_entry())
