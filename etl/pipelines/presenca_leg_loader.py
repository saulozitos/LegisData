"""
Carga de presença, falta e justificativa em `leg.presenca` (Câmara e Senado, de 1995 em diante).

Origens, da mais confiável para a menos:
- Portal da Câmara (2020 em diante): presença, ausência e justificativa oficiais por dia (`CAMARA_PORTAL`);
- Votações nominais do Senado (1995 em diante): presença derivada do voto, com o código de justificativa (`SENADO_API`);
- Arquivos de presença em eventos da Câmara (antes de 2020, `CAMARA_CSV`): trazem só a presença. A falta é
  INFERIDA (`AUSENCIA_INFERIDA`) quando o deputado estava em exercício (situação EXERCICIO ou SUPLENCIA) num dia com
  sessão deliberativa do plenário e não consta em nenhuma delas. Sem justificativa e sem mistura com a falta oficial.
  A inferência começa em 2003-02-03, quando passam a existir as situações de exercício; antes disso só há presença.

Uma sessão deliberativa só conta como realizada quando tem ao menos `QUORUM_ABERTURA` presentes (um décimo da Casa,
mínimo regimental para abrir a sessão), o que descarta sessões convocadas e não realizadas.

O partido de cada dia é resolvido ao final por `etl.resolver_partido_presenca()` (votação, mandato, filiação ou
presença mais próxima), com a origem em `partido_origem`.

Idempotente: cada origem apaga e regrava só as próprias linhas.
"""

import csv
import io
import logging
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.extractors.camara_presenca_eventos_extractor import caminho_do_arquivo
from etl.extractors.presenca_extractor import carregar_dias
from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy.engine import Engine  # noqa: E402

logger = logging.getLogger("PresencaLegLoader")

QUORUM_ABERTURA = 52
PORTAL_DESDE = date(2020, 1, 1)
INFERENCIA_DESDE = date(2003, 2, 3)
INICIO_JANELA = date(1995, 1, 1)


def sessoes_deliberativas(raw_dir: Path, ano: int) -> Dict[int, date]:
    """Eventos do ano que são sessão deliberativa do plenário: {id do evento: data}."""
    caminho = caminho_do_arquivo(raw_dir, "eventos", ano)
    if not caminho.exists():
        return {}
    saida: Dict[int, date] = {}
    with open(caminho, encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo, delimiter=";"):
            tipo = (linha.get("descricaoTipo") or "").strip()
            local = (linha.get("localCamara.nome") or "").strip()
            if not tipo.startswith("Sessão Deliberativa"):
                continue
            if local and "Plenário da Câmara" not in local:
                continue
            saida[int(linha["id"])] = datetime.fromisoformat(linha["dataHoraInicio"]).date()
    return saida


def presencas_por_dia(raw_dir: Path, ano: int) -> Tuple[Set[Tuple[int, date]], Set[date]]:
    """Presenças (deputado, dia) e dias com sessão deliberativa realizada, a partir dos arquivos do ano."""
    sessoes = sessoes_deliberativas(raw_dir, ano)
    caminho = caminho_do_arquivo(raw_dir, "eventosPresencaDeputados", ano)
    if not sessoes or not caminho.exists():
        return set(), set()
    por_sessao: Dict[int, Set[int]] = defaultdict(set)
    with open(caminho, encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo, delimiter=";"):
            evento = int(linha["idEvento"])
            if evento in sessoes:
                por_sessao[evento].add(int(linha["idDeputado"]))
    presencas: Set[Tuple[int, date]] = set()
    dias: Set[date] = set()
    for evento, deputados in por_sessao.items():
        if len(deputados) < QUORUM_ABERTURA:
            continue
        dia = sessoes[evento]
        dias.add(dia)
        presencas.update((deputado, dia) for deputado in deputados)
    return presencas, dias


