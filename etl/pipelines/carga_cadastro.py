"""
Carga do cadastro e do legislativo: arquivos processados -> staging relacional (`stg`) -> fusão em `core`/`leg`.

Cada recurso é uma carga própria: abre a sua linha em `etl.execucao` (fonte, estágio `CARREGAR`, `parametros['recurso']`),
grava o que mudou no `stg` numa transação (a das linhas em memória, por `COPY`; ver `stg_tabela`), registra os arquivos de
origem em `etl.arquivo_bruto`, mede as verificações do catálogo (`etl.utils.verificacoes`) e fecha a linha com as contagens
(`lidas == gravadas + rejeitadas`, rejeitadas por motivo). A fusão é uma execução à parte (estágio `MERGE`). Os recursos
dependem só do que está no banco (os mapas de partido, deputado, senador e proposição saem do próprio `stg`), então um
recurso pode ser recarregado sozinho sem tocar nos outros.

Ordem: partidos, politicos, filiacoes, mandatos, parlamentares_historicos, proposicoes, votacoes_plenario,
votacoes_historico; depois a fusão. O `id` do `stg` de uma linha que já existe nunca muda (é o `uid` público em `core`).
"""

import argparse
import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.config import PROCESSED_DATA_DIR
from etl.pipelines import stg_tabela
from etl.pipelines.dados_partidos import PARTIDOS_BASE
from etl.pipelines.loader_helpers import SEM_PARTIDO
from etl.pipelines.staging_cadastro import Cadastro, carregar_filiacoes, carregar_mandatos, carregar_politicos
from etl.pipelines.staging_partidos import gravar_partidos, montar_partidos
from etl.pipelines.staging_proposicoes import carregar_proposicoes
from etl.pipelines.staging_votacoes import (
    carregar_parlamentares_historicos,
    carregar_votacoes,
    carregar_votacoes_plenario,
)
from etl.pipelines.staging_votos import ContagemDeVotos
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.copia import transacao_de_carga
from etl.utils.datafiles import load_deputados, load_json, load_senadores
from etl.utils.execucao import Contagem, Execucao, registrar_arquivo_bruto, registrar_execucao
from etl.utils.manutencao import posprocessar_carga
from etl.utils.verificacoes import (
    cobertura_minima,
    dentro_da_janela,
    sem_duplicatas,
    sem_nulos,
    total_confere,
)

ensure_backend_on_path()

from app.core.database import SessionLocal  # noqa: E402
from app.core.database import engine as engine_padrao  # noqa: E402

logger = logging.getLogger("CargaCadastro")

# Mandato da fonte LEGADO que a fusão do cadastro poupou por ainda ser referenciado (a 0038 só os pula, não os vincula).
# O critério é o do DELETE de `etl.merge_cadastro` (migrações 0020 e 0038): quem mudar um deve mudar o outro.
SQL_MANDATOS_PRESERVADOS = (
    "SELECT count(*) FROM core.mandato c WHERE c.fonte_id = (SELECT id FROM etl.fonte WHERE codigo = 'LEGADO') "
    "AND NOT EXISTS (SELECT 1 FROM core.mandato_legado l WHERE l.mandato_id = c.id)"
)
MOTIVO_VOTO = "SEM_SESSAO_POLITICO_OU_OPCAO"  # voto que não virou linha (sessão, político ou opção ausentes)

RECURSOS = (
    "partidos",
    "politicos",
    "filiacoes",
    "mandatos",
    "parlamentares_historicos",
    "proposicoes",
    "votacoes_plenario",
    "votacoes_historico",
)


def _sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def _caminho_relativo(caminho: Path) -> str:
    """O caminho sem o diretório do usuário: relativo à raiz do projeto quando está dentro dela."""
    raiz = Path(__file__).resolve().parents[2]
    try:
        return caminho.resolve().relative_to(raiz).as_posix()
    except ValueError:
        return caminho.name


def contagem_de_votos(votos: ContagemDeVotos) -> Contagem:
    """A contagem de votos no formato de `etl.execucao` (o que não virou linha é rejeitado com motivo)."""
    contagem = Contagem(lidas=votos.lidas, gravadas=votos.gravadas)
    if votos.rejeitadas:
        contagem.rejeitar(MOTIVO_VOTO, votos.rejeitadas)
    return contagem


@dataclass
class Estagio:
    recurso: str
    fonte: str
    arquivos: Sequence[str]  # nomes (ou prefixos, com "*") sob a pasta de dados processados
    executar: Callable[[Any], Tuple[Contagem, bool]]  # (cursor) -> (contagem, algum arquivo ignorado inteiro)
    verificar: Optional[Callable[[Execucao], None]] = None


