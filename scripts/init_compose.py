"""Create local Compose credentials. Existing files are never overwritten."""

from pathlib import Path
import secrets

destination = Path(__file__).resolve().parents[1] / ".env"
admin, migration, runtime, secret = (secrets.token_hex(32) for _ in range(4))
content = f"""SECRET_KEY={secret}
POSTGRES_PASSWORD={admin}
MIGRATION_PASSWORD={migration}
RUNTIME_PASSWORD={runtime}
ADMIN_DATABASE_URL=postgresql://postgres:{admin}@database/ledgerops
MIGRATION_DATABASE_URL=postgresql+psycopg://ledgerops_migrator:{migration}@database/ledgerops
DATABASE_URL=postgresql+psycopg://ledgerops_runtime:{runtime}@database/ledgerops
"""
with destination.open("x", encoding="utf-8") as output:
    output.write(content)
print("Created .env with local credentials. Keep it out of Git.")