def _copiar(cursor, tabela: str, colunas: str, linhas: Iterable[Iterable[Any]]) -> int:
    saida = io.StringIO()
    escritor = csv.writer(saida)
    n = 0
    for linha in linhas:
        escritor.writerow(["" if v is None else v for v in linha])
        n += 1
    saida.seek(0)
    cursor.copy_expert(f"COPY {tabela} ({colunas}) FROM STDIN WITH (FORMAT csv, NULL '')", saida)
    return n


_MANDATO_LATERAL = """
    LEFT JOIN LATERAL (
        SELECT m.id FROM core.mandato m
        WHERE m.pessoa_id = pe.id AND m.cargo_id = {cargo} AND m.inicio <= s.data AND (m.fim IS NULL OR m.fim >= s.data)
        ORDER BY m.inicio DESC LIMIT 1
    ) mm ON true
"""


def _garantir_pessoas(cursor, tipo: str, fonte_codigo: str, nomes: Dict[int, str]) -> int:
    """Cria pessoa mínima (nome e identificador oficial, nunca CPF) para parlamentar sem cadastro."""
    cursor.execute("SELECT valor FROM core.pessoa_identificador WHERE tipo = %s", (tipo,))
    existentes = {int(r[0]) for r in cursor.fetchall()}
    criados = 0
    cursor.execute("SELECT id FROM etl.fonte WHERE codigo = %s", (fonte_codigo,))
    fonte_id = cursor.fetchone()[0]
    for codigo, nome in sorted(nomes.items()):
        if codigo in existentes:
            continue
        cursor.execute(
            "INSERT INTO core.pessoa (nome_exibicao) VALUES (%s) RETURNING id", ((nome or f"Parlamentar {codigo}"),)
        )
        pessoa_id = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor) VALUES (%s, %s, %s, %s)",
            (pessoa_id, fonte_id, tipo, str(codigo)),
        )
        criados += 1
    return criados


def _carregar_oficial(
    cursor,
    casa_codigo: str,
    cargo_codigo: str,
    tipo_id: str,
    fonte_codigo: str,
    linhas: List[List[Any]],
    desde: date,
    partidos: Optional[List[List[Any]]] = None,
) -> Dict[str, int]:
    """Carrega [parlamentar_id, 'AAAA-MM-DD', status, justificativa] de uma fonte com falta e justificativa."""
    cursor.execute("CREATE TEMP TABLE _of (codigo int, data date, tipo text, justificativa text) ON COMMIT DROP")
    selecionadas = [(int(c), d, s, j) for c, d, s, j in linhas if date.fromisoformat(d) >= max(desde, INICIO_JANELA)]
    _copiar(cursor, "_of", "codigo, data, tipo, justificativa", selecionadas)
    cursor.execute("CREATE TEMP TABLE _pt (codigo int, desde date, sigla text) ON COMMIT DROP")
    _copiar(cursor, "_pt", "codigo, desde, sigla", [(int(c), d, g) for c, d, g in (partidos or [])])
    cursor.execute("SELECT id FROM ref.casa_legislativa WHERE codigo = %s", (casa_codigo,))
    casa_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM ref.cargo WHERE codigo = %s", (cargo_codigo,))
    cargo_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM etl.fonte WHERE codigo = %s", (fonte_codigo,))
    fonte_id = cursor.fetchone()[0]
    cursor.execute("DELETE FROM leg.presenca WHERE casa_id = %s AND fonte_id = %s", (casa_id, fonte_id))
    apagados = cursor.rowcount
    cursor.execute(
        f"""
        INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo, mandato_id, justificativa, fonte_id,
                                  partido_id)
        SELECT DISTINCT ON (pe.id, s.data) pe.id, %s, s.data, s.tipo, mm.id, s.justificativa, %s, pa.id
        FROM _of s
        JOIN core.pessoa_identificador i ON i.tipo = %s AND i.valor = s.codigo::text
        JOIN core.pessoa pe ON pe.id = i.pessoa_id
        {_MANDATO_LATERAL.format(cargo="%s")}
        LEFT JOIN LATERAL (
            SELECT CASE WHEN lower(sigla) = 's/partido' THEN 'S.PART.' WHEN lower(sigla) = 'sem registro' THEN NULL
                        ELSE sigla END AS sigla
            FROM _pt t WHERE t.codigo = s.codigo AND t.desde <= s.data ORDER BY t.desde DESC LIMIT 1
        ) pt ON true
        LEFT JOIN LATERAL (
            SELECT id FROM core.partido x WHERE x.sigla_normalizada = ref.normalizar_texto(pt.sigla)
            ORDER BY x.catalogo DESC, x.id LIMIT 1
        ) pa ON true
        ORDER BY pe.id, s.data
        ON CONFLICT (pessoa_id, casa_id, data_sessao) DO UPDATE
            SET tipo_codigo = EXCLUDED.tipo_codigo, justificativa = EXCLUDED.justificativa,
                mandato_id = EXCLUDED.mandato_id, fonte_id = EXCLUDED.fonte_id, partido_id = EXCLUDED.partido_id
        """,
        (casa_id, fonte_id, tipo_id, cargo_id),
    )
    inseridos = cursor.rowcount
    cursor.execute("DROP TABLE _of")
    cursor.execute("DROP TABLE _pt")
    return {"apagados": apagados, "inseridos": inseridos, "lidos": len(selecionadas)}


