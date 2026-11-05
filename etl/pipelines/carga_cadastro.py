"""
Carga do cadastro e do legislativo: arquivos processados -> tabelas planas de `stg` -> fusão em `core`/`leg`.

Cada recurso é uma carga própria: abre a sua linha em `etl.execucao` (fonte, estágio `CARREGAR`, `parametros['recurso']`),
copia o arquivo para a(s) tabela(s) plana(s) de `stg` numa transação (só `COPY`: nenhuma consulta ao banco, nenhuma decisão
sobre identidade), registra os arquivos de origem em `etl.arquivo_bruto`, mede as verificações do catálogo
(`etl.utils.verificacoes`) e fecha a linha com as contagens (`lidas == gravadas + rejeitadas`, rejeitadas por motivo).

A fusão é uma execução à parte (estágio `MERGE`, fonte `PIPELINE`): numa só transação a função SQL `etl.preparar_staging`
resolve a que pessoa, partido, mandato e proposição cada registro se refere (a identidade vem de `core`/`leg`: o `uid` público
que já existe nunca muda) e as funções `etl.merge_*` projetam o resultado em `core` e `leg`. O que o arquivo traz e a fusão
rejeita (filiação sem proveniência, sessão sem proposição...) volta no resumo da fusão, com motivo.

Ordem: partidos, politicos, filiacoes, parlamentares_historicos, proposicoes, votacoes_plenario, votacoes_historico; depois a
fusão. Cada recurso só depende das tabelas planas, então um recurso pode ser recarregado sozinho sem tocar nos outros. Os
mandatos de presidentes, deputados e senadores saem dos mesmos arquivos de `politicos`.
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
from etl.pipelines import planas_cadastro, planas_proposicoes, planas_votacoes
from etl.pipelines.staging_votos import ContagemDeVotos
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.copia import contar, transacao_de_carga
from etl.utils.execucao import Contagem, Execucao, registrar_arquivo_bruto, registrar_execucao
from etl.utils.manutencao import posprocessar_carga
from etl.utils.verificacoes import cobertura_minima, dentro_da_janela, total_confere

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
MOTIVO_VOTO = "SEM_SESSAO_POLITICO_OU_OPCAO"  # voto que a fusão não transformou em linha (sem sessão ou sem político)
MOTIVO_VOTO_NA_CARGA = "OPCAO_OU_PARLAMENTAR_INVALIDO"  # voto que já fica de fora na cópia (opção desconhecida, sem id)

RECURSOS = (
    "partidos",
    "politicos",
    "filiacoes",
    "parlamentares_historicos",
    "proposicoes",
    "votacoes_plenario",
    "votacoes_historico",
)

# Linhas por tabela plana, para o relatório da carga
TABELAS_DO_RELATORIO = (
    ("stg.curadoria_partido", "Partidos Políticos (curadoria)"),
    ("stg.curadoria_presidente", "Presidentes"),
    ("stg.camara_deputado", "Deputados"),
    ("stg.senado_senador", "Senadores"),
    ("stg.tse_filiacao", "Filiações Partidárias (arquivo)"),
    ("stg.camara_proposicao_api", "Proposições da Câmara (arquivo)"),
    ("stg.senado_proposicao_api", "Proposições do Senado (arquivo)"),
    ("stg.camara_sessao_plenario", "Sessões do Plenário da Câmara"),
    ("stg.senado_sessao_plenario", "Sessões do Plenário do Senado"),
    ("stg.historico_sessao", "Sessões Históricas"),
    ("stg.historico_voto", "Votos Históricos"),
)


# Tabelas planas que duas cargas dividem: cada uma só confere as linhas da sua origem
FILTROS_DA_CARGA = {"stg.historico_parlamentar": "origem = 'LEGISLATURAS_ANTERIORES'"}


def _contar_da_carga(cursor: Any, tabela: str) -> int:
    filtro = FILTROS_DA_CARGA.get(tabela)
    if filtro is None:
        return contar(cursor, tabela)
    cursor.execute(f"SELECT count(*) FROM {tabela} WHERE {filtro}")  # nosec B608 - constantes deste módulo
    return int(cursor.fetchone()[0])


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
        contagem.rejeitar(MOTIVO_VOTO_NA_CARGA, votos.rejeitadas)
    return contagem


@dataclass
class Estagio:
    recurso: str
    fonte: str
    arquivos: Sequence[str]  # nomes (ou prefixos, com "*") sob a pasta de dados processados
    # (cursor, execucao_id) -> (contagem, algum arquivo ignorado inteiro, tabelas planas gravadas)
    executar: Callable[[Any, Any], Tuple[Contagem, bool, Dict[str, int]]]


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
        self.contagens: Dict[str, Contagem] = {}  # a contagem de cada recurso carregado
        self.resumo_fusao: Optional[Dict[str, Any]] = None  # o resumo da fusão, se rodou

    # ------------------------------------------------------------------ banco
    def ensure_tables(self) -> None:
        """Aplica as migrações Alembic, únicas donas do schema (as tabelas de `stg` nascem delas)."""
        logger.info("Aplicando as migrações do schema no PostgreSQL...")
        from app.core.migrations import upgrade_schema

        upgrade_schema()

    # ------------------------------------------------------------------ os recursos
    def _partidos(self, cursor: Any, execucao_id: Any) -> Tuple[Contagem, bool, Dict[str, int]]:
        tabelas = planas_cadastro.gravar_planas(cursor, self.data_dir, execucao_id, "partidos")
        n = tabelas["stg.curadoria_partido"]
        return Contagem(lidas=n, gravadas=n), False, tabelas

    def _politicos(self, cursor: Any, execucao_id: Any) -> Tuple[Contagem, bool, Dict[str, int]]:
        tabelas = planas_cadastro.gravar_planas(cursor, self.data_dir, execucao_id, "politicos")
        n = tabelas["stg.curadoria_presidente"] + tabelas["stg.camara_deputado"] + tabelas["stg.senado_senador"]
        return Contagem(lidas=n, gravadas=n), False, tabelas

    def _filiacoes(self, cursor: Any, execucao_id: Any) -> Tuple[Contagem, bool, Dict[str, int]]:
        tabelas = planas_cadastro.gravar_planas(cursor, self.data_dir, execucao_id, "filiacoes")
        n = tabelas.get("stg.tse_filiacao", 0)
        return Contagem(lidas=n, gravadas=n), False, tabelas

    def _parlamentares_historicos(self, cursor: Any, execucao_id: Any) -> Tuple[Contagem, bool, Dict[str, int]]:
        contagem = Contagem()
        n = planas_votacoes.gravar_planas_parlamentares_anteriores(cursor, self.data_dir, execucao_id, contagem)
        return contagem, False, {"stg.historico_parlamentar": n}

    def _proposicoes(self, cursor: Any, execucao_id: Any) -> Tuple[Contagem, bool, Dict[str, int]]:
        contagem = planas_proposicoes.gravar_planas_proposicoes(
            cursor, self.data_dir, execucao_id, self.allow_unverified
        )
        return contagem, False, {"stg.camara_proposicao_api": 0, "stg.senado_proposicao_api": 0}

    def _votacoes_plenario(self, cursor: Any, execucao_id: Any) -> Tuple[Contagem, bool, Dict[str, int]]:
        votos = planas_votacoes.gravar_planas_plenario(cursor, self.data_dir, execucao_id)
        return contagem_de_votos(votos), votos.arquivos_ignorados > 0, {}

    def _votacoes_historico(self, cursor: Any, execucao_id: Any) -> Tuple[Contagem, bool, Dict[str, int]]:
        votos = planas_votacoes.gravar_planas_historico(cursor, self.data_dir, execucao_id)
        return contagem_de_votos(votos), votos.arquivos_ignorados > 0, {}

    def _estagios(self) -> Dict[str, Estagio]:
        return {
            e.recurso: e
            for e in (
                Estagio(
                    "partidos",
                    "CURADORIA",
                    ["deputados_camara.json", "senadores_senado.json", "filiacoes_partidarias.json"],
                    self._partidos,
                ),
                Estagio(
                    "politicos",
                    "CAMARA_API",
                    ["presidentes_historico.json", "deputados_camara.json", "senadores_senado.json"],
                    self._politicos,
                ),
                Estagio("filiacoes", "TSE", ["filiacoes_partidarias.json"], self._filiacoes),
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
                contagem, ignorado, enviadas = estagio.executar(cursor, execucao.id)
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
                gravadas = {tabela: _contar_da_carga(cursor, tabela) for tabela in enviadas}
            execucao.aplicar(contagem)
            self.contagens[estagio.recurso] = contagem
            execucao.com_alerta = ignorado  # arquivo pulado inteiro: os votos dele não foram contados
            for tabela, esperado in enviadas.items():
                if esperado:  # tabela cujo total o carregador conhece: o COPY entregou tudo?
                    execucao.verificar(total_confere(f"{tabela.split('.')[-1]}_copiada", esperado, gravadas[tabela]))
            logger.info("   (%s levou %.1f s)", estagio.recurso, time.monotonic() - inicio)
        return contagem

    def load_all(
        self, recursos: Optional[Sequence[str]] = None, fundir: bool = True, migrar: bool = True
    ) -> Dict[str, int]:
        """
        Carrega os recursos pedidos (todos, por padrão), nesta ordem, e funde o staging em `core`/`leg`. Devolve a contagem de
        linhas de cada tabela plana. `migrar=False` pula as migrações (o cron diário não migra o schema).
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
        Prepara e funde o staging em `core`/`leg` (execução `MERGE` da fonte `PIPELINE`). A carga das planas já foi confirmada
        e fica; mas a fusão que falha é relançada, para a etapa aparecer como FALHOU no resumo da esteira em vez de OK com
        `core` e `leg` sem a carga nova.
        """
        from app.services.staging_merge import merge_staging

        with (
            registrar_execucao(self.engine, "PIPELINE", "MERGE", {"recurso": "cadastro_e_legislativo"}) as execucao,
            SessionLocal() as session,
        ):
            try:
                resumo = self.resumo_fusao = merge_staging(
                    session, allow_synthetic=self.allow_synthetic, allow_unverified=self.allow_unverified
                )
            except Exception as exc:
                session.rollback()
                logger.error("Fusão staging -> core/leg falhou: %s", exc)  # o trace sai uma vez só, em quem chamou
                raise
            rejeitos = dict(resumo.get("preparo", {}).get("rejeitos", {}))
            rejeitados_na_fusao = int(resumo.get("rejeitos") or 0)
            gravadas = _soma_inteiros({k: v for k, v in resumo.items() if k not in ("preparo", "rejeitos")})
            execucao.lidas = gravadas + rejeitados_na_fusao + sum(rejeitos.values())
            execucao.gravadas = gravadas
            execucao.rejeitadas = rejeitados_na_fusao + sum(rejeitos.values())
            motivos = {motivo: n for motivo, n in rejeitos.items() if n}
            if rejeitados_na_fusao:
                motivos["REJEITADO_NA_FUSAO"] = rejeitados_na_fusao
            execucao.motivos = motivos
            self._verificar_fusao(session, execucao)
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

    @staticmethod
    def _verificar_fusao(session: Any, execucao: Execucao) -> None:
        """Verificações sobre o que a fusão gravou em `core`/`leg` (a partir da janela de dados de 1995, e cobertura)."""
        legado = "(SELECT id FROM etl.fonte WHERE codigo = 'LEGADO')"
        datas = session.execute(
            text(f"SELECT inicio FROM core.mandato WHERE fonte_id = {legado} AND condicao <> 'NOMEADO'")  # nosec B608
        ).scalars()
        execucao.verificar(dentro_da_janela("mandatos_a_partir_de_1995", datas))
        datas = session.execute(
            text(f"SELECT data_apresentacao FROM leg.proposicao WHERE fonte_id = {legado}")  # nosec B608
        ).scalars()
        execucao.verificar(dentro_da_janela("proposicoes_a_partir_de_1995", datas))
        for nome, tabela, coluna, tipo in (
            ("deputados_da_fonte_com_pessoa", "stg.camara_deputado", "camara_id", "CAMARA_ID"),
            ("senadores_da_fonte_com_pessoa", "stg.senado_senador", "senado_id", "SENADO_ID"),
        ):
            total, achados = session.execute(
                text(
                    f"SELECT count(*), count(i.id) FROM {tabela} f LEFT JOIN core.pessoa_identificador i "  # nosec B608
                    f"ON i.tipo = '{tipo}' AND i.valor = f.{coluna}::text"
                )
            ).one()
            execucao.verificar(cobertura_minima(nome, int(achados), int(total)))

    # ------------------------------------------------------------------ relatórios
    @staticmethod
    def _get_table_counts(cursor: Any) -> Dict[str, int]:
        """Consulta e retorna a quantidade de linhas em cada tabela plana carregada."""
        return {rotulo: contar(cursor, tabela) for tabela, rotulo in TABELAS_DO_RELATORIO}

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
