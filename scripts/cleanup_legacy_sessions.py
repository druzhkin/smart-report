"""One-shot ops script: handle legacy public V4 sessions.

Pre-isolation rows in `v4_sessions` have `payload->>'user_email' IS NULL`.
The router treats these as public ("legacy/public session" comment in
`_ensure_owner`), which means anyone who guesses the 12-hex session_id
can read its contents. Now that auth has been required for >24h on
new sessions, every still-anonymous row is either:
  (a) genuine pre-auth experimentation with no user attached → safe to
      delete; or
  (b) a row where we lost the user_email column for some reason → also
      safe to delete (user can recreate).

Usage:
    DATABASE_URL=$RAILWAY_PG_URL python scripts/cleanup_legacy_sessions.py --dry-run
    DATABASE_URL=$RAILWAY_PG_URL python scripts/cleanup_legacy_sessions.py --apply

`--dry-run` (default): list rows that would be deleted, no changes.
`--apply`: actually delete.
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually delete rows (default is dry-run)",
    )
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2

    try:
        import psycopg
    except ImportError:
        print("ERROR: psycopg not installed (pip install 'psycopg[binary]')", file=sys.stderr)
        return 2

    with psycopg.connect(db_url) as conn:
        # Inspect first.
        rows = conn.execute(
            """
            SELECT session_id, payload->>'raw_question' AS q,
                   payload->>'created_at' AS created
              FROM v4_sessions
             WHERE payload->>'user_email' IS NULL
                OR payload->>'user_email' = ''
             ORDER BY updated_at DESC
            """
        ).fetchall()
        if not rows:
            print("No legacy public sessions found. Nothing to do.")
            return 0

        print(f"Found {len(rows)} legacy public sessions:")
        for sid, q, created in rows[:50]:
            q_preview = (q or "")[:80].replace("\n", " ")
            print(f"  {sid}  {created or '(no ts)':<30}  {q_preview!r}")
        if len(rows) > 50:
            print(f"  …and {len(rows) - 50} more")

        if not args.apply:
            print("\nDry run — pass --apply to delete.")
            return 0

        n = conn.execute(
            """
            DELETE FROM v4_sessions
             WHERE payload->>'user_email' IS NULL
                OR payload->>'user_email' = ''
            """
        ).rowcount
        print(f"\nDeleted {n} rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
