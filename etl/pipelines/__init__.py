"""Pipelines do ETL. Imports são preguiçosos: `carga_cadastro` exige SQLAlchemy/backend e não deve ser
carregado só porque outro pipeline (ex.: sync_ceap_emendas) foi importado."""

__all__ = ["PresidentsEconomicSyncPipeline", "CargaCadastro"]


def __getattr__(name):
    if name == "PresidentsEconomicSyncPipeline":
        from .presidents_economic_sync import PresidentsEconomicSyncPipeline

        return PresidentsEconomicSyncPipeline
    if name == "CargaCadastro":
        from .carga_cadastro import CargaCadastro

        return CargaCadastro
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
