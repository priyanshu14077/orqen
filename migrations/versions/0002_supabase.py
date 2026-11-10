"""Run on Supabase: Supabase Auth owns users, and the Data API can't see Orqen tables.

1. Supabase Auth stores users and passwords in `auth.users`, so `users.password_hash`
   goes. `users.id` is the Supabase Auth user id. When the `auth` schema exists, a
   foreign key enforces that.
2. On Supabase, new tables in `public` are granted to the `anon` and `authenticated`
   roles, which the Data API (PostgREST) uses. Orqen never serves data through the
   Data API, so this revokes those grants, including on alembic_version, and stops
   future tables from receiving them.

Both steps check for the Supabase objects first, so the migration also runs on plain
Postgres.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-09
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN password_hash")

    op.execute("""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'auth' AND table_name = 'users'
        ) THEN
            ALTER TABLE users ADD CONSTRAINT users_auth_user_fk
                FOREIGN KEY (id) REFERENCES auth.users (id) ON DELETE CASCADE;
        END IF;
    END
    $$;
    """)

    op.execute("""
    DO $$
    DECLARE
        r text;
    BEGIN
        FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = r) THEN
                EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', r);
                EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', r);
                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', r
                );
                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I',
                    r
                );
            END IF;
        END LOOP;
    END
    $$;
    """)


def downgrade() -> None:
    # The revoked Data API grants are not restored: exposing the tables again
    # should be a deliberate act, not a side effect of a rollback.
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_auth_user_fk")
    # Nullable: existing users have no local password to restore.
    op.execute("ALTER TABLE users ADD COLUMN password_hash text")
