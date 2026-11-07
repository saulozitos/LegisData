"""
A carga completa do cadastro e do legislativo, na ordem em que um recurso depende do outro:

partidos -> pessoas (e mandatos) -> camara_historico -> filiacoes (derivadas dos mandatos) -> camara_lote -> proposicoes -> votacoes

Cada recurso é uma execução própria (`etl.execucao`, estágio `CARREGAR`, `parametros['recurso']`) numa transação própria:
falhar em um não desfaz os anteriores, e rodar de novo é seguro (tudo é `INSERT ... ON CONFLICT` pela chave natural).
"""

import argparse
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from etl.carga import camara, filiacoes, partidos, pessoas, proposicoes, votacoes
from etl.carga.base import Resultado, rodar
from etl.config import PROCESSED_DATA_DIR
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.execucao import Execucao, registrar_arquivo_bruto
from etl.utils.manutencao import posprocessar_carga
from etl.utils.verificacoes import Verificacao, cobertura_minima, dentro_da_janela

ensure_backend_on_path()

from app.core.database import engine as engine_padrao  # noqa: E402

logger = logging.getLogger("Carga")

RECURSOS = ("partidos", "pessoas", "camara_historico", "filiacoes", "camara_lote", "proposicoes", "votacoes")
ARQUIVOS = {
    "pessoas": (
        "presidentes_historico.json",
        "deputados_camara.json",
        "senadores_senado.json",
        pessoas.ARQUIVO_ANTERIORES,
    ),
    "proposicoes": ("proposicoes_2023.json", "proposicoes_senado.json"),
    "votacoes": (
        "sessoes_votacao_2023.json",
        "votos_nominais_2023.json",
        "sessoes_votacao_senado.json",
        "votos_nominais_senado.json",
        "votacoes/*.json.gz",
    ),
}
FONTES = {
    "partidos": "CURADORIA",
    "pessoas": "CAMARA_API",
    "filiacoes": "CAMARA_API",
    "camara_historico": "CAMARA_API",
    "camara_lote": "CAMARA_CSV",
    "proposicoes": "CAMARA_API",
    "votacoes": "CAMARA_API",
}


def _sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def _relativo(caminho: Path) -> str:
    raiz = Path(__file__).resolve().parents[2]
    try:
        return caminho.resolve().relative_to(raiz).as_posix()
    except ValueError:
        return caminho.name


def registrar_origem(cursor: Any, execucao: Execucao, fonte: str, caminhos: Iterable[Path]) -> None:
    for caminho in caminhos:
        if caminho.is_file():
            registrar_arquivo_bruto(
                cursor,
                fonte,
                f"arquivo://{_relativo(caminho)}",
                _sha256(caminho),
                caminho.stat().st_size,
                _relativo(caminho),
                execucao.id,
            )


def _caminhos(data_dir: Path, nomes: Sequence[str]) -> List[Path]:
    achados: List[Path] = []
    for nome in nomes:
        achados += sorted(data_dir.glob(nome)) if "*" in nome else [data_dir / nome]
    return achados


