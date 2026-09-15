"""Regression tests for backend/alembic/env.py's explicit model-import list.

alembic/env.py builds Base.metadata purely from whatever domain model
modules it explicitly imports. Any domain whose models module isn't
imported there is invisible to `alembic revision --autogenerate`, which
then proposes DROPPING that domain's real tables. These tests spawn a
clean subprocess that imports *only* what env.py imports (nothing else in
the test suite has a chance to register models as a side effect first) and
checks the resulting Base.metadata against the domains that are known to
have real tables in the database.
"""

import re
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_PY = BACKEND_ROOT / "alembic" / "env.py"

# Domains with real model files under src/ that must have their tables
# registered in Base.metadata via env.py's import block. Each domain maps
# to at least one table name it owns.
EXPECTED_DOMAIN_TABLES = {
    "stockcount": {"stock_counts", "stock_count_items"},
    "invoice_schemes": {"invoice_schemes"},
    "auth": {"users"},
    "products": {"products"},
    "sales": {"sales"},
    "orders": {"purchase_orders"},
    "audit": {"audit_logs"},
}


def _extract_import_statements() -> list[str]:
    """Pull every `from src.<domain>.models import ...` block out of env.py,
    exactly as alembic itself would execute them (multi-line imports included).
    """
    source = ENV_PY.read_text()
    return re.findall(
        r"^from src\.\w+\.models import \([^)]*\)|^from src\.\w+\.models import .+$",
        source,
        re.MULTILINE,
    )


def _registered_table_names() -> set[str]:
    """Run a subprocess that imports only env.py's model imports, then
    report which table names ended up in Base.metadata.
    """
    imports = _extract_import_statements()
    assert imports, "env.py should contain at least one 'from src.*.models import' line"

    script = "\n".join(
        [
            "import sys",
            f"sys.path.insert(0, {str(BACKEND_ROOT)!r})",
            "import os",
            "os.environ.setdefault('SECRET_KEY', 'x' * 32)",
            "os.environ.setdefault('UPLOAD_DIR', '/tmp/modishlog_test_uploads')",
            *imports,
            "from src.core.database import Base",
            "print(','.join(sorted(Base.metadata.tables.keys())))",
        ]
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"subprocess exercising env.py's imports failed:\n{result.stderr}"
    )
    return set(result.stdout.strip().split(","))


def test_env_py_registers_tables_for_every_known_domain():
    """Happy path: every domain that owns real tables must be reachable
    from env.py's own import list, not just from being imported elsewhere
    in the app (e.g. by main.py or a router)."""
    registered = _registered_table_names()
    all_expected = set().union(*EXPECTED_DOMAIN_TABLES.values())
    missing = all_expected - registered
    assert not missing, (
        f"alembic/env.py does not import model modules that register: {sorted(missing)}. "
        "autogenerate would propose dropping these tables."
    )


def test_env_py_specifically_imports_stockcount_and_invoice_schemes():
    """Error case this task fixes: stockcount and invoice_schemes were the
    two domains missing from env.py's import block, risking accidental
    DROP TABLE migrations for stock_counts, stock_count_items, and
    invoice_schemes."""
    registered = _registered_table_names()
    assert EXPECTED_DOMAIN_TABLES["stockcount"] <= registered
    assert EXPECTED_DOMAIN_TABLES["invoice_schemes"] <= registered
