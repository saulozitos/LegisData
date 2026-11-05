"""
Linhas do staging relacional (`stg`) em memória, gravadas de uma vez por `COPY`.

O staging relacional é o que as funções `etl.merge_*` leem. Em vez de um objeto de ORM por linha e um `INSERT`/`UPDATE` por
vez, a carga lê a tabela inteira (os cadastros são pequenos: milhares de linhas), conversa com objetos simples na memória
(`Linha`: um `SimpleNamespace`) e grava só a diferença ao fim: as linhas novas por `COPY` numa tabela temporária tipada e as
alteradas por um `UPDATE ... FROM` dessa mesma tabela. As consultas por chave natural viram dicionários da própria carga.

O `id` de uma linha que já existe nunca muda: ele é o `uid` público em `core` (pessoa, partido, proposição). Uma linha nova
ganha um `uuid4` aqui mesmo, então as chaves estrangeiras entre tabelas novas não dependem de ida e volta ao banco.

Texto vazio vira `NULL` no `COPY` (desconhecido é nulo, nunca texto vazio). Os nomes de tabela e de coluna são constantes
deste módulo e passam pela mesma allowlist do `COPY` (`etl.utils.copia`).
"""

import enum
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional

from etl.utils.copia import _identificador, _validar_tabela, copiar_linhas

logger = logging.getLogger("StgTabela")


class Linha(SimpleNamespace):
    """Uma linha do staging; os atributos têm os nomes de `Tabela.colunas`."""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Tabela:
    """
    Uma tabela de `stg` em memória. `colunas` liga o atributo da `Linha` à coluna do banco; `padroes` dá o valor (ou uma função
    sem argumentos) dos atributos que o chamador não informou ao criar uma linha, no lugar do `default` das colunas que não têm
    um no banco.
    """

    nome: str
    colunas: Dict[str, str]
    padroes: Dict[str, Any] = field(default_factory=dict)
    json_attrs: frozenset = frozenset()  # atributos que são JSON (a coluna é `json`)
    atualizado_em: Optional[str] = None  # coluna `updated_at`, tocada ao atualizar uma linha
    linhas: List[Linha] = field(default_factory=list)
    _originais: Dict[Any, Dict[str, Any]] = field(default_factory=dict)
    _novas: List[Linha] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validar_tabela(self.nome)
        for coluna in self.colunas.values():
            _identificador(coluna)

    # ------------------------------------------------------------------ leitura
    def carregar(self, cursor: Any) -> "Tabela":
        """Lê a tabela inteira do banco; o estado lido é o ponto de comparação para saber o que mudou."""
        atributos = list(self.colunas)
        lista = ", ".join(_identificador(self.colunas[a]) for a in atributos)
        cursor.execute(f"SELECT {lista} FROM stg.{self.nome}")  # nosec B608 - nomes constantes e validados
        self.linhas, self._originais, self._novas = [], {}, []
        for registro in cursor.fetchall():
            linha = Linha(**dict(zip(atributos, registro)))
            self.linhas.append(linha)
            self._originais[linha.id] = self._instantaneo(linha)
        return self

    def _instantaneo(self, linha: Linha) -> Dict[str, Any]:
        return {a: getattr(linha, a, None) for a in self.colunas}

    # ------------------------------------------------------------------ escrita em memória
    def nova(self, **atributos: Any) -> Linha:
        """Cria uma linha (ainda só em memória); o `id` é gerado aqui, a menos que venha informado."""
        desconhecidos = set(atributos) - set(self.colunas)
        if desconhecidos:
            raise AttributeError(f"{self.nome}: atributos desconhecidos {sorted(desconhecidos)}")
        valores: Dict[str, Any] = {a: None for a in self.colunas}
        for atributo, padrao in self.padroes.items():
            valores[atributo] = padrao() if callable(padrao) else padrao
        valores.update(atributos)
        valores["id"] = valores.get("id") or uuid.uuid4()
        linha = Linha(**valores)
        self.linhas.append(linha)
        self._novas.append(linha)
        return linha

    def __iter__(self) -> Iterator[Linha]:
        return iter(self.linhas)

    def __len__(self) -> int:
        return len(self.linhas)

    # ------------------------------------------------------------------ gravação
    def alteradas(self) -> List[Linha]:
        """As linhas que já existiam no banco e tiveram algum atributo mudado."""
        novas = {id(linha) for linha in self._novas}
        return [
            linha
            for linha in self.linhas
            if id(linha) not in novas and self._originais.get(linha.id) != self._instantaneo(linha)
        ]

    def _valor(self, atributo: str, valor: Any) -> Any:
        if valor is None:
            return None
        if atributo in self.json_attrs:
            return json.dumps(valor, ensure_ascii=False)
        if isinstance(valor, enum.Enum):
            return valor.name  # o banco guarda o nome do membro do enum
        if isinstance(valor, bool):
            return "true" if valor else "false"
        return str(valor) if isinstance(valor, uuid.UUID) else valor

    def _tabela_temporaria(self, cursor: Any, colunas: List[str]) -> str:
        temporaria = f"_stg_{self.nome}"
        lista = ", ".join(_identificador(c) for c in colunas)
        # Tipos da tabela de verdade, sem restrições: o COPY converte o texto (enum, uuid, data, json) como o banco faria
        cursor.execute(
            f"CREATE TEMP TABLE IF NOT EXISTS {temporaria} ON COMMIT DROP AS "  # nosec B608
            f"SELECT {lista} FROM stg.{self.nome} WHERE false"
        )
        cursor.execute(f"TRUNCATE {temporaria}")
        return temporaria

    def gravar(self, cursor: Any) -> Dict[str, int]:
        """Grava as linhas novas e as alteradas na transação do cursor; devolve `{'inseridas': n, 'atualizadas': m}`."""
        atributos = list(self.colunas)
        colunas = [self.colunas[a] for a in atributos]
        lista = ", ".join(_identificador(c) for c in colunas)
        inseridas = self._novas
        atualizadas = self.alteradas()
        if inseridas:
            temporaria = self._tabela_temporaria(cursor, colunas)
            copiar_linhas(
                cursor,
                temporaria,
                colunas,
                ([self._valor(a, getattr(linha, a)) for a in atributos] for linha in inseridas),
            )
            cursor.execute(f"INSERT INTO stg.{self.nome} ({lista}) SELECT {lista} FROM {temporaria}")  # nosec B608
        if atualizadas:
            temporaria = self._tabela_temporaria(cursor, colunas)
            copiar_linhas(
                cursor,
                temporaria,
                colunas,
                ([self._valor(a, getattr(linha, a)) for a in atributos] for linha in atualizadas),
            )
            definicoes = [f"{_identificador(c)} = x.{_identificador(c)}" for c in colunas if c != "id"]
            if self.atualizado_em:
                definicoes.append(f"{_identificador(self.atualizado_em)} = now()")
            cursor.execute(
                f"UPDATE stg.{self.nome} s SET {', '.join(definicoes)} FROM {temporaria} x WHERE s.id = x.id"  # nosec B608
            )
        for linha in self.linhas:
            self._originais[linha.id] = self._instantaneo(linha)
        self._novas = []
        return {"inseridas": len(inseridas), "atualizadas": len(atualizadas)}


