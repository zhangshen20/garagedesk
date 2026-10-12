from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = get_settings().database_url
        kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _fk_on(dbapi_conn, _):
                dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return _engine


def reset_engine() -> None:
    """Tests swap the database URL; drop the cached engine so it is rebuilt."""
    global _engine
    _engine = None


def init_db() -> None:
    from . import models  # noqa: F401  ensure tables are registered

    SQLModel.metadata.create_all(get_engine())
    _add_missing_columns()


def _add_missing_columns() -> None:
    """create_all makes new tables but never new columns on an existing one. Add any
    nullable column the model has and the database lacks, so a deploy doesn't need the
    demo data wiped first."""
    from sqlalchemy import inspect, text

    engine = get_engine()
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have and col.nullable:
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(engine.dialect)}'))


@contextmanager
def session_scope() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with Session(get_engine()) as session:
        yield session


def reset_demo_data() -> None:
    """Drop every table and reseed: the clean state for recording a demo take."""
    from . import models  # noqa: F401
    from .seed import seed

    engine = get_engine()
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        seed(s)
        s.commit()
