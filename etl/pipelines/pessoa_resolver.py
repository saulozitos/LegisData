"""
Resolve, em `core`, a pessoa a que um registro das fontes de finanças se refere.

Ordem: identificador oficial (Câmara ou Senado), depois o HMAC do CPF (`CPF_HMAC`; o registro traz só o HMAC) e, na falta
deles, nome normalizado ÚNICO (qualquer nome registrado da pessoa: civil, eleitoral, parlamentar, histórico ou grafia da
fonte). Um HMAC que casa com mais de uma pessoa é ambíguo e não cai no nome; um HMAC que não casa com ninguém deixa o nome
valer, mas só entre quem não tem CPF conhecido diferente: CPF diferente prova que o homônimo é outra pessoa. Nome que casa com mais de uma pessoa nunca é
atribuído por palpite: só se desfaz pelo mandato no ano do registro (regra de intervalo temporal da decisão 2 de
`docs/DECISOES_E_DUVIDAS_PENDENTES.md`): vale a única pessoa com mandato no ano e, sem nenhuma, a única que não foi
descartada por ter mandatos conhecidos só em outros anos (pessoa sem mandato cadastrado é "desconhecida", não excluída).
O nome é comparado com título ("Padre João" e "Dr. João" são pessoas diferentes) e, só quando nada casa, sem título.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from etl.pipelines.loader_helpers import inteiro
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.names import normalize_name_tokens, normalize_plain

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402

IDENTIFICADORES = ("CAMARA_ID", "SENADO_ID")


@dataclass(frozen=True)
class Resolucao:
    """`pessoa_id` só vem preenchido quando a identificação é segura; `situacao` explica o que houve."""

    pessoa_id: Optional[int]
    situacao: str  # IDENTIFICADO, NAO_CADASTRADO ou HOMONIMO_NAO_DESAMBIGUADO


class ResolvedorDePessoas:
    def __init__(self, conn: Connection):
        self._por_identificador: Dict[Tuple[str, int], int] = {}
        for tipo, valor, pessoa_id in conn.execute(
            text("SELECT tipo, valor, pessoa_id FROM core.pessoa_identificador WHERE tipo = ANY(:tipos)"),
            {"tipos": list(IDENTIFICADORES)},
        ):
            if re.fullmatch(r"[0-9]+", str(valor)):
                self._por_identificador[(tipo, int(valor))] = pessoa_id

        nomes: Dict[str, Set[int]] = defaultdict(set)
        nomes_sem_titulo: Dict[str, Set[int]] = defaultdict(set)
        for pessoa_id, nome in conn.execute(
            text("SELECT pessoa_id, nome FROM core.pessoa_nome UNION SELECT id, nome_exibicao FROM core.pessoa")
        ):
            for indice, chave in ((nomes, normalize_plain(nome)), (nomes_sem_titulo, normalize_name_tokens(nome))):
                if chave:
                    indice[chave].add(pessoa_id)
        self._por_nome = nomes
        self._por_cpf_hmac: Dict[str, Set[int]] = defaultdict(set)
        self._cpfs_da_pessoa: Dict[int, Set[str]] = defaultdict(set)
        for valor, pessoa_id in conn.execute(
            text("SELECT valor, pessoa_id FROM core.pessoa_identificador WHERE tipo = 'CPF_HMAC'")
        ):
            self._por_cpf_hmac[str(valor)].add(pessoa_id)
            self._cpfs_da_pessoa[pessoa_id].add(str(valor))
        self._por_nome_sem_titulo = nomes_sem_titulo

        self._mandatos: Dict[int, List[Tuple[date, Optional[date]]]] = defaultdict(list)
        for pessoa_id, inicio, fim in conn.execute(text("SELECT pessoa_id, inicio, fim FROM core.mandato")):
            self._mandatos[pessoa_id].append((inicio, fim))

    def por_identificador(self, camara_id: Any = None, senado_id: Any = None) -> Optional[int]:
        for tipo, valor in (("CAMARA_ID", camara_id), ("SENADO_ID", senado_id)):
            numero = inteiro(valor)  # a mesma regra do resto do ETL: bool e fração não são identificador
            achado = self._por_identificador.get((tipo, numero)) if numero is not None else None
            if achado is not None:
                return achado
        return None

    def por_cpf_hmac(self, cpf_hmac: Any) -> Optional[int]:
        pessoas = self._por_cpf_hmac.get(str(cpf_hmac or ""), set())
        return next(iter(pessoas)) if len(pessoas) == 1 else None

    def _tinha_mandato_em(self, pessoa_id: int, ano: int) -> bool:
        inicio_ano, fim_ano = date(ano, 1, 1), date(ano, 12, 31)
        return any(
            inicio <= fim_ano and (fim is None or fim >= inicio_ano) for inicio, fim in self._mandatos[pessoa_id]
        )

    def _candidatos(self, nome: Any, cpf_hmac: Optional[str] = None) -> Set[int]:
        texto = str(nome) if nome else ""
        achados = self._por_nome.get(normalize_plain(texto)) or self._por_nome_sem_titulo.get(
            normalize_name_tokens(texto), set()
        )
        if not cpf_hmac:
            return achados
        # quem já tem CPF conhecido e nenhum é o do registro é outra pessoa, por mais igual que seja o nome
        return {c for c in achados if not self._cpfs_da_pessoa.get(c) or cpf_hmac in self._cpfs_da_pessoa[c]}

    def _desfazer(self, candidatos: Set[int], ano: int) -> Optional[int]:
        com_mandato = [c for c in candidatos if self._tinha_mandato_em(c, ano)]
        if len(com_mandato) == 1:
            return com_mandato[0]
        if com_mandato:
            return None
        # ninguém tinha mandato no ano: sobra quem não tem mandato cadastrado (desconhecido), se for uma só pessoa
        desconhecidos = [c for c in candidatos if not self._mandatos[c]]
        return desconhecidos[0] if len(desconhecidos) == 1 else None

    def por_nome(self, nomes: Iterable[Any], ano: Optional[int] = None, cpf_hmac: Optional[str] = None) -> Resolucao:
        """Primeiro nome (da lista) com resultado seguro; ambíguo é desfeito pelo mandato do `ano`, se houver."""
        ambiguo = False
        for nome in nomes:
            candidatos = self._candidatos(nome, cpf_hmac)
            if len(candidatos) == 1:
                # Nome único vale mesmo que os mandatos cadastrados sejam de outros anos: o cadastro de mandatos do Senado
                # anterior a 2023 está incompleto, e exigir mandato no ano desligaria cerca de 1.000 emendas de
                # parlamentares reais (Otto Alencar, Cid Gomes, Flávio Bolsonaro...). O risco oposto (um autor atual
                # fora do cadastro com o mesmo nome de um ex-parlamentar) está anotado no plano.
                return Resolucao(next(iter(candidatos)), "IDENTIFICADO")
            if len(candidatos) > 1:
                ambiguo = True
                escolhida = self._desfazer(candidatos, ano) if ano is not None else None
                if escolhida is not None:
                    return Resolucao(escolhida, "IDENTIFICADO")
        return Resolucao(None, "HOMONIMO_NAO_DESAMBIGUADO" if ambiguo else "NAO_CADASTRADO")

    def resolver(self, item: Dict[str, Any], ano: Optional[int] = None) -> Resolucao:
        """Registro das fontes com `camara_id`/`senado_id` e nomes civil e eleitoral."""
        achado = self.por_identificador(item.get("camara_id"), item.get("senado_id"))
        if achado is not None:
            return Resolucao(achado, "IDENTIFICADO")
        cpf_hmac = str(item.get("cpf_hmac") or "") or None
        if cpf_hmac:
            donos = self._por_cpf_hmac.get(cpf_hmac, set())
            if len(donos) == 1:
                return Resolucao(next(iter(donos)), "IDENTIFICADO")
            if len(donos) > 1:  # o mesmo CPF em dois cadastros: a fusão ainda não veio, e o nome não desempata
                return Resolucao(None, "HOMONIMO_NAO_DESAMBIGUADO")
        # Identificador que o cadastro não conhece cai no nome, mesmo que o candidato tenha OUTRO identificador do mesmo
        # tipo (comportamento fixado em teste). O risco é o mesmo da regra de nome único, anotado no plano: um parlamentar
        # fora do cadastro com o nome de outro herdaria os dados dele.
        return self.por_nome([item.get("nome_civil"), item.get("nome_eleitoral"), item.get("nome")], ano, cpf_hmac)
