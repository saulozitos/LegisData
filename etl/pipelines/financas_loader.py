"""
Carga do schema `fin` (finanças e fiscalização) a partir dos arquivos oficiais já extraídos em `etl/data/processed`.

Seis cargas independentes, todas idempotentes e ligadas a `core.pessoa` pelo `ResolvedorDePessoas`:
- CEAP (`despesas_ceap_2019_2026.json`): total por pessoa, ano e tipo; maiores fornecedores e quantidade de notas;
- emendas (`emendas_parlamentares_2019_2026.json`): uma linha por emenda/localidade/função, atualizada pela chave
  natural (o `uid` público não muda entre cargas); o que saiu da fonte sai da tabela;
- remuneração (`remuneracao_parlamentares.json`), patrimônio, doações de campanha e situação de registro do TSE.

Só entram registros com proveniência oficial (`fonte` presente e `is_synthetic` falso). Um arquivo ausente, sem nenhum
registro utilizável ou que reduziria a tabela a menos da metade (arquivo truncado, resolvedor degradado) nunca apaga o
que já está no banco. Cada carga é uma transação: ou grava inteira ou não grava.
"""

import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from etl.config import PROCESSED_DATA_DIR
from etl.pipelines.loader_helpers import (
    LIMITE_CEAP,
    LIMITE_EMENDA,
    chave_da_prestacao,
    fornecedores_do_parlamentar,
    inteiro,
    ler_ceap,
    ler_certidao,
    ler_doacoes,
    ler_emenda,
    ler_patrimonio,
    ler_registros_da_remuneracao,
    ler_remuneracao,
    manter_a_melhor,
    resumos_completos,
    soma_na_faixa,
    somar_linhas,
    tipo_do_autor,
    uf_da_localidade,
)
from etl.pipelines.pessoa_resolver import ResolvedorDePessoas
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_json

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Connection, Engine  # noqa: E402

logger = logging.getLogger("FinancasLoader")

CEAP_ARQUIVO = "despesas_ceap_2019_2026.json"
EMENDAS_ARQUIVO = "emendas_parlamentares_2019_2026.json"
REMUNERACAO_ARQUIVO = "remuneracao_parlamentares.json"
PATRIMONIO_ARQUIVO = "declaracoes_patrimonio.json"
DOACOES_ARQUIVO = "tse_doacoes_campanha.json"
CERTIDOES_ARQUIVO = "certidoes_tse.json"

FONTE_CEAP_CAMARA = "CAMARA_CSV"
FONTE_CEAP_SENADO = "SENADO_API"
FONTE_EMENDAS = "PORTAL_TRANSPARENCIA"
FONTE_REMUNERACAO = "CAMARA_PORTAL"
FONTE_TSE = "TSE"

LOTE = 5000

# Proteção contra encolhimento: se a tabela já tem ao menos MINIMO_PARA_GUARDA linhas e a carga traria menos que
# FRACAO_MINIMA delas, a carga aborta sem alterar o banco. LEGISDATA_ACEITAR_ENCOLHIMENTO=1 libera uma redução legítima.
MINIMO_PARA_GUARDA = 10
FRACAO_MINIMA = 0.5
VARIAVEL_ACEITAR_ENCOLHIMENTO = "LEGISDATA_ACEITAR_ENCOLHIMENTO"
# SQL literal por tabela (nada de montar o nome da tabela na consulta). A contagem alimenta a guarda contra encolhimento
# de todas as tabelas; o DELETE total existe só para as que a carga substitui por inteiro. `fin.emenda` fica de fora de
# propósito: ela faz upsert pela chave natural e o `uid` público não pode mudar entre cargas.
_SQL_CONTAGEM = {
    "fin.despesa_cota": "SELECT count(*) FROM fin.despesa_cota",
    "fin.emenda": "SELECT count(*) FROM fin.emenda",
    "fin.remuneracao": "SELECT count(*) FROM fin.remuneracao",
    "fin.declaracao_patrimonio": "SELECT count(*) FROM fin.declaracao_patrimonio",
    "fin.doacao_campanha": "SELECT count(*) FROM fin.doacao_campanha",
    "fin.certidao": "SELECT count(*) FROM fin.certidao",
    "fin.despesa_cota_fornecedor": "SELECT count(*) FROM fin.despesa_cota_fornecedor",
    "fin.despesa_cota_resumo": "SELECT count(*) FROM fin.despesa_cota_resumo",
}
_SQL_DELETE = {
    "fin.despesa_cota": "DELETE FROM fin.despesa_cota",
    "fin.remuneracao": "DELETE FROM fin.remuneracao",
    "fin.declaracao_patrimonio": "DELETE FROM fin.declaracao_patrimonio",
    "fin.doacao_campanha": "DELETE FROM fin.doacao_campanha",
    "fin.certidao": "DELETE FROM fin.certidao",
    "fin.despesa_cota_fornecedor": "DELETE FROM fin.despesa_cota_fornecedor",
    "fin.despesa_cota_resumo": "DELETE FROM fin.despesa_cota_resumo",
}


