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
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from etl.config import PROCESSED_DATA_DIR
from etl.pipelines.loader_helpers import (
    ANO_MAXIMO,
    ANO_MINIMO,
    LIMITE_TSE,
    cnpj_do_fornecedor,
    decimal_de,
    inteiro,
    inteiro_em,
    ler_ceap,
    ler_doacoes,
    ler_emenda,
    ler_remuneracao,
    nome_do_fornecedor,
    texto,
    texto_sem_cpf,
    tipo_do_autor,
    uf_da_localidade,
)
from etl.pipelines.pessoa_resolver import ResolvedorDePessoas
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_json
from etl.utils.provenance import is_trusted

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
_CONTAGENS = {
    "fin.despesa_cota": "SELECT count(*) FROM fin.despesa_cota",
    "fin.emenda": "SELECT count(*) FROM fin.emenda",
    "fin.remuneracao": "SELECT count(*) FROM fin.remuneracao",
    "fin.declaracao_patrimonio": "SELECT count(*) FROM fin.declaracao_patrimonio",
    "fin.doacao_campanha": "SELECT count(*) FROM fin.doacao_campanha",
    "fin.certidao": "SELECT count(*) FROM fin.certidao",
    "fin.despesa_cota_fornecedor": "SELECT count(*) FROM fin.despesa_cota_fornecedor",
    "fin.despesa_cota_resumo": "SELECT count(*) FROM fin.despesa_cota_resumo",
}


def _protege_contra_encolhimento(conn: Connection, tabela: str, novas: int) -> None:
    """Levanta RuntimeError (sem tocar no banco) se a carga reduziria `tabela` a menos de FRACAO_MINIMA do que existe."""
    existentes = int(conn.execute(text(_CONTAGENS[tabela])).scalar() or 0)
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


# ── CEAP ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _fornecedores_do_parlamentar(dados: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fornecedores de uma entrada, com o mesmo CNPJ em grafias diferentes unido (fica o nome de maior valor)."""
    agrupados: Dict[str, List[Any]] = {}  # grupo -> [valor, notas (None se desconhecida), nome, maior valor, cnpj]
    lista_fornecedores = dados.get("fornecedores")
    for item in (lista_fornecedores if isinstance(lista_fornecedores, dict) else {}).values():
        if not isinstance(item, dict):
            continue
        valor_dec = decimal_de(item.get("total"))
        if valor_dec is None:
            continue
        nome, cnpj = nome_do_fornecedor(item.get("nome")), cnpj_do_fornecedor(item.get("cnpj_cpf"))
        notas = inteiro(item.get("notas"))
        notas = notas if notas is not None and notas >= 0 else None
        grupo = cnpj or f"nome:{nome}"  # sem CNPJ, vale o nome; é a mesma chave que a API usa para agrupar
        acumulado = agrupados.setdefault(grupo, [Decimal(0), 0, nome, valor_dec, cnpj])
        acumulado[0] += valor_dec
        acumulado[1] = _soma_ou_desconhecido(acumulado[1], notas)
        if valor_dec > acumulado[3]:
            acumulado[2], acumulado[3] = nome, valor_dec
    return [
        {"grupo": grupo, "nome": nome, "cnpj": cnpj, "valor": valor, "notas": notas}
        for grupo, (valor, notas, nome, _maior, cnpj) in agrupados.items()
    ]


