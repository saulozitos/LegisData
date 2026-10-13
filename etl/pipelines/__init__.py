"""Pipelines do ETL. Imports são preguiçosos: `db_loader` exige SQLAlchemy/backend e não deve ser
carregado só porque outro pipeline (ex.: sync_ceap_emendas) foi importado."""

__all__ = ["PresidentsEconomicSyncPipeline", "DatabaseLoader"]


def __getattr__(name):
    if name == "PresidentsEconomicSyncPipeline":
        from .presidents_economic_sync import PresidentsEconomicSyncPipeline

        return PresidentsEconomicSyncPipeline
    if name == "DatabaseLoader":
        from .db_loader import DatabaseLoader

        return DatabaseLoader
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