def _protege_contra_encolhimento(conn: Connection, tabela: str, novas: int) -> None:
    """Levanta RuntimeError (sem tocar no banco) se a carga reduziria `tabela` a menos de FRACAO_MINIMA do que existe."""
    existentes = int(conn.execute(text(_SQL_CONTAGEM[tabela])).scalar() or 0)
    if existentes < MINIMO_PARA_GUARDA or novas >= existentes * FRACAO_MINIMA:
        return
    if os.environ.get(VARIAVEL_ACEITAR_ENCOLHIMENTO) == "1":
        logger.warning(
            "%s: %d -> %d linhas (encolhimento aceito por %s).",
            tabela,
            existentes,
            novas,
            VARIAVEL_ACEITAR_ENCOLHIMENTO,
        )
        return
    raise RuntimeError(
        f"{tabela}: a carga traria {novas} linhas e o banco tem {existentes}; nada foi alterado. "
        f"Se a redução é legítima, rode de novo com {VARIAVEL_ACEITAR_ENCOLHIMENTO}=1."
    )


def _lotes(linhas: List[Dict[str, Any]]) -> Iterable[List[Dict[str, Any]]]:
    for i in range(0, len(linhas), LOTE):
        yield linhas[i : i + LOTE]


def _fontes(conn: Connection) -> Dict[str, int]:
    return {codigo: fonte_id for fonte_id, codigo in conn.execute(text("SELECT id, codigo FROM etl.fonte"))}


def _arquivo(processed_dir: Path, nome: str) -> Any:
    dados = load_json(processed_dir / nome, None)
    if dados is None:
        logger.warning("%s não encontrado; a carga foi pulada e o banco não foi alterado.", nome)
    return dados


def _inserir(conn: Connection, sql: str, linhas: List[Dict[str, Any]]) -> None:
    for lote in _lotes(linhas):
        conn.execute(text(sql), lote)


def _substituir(conn: Connection, tabelas: List[Tuple[str, str, List[Dict[str, Any]]]]) -> None:
    """
    Troca o conteúdo das tabelas `fin` dadas (tabela, INSERT, linhas): primeiro a guarda contra encolhimento de TODAS
    (nada é tocado se alguma abortar), depois DELETE e INSERT de cada uma.
    """
    for tabela, _insercao, linhas in tabelas:
        _protege_contra_encolhimento(conn, tabela, len(linhas))
    for tabela, insercao, linhas in tabelas:
        conn.execute(text(_SQL_DELETE[tabela]))
        _inserir(conn, insercao, linhas)


