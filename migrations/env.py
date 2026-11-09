"""Alembic environment. Migrations are hand-written SQL: there is no ORM metadata,
so `alembic revision --autogenerate` is deliberately unsupported. Constraints that
live only in SQL (CHECKs, partial indexes, RLS policies) would be dropped by it.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from orqen_core.settings import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def database_url() -> str:
    # `alembic -x url=...` wins, so tests can migrate a separate database.
    return context.get_x_argument(as_dictionary=True).get("url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=database_url(), literal_binds=True, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
