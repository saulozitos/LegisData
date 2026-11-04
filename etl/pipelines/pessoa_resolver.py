"""
Resolve, em `core`, a pessoa a que um registro das fontes de finanças se refere.

Ordem: identificador oficial (Câmara ou Senado) e, na falta dele, nome normalizado ÚNICO (qualquer nome registrado da
pessoa: civil, eleitoral, parlamentar, histórico ou grafia da fonte). Nome que casa com mais de uma pessoa nunca é
atribuído por palpite: só se desfaz pelo mandato no ano do registro (regra de intervalo temporal da decisão 2 de
`docs/DECISOES_E_DUVIDAS_PENDENTES.md`): vale a única pessoa com mandato no ano e, sem nenhuma, a única que não foi
descartada por ter mandatos conhecidos só em outros anos (pessoa sem mandato cadastrado é "desconhecida", não excluída).
O nome é comparado com título ("Padre João" e "Dr. João" são pessoas diferentes) e, só quando nada casa, sem título.

Enquanto as pessoas duplicadas não são unificadas (`docs/PESSOAS_DUPLICADAS.md`), o mesmo parlamentar pode existir como
cadastro do legado (sem identificador, mas com o `camaraId`/`senadoId` em `stg.politicos`) e como cadastro novo (com
identificador). Os dois contam como UMA pessoa e o dado é gravado no cadastro com identificador, que é o que o dossiê
alcança pelo `camara_id`/`senado_id`. Homônimos de verdade têm identificadores diferentes e continuam separados.
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

        # Cadastro do legado sem identificador -> cadastro com o identificador que o legado conhece (se existir)
        self._gemeo: Dict[int, int] = {}
        if conn.execute(text("SELECT to_regclass('stg.politicos') IS NOT NULL")).scalar():
            for pessoa_id, camara_id, senado_id in conn.execute(
                text(
                    'SELECT pe.id, po."camaraId", po."senadoId" FROM core.pessoa pe '
                    "JOIN stg.politicos po ON po.id = pe.uid"
                )
            ):
                canonica = self.por_identificador(camara_id, senado_id)
                if canonica is not None and canonica != pessoa_id:
                    self._gemeo[pessoa_id] = canonica

        nomes: Dict[str, Set[int]] = defaultdict(set)
        nomes_sem_titulo: Dict[str, Set[int]] = defaultdict(set)
        for pessoa_id, nome in conn.execute(
            text("SELECT pessoa_id, nome FROM core.pessoa_nome UNION SELECT id, nome_exibicao FROM core.pessoa")
        ):
            canonica = self._gemeo.get(pessoa_id, pessoa_id)
            for indice, chave in ((nomes, normalize_plain(nome)), (nomes_sem_titulo, normalize_name_tokens(nome))):
                if chave:
                    indice[chave].add(canonica)
        self._por_nome = nomes
        self._por_nome_sem_titulo = nomes_sem_titulo

        self._mandatos: Dict[int, List[Tuple[date, Optional[date]]]] = defaultdict(list)
        for pessoa_id, inicio, fim in conn.execute(text("SELECT pessoa_id, inicio, fim FROM core.mandato")):
            self._mandatos[self._gemeo.get(pessoa_id, pessoa_id)].append((inicio, fim))

    def por_identificador(self, camara_id: Any = None, senado_id: Any = None) -> Optional[int]:
        for tipo, valor in (("CAMARA_ID", camara_id), ("SENADO_ID", senado_id)):
            numero = inteiro(valor)  # a mesma regra do resto do ETL: bool e fração não são identificador
            achado = self._por_identificador.get((tipo, numero)) if numero is not None else None
            if achado is not None:
                return achado
        return None

    def _tinha_mandato_em(self, pessoa_id: int, ano: int) -> bool:
        inicio_ano, fim_ano = date(ano, 1, 1), date(ano, 12, 31)
        return any(
            inicio <= fim_ano and (fim is None or fim >= inicio_ano) for inicio, fim in self._mandatos[pessoa_id]
        )

    def _candidatos(self, nome: Any) -> Set[int]:
        texto = str(nome) if nome else ""
        return self._por_nome.get(normalize_plain(texto)) or self._por_nome_sem_titulo.get(
            normalize_name_tokens(texto), set()
        )

    def _desfazer(self, candidatos: Set[int], ano: int) -> Optional[int]:
        com_mandato = [c for c in candidatos if self._tinha_mandato_em(c, ano)]
        if len(com_mandato) == 1:
            return com_mandato[0]
        if com_mandato:
            return None
        # ninguém tinha mandato no ano: sobra quem não tem mandato cadastrado (desconhecido), se for uma só pessoa
        desconhecidos = [c for c in candidatos if not self._mandatos[c]]
        return desconhecidos[0] if len(desconhecidos) == 1 else None

    def por_nome(self, nomes: Iterable[Any], ano: Optional[int] = None) -> Resolucao:
        """Primeiro nome (da lista) com resultado seguro; ambíguo é desfeito pelo mandato do `ano`, se houver."""
        ambiguo = False
        for nome in nomes:
            candidatos = self._candidatos(nome)
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
        # Identificador que o cadastro não conhece cai no nome, mesmo que o candidato tenha OUTRO identificador do mesmo
        # tipo (comportamento fixado em teste). O risco é o mesmo da regra de nome único, anotado no plano: um parlamentar
        # fora do cadastro com o nome de outro herdaria os dados dele.
        return self.por_nome([item.get("nome_civil"), item.get("nome_eleitoral"), item.get("nome")], ano)