# ---------------------------------------------------------------------------------------------- as tabelas do staging
def politicos() -> Tabela:
    return Tabela(
        "politicos",
        {
            "id": "id",
            "civil_name": "nomeCivil",
            "electoral_name": "nomeEleitoral",
            "tse_id": "tseId",
            "camara_id": "camaraId",
            "senado_id": "senadoId",
            "birth_date": "dataNascimento",
            "death_date": "dataFalecimento",
            "gender": "genero",
            "birthplace_city": "naturalidadeMunicipio",
            "birthplace_state": "naturalidadeUf",
            "photo_url": "fotoUrl",
            "biography": "biografia",
            "email": "email",
            "cabinet_room": "gabineteSala",
            "cabinet_phone": "gabineteTelefone",
            "social_links": "redesSociais",
            "possui_processos_declarados": "possuiProcessosDeclarados",
        },
        padroes={"possui_processos_declarados": False},
        json_attrs=frozenset({"social_links"}),
        atualizado_em="updated_at",
    )


def filiacoes() -> Tabela:
    return Tabela(
        "filiacoes_partidarias",
        {
            "id": "id",
            "politician_id": "politicoId",
            "party_id": "partidoId",
            "start_date": "dataFiliacao",
            "end_date": "dataDesfiliacao",
            "is_current": "isAtual",
            "disaffiliation_reason": "motivoDesfiliacao",
            "state": "uf",
            "created_at": "created_at",
        },
        padroes={"is_current": False, "created_at": date.today},
    )


def mandatos() -> Tabela:
    return Tabela(
        "mandatos",
        {
            "id": "id",
            "politician_id": "politicoId",
            "party_id": "partidoId",
            "office": "cargo",
            "sphere": "esfera",
            "jurisdiction_state": "ufJurisdicao",
            "election_year": "anoEleicao",
            "term_number": "numeroMandato",
            "start_date": "dataInicio",
            "end_date": "dataFim",
            "status": "status",
            "coalition_name": "coligacaoNome",
            "total_votes": "totalVotos",
            "vote_percentage": "percentualVotos",
        },
        padroes={"sphere": "FEDERAL", "jurisdiction_state": "BR", "term_number": 1, "status": "TITULAR_ATIVO"},
        atualizado_em="updated_at",
    )