class CargaCadastro:
    """Gerencia a carga e a sincronização do cadastro e do legislativo no PostgreSQL."""

    def __init__(
        self,
        data_dir: Path = PROCESSED_DATA_DIR,
        allow_synthetic: bool = False,
        allow_unverified: bool = False,
        engine: Optional[Engine] = None,
    ):
        self.data_dir = Path(data_dir)
        self.allow_synthetic = allow_synthetic
        self.allow_unverified = allow_unverified
        self.engine = engine or engine_padrao
        self.staging: Optional[stg_tabela.Staging] = None
        self.party_map: Dict[str, Any] = {}
        self.contagens: Dict[str, Contagem] = {}  # a contagem de cada recurso carregado
        self.resumo_fusao: Optional[Dict[str, Any]] = None  # o resumo da fusão, se rodou

    # ------------------------------------------------------------------ banco
    def ensure_tables(self) -> None:
        """Aplica as migrações Alembic, únicas donas do schema (as tabelas de `stg` nascem delas)."""
        logger.info("Aplicando as migrações do schema no PostgreSQL...")
        from app.core.migrations import upgrade_schema

        upgrade_schema()

    def _carregar_staging(self) -> None:
        with transacao_de_carga(self.engine) as cursor:
            self.staging = stg_tabela.Staging.carregar(cursor)
            self.party_map = self._mapa_de_partidos(cursor)

    @staticmethod
    def _mapa_de_partidos(cursor: Any) -> Dict[str, Any]:
        cursor.execute("SELECT sigla, id FROM stg.partidos_politicos ORDER BY created_at, id")
        mapa: Dict[str, Any] = {}
        for sigla, identificador in cursor.fetchall():
            mapa.setdefault(sigla, identificador)
            mapa.setdefault(sigla.upper(), identificador)
        return mapa

    # ------------------------------------------------------------------ mapas (saem do próprio stg)
    def _deputados(self) -> Dict[int, Any]:
        return {p.camara_id: p.id for p in self.staging.politicos if p.camara_id is not None}

    def _senadores(self) -> Dict[int, Any]:
        return {p.senado_id: p.id for p in self.staging.politicos if p.senado_id is not None}

    def _presidentes(self) -> Dict[str, Any]:
        mapa: Dict[str, Any] = {}
        for p in load_json(self.data_dir / "presidentes_historico.json", []) or []:
            pol = next(
                (
                    x
                    for x in self.staging.politicos
                    if x.civil_name == p["nome_civil"] or x.electoral_name == p["nome_eleitoral"]
                ),
                None,
            )
            if pol is not None:
                mapa[p["id_referencia"]] = pol.id
        return mapa

    def _proposicoes_da_camara(self) -> Dict[int, Any]:
        return {p.external_camara_id: p.id for p in self.staging.proposicoes if p.external_camara_id is not None}

    def _cadastro(self, cursor: Any) -> Cadastro:
        return Cadastro(
            cursor,
            self.data_dir,
            self.staging,
            allow_synthetic=self.allow_synthetic,
            allow_unverified=self.allow_unverified,
        )

    # ------------------------------------------------------------------ os recursos
    def _partidos(self, cursor: Any) -> Tuple[Contagem, bool]:
        partidos = montar_partidos(self.data_dir)
        self.party_map = gravar_partidos(cursor, partidos)
        distintos = len({v for v in self.party_map.values()})
        contagem = Contagem(lidas=len(partidos), gravadas=distintos)
        self._partidos_esperados = len(partidos)
        return contagem, False

    def _politicos(self, cursor: Any) -> Tuple[Contagem, bool]:
        *_, contagem = carregar_politicos(self._cadastro(cursor))
        return contagem, False

    def _filiacoes(self, cursor: Any) -> Tuple[Contagem, bool]:
        return carregar_filiacoes(self._cadastro(cursor), self._deputados(), self._senadores(), self.party_map), False

    def _mandatos(self, cursor: Any) -> Tuple[Contagem, bool]:
        _, contagem = carregar_mandatos(
            self._cadastro(cursor), self._presidentes(), self._deputados(), self._senadores(), self.party_map
        )
        return contagem, False

    def _parlamentares_historicos(self, cursor: Any) -> Tuple[Contagem, bool]:
        _, contagem = carregar_parlamentares_historicos(
            cursor, self.staging, self.data_dir, self._deputados(), self._senadores(), self.party_map
        )
        return contagem, False

    def _proposicoes(self, cursor: Any) -> Tuple[Contagem, bool]:
        _, contagem = carregar_proposicoes(
            self.staging.proposicoes,
            self.staging.politicos,
            self.data_dir,
            self._deputados(),
            self._senadores(),
            self.allow_unverified,
        )
        return contagem, False

    def _votacoes_plenario(self, cursor: Any) -> Tuple[Contagem, bool]:
        votos = carregar_votacoes_plenario(
            cursor,
            self.staging,
            self.data_dir,
            self._proposicoes_da_camara(),
            self._deputados(),
            self._senadores(),
            self.party_map,
        )
        return contagem_de_votos(votos), votos.arquivos_ignorados > 0

    def _votacoes_historico(self, cursor: Any) -> Tuple[Contagem, bool]:
        contadores = carregar_votacoes(
            cursor, self.staging, self.data_dir, self._deputados(), self._senadores(), self.party_map
        )
        votos = ContagemDeVotos.de_contadores(contadores)
        return contagem_de_votos(votos), votos.arquivos_ignorados > 0

    # ------------------------------------------------------------------ verificações do catálogo
    def _verificar_partidos(self, execucao: Execucao) -> None:
        execucao.verificar(
            total_confere("partidos_mapeados", self._partidos_esperados, len({v for v in self.party_map.values()}))
        )
        execucao.verificar(
            cobertura_minima(
                "partidos_de_base_presentes", sum(1 for s in PARTIDOS_BASE if s in self.party_map), len(PARTIDOS_BASE)
            )
        )
        execucao.verificar(cobertura_minima("sem_partido_presente", int(SEM_PARTIDO in self.party_map), 1))

    def _verificar_politicos(self, execucao: Execucao) -> None:
        politicos = self.staging.politicos
        execucao.verificar(sem_duplicatas("camara_id_unico", [p.camara_id for p in politicos if p.camara_id]))
        execucao.verificar(sem_duplicatas("senado_id_unico", [p.senado_id for p in politicos if p.senado_id]))
        execucao.verificar(
            sem_nulos("nome_eleitoral_preenchido", "nome_eleitoral", sum(1 for p in politicos if not p.electoral_name))
        )
        execucao.verificar(
            cobertura_minima(
                "deputados_da_fonte_no_staging",
                sum(1 for d in load_deputados(self.data_dir) if d["camara_id"] in self._deputados()),
                len(load_deputados(self.data_dir)),
            )
        )
        execucao.verificar(
            cobertura_minima(
                "senadores_da_fonte_no_staging",
                sum(1 for s in load_senadores(self.data_dir) if s["senado_id"] in self._senadores()),
                len(load_senadores(self.data_dir)),
            )
        )

    def _verificar_mandatos(self, execucao: Execucao) -> None:
        execucao.verificar(dentro_da_janela("mandatos_a_partir_de_1995", [m.start_date for m in self.staging.mandatos]))
        com_mandato = {m.politician_id for m in self.staging.mandatos}
        deputados = self._deputados()
        da_fonte = [deputados[d["camara_id"]] for d in load_deputados(self.data_dir) if d["camara_id"] in deputados]
        execucao.verificar(
            cobertura_minima(
                "deputados_da_fonte_com_mandato", sum(1 for i in da_fonte if i in com_mandato), len(da_fonte)
            )
        )

    def _verificar_proposicoes(self, execucao: Execucao) -> None:
        props = self.staging.proposicoes
        execucao.verificar(
            sem_duplicatas("id_camara_unico", [p.external_camara_id for p in props if p.external_camara_id])
        )
        execucao.verificar(
            sem_duplicatas("id_senado_unico", [p.external_senado_id for p in props if p.external_senado_id])
        )
        execucao.verificar(dentro_da_janela("proposicoes_a_partir_de_1995", [p.presentation_date for p in props]))

    def _estagios(self) -> Dict[str, Estagio]:
        return {
            e.recurso: e
            for e in (
                Estagio(
                    "partidos",
                    "CURADORIA",
                    ["deputados_camara.json", "senadores_senado.json", "filiacoes_partidarias.json"],
                    self._partidos,
                    self._verificar_partidos,
                ),
                Estagio(
                    "politicos",
                    "CAMARA_API",
                    ["presidentes_historico.json", "deputados_camara.json", "senadores_senado.json"],
                    self._politicos,
                    self._verificar_politicos,
                ),
                Estagio("filiacoes", "TSE", ["filiacoes_partidarias.json"], self._filiacoes),
                Estagio(
                    "mandatos",
                    "CAMARA_API",
                    ["presidentes_historico.json", "deputados_camara.json", "senadores_senado.json"],
                    self._mandatos,
                    self._verificar_mandatos,
                ),
                Estagio(
                    "parlamentares_historicos",
                    "CAMARA_API",
                    ["parlamentares_legislaturas_anteriores.json"],
                    self._parlamentares_historicos,
                ),
                Estagio(
                    "proposicoes",
                    "CAMARA_API",
                    ["proposicoes_2023.json", "proposicoes_senado.json"],
                    self._proposicoes,
                    self._verificar_proposicoes,
                ),
                Estagio(
                    "votacoes_plenario",
                    "CAMARA_API",
                    [
                        "sessoes_votacao_2023.json",
                        "votos_nominais_2023.json",
                        "sessoes_votacao_senado.json",
                        "votos_nominais_senado.json",
                    ],
                    self._votacoes_plenario,
                ),
                Estagio("votacoes_historico", "CAMARA_API", ["votacoes/*.json.gz"], self._votacoes_historico),
            )
        }

    # ------------------------------------------------------------------ execução
    def _arquivos(self, nomes: Sequence[str]) -> List[Path]:
        achados: List[Path] = []
        for nome in nomes:
            achados += sorted(self.data_dir.glob(nome)) if "*" in nome else [self.data_dir / nome]
        return [caminho for caminho in achados if caminho.is_file()]

    def _rodar_estagio(self, estagio: Estagio) -> Contagem:
        parametros = {
            "recurso": estagio.recurso,
            "allow_synthetic": self.allow_synthetic,
            "allow_unverified": self.allow_unverified,
        }
        with registrar_execucao(self.engine, estagio.fonte, "CARREGAR", parametros) as execucao:
            inicio = time.monotonic()
            with transacao_de_carga(self.engine) as cursor:
                contagem, ignorado = estagio.executar(cursor)
                self.staging.gravar(cursor)
                for caminho in self._arquivos(estagio.arquivos):
                    registrar_arquivo_bruto(
                        cursor,
                        estagio.fonte,
                        f"arquivo://{_caminho_relativo(caminho)}",
                        _sha256(caminho),
                        caminho.stat().st_size,
                        _caminho_relativo(caminho),
                        execucao.id,
                    )
            execucao.aplicar(contagem)
            self.contagens[estagio.recurso] = contagem
            execucao.com_alerta = ignorado  # arquivo pulado inteiro: os votos dele não foram contados
            if estagio.verificar:
                estagio.verificar(execucao)
            logger.info("   (%s levou %.1f s)", estagio.recurso, time.monotonic() - inicio)
        return contagem

    def load_all(
        self, recursos: Optional[Sequence[str]] = None, fundir: bool = True, migrar: bool = True
    ) -> Dict[str, int]:
        """
        Carrega os recursos pedidos (todos, por padrão), nesta ordem, e funde o staging em `core`/`leg`. Devolve a contagem de
        linhas de cada tabela do staging. `migrar=False` pula
        as migrações (o cron diário não migra o schema).
        """
        pedidos = list(recursos or RECURSOS)
        desconhecidos = [r for r in pedidos if r not in RECURSOS]
        if desconhecidos:
            raise ValueError(f"recurso desconhecido: {desconhecidos}; use um de {RECURSOS}")
        if migrar:
            self.ensure_tables()
        logger.info("=" * 70)
        logger.info("INICIANDO CARGA DE DADOS NO POSTGRESQL")
        logger.info("=" * 70)
        self._carregar_staging()
        estagios = self._estagios()
        for n, recurso in enumerate((r for r in RECURSOS if r in pedidos), start=1):
            logger.info("[%d/%d] %s", n, len(pedidos), recurso)
            self._rodar_estagio(estagios[recurso])
        if fundir:
            self._fundir_staging()
        with transacao_de_carga(self.engine) as cursor:
            counts = self._get_table_counts(cursor)
        self._print_summary_report(counts)
        return counts

    def _fundir_staging(self) -> None:
        """
        Funde o staging em `core`/`leg` (execução `MERGE` da fonte `PIPELINE`). A carga do staging já foi confirmada e
        fica; mas a fusão que falha é relançada, para a etapa aparecer como FALHOU no resumo da esteira em vez de OK com
        `core` e `leg` sem a carga nova.
        """
        from app.services.staging_merge import merge_staging

        with (
            registrar_execucao(self.engine, "PIPELINE", "MERGE", {"recurso": "cadastro_e_legislativo"}) as execucao,
            SessionLocal() as session,
        ):
            try:
                resumo = self.resumo_fusao = merge_staging(session)
            except Exception as exc:
                session.rollback()
                logger.error("Fusão staging -> core/leg falhou: %s", exc)  # o trace sai uma vez só, em quem chamou
                raise
            gravadas = _soma_inteiros(resumo)
            execucao.lidas, execucao.rejeitadas = gravadas + int(resumo.get("rejeitos") or 0), int(
                resumo.get("rejeitos") or 0
            )
            execucao.gravadas = gravadas
            if execucao.rejeitadas:
                execucao.motivos = {"REJEITADO_NA_FUSAO": execucao.rejeitadas}
            preservados = self._mandatos_preservados(session)
            if preservados:
                logger.warning(
                    "-> %d mandatos da fonte LEGADO saíram do staging mas seguem em core.mandato: a presença (ou outro "
                    "mandato) ainda os referencia. A fusão seguinte os remove quando a referência sumir.",
                    preservados,
                )

    @staticmethod
    def _mandatos_preservados(session: Any) -> int:
        """Mandatos da fonte LEGADO sem vínculo em `core.mandato_legado`: a fusão os poupou (ver a migração 0038)."""
        return int(session.execute(text(SQL_MANDATOS_PRESERVADOS)).scalar() or 0)

    # ------------------------------------------------------------------ relatórios
    @staticmethod
    def _get_table_counts(cursor: Any) -> Dict[str, int]:
        """Consulta e retorna a quantidade de linhas em cada tabela do staging."""
        tables = [
            ("partidos_politicos", "Partidos Políticos"),
            ("politicos", "Políticos (Presidentes + Deputados)"),
            ("filiacoes_partidarias", "Filiações Partidárias (TSE)"),
            ("mandatos", "Mandatos Eletivos"),
            ("membros_gabinete", "Membros de Gabinete (Fazenda/Planejamento)"),
            ("proposicoes", "Proposições Legislativas"),
            ("sessoes_votacao", "Sessões de Votação em Plenário"),
            ("votos_parlamentares", "Votos Parlamentares Nominais"),
        ]
        counts: Dict[str, int] = {}
        for tbl_name, label in tables:
            # Nomes de tabela são constantes desta lista (não vêm de entrada externa).
            cursor.execute(f"SELECT COUNT(*) FROM stg.{tbl_name}")  # nosec B608
            counts[label] = int(cursor.fetchone()[0] or 0)
        return counts

    @staticmethod
    def _print_summary_report(counts: Dict[str, int]) -> None:
        """Imprime no terminal o relatório com a contagem de linhas no PostgreSQL."""
        print("\n" + "=" * 80)
        print("          RELATÓRIO DE CARGA NO BANCO DE DADOS POSTGRESQL")
        print("=" * 80)
        print(f"{'TABELA / ENTIDADE':<52} | {'TOTAL DE LINHAS':>20}")
        print("-" * 80)
        total_geral = 0
        for label, count in counts.items():
            print(f"{label:<52} | {count:>20,}".replace(",", "."))
            total_geral += count
        print("-" * 80)
        print(f"{'TOTAL GERAL DE REGISTROS NAS TABELAS':<52} | {total_geral:>20,}".replace(",", "."))
        print("=" * 80 + "\n")


