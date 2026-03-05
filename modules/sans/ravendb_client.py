"""RavenDB singleton client — ported from Hades"""
from ravendb import DocumentStore
from config import settings, logger

_store: DocumentStore | None = None


def init_ravendb():
    global _store
    _store = DocumentStore(urls=[settings.ravendb_url], database=settings.ravendb_database)
    _store.initialize()
    logger.info(f"RavenDB connected: {settings.ravendb_url}/{settings.ravendb_database}")


def get_store() -> DocumentStore:
    if _store is None:
        init_ravendb()
    return _store


def open_session():
    return get_store().open_session()