def _carga_simples(
    conn: Connection,
    processed_dir: Path,
    *,
    arquivo: str,
    aceita: Callable[[Any], bool],
    chave_ausente: str,
    montar: Callable[[Any, ResolvedorDePessoas, int], Tuple[List[Dict[str, Any]], Dict[str, int]]],
    fonte: str,
    rotulo: str,
    chave_total: str,
    tabela: str,
    insercao: str,
) -> Dict[str, int]:
    """
    Roteiro das cargas que trocam uma tabela inteira: lê o arquivo, monta as linhas, e só substitui a tabela se alguma
    linha serviu (arquivo ausente, de formato inválido ou sem nenhum registro utilizável nunca apaga o que já está lá).
    """
    dados = _arquivo(processed_dir, arquivo)
    if not aceita(dados):
        if dados is not None:
            logger.warning("%s com formato ou proveniência inválidos; carga pulada.", arquivo)
        return {chave_ausente: 1}
    linhas, contagem = montar(dados, ResolvedorDePessoas(conn), _fontes(conn)[fonte])
    if not linhas:
        logger.warning("%s sem nenhum registro utilizável (%s); o banco não foi alterado.", rotulo, contagem)
        return {**contagem, chave_total: 0}
    _substituir(conn, [(tabela, insercao, linhas)])
    return {**contagem, chave_total: len(linhas)}


# ── CEAP ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def linhas_da_ceap(
    ceap: Dict[str, Any], resolvedor: ResolvedorDePessoas, fontes: Dict[str, int]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    """Despesas, fornecedores e resumos prontos para gravar, mais a contagem do que ficou de fora."""
    despesas: List[Dict[str, Any]] = []
    fornecedores: List[Dict[str, Any]] = []
    resumos: List[Dict[str, Any]] = []
    contagem: Dict[str, int] = defaultdict(
        int,
        {
            "parlamentares": 0,
            "sem_pessoa": 0,
            "sem_identificador": 0,
            "sem_proveniencia": 0,
            "sem_detalhe_por_ano": 0,
        },
    )
    for dados in ceap.values():
        valores, motivo = ler_ceap(dados)
        if valores is None:
            contagem[str(motivo)] += 1
            continue
        pessoa = resolvedor.resolver(dados).pessoa_id
        if pessoa is None:
            contagem["sem_pessoa"] += 1
            continue
        # a origem é o identificador que o registro carrega (nenhum registro do arquivo traz os dois)
        fonte_id = fontes[FONTE_CEAP_CAMARA if dados.get("camara_id") else FONTE_CEAP_SENADO]
        contagem["parlamentares"] += 1
        despesas += [
            {"p": pessoa, "ano": ano, "tipo": tipo, "valor": valor, "f": fonte_id}
            for (ano, tipo), valor in valores.items()
        ]
        if valores:  # fornecedores e quantidade de notas só valem ao lado de um gasto que a entrada realmente somou
            fornecedores += [{"p": pessoa, "f": fonte_id, **x} for x in fornecedores_do_parlamentar(dados)]
            notas = inteiro(dados.get("total_notas"))
            # quantidade desconhecida não vira zero: a linha com `notas` None só marca a pessoa para `resumos_completos`
            resumos.append({"p": pessoa, "notas": notas if notas is not None and notas >= 0 else None, "f": fonte_id})
    return despesas, fornecedores, resumos, contagem