def _soma_inteiros(resumo: Any) -> int:
    """Soma os contadores inteiros do resumo da fusão (inclusive os aninhados), sem os rejeitos."""
    total = 0
    for chave, valor in resumo.items():
        if chave == "rejeitos":
            continue
        if isinstance(valor, bool):
            continue
        if isinstance(valor, int):
            total += valor
        elif isinstance(valor, dict):
            total += _soma_inteiros(valor)
    return total


def main(argv: Optional[List[str]] = None) -> Dict[str, int]:
    parser = argparse.ArgumentParser(description="Carga dos dados processados no PostgreSQL.")
    parser.add_argument(
        "--allow-synthetic", action="store_true", help="Carrega dados sintéticos de demonstração (marcados no texto)."
    )
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Carrega dados digitados e não verificados (ex.: eleições por UF).",
    )
    parser.add_argument(
        "--recurso", action="append", choices=RECURSOS, help="Carrega só este recurso (repetível); sem ele, todos."
    )
    parser.add_argument("--sem-fusao", action="store_true", help="Não funde o staging em core/leg depois da carga.")
    args = parser.parse_args(argv)
    contagens = CargaCadastro(allow_synthetic=args.allow_synthetic, allow_unverified=args.allow_unverified).load_all(
        recursos=args.recurso, fundir=not args.sem_fusao
    )
    posprocessar_carga(
        engine_padrao
    )  # ponto de entrada próprio: ninguém mais roda o ANALYZE e os derivados depois dele
    return contagens


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()