class Carga:
    def __init__(
        self,
        engine: Any = None,
        data_dir: Path = PROCESSED_DATA_DIR,
        historico_dir: Optional[Path] = None,
        lote_arquivos: Optional[Sequence[Any]] = None,
        allow_synthetic: bool = False,
        allow_unverified: bool = False,
        votacoes_ano_inicio: Optional[int] = None,
    ):
        self.engine = engine or engine_padrao
        self.data_dir = Path(data_dir)
        self.historico_dir = Path(historico_dir) if historico_dir else None
        self.lote_arquivos = list(lote_arquivos or [])
        self.allow_synthetic = allow_synthetic
        self.allow_unverified = allow_unverified
        self.votacoes_ano_inicio = (
            votacoes_ano_inicio  # carga incremental: pula os arquivos anuais anteriores a este ano
        )
        self.resultados: Dict[str, Resultado] = {}
        self._lote: Optional[pessoas.Lote] = None

    # ------------------------------------------------------------------ pessoas
    def lote(self) -> pessoas.Lote:
        """Pessoas e mandatos de todos os arquivos (a fonte atual primeiro, depois os ex-parlamentares)."""
        if self._lote is None:
            lote = pessoas.Lote()
            pessoas.ler_deputados(lote, self.data_dir)
            pessoas.ler_senadores(lote, self.data_dir)
            pessoas.ler_presidentes(lote, self.data_dir)
            pessoas.ler_cpfs(lote, self.data_dir)
            votantes = votacoes.ler_parlamentares_dos_arquivos(lote, self.data_dir, self.votacoes_ano_inicio)
            pessoas.ler_anteriores(lote, self.data_dir, votantes)
            pessoas.ler_senadores_basicos(lote, self.data_dir)
            self._lote = lote
        return self._lote

    # ------------------------------------------------------------------ recursos
    def _partidos(self, cursor: Any, execucao: Execucao) -> Resultado:
        siglas = set(partidos.siglas_das_fontes(self.data_dir)) | self.lote().siglas
        return partidos.carregar_partidos(cursor, siglas)

    def _pessoas(self, cursor: Any, execucao: Execucao) -> Resultado:
        registrar_origem(cursor, execucao, "CAMARA_API", _caminhos(self.data_dir, ARQUIVOS["pessoas"]))
        resultado = pessoas.gravar_lote(cursor, self.lote())
        cursor.execute(
            "SELECT inicio FROM core.mandato WHERE condicao <> 'NOMEADO' AND fonte_id IN "
            "(SELECT id FROM etl.fonte WHERE codigo IN ('CAMARA_API', 'SENADO_API', 'CURADORIA'))"
        )
        execucao.verificar(dentro_da_janela("mandatos_a_partir_de_1995", (linha[0] for linha in cursor.fetchall())))
        for nome, tipo, total in (
            (
                "deputados_da_fonte_com_pessoa",
                "CAMARA_ID",
                len([p for p in self.lote().pessoas if p[0] == "CAMARA_ID"]),
            ),
            (
                "senadores_da_fonte_com_pessoa",
                "SENADO_ID",
                len([p for p in self.lote().pessoas if p[0] == "SENADO_ID"]),
            ),
        ):
            cursor.execute("SELECT count(*) FROM core.pessoa_identificador WHERE tipo = %s", (tipo,))
            execucao.verificar(cobertura_minima(nome, int(cursor.fetchone()[0]), total))
        return resultado

    def _filiacoes(self, cursor: Any, execucao: Execucao) -> Resultado:
        return filiacoes.derivar_filiacoes(cursor)

    def _camara_historico(self, cursor: Any, execucao: Execucao) -> Resultado:
        if self.historico_dir is None or not (self.historico_dir / "_legislaturas.json").is_file():
            raise FileNotFoundError("histórico da Câmara não baixado (raw/camara_historico/_legislaturas.json)")
        return camara.carregar_historico(cursor, self.historico_dir)

    def _camara_lote(self, cursor: Any, execucao: Execucao) -> Resultado:
        for arquivo in sorted(self.lote_arquivos, key=lambda a: (a.recurso, a.ano)):
            registrar_arquivo_bruto(
                cursor, "CAMARA_CSV", arquivo.url, arquivo.sha256, arquivo.bytes, str(arquivo.caminho), execucao.id
            )
        propostas = [a.caminho for a in sorted(self.lote_arquivos, key=lambda a: a.ano) if a.recurso == "proposicoes"]
        autores = [
            a.caminho for a in sorted(self.lote_arquivos, key=lambda a: a.ano) if a.recurso == "proposicoesAutores"
        ]
        resultado = camara.carregar_lote(cursor, propostas, autores, execucao.id)
        # fora do escopo (tipo sem peso na metodologia) é esperado; qualquer outro motivo de rejeição reprova a cobertura
        rejeitadas = {m: n for m, n in resultado.contagem.motivos.items() if m != "TIPO_FORA_DO_ESCOPO"}
        execucao.verificar(
            Verificacao(
                "camara_bulk_cobertura",
                not rejeitadas,
                {
                    "proposicoes_lidas": resultado.extras["proposicoes_lidas"],
                    "fora_de_escopo_por_tipo": resultado.extras["fora_de_escopo_por_tipo"],
                    "rejeitadas": rejeitadas,
                },
            )
        )
        cursor.execute("SELECT data_apresentacao FROM leg.proposicao")
        execucao.verificar(dentro_da_janela("proposicoes_a_partir_de_1995", (linha[0] for linha in cursor.fetchall())))
        return resultado

    def _proposicoes(self, cursor: Any, execucao: Execucao) -> Resultado:
        registrar_origem(cursor, execucao, "CAMARA_API", _caminhos(self.data_dir, ARQUIVOS["proposicoes"]))
        resultado = proposicoes.carregar_proposicoes(cursor, self.data_dir, self.allow_unverified)
        return resultado

    def _votacoes(self, cursor: Any, execucao: Execucao) -> Resultado:
        registrar_origem(cursor, execucao, "CAMARA_API", _caminhos(self.data_dir, ARQUIVOS["votacoes"]))
        return votacoes.carregar_votacoes(cursor, self.data_dir, self.votacoes_ano_inicio)

    # ------------------------------------------------------------------ execução
    def carregar(self, recursos: Optional[Sequence[str]] = None) -> Dict[str, Resultado]:
        pedidos = list(recursos or RECURSOS)
        desconhecidos = [r for r in pedidos if r not in RECURSOS]
        if desconhecidos:
            raise ValueError(f"recurso desconhecido: {desconhecidos}; use um de {RECURSOS}")
        funcoes = {
            "partidos": self._partidos,
            "pessoas": self._pessoas,
            "filiacoes": self._filiacoes,
            "camara_historico": self._camara_historico,
            "camara_lote": self._camara_lote,
            "proposicoes": self._proposicoes,
            "votacoes": self._votacoes,
        }
        for recurso in (r for r in RECURSOS if r in pedidos):
            if recurso == "camara_lote" and not self.lote_arquivos:
                logger.info("camara_lote: nenhum CSV informado, recurso pulado.")
                continue
            if recurso == "camara_historico" and self.historico_dir is None:
                logger.info("camara_historico: pasta do histórico não informada, recurso pulado.")
                continue
            self.resultados[recurso] = rodar(
                self.engine,
                FONTES[recurso],
                recurso,
                funcoes[recurso],
                {"allow_synthetic": self.allow_synthetic, "allow_unverified": self.allow_unverified},
            )
        return self.resultados


def main(argv: Optional[List[str]] = None) -> Dict[str, Resultado]:
    parser = argparse.ArgumentParser(description="Carga do cadastro e do legislativo no PostgreSQL.")
    parser.add_argument("--allow-synthetic", action="store_true", help="Carrega dados sintéticos de demonstração.")
    parser.add_argument("--allow-unverified", action="store_true", help="Carrega dados sem proveniência registrada.")
    parser.add_argument("--recurso", action="append", choices=RECURSOS, help="Carrega só este recurso (repetível).")
    parser.add_argument("--historico-dir", type=Path, help="Pasta com o histórico por deputado (raw/camara_historico).")
    args = parser.parse_args(argv)
    carga = Carga(
        allow_synthetic=args.allow_synthetic, allow_unverified=args.allow_unverified, historico_dir=args.historico_dir
    )
    resultados = carga.carregar(args.recurso)
    posprocessar_carga(engine_padrao)
    return resultados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()