def linhas_da_ceap(
    ceap: Dict[str, Any], resolvedor: ResolvedorDePessoas, fontes: Dict[str, int]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    """Despesas, fornecedores e resumos prontos para gravar, mais a contagem do que ficou de fora."""
    despesas: List[Dict[str, Any]] = []
    fornecedores: List[Dict[str, Any]] = []
    resumos: List[Dict[str, Any]] = []
    contagem = {
        "parlamentares": 0,
        "sem_pessoa": 0,
        "sem_identificador": 0,
        "sem_proveniencia": 0,
        "sem_detalhe_por_ano": 0,
    }
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
        fornecedores += [
            {"p": pessoa, "f": fonte_id, **fornecedor} for fornecedor in _fornecedores_do_parlamentar(dados)
        ]
        if valores:  # a quantidade de notas só vale ao lado de um gasto que a entrada realmente somou
            notas = inteiro(dados.get("total_notas"))
            # quantidade desconhecida não vira zero: a linha com `notas` None só marca a pessoa para `_resumos_completos`
            resumos.append({"p": pessoa, "notas": notas if notas is not None and notas >= 0 else None, "f": fonte_id})
    return despesas, fornecedores, resumos, contagem


def _resumos_completos(resumos: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """
    Resumos de quem tem a quantidade de notas conhecida em TODAS as entradas (Câmara e Senado) que somaram gasto. Uma
    contagem parcial ao lado do gasto completo enganaria, então a pessoa fica sem resumo. Devolve também quantas ficaram.
    """
    incompletas = {r["p"] for r in resumos if r["notas"] is None}
    return [r for r in resumos if r["p"] not in incompletas and r["notas"] is not None], len(incompletas)


def carregar_ceap(conn: Connection, processed_dir: Path) -> Dict[str, int]:
    ceap = _arquivo(processed_dir, CEAP_ARQUIVO)
    if not isinstance(ceap, dict):
        return {"arquivo_ausente": 1}
    despesas, fornecedores, resumos, contagem = linhas_da_ceap(ceap, ResolvedorDePessoas(conn), _fontes(conn))
    if not despesas:
        logger.warning("CEAP sem nenhum registro utilizável (%s); o banco não foi alterado.", contagem)
        return {**contagem, "despesas": 0}
    # Duas entradas do arquivo podem resolver para a mesma pessoa (Câmara e Senado, ou variantes do nome): `_somar`
    # deixa uma linha por chave em cada tabela e a guarda de encolhimento olha o tamanho final.
    despesas, repetidas = _somar(despesas, ("p", "ano", "tipo"), ("valor",))
    fornecedores, _ = _somar(fornecedores, ("p", "grupo"), ("valor", "notas"))
    completos, resumo_incompleto = _resumos_completos(resumos)
    resumos, _ = _somar(completos, ("p",), ("notas",))
    if repetidas:
        logger.warning(
            "CEAP: %d linhas repetidas na mesma fonte (variantes do nome); ficou a de maior valor.", repetidas
        )
    contagem["mesma_fonte_repetida"] = repetidas
    contagem["resumo_incompleto"] = resumo_incompleto
    _protege_contra_encolhimento(conn, "fin.despesa_cota", len(despesas))
    _protege_contra_encolhimento(conn, "fin.despesa_cota_fornecedor", len(fornecedores))
    _protege_contra_encolhimento(conn, "fin.despesa_cota_resumo", len(resumos))
    conn.execute(text("DELETE FROM fin.despesa_cota"))
    conn.execute(text("DELETE FROM fin.despesa_cota_fornecedor"))
    conn.execute(text("DELETE FROM fin.despesa_cota_resumo"))
    _inserir(
        conn,
        "INSERT INTO fin.despesa_cota (pessoa_id, ano, tipo_despesa, valor_liquido, fonte_id) "
        "VALUES (:p, :ano, :tipo, :valor, :f)",
        despesas,
    )
    _inserir(
        conn,
        "INSERT INTO fin.despesa_cota_fornecedor (pessoa_id, nome, cnpj, valor_total, notas, fonte_id) "
        "VALUES (:p, :nome, :cnpj, :valor, :notas, :f)",
        fornecedores,
    )
    _inserir(
        conn,
        "INSERT INTO fin.despesa_cota_resumo (pessoa_id, total_notas, fonte_id) VALUES (:p, :notas, :f)",
        resumos,
    )
    return {**contagem, "despesas": len(despesas), "fornecedores": len(fornecedores)}


def _chave_de_desempate(linha: Dict[str, Any], *campos: str) -> Tuple[Any, ...]:
    """
    Ordem total entre duas linhas que disputam a mesma chave: os campos na ordem dada, com o desconhecido (None) abaixo de
    qualquer valor. O resultado não depende da ordem em que o arquivo traz as linhas.
    """
    return tuple((0, "") if linha[c] is None else (1, linha[c]) for c in campos)


def _soma_ou_desconhecido(a: Any, b: Any) -> Any:
    """Soma de duas parcelas; se qualquer uma é desconhecida (None) o total também é: parcial nunca vale como total."""
    return None if a is None or b is None else a + b


def _somar(
    linhas: List[Dict[str, Any]], chave: Tuple[str, ...], somas: Tuple[str, ...]
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Junta linhas de mesma chave e devolve também quantas linhas repetiram a chave na MESMA fonte. Dentro de uma fonte
    a repetição é o mesmo dado sob outra grafia do nome, então fica a linha de maior valor; entre fontes diferentes
    (Câmara e Senado) os campos numéricos se somam (desconhecido em qualquer parcela deixa o total desconhecido). Nos empates
    decide o conteúdo da linha, não a ordem do arquivo; a linha vencedora define os demais campos.
    """
    por_fonte: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    repetidas = 0
    for linha in linhas:
        k = (tuple(linha[c] for c in chave), linha["f"])
        atual = por_fonte.get(k)
        if atual is None:
            por_fonte[k] = dict(linha)
            continue
        repetidas += 1
        if _chave_de_desempate(linha, *somas, *sorted(set(linha) - set(somas))) > _chave_de_desempate(
            atual, *somas, *sorted(set(atual) - set(somas))
        ):
            por_fonte[k] = dict(linha)
    unicas: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for (k, _fonte), linha in por_fonte.items():
        if k in unicas:
            for campo in somas:
                unicas[k][campo] = _soma_ou_desconhecido(unicas[k][campo], linha[campo])
        else:
            unicas[k] = dict(linha)
    return list(unicas.values()), repetidas


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
    contagem = {
        "IDENTIFICADO": 0,
        "NAO_CADASTRADO": 0,
        "HOMONIMO_NAO_DESAMBIGUADO": 0,
        "INSTITUCIONAL": 0,
        "sem_proveniencia": 0,
        "invalidas": 0,
        "chave_repetida": 0,
    }
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
    return list(unicas.values()), contagem


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
    contagem = {"sem_pessoa": 0, "invalidas": 0, "repetidas": 0}
    unicas: Dict[Tuple[int, int, int], Dict[str, Any]] = {}
    registros = corpo.get("registros")
    for registro in registros if isinstance(registros, list) else []:
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
        anterior = unicas.get(chave)
        if (
            anterior is not None
        ):  # duas folhas no mesmo mês: vale a de maior bruto (depois o maior líquido), não a do arquivo
            contagem["repetidas"] += 1
            if _chave_de_desempate(anterior, "bruto", "liquido") >= _chave_de_desempate(linha, "bruto", "liquido"):
                continue
        unicas[chave] = linha
    return list(unicas.values()), contagem


def carregar_remuneracao(conn: Connection, processed_dir: Path) -> Dict[str, int]:
    corpo = _arquivo(processed_dir, REMUNERACAO_ARQUIVO)
    if not isinstance(corpo, dict) or not is_trusted(corpo):
        if corpo is not None:
            logger.warning("%s sem proveniência oficial; carga pulada.", REMUNERACAO_ARQUIVO)
        return {"arquivo_ausente_ou_sem_proveniencia": 1}
    linhas, contagem = linhas_da_remuneracao(corpo, ResolvedorDePessoas(conn), _fontes(conn)[FONTE_REMUNERACAO])
    if not linhas:
        logger.warning("Remuneração sem nenhum registro utilizável (%s); o banco não foi alterado.", contagem)
        return {**contagem, "meses": 0}
    _protege_contra_encolhimento(conn, "fin.remuneracao", len(linhas))
    conn.execute(text("DELETE FROM fin.remuneracao"))
    _inserir(
        conn,
        "INSERT INTO fin.remuneracao (pessoa_id, ano, mes, salario_bruto, salario_liquido, fonte_id) "
        "VALUES (:p, :ano, :mes, :bruto, :liquido, :f)",
        linhas,
    )
    return {**contagem, "meses": len(linhas)}


# ── TSE: patrimônio, doações e certidões ─────────────────────────────────────────────────────────────────────────────
def linhas_do_patrimonio(
    declaracoes: List[Any], resolvedor: ResolvedorDePessoas, fonte_id: int
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    contagem = {"sem_pessoa": 0, "sem_proveniencia": 0, "invalidas": 0, "repetidas": 0}
    unicas: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for item in declaracoes:
        if not isinstance(item, dict) or not is_trusted(item):
            contagem["sem_proveniencia"] += 1
            continue
        ano = inteiro_em(item.get("ano_eleicao"), ANO_MINIMO, ANO_MAXIMO)
        valor = decimal_de(item.get("valor_declarado_brl"), LIMITE_TSE)
        if ano is None or valor is None:
            contagem["invalidas"] += 1
            continue
        pessoa = resolvedor.resolver(item).pessoa_id
        if pessoa is None:
            contagem["sem_pessoa"] += 1
            continue
        quantidade = inteiro(item.get("quantidade_bens"))
        linha = {
            "p": pessoa,
            "ano": ano,
            "valor": valor,
            "qtd": quantidade if quantidade is not None and quantidade >= 0 else None,
            "det": texto_sem_cpf(item.get("detalhes_bens")),
            "f": fonte_id,
        }
        anterior = unicas.get((pessoa, ano))
        if (
            anterior is not None
        ):  # duas declarações do mesmo ano: vale a de maior valor (depois quantidade e detalhes), não a do arquivo
            contagem["repetidas"] += 1
            if _chave_de_desempate(anterior, "valor", "qtd", "det") >= _chave_de_desempate(
                linha, "valor", "qtd", "det"
            ):
                continue
        unicas[(pessoa, ano)] = linha
    return list(unicas.values()), contagem


def carregar_patrimonio(conn: Connection, processed_dir: Path) -> Dict[str, int]:
    declaracoes = _arquivo(processed_dir, PATRIMONIO_ARQUIVO)
    if not isinstance(declaracoes, list):
        return {"arquivo_ausente": 1}
    linhas, contagem = linhas_do_patrimonio(declaracoes, ResolvedorDePessoas(conn), _fontes(conn)[FONTE_TSE])
    if not linhas:
        logger.warning("Patrimônio sem nenhum registro utilizável (%s); o banco não foi alterado.", contagem)
        return {**contagem, "declaracoes": 0}
    _protege_contra_encolhimento(conn, "fin.declaracao_patrimonio", len(linhas))
    conn.execute(text("DELETE FROM fin.declaracao_patrimonio"))
    _inserir(
        conn,
        "INSERT INTO fin.declaracao_patrimonio (pessoa_id, ano_eleicao, valor_declarado, quantidade_bens, detalhes, "
        "fonte_id) VALUES (:p, :ano, :valor, :qtd, :det, :f)",
        linhas,
    )
    return {**contagem, "declaracoes": len(linhas)}


def _chave_da_prestacao(linhas: List[Dict[str, Any]]) -> Tuple[Any, ...]:
    """Ordem total entre prestações do mesmo (pessoa, ano): quantidade, soma e, no empate, o conteúdo das linhas."""
    conteudo = sorted((x["nome"], x["doc"] or "", str(x["valor"]), x["tipo"] or "") for x in linhas)
    return len(linhas), sum((x["valor"] for x in linhas), Decimal(0)), conteudo


def linhas_das_doacoes(
    prestacoes: List[Any], resolvedor: ResolvedorDePessoas, fonte_id: int
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    por_prestacao: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    contagem = {"sem_pessoa": 0, "sem_proveniencia": 0, "invalidas": 0, "prestacao_descartada": 0}
    for item in prestacoes:
        ano, doadores, motivo = ler_doacoes(item)
        if ano is None:
            contagem[str(motivo)] += 1
            continue
        pessoa = resolvedor.resolver(item).pessoa_id
        if pessoa is None:
            contagem["sem_pessoa"] += 1
            continue
        linhas = [{"p": pessoa, "f": fonte_id, **doador} for doador in doadores]
        anteriores = por_prestacao.get((pessoa, ano))
        if anteriores is None:
            por_prestacao[(pessoa, ano)] = linhas
            continue
        # a prestação mais completa (mais linhas, depois maior valor, depois o conteúdo) vale para a (pessoa, ano)
        contagem["prestacao_descartada"] += 1
        if _chave_da_prestacao(linhas) > _chave_da_prestacao(anteriores):
            por_prestacao[(pessoa, ano)] = linhas
    contagem["prestacoes"] = len(por_prestacao)
    return [linha for linhas in por_prestacao.values() for linha in linhas], contagem


def carregar_doacoes(conn: Connection, processed_dir: Path) -> Dict[str, int]:
    prestacoes = _arquivo(processed_dir, DOACOES_ARQUIVO)
    if not isinstance(prestacoes, list):
        return {"arquivo_ausente": 1}
    linhas, contagem = linhas_das_doacoes(prestacoes, ResolvedorDePessoas(conn), _fontes(conn)[FONTE_TSE])
    if not linhas:
        logger.warning("Doações sem nenhuma linha utilizável (%s); o banco não foi alterado.", contagem)
        return {**contagem, "linhas": 0}
    _protege_contra_encolhimento(conn, "fin.doacao_campanha", len(linhas))
    conn.execute(text("DELETE FROM fin.doacao_campanha"))
    _inserir(
        conn,
        "INSERT INTO fin.doacao_campanha (pessoa_id, ano_eleicao, doador_nome, doador_documento, valor, tipo_receita, "
        "fonte_id) VALUES (:p, :ano, :nome, :doc, :valor, :tipo, :f)",
        linhas,
    )
    return {**contagem, "linhas": len(linhas)}


def linhas_das_certidoes(
    ocorrencias: List[Any], resolvedor: ResolvedorDePessoas, fonte_id: int
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    contagem = {"sem_pessoa": 0, "sem_proveniencia": 0, "invalidas": 0, "repetidas": 0}
    unicas: Dict[Tuple[int, str, str], Dict[str, Any]] = {}
    for item in ocorrencias:
        if not isinstance(item, dict) or not is_trusted(item):
            contagem["sem_proveniencia"] += 1
            continue
        orgao, tipo, situacao = (
            texto(item.get("orgao")),
            texto(item.get("tipo_certidao")),
            texto(item.get("status_ficha")),
        )
        if not (orgao and tipo and situacao):
            contagem["invalidas"] += 1
            continue
        pessoa = resolvedor.resolver(item).pessoa_id
        if pessoa is None:
            contagem["sem_pessoa"] += 1
            continue
        linha = {
            "p": pessoa,
            "orgao": orgao,
            "tipo": tipo,
            "situacao": situacao,
            "det": texto_sem_cpf(item.get("detalhes")),
            "proc": texto(item.get("numero_processo")),
            "f": fonte_id,
        }
        anterior = unicas.get((pessoa, orgao, tipo))
        if anterior is not None:  # mesma (pessoa, órgão, tipo): critério fixo, não a ordem do arquivo
            contagem["repetidas"] += 1
            if _chave_de_desempate(anterior, "situacao", "det", "proc") >= _chave_de_desempate(
                linha, "situacao", "det", "proc"
            ):
                continue
        unicas[(pessoa, orgao, tipo)] = linha
    return list(unicas.values()), contagem


def carregar_certidoes(conn: Connection, processed_dir: Path) -> Dict[str, int]:
    ocorrencias = _arquivo(processed_dir, CERTIDOES_ARQUIVO)
    if not isinstance(ocorrencias, list):
        return {"arquivo_ausente": 1}
    linhas, contagem = linhas_das_certidoes(ocorrencias, ResolvedorDePessoas(conn), _fontes(conn)[FONTE_TSE])
    if not linhas:
        logger.warning("Certidões sem nenhum registro utilizável (%s); o banco não foi alterado.", contagem)
        return {**contagem, "certidoes": 0}
    _protege_contra_encolhimento(conn, "fin.certidao", len(linhas))
    conn.execute(text("DELETE FROM fin.certidao"))
    _inserir(
        conn,
        "INSERT INTO fin.certidao (pessoa_id, orgao, tipo, situacao, detalhes, numero_processo, fonte_id) "
        "VALUES (:p, :orgao, :tipo, :situacao, :det, :proc, :f)",
        linhas,
    )
    return {**contagem, "certidoes": len(linhas)}


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
