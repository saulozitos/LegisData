"""Pipelines do ETL. Imports são preguiçosos: o pipeline de presidentes exige SQLAlchemy/backend e não deve ser
carregado só porque outro pipeline (ex.: sync_ceap_emendas) foi importado. A carga do cadastro e do legislativo vive em
`etl.carga`."""

__all__ = ["PresidentsEconomicSyncPipeline"]


def __getattr__(name):
    if name == "PresidentsEconomicSyncPipeline":
        from .presidents_economic_sync import PresidentsEconomicSyncPipeline

        return PresidentsEconomicSyncPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