def _nome_deputado_api(camara_id: int) -> str:
    """Nome do deputado na API de dados abertos; vazio se indisponível (a pessoa é criada com nome genérico)."""
    from etl.utils.http_client import HttpClient

    try:
        dados = HttpClient().get_json(f"https://dadosabertos.camara.leg.br/api/v2/deputados/{camara_id}")["dados"]
        status = dados.get("ultimoStatus") or {}
        return status.get("nomeEleitoral") or status.get("nome") or dados.get("nomeCivil") or ""
    except Exception as exc:  # noqa: BLE001 - nome é só rótulo; a presença não depende dele
        logger.warning("Nome do deputado %s indisponível: %s", camara_id, exc)
        return ""


def _carregar_camara_eventos(cursor, raw_dir: Path, anos: Iterable[int]) -> Dict[str, int]:
    presencas: Set[Tuple[int, date]] = set()
    dias: Set[date] = set()
    for ano in anos:
        p, d = presencas_por_dia(raw_dir, ano)
        presencas |= {x for x in p if x[1] < PORTAL_DESDE}
        dias |= {x for x in d if x < PORTAL_DESDE}
    cursor.execute("CREATE TEMP TABLE _cp (codigo int, data date) ON COMMIT DROP")
    cursor.execute("CREATE TEMP TABLE _cd (data date) ON COMMIT DROP")
    _copiar(cursor, "_cp", "codigo, data", sorted(presencas))
    _copiar(cursor, "_cd", "data", ((d,) for d in sorted(dias)))
    cursor.execute("SELECT valor FROM core.pessoa_identificador WHERE tipo = 'CAMARA_ID'")
    conhecidos = {int(r[0]) for r in cursor.fetchall()}
    desconhecidos = {codigo for codigo, _ in presencas} - conhecidos
    criados = _garantir_pessoas(cursor, "CAMARA_ID", "CAMARA_API", {c: _nome_deputado_api(c) for c in desconhecidos})
    cursor.execute("SELECT id FROM ref.casa_legislativa WHERE codigo = 'CAMARA_DOS_DEPUTADOS'")
    casa_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM ref.cargo WHERE codigo = 'DEPUTADO_FEDERAL'")
    cargo_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_CSV'")
    fonte_id = cursor.fetchone()[0]
    cursor.execute(
        "DELETE FROM leg.presenca WHERE casa_id = %s AND fonte_id = %s AND data_sessao < %s",
        (casa_id, fonte_id, PORTAL_DESDE),
    )
    apagados = cursor.rowcount
    cursor.execute(
        f"""
        INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo, mandato_id, fonte_id)
        SELECT DISTINCT ON (pe.id, s.data) pe.id, %s, s.data, 'PRESENTE', mm.id, %s
        FROM _cp s
        JOIN core.pessoa_identificador i ON i.tipo = 'CAMARA_ID' AND i.valor = s.codigo::text
        JOIN core.pessoa pe ON pe.id = i.pessoa_id
        {_MANDATO_LATERAL.format(cargo="%s")}
        ORDER BY pe.id, s.data
        ON CONFLICT (pessoa_id, casa_id, data_sessao) DO NOTHING
        """,
        (casa_id, fonte_id, cargo_id),
    )
    presentes = cursor.rowcount
    cursor.execute(
        """
        INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo, mandato_id, fonte_id)
        SELECT DISTINCT ON (m.pessoa_id, d.data) m.pessoa_id, %s, d.data, 'AUSENCIA_INFERIDA', m.id, %s
        FROM _cd d
        JOIN core.mandato_situacao ms ON ms.periodo @> d.data AND ms.situacao IN ('EXERCICIO', 'SUPLENCIA')
        JOIN core.mandato m ON m.id = ms.mandato_id AND m.cargo_id = %s
        WHERE d.data >= %s
        ORDER BY m.pessoa_id, d.data, m.inicio DESC
        ON CONFLICT (pessoa_id, casa_id, data_sessao) DO NOTHING
        """,
        (casa_id, fonte_id, cargo_id, INFERENCIA_DESDE),
    )
    return {
        "deputados_criados": criados,
        "dias_com_sessao": len(dias),
        "presencas_lidas": len(presencas),
        "apagados": apagados,
        "presencas": presentes,
        "faltas_inferidas": cursor.rowcount,
    }