def carregar_ceap(conn: Connection, processed_dir: Path) -> Dict[str, int]:
    ceap = _arquivo(processed_dir, CEAP_ARQUIVO)
    if not isinstance(ceap, dict):
        return {"arquivo_ausente": 1}
    despesas, fornecedores, resumos, contagem = linhas_da_ceap(ceap, ResolvedorDePessoas(conn), _fontes(conn))
    if not despesas:
        logger.warning("CEAP sem nenhum registro utilizável (%s); o banco não foi alterado.", contagem)
        return {**contagem, "despesas": 0}
    # Duas entradas do arquivo podem resolver para a mesma pessoa (Câmara e Senado, ou variantes do nome): `somar_linhas`
    # deixa uma linha por chave em cada tabela e a guarda de encolhimento olha o tamanho final.
    despesas, repetidas = somar_linhas(despesas, ("p", "ano", "tipo"), ("valor",))
    fornecedores, _ = somar_linhas(fornecedores, ("p", "grupo"), ("valor", "notas"))
    # a soma entre fontes (Câmara + Senado) também precisa caber na coluna
    antes = len(despesas) + len(fornecedores)
    despesas = [x for x in despesas if soma_na_faixa(x["valor"], LIMITE_CEAP) is not None]
    fornecedores = [x for x in fornecedores if soma_na_faixa(x["valor"], LIMITE_CEAP) is not None]
    contagem["soma_fora_da_faixa"] = antes - len(despesas) - len(fornecedores)
    completos, resumo_incompleto = resumos_completos(resumos)
    resumos, _ = somar_linhas(completos, ("p",), ("notas",))
    if repetidas:
        logger.warning(
            "CEAP: %d linhas repetidas na mesma fonte (variantes do nome); ficou a de maior valor.", repetidas
        )
    contagem["mesma_fonte_repetida"] = repetidas
    contagem["resumo_incompleto"] = resumo_incompleto
    _substituir(
        conn,
        [
            (
                "fin.despesa_cota",
                "INSERT INTO fin.despesa_cota (pessoa_id, ano, tipo_despesa, valor_liquido, fonte_id) "
                "VALUES (:p, :ano, :tipo, :valor, :f)",
                despesas,
            ),
            (
                "fin.despesa_cota_fornecedor",
                "INSERT INTO fin.despesa_cota_fornecedor (pessoa_id, nome, cnpj, valor_total, notas, fonte_id) "
                "VALUES (:p, :nome, :cnpj, :valor, :notas, :f)",
                fornecedores,
            ),
            (
                "fin.despesa_cota_resumo",
                "INSERT INTO fin.despesa_cota_resumo (pessoa_id, total_notas, fonte_id) VALUES (:p, :notas, :f)",
                resumos,
            ),
        ],
    )
    return {**contagem, "despesas": len(despesas), "fornecedores": len(fornecedores)}


# ── Emendas ──────────────────────────────────────────────────────────────────────────────────────────────────────────
SQL_EMENDA = """
INSERT INTO fin.emenda (pessoa_id, autor_texto, autor_codigo, tipo_autor, autor_situacao, ano, codigo_emenda,
                        tipo_emenda, valor_empenhado, valor_pago, localidade_destino, uf, funcao, fonte_id)
VALUES (:p, :autor, :cod_autor, :tipo_autor, :situacao, :ano, :codigo, :tipo_emenda, :empenhado, :pago, :local,
        :uf, :funcao, :f)
ON CONFLICT (autor_texto, codigo_emenda, ano, tipo_emenda, localidade_destino, funcao) DO UPDATE SET
    pessoa_id = EXCLUDED.pessoa_id, autor_codigo = EXCLUDED.autor_codigo,
    tipo_autor = EXCLUDED.tipo_autor, autor_situacao = EXCLUDED.autor_situacao,
    valor_empenhado = EXCLUDED.valor_empenhado, valor_pago = EXCLUDED.valor_pago, uf = EXCLUDED.uf,
    fonte_id = EXCLUDED.fonte_id, atualizado_em = now()
"""


