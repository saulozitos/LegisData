"""
Apoio dos testes que conferem o staging relacional: consultas simples (`query`, `filter_by`, `one`, `count`...) sobre as
linhas de `etl.pipelines.stg_tabela`, e a semeadura de linhas por objetos (`Politician(...)`, `session.add`, `commit`).

Não é um ORM: cada `query(Modelo)` lê a tabela inteira do banco de teste e o `commit` grava o que mudou, pelo mesmo caminho
da carga (`Tabela.gravar`). Serve só para os testes poderem escrever `s.query(Politician).filter_by(camara_id=1).one()`.
"""

from typing import Any, Callable, Dict, List

from etl.pipelines import stg_tabela
from etl.utils.copia import transacao_de_carga


class _Coluna:
    def __init__(self, atributo: str):
        self.atributo = atributo

    def __eq__(self, valor: Any) -> Callable[[Any], bool]:  # type: ignore[override]
        return lambda linha: getattr(linha, self.atributo) == valor

    def isnot(self, valor: Any) -> Callable[[Any], bool]:
        return lambda linha: getattr(linha, self.atributo) is not valor

    def is_(self, valor: Any) -> Callable[[Any], bool]:
        return lambda linha: getattr(linha, self.atributo) is valor


class Modelo:
    """Um nome de tabela do staging que se comporta como a classe do modelo: `Modelo(...)` cria uma linha pendente."""

    def __init__(self, fabrica: Callable[[], stg_tabela.Tabela]):
        self.fabrica = fabrica
        self.nome = fabrica().nome

    def __getattr__(self, atributo: str) -> _Coluna:
        if atributo.startswith("_") or atributo in ("fabrica", "nome"):
            raise AttributeError(atributo)
        return _Coluna(atributo)

    def __call__(self, **atributos: Any) -> "Pendente":
        return Pendente(self, atributos)


class Pendente:
    """Uma linha ainda não adicionada à sessão; o `id` existe desde já (o `stg` o define na criação)."""

    def __init__(self, modelo: Modelo, atributos: Dict[str, Any]):
        import uuid

        self.modelo = modelo
        self.atributos = dict(atributos)
        self.atributos.setdefault("id", uuid.uuid4())

    @property
    def id(self) -> Any:
        return self.atributos["id"]

    def __getattr__(self, atributo: str) -> Any:
        try:
            return self.__dict__["atributos"][atributo]
        except KeyError:
            raise AttributeError(atributo) from None


Politician = Modelo(stg_tabela.politicos)
PoliticalParty = Modelo(stg_tabela.partidos)
PartyAffiliation = Modelo(stg_tabela.filiacoes)
Mandate = Modelo(stg_tabela.mandatos)
CabinetMember = Modelo(stg_tabela.membros_gabinete)
Proposition = Modelo(stg_tabela.proposicoes)
VotingSession = Modelo(stg_tabela.sessoes_votacao)
ParliamentaryVote = Modelo(stg_tabela.votos_parlamentares)


class Consulta:
    def __init__(self, linhas: List[Any]):
        self.linhas = linhas

    def filter_by(self, **filtros: Any) -> "Consulta":
        return Consulta([l_ for l_ in self.linhas if all(getattr(l_, k) == v for k, v in filtros.items())])

    def filter(self, *predicados: Callable[[Any], bool]) -> "Consulta":
        return Consulta([l_ for l_ in self.linhas if all(p(l_) for p in predicados)])

    def all(self) -> List[Any]:
        return list(self.linhas)

    def first(self) -> Any:
        return self.linhas[0] if self.linhas else None

    def one(self) -> Any:
        if len(self.linhas) != 1:
            raise AssertionError(f"esperava exatamente 1 linha, achei {len(self.linhas)}")
        return self.linhas[0]

    def count(self) -> int:
        return len(self.linhas)

    def __iter__(self):
        return iter(self.linhas)


class _Resultado:
    def __init__(self, linhas: List[Any]):
        self.linhas = linhas

    def all(self) -> List[Any]:
        return self.linhas

    def scalar(self) -> Any:
        return self.linhas[0][0] if self.linhas else None

    def scalar_one(self) -> Any:
        if len(self.linhas) != 1:
            raise AssertionError(f"esperava 1 linha, achei {len(self.linhas)}")
        return self.linhas[0][0]

    def __iter__(self):
        return iter(self.linhas)


class Sessao:
    """Lê o staging do banco de teste e grava o que o teste adicionou ou alterou."""

    def __init__(self, engine: Any):
        self.engine = engine
        self._tabelas: Dict[str, stg_tabela.Tabela] = {}

    def __enter__(self) -> "Sessao":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _tabela(self, modelo: Modelo) -> stg_tabela.Tabela:
        if modelo.nome not in self._tabelas:
            with transacao_de_carga(self.engine) as cursor:
                self._tabelas[modelo.nome] = modelo.fabrica().carregar(cursor)
        return self._tabelas[modelo.nome]

    def query(self, modelo: Modelo) -> Consulta:
        return Consulta(list(self._tabela(modelo)))

    def get(self, modelo: Modelo, identificador: Any) -> Any:
        return next((linha for linha in self._tabela(modelo) if linha.id == identificador), None)

    def add(self, pendente: Pendente) -> Pendente:
        self._tabela(pendente.modelo).nova(**pendente.atributos)
        return pendente

    def add_all(self, pendentes: List[Pendente]) -> None:
        for pendente in pendentes:
            self.add(pendente)

    def flush(self) -> None:
        self.commit()

    def commit(self) -> None:
        """Grava o que mudou, na ordem das chaves estrangeiras, e recarrega na próxima consulta."""
        ordem = [
            "partidos_politicos",
            "politicos",
            "filiacoes_partidarias",
            "mandatos",
            "membros_gabinete",
            "proposicoes",
            "sessoes_votacao",
            "votos_parlamentares",
        ]
        with transacao_de_carga(self.engine) as cursor:
            for nome in sorted(self._tabelas, key=ordem.index):
                self._tabelas[nome].gravar(cursor)
        self._tabelas.clear()  # a próxima consulta lê o banco de novo (a carga pode ter mudado o resto)

    def execute(self, comando: Any, parametros: Any = None) -> _Resultado:
        """SQL direto no banco de teste (confirmado na hora); devolve as linhas já lidas."""
        with self.engine.begin() as conexao:
            resultado = conexao.execute(comando, parametros or {})
            return _Resultado(list(resultado.all()) if resultado.returns_rows else [])

    def rollback(self) -> None:
        self._tabelas.clear()

    def close(self) -> None:
        self._tabelas.clear()