def carregar(
    engine: Engine,
    raw_dir: Optional[Path] = None,
    processed_dir: Path = PROCESSED_DATA_DIR,
    anos_eventos: Optional[Iterable[int]] = None,
) -> Dict[str, Any]:
    raw_dir = Path(raw_dir) if raw_dir else RAW_DATA_DIR / "camara_presenca_eventos"
    anos = list(anos_eventos) if anos_eventos is not None else list(range(INICIO_JANELA.year, PORTAL_DESDE.year + 1))
    corpo = carregar_dias(processed_dir)
    resumo: Dict[str, Any] = {}
    conexao = engine.raw_connection()
    try:
        cursor = conexao.cursor()
        if anos:  # sem anos, a história anterior a 2020 (já fechada) é preservada
            resumo["camara_eventos"] = _carregar_camara_eventos(cursor, raw_dir, anos)
        if corpo:
            nomes_sen = _nomes_senado(processed_dir)
            resumo["senadores_criados"] = _garantir_pessoas(cursor, "SENADO_ID", "SENADO_API", nomes_sen)
            resumo["camara_portal"] = _carregar_oficial(
                cursor, "CAMARA_DOS_DEPUTADOS", "DEPUTADO_FEDERAL", "CAMARA_ID", "CAMARA_PORTAL",
                corpo.get("camara") or [], PORTAL_DESDE,
            )  # fmt: skip
            resumo["senado"] = _carregar_oficial(
                cursor, "SENADO_FEDERAL", "SENADOR", "SENADO_ID", "SENADO_API", corpo.get("senado") or [], INICIO_JANELA,
                corpo.get("senado_partidos") or [],
            )  # fmt: skip
        cursor.execute("SELECT etl.resolver_partido_presenca()")
        resumo["partido_presenca"] = cursor.fetchone()[0]
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    logger.info("Presença carregada em leg.presenca: %s", resumo)
    return resumo


def _nomes_senado(processed_dir: Path) -> Dict[int, str]:
    import json

    from etl.extractors.presenca_extractor import ARQ_RESUMO

    resumo = json.loads((Path(processed_dir) / ARQ_RESUMO).read_text(encoding="utf-8"))
    return {
        int(r["parlamentar_id"]): r.get("nome") or "" for r in resumo.get("resumos", []) if r.get("casa") == "SENADO"
    }