def linhas_das_emendas(
    emendas: List[Any], resolvedor: ResolvedorDePessoas, fonte_id: int
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    contagem: Dict[str, int] = defaultdict(
        int,
        {
            "IDENTIFICADO": 0,
            "NAO_CADASTRADO": 0,
            "HOMONIMO_NAO_DESAMBIGUADO": 0,
            "INSTITUCIONAL": 0,
            "sem_proveniencia": 0,
            "invalidas": 0,
            "chave_repetida": 0,
        },
    )
    unicas: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for bruta in emendas:
        lida, motivo = ler_emenda(bruta)
        if lida is None:
            contagem[str(motivo)] += 1
            continue
        autor, ano = lida["autor"], lida["ano"]
        tipo_autor = tipo_do_autor(autor, lida["tipo_emenda"])
        if tipo_autor == "INDIVIDUAL":
            resolucao = resolvedor.por_nome([autor], ano)
            situacao, pessoa = resolucao.situacao, resolucao.pessoa_id
        else:
            situacao, pessoa = "INSTITUCIONAL", None
        linha = {
            "p": pessoa,
            "autor": autor,
            "cod_autor": lida["cod_autor"],
            "tipo_autor": tipo_autor,
            "situacao": situacao,
            "ano": ano,
            "codigo": lida["codigo"],
            "tipo_emenda": lida["tipo_emenda"],
            "empenhado": lida["empenhado"],
            "pago": lida["pago"],
            "local": lida["local"],
            "uf": uf_da_localidade(lida["local"]),
            "funcao": lida["funcao"],
            "f": fonte_id,
        }
        chave = (autor, lida["codigo"], ano, lida["tipo_emenda"], lida["local"], lida["funcao"])
        if chave in unicas:  # linhas distintas da fonte com a mesma chave: somam, para o total bater com o arquivo
            contagem["chave_repetida"] += 1
            unicas[chave]["empenhado"] += lida["empenhado"]
            unicas[chave]["pago"] += lida["pago"]
        else:
            contagem[situacao] += 1
            unicas[chave] = linha
    cabem = [
        x
        for x in unicas.values()
        if soma_na_faixa(x["empenhado"], LIMITE_EMENDA) is not None
        and soma_na_faixa(x["pago"], LIMITE_EMENDA) is not None
    ]
    contagem["soma_fora_da_faixa"] = len(unicas) - len(cabem)
    return cabem, contagem


def carregar_emendas(conn: Connection, processed_dir: Path) -> Dict[str, int]:
    emendas = _arquivo(processed_dir, EMENDAS_ARQUIVO)
    if not isinstance(emendas, list):
        return {"arquivo_ausente": 1}
    linhas, contagem = linhas_das_emendas(emendas, ResolvedorDePessoas(conn), _fontes(conn)[FONTE_EMENDAS])
    if not linhas:
        logger.warning("Emendas sem nenhum registro utilizável (%s); o banco não foi alterado.", contagem)
        return {**contagem, "emendas": 0}
    _protege_contra_encolhimento(conn, "fin.emenda", len(linhas))
    inicio = conn.execute(text("SELECT now()")).scalar()  # fixo na transação: toda linha tocada recebe este instante
    _inserir(conn, SQL_EMENDA, linhas)
    removidas = conn.execute(text("DELETE FROM fin.emenda WHERE atualizado_em < :t"), {"t": inicio}).rowcount
    return {**contagem, "emendas": len(linhas), "removidas": removidas}


# ── Remuneração ──────────────────────────────────────────────────────────────────────────────────────────────────────
def linhas_da_remuneracao(
    corpo: Dict[str, Any], resolvedor: ResolvedorDePessoas, fonte_id: int
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    contagem: Dict[str, int] = defaultdict(int, {"sem_pessoa": 0, "invalidas": 0, "repetidas": 0})
    unicas: Dict[Tuple[int, int, int], Dict[str, Any]] = {}
    for registro in ler_registros_da_remuneracao(corpo)[0] or []:
        lido, motivo = ler_remuneracao(registro)
        if lido is None:
            contagem[str(motivo)] += 1
            continue
        pessoa = resolvedor.por_identificador(camara_id=registro.get("camara_id"))
        if pessoa is None:
            contagem["sem_pessoa"] += 1
            continue
        chave = (pessoa, lido["ano"], lido["mes"])
        linha = {"p": pessoa, **lido, "f": fonte_id}
        # duas folhas no mesmo mês: vale a de maior bruto (depois o maior líquido), não a do arquivo
        if manter_a_melhor(unicas, chave, linha, ("bruto", "liquido")):
            contagem["repetidas"] += 1
    return list(unicas.values()), contagem


def carregar_remuneracao(conn: Connection, processed_dir: Path) -> Dict[str, int]:
    return _carga_simples(
        conn,
        processed_dir,
        arquivo=REMUNERACAO_ARQUIVO,
        aceita=lambda dados: ler_registros_da_remuneracao(dados)[0] is not None,
        chave_ausente="arquivo_ausente_ou_sem_proveniencia",
        montar=linhas_da_remuneracao,
        fonte=FONTE_REMUNERACAO,
        rotulo="Remuneração",
        chave_total="meses",
        tabela="fin.remuneracao",
        insercao=(
            "INSERT INTO fin.remuneracao (pessoa_id, ano, mes, salario_bruto, salario_liquido, fonte_id) "
            "VALUES (:p, :ano, :mes, :bruto, :liquido, :f)"
        ),
    )


# ── TSE: patrimônio, doações e certidões ─────────────────────────────────────────────────────────────────────────────
def linhas_do_patrimonio(
    declaracoes: List[Any], resolvedor: ResolvedorDePessoas, fonte_id: int
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    contagem: Dict[str, int] = defaultdict(
        int, {"sem_pessoa": 0, "sem_proveniencia": 0, "invalidas": 0, "repetidas": 0}
    )
    unicas: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for item in declaracoes:
        lido, motivo = ler_patrimonio(item)
        if lido is None:
            contagem[str(motivo)] += 1
            continue
        pessoa = resolvedor.resolver(item).pessoa_id
        if pessoa is None:
            contagem["sem_pessoa"] += 1
            continue
        linha = {"p": pessoa, **lido, "f": fonte_id}
        # duas declarações do mesmo ano: vale a de maior valor (depois quantidade e detalhes)
        if manter_a_melhor(unicas, (pessoa, lido["ano"]), linha, ("valor", "qtd", "det")):
            contagem["repetidas"] += 1
    return list(unicas.values()), contagem


def carregar_patrimonio(conn: Connection, processed_dir: Path) -> Dict[str, int]:
    return _carga_simples(
        conn,
        processed_dir,
        arquivo=PATRIMONIO_ARQUIVO,
        aceita=lambda dados: isinstance(dados, list),
        chave_ausente="arquivo_ausente",
        montar=linhas_do_patrimonio,
        fonte=FONTE_TSE,
        rotulo="Patrimônio",
        chave_total="declaracoes",
        tabela="fin.declaracao_patrimonio",
        insercao=(
            "INSERT INTO fin.declaracao_patrimonio (pessoa_id, ano_eleicao, valor_declarado, quantidade_bens, detalhes, "
            "fonte_id) VALUES (:p, :ano, :valor, :qtd, :det, :f)"
        ),
    )


def linhas_das_doacoes(
    prestacoes: List[Any], resolvedor: ResolvedorDePessoas, fonte_id: int
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    por_prestacao: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    contagem: Dict[str, int] = defaultdict(
        int, {"sem_pessoa": 0, "sem_proveniencia": 0, "invalidas": 0, "prestacao_descartada": 0}
    )
    for item in prestacoes:
        lida, motivo = ler_doacoes(item)
        if lida is None:
            contagem[str(motivo)] += 1
            continue
        pessoa = resolvedor.resolver(item).pessoa_id
        if pessoa is None:
            contagem["sem_pessoa"] += 1
            continue
        ano = lida["ano"]
        linhas = [{"p": pessoa, "f": fonte_id, **doador} for doador in lida["linhas"]]
        anteriores = por_prestacao.get((pessoa, ano))
        if anteriores is None:
            por_prestacao[(pessoa, ano)] = linhas
            continue
        # a prestação mais completa (mais linhas, depois maior valor, depois o conteúdo) vale para a (pessoa, ano)
        contagem["prestacao_descartada"] += 1
        if chave_da_prestacao(linhas) > chave_da_prestacao(anteriores):
            por_prestacao[(pessoa, ano)] = linhas
    contagem["prestacoes"] = len(por_prestacao)
    return [linha for linhas in por_prestacao.values() for linha in linhas], contagem


def carregar_doacoes(conn: Connection, processed_dir: Path) -> Dict[str, int]:
    return _carga_simples(
        conn,
        processed_dir,
        arquivo=DOACOES_ARQUIVO,
        aceita=lambda dados: isinstance(dados, list),
        chave_ausente="arquivo_ausente",
        montar=linhas_das_doacoes,
        fonte=FONTE_TSE,
        rotulo="Doações",
        chave_total="linhas",
        tabela="fin.doacao_campanha",
        insercao=(
            "INSERT INTO fin.doacao_campanha (pessoa_id, ano_eleicao, doador_nome, doador_documento, valor, tipo_receita, "
            "agregado, quantidade_doadores, fonte_id) "
            "VALUES (:p, :ano, :nome, :doc, :valor, :tipo, :agregado, :qtd, :f)"
        ),
    )


def linhas_das_certidoes(
    ocorrencias: List[Any], resolvedor: ResolvedorDePessoas, fonte_id: int
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    contagem: Dict[str, int] = defaultdict(
        int, {"sem_pessoa": 0, "sem_proveniencia": 0, "invalidas": 0, "repetidas": 0}
    )
    unicas: Dict[Tuple[int, str, str], Dict[str, Any]] = {}
    for item in ocorrencias:
        lido, motivo = ler_certidao(item)
        if lido is None:
            contagem[str(motivo)] += 1
            continue
        pessoa = resolvedor.resolver(item).pessoa_id
        if pessoa is None:
            contagem["sem_pessoa"] += 1
            continue
        linha = {"p": pessoa, **lido, "f": fonte_id}
        chave = (pessoa, lido["orgao"], lido["tipo"])
        # mesma (pessoa, órgão, tipo): critério fixo, não a ordem do arquivo
        if manter_a_melhor(unicas, chave, linha, ("situacao", "det", "proc")):
            contagem["repetidas"] += 1
    return list(unicas.values()), contagem


def carregar_certidoes(conn: Connection, processed_dir: Path) -> Dict[str, int]:
    return _carga_simples(
        conn,
        processed_dir,
        arquivo=CERTIDOES_ARQUIVO,
        aceita=lambda dados: isinstance(dados, list),
        chave_ausente="arquivo_ausente",
        montar=linhas_das_certidoes,
        fonte=FONTE_TSE,
        rotulo="Certidões",
        chave_total="certidoes",
        tabela="fin.certidao",
        insercao=(
            "INSERT INTO fin.certidao (pessoa_id, orgao, tipo, situacao, detalhes, numero_processo, fonte_id) "
            "VALUES (:p, :orgao, :tipo, :situacao, :det, :proc, :f)"
        ),
    )


CARGAS: Tuple[Tuple[str, Callable[[Connection, Path], Dict[str, int]]], ...] = (
    ("ceap", carregar_ceap),
    ("emendas", carregar_emendas),
    ("remuneracao", carregar_remuneracao),
    ("patrimonio", carregar_patrimonio),
    ("doacoes", carregar_doacoes),
    ("certidoes", carregar_certidoes),
)


def carregar(engine: Engine, processed_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Executa as seis cargas, cada uma na sua transação; uma que falha não impede as demais e o erro sobe no fim."""
    pasta = Path(processed_dir or PROCESSED_DATA_DIR)
    resultados: Dict[str, Any] = {}
    falhas: List[str] = []
    for chave, funcao in CARGAS:
        try:
            with engine.begin() as conn:
                resultados[chave] = funcao(conn, pasta)
            logger.info("Finanças — %s: %s", chave, resultados[chave])
        except Exception as exc:  # noqa: BLE001 - isolada de propósito; relatada abaixo
            logger.error("Carga de finanças '%s' falhou: %s", chave, exc, exc_info=True)
            falhas.append(f"{chave}: {exc}")
    if falhas:
        raise RuntimeError("; ".join(falhas))
    return resultados