def membros_gabinete() -> Tabela:
    return Tabela(
        "membros_gabinete",
        {
            "id": "id",
            "mandate_id": "mandatoId",
            "politician_id": "politicoId",
            "occupant_name": "nomeOcupante",
            "ministry_name": "ministerioNome",
            "inauguration_date": "dataPosse",
            "departure_date": "dataExoneracao",
            "is_economy_minister": "isMinistroEconomia",
        },
        padroes={"is_economy_minister": False},
    )


def proposicoes() -> Tabela:
    return Tabela(
        "proposicoes",
        {
            "id": "id",
            "external_camara_id": "idExternoCamara",
            "external_senado_id": "idExternoSenado",
            "proposition_type": "tipo",
            "number": "numero",
            "year": "ano",
            "title": "titulo",
            "summary": "ementa",
            "detailed_summary": "explicacaoEmenta",
            "thematic_area": "areaTematica",
            "presentation_date": "dataApresentacao",
            "sanction_date": "dataSancaoPromulgacao",
            "status": "statusTramitacao",
            "full_text_url": "urlTextoOriginal",
            "is_structural_reform": "isReformaEstrutural",
            "author_name": "autorNome",
            "author_politician_id": "autorPoliticoId",
            "is_executive_initiative": "iniciativaPoderExecutivo",
            "impact_axis": "eixoImpacto",
            "impact_tags": "eixosImpacto",
            "official_url": "urlOficial",
        },
        padroes={"status": "EM_TRAMITACAO", "is_structural_reform": False, "is_executive_initiative": False},
        atualizado_em="updated_at",
    )


def sessoes_votacao() -> Tabela:
    return Tabela(
        "sessoes_votacao",
        {
            "id": "id",
            "external_id": "idExterno",
            "proposition_id": "proposicaoId",
            "legislative_house": "casaLegislativa",
            "session_datetime": "dataHoraVotacao",
            "agenda_title": "tituloPauta",
            "detailed_description": "descricaoDetalhada",
            "is_secret_vote": "isVotacaoSecreta",
            "is_approved": "aprovada",
            "votes_yes_count": "totalSim",
            "votes_no_count": "totalNao",
            "votes_abstain_count": "totalAbstencao",
            "votes_obstruction_count": "totalObstrucao",
            "government_orientation": "orientacaoGoverno",
            "party_orientations": "orientacoesBancadas",
            "created_at": "created_at",
        },
        padroes={
            "is_secret_vote": False,
            "votes_yes_count": 0,
            "votes_no_count": 0,
            "votes_abstain_count": 0,
            "votes_obstruction_count": 0,
            "created_at": _agora,
        },
    )


def partidos() -> Tabela:
    """Os partidos: gravados por `staging_partidos`; esta definição serve a quem precisa lê-los ou semeá-los (testes)."""
    return Tabela(
        "partidos_politicos",
        {
            "id": "id",
            "acronym": "sigla",
            "full_name": "nomeCompleto",
            "electoral_number": "numeroEleitoral",
            "foundation_date": "dataFundacao",
            "dissolution_date": "dataExtincao",
            "successor_party_id": "partidoSucessorId",
            "logo_url": "logoUrl",
            "political_spectrum": "espectroPolitico",
            "ideology": "ideologia",
            "motto": "lema",
        },
        atualizado_em="updated_at",
    )


def votos_parlamentares() -> Tabela:
    """Os votos: gravados por `staging_votos`; esta definição serve a quem precisa lê-los ou semeá-los (testes)."""
    return Tabela(
        "votos_parlamentares",
        {
            "id": "id",
            "voting_session_id": "sessaoVotacaoId",
            "politician_id": "politicoId",
            "party_id": "partidoId",
            "vote_choice": "voto",
            "created_at": "created_at",
        },
        padroes={"created_at": _agora},
    )


@dataclass
class Staging:
    """Todas as tabelas relacionais que a carga do cadastro e do legislativo escreve, na ordem das chaves estrangeiras."""

    politicos: Tabela
    filiacoes: Tabela
    mandatos: Tabela
    gabinete: Tabela
    proposicoes: Tabela
    sessoes: Tabela

    @classmethod
    def carregar(cls, cursor: Any) -> "Staging":
        return cls(
            politicos=politicos().carregar(cursor),
            filiacoes=filiacoes().carregar(cursor),
            mandatos=mandatos().carregar(cursor),
            gabinete=membros_gabinete().carregar(cursor),
            proposicoes=proposicoes().carregar(cursor),
            sessoes=sessoes_votacao().carregar(cursor),
        )

    def tabelas(self) -> List[Tabela]:
        return [self.politicos, self.filiacoes, self.mandatos, self.gabinete, self.proposicoes, self.sessoes]

    def gravar(self, cursor: Any) -> Dict[str, Dict[str, int]]:
        """Grava o que mudou, na ordem das chaves estrangeiras (político antes de mandato, proposição antes de sessão)."""
        return {t.nome: t.gravar(cursor) for t in self.tabelas()}
