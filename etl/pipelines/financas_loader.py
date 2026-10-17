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
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from etl.config import PROCESSED_DATA_DIR
from etl.pipelines.loader_helpers import (
    ANO_MAXIMO,
    ANO_MINIMO,
    LIMITE_EMENDA,
    LIMITE_REMUNERACAO,
    LIMITE_TSE,
    cnpj_do_fornecedor,
    decimal_de,
    documento_do_doador,
    inteiro,
    inteiro_em,
    nome_do_fornecedor,
    nome_sem_cpf,
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
def valores_da_ceap(dados: Dict[str, Any]) -> Dict[Tuple[int, str], Decimal]:
    """Total por (ano, tipo de despesa) de um parlamentar do arquivo. A reconciliação usa a mesma regra do loader."""
    totais: Dict[Tuple[int, str], Decimal] = defaultdict(Decimal)
    por_ano_tipo = dados.get("por_ano_tipo")
    for ano, tipos in (por_ano_tipo if isinstance(por_ano_tipo, dict) else {}).items():
        ano_ok = inteiro_em(ano, ANO_MINIMO, ANO_MAXIMO)
        for tipo, valor in (tipos if isinstance(tipos, dict) else {}).items():
            valor_dec = decimal_de(valor)
            nome_tipo = texto(tipo)
            if ano_ok is not None and valor_dec is not None and nome_tipo:
                totais[(ano_ok, nome_tipo)] += valor_dec
    return totais


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
    for chave, dados in ceap.items():
        if not isinstance(dados, dict) or not is_trusted(dados):
            contagem["sem_proveniencia"] += 1
            continue
        if not (dados.get("camara_id") or dados.get("senado_id")):
            contagem["sem_identificador"] += 1  # sem id não há como saber a fonte (Câmara ou Senado)
            continue
        pessoa = resolvedor.resolver(dados).pessoa_id
        if pessoa is None:
            contagem["sem_pessoa"] += 1
            continue
        por_ano_tipo = dados.get("por_ano_tipo")
        if not isinstance(por_ano_tipo, dict) or not por_ano_tipo:
            contagem["sem_detalhe_por_ano"] += 1
            continue
        # a origem é o identificador que o registro carrega (nenhum registro do arquivo traz os dois)
        fonte_id = fontes[FONTE_CEAP_CAMARA if dados.get("camara_id") else FONTE_CEAP_SENADO]
        contagem["parlamentares"] += 1
        despesas += [
            {"p": pessoa, "ano": ano, "tipo": tipo, "valor": valor, "f": fonte_id}
            for (ano, tipo), valor in valores_da_ceap(dados).items()
        ]
        agrupados: Dict[Tuple[str, Optional[str]], List[Any]] = {}  # chave -> [valor, notas, nome, maior valor, cnpj]
        lista_fornecedores = dados.get("fornecedores")
        for item in (lista_fornecedores if isinstance(lista_fornecedores, dict) else {}).values():
            if not isinstance(item, dict):
                continue
            valor_dec = decimal_de(item.get("total"))
            if valor_dec is None:
                continue
            nome, cnpj = nome_do_fornecedor(item.get("nome")), cnpj_do_fornecedor(item.get("cnpj_cpf"))
            # o mesmo CNPJ com grafias diferentes é um fornecedor só (fica o nome de maior valor); sem CNPJ, vale o nome
            chave = ("cnpj", cnpj) if cnpj else ("nome", nome)
            acumulado = agrupados.setdefault(chave, [Decimal(0), 0, nome, valor_dec, cnpj])
            acumulado[0] += valor_dec
            acumulado[1] += max(inteiro(item.get("notas")) or 0, 0)
            if valor_dec > acumulado[3]:
                acumulado[2], acumulado[3] = nome, valor_dec
        fornecedores += [
            {"p": pessoa, "nome": nome, "cnpj": cnpj, "valor": valor, "notas": notas, "f": fonte_id}
            for valor, notas, nome, _maior, cnpj in agrupados.values()
        ]
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
    fornecedores, _ = _somar(fornecedores, ("p", "nome", "cnpj"), ("valor", "notas"))
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


def _somar(
    linhas: List[Dict[str, Any]], chave: Tuple[str, ...], somas: Tuple[str, ...]
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Junta linhas de mesma chave e devolve também quantas linhas repetiram a chave na MESMA fonte. Dentro de uma fonte
    a repetição é o mesmo dado sob outra grafia do nome, então fica a linha de maior valor; entre fontes diferentes
    (Câmara e Senado) os campos numéricos se somam. A primeira linha define os demais campos.
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
        if linha[somas[0]] > atual[somas[0]]:
            por_fonte[k] = dict(linha)
    unicas: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for (k, _fonte), linha in por_fonte.items():
        if k in unicas:
            for campo in somas:
                unicas[k][campo] += linha[campo]
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


def ler_emenda(emenda: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Campos de uma emenda do arquivo, ou (None, motivo) quando ela não entra: "sem_proveniencia" ou "invalidas".
    É a regra única de elegibilidade: a reconciliação usa esta mesma função para somar o que o arquivo deveria ter no banco.
    """
    if not isinstance(emenda, dict) or not is_trusted(emenda):
        return None, "sem_proveniencia"
    ano = inteiro_em(emenda.get("ano"), ANO_MINIMO, ANO_MAXIMO)
    tipo_emenda, autor = texto(emenda.get("tipo_emenda")), texto(emenda.get("politician_name"))
    local = texto(emenda.get("localidade_destino"))
    empenhado = decimal_de(emenda.get("valor_empenhado"), LIMITE_EMENDA)
    pago = decimal_de(emenda.get("valor_pago"), LIMITE_EMENDA)
    # valor pago desconhecido não vira zero: a emenda sem os dois valores fica de fora e é contada
    if ano is None or not (tipo_emenda and autor and local) or empenhado is None or pago is None:
        return None, "invalidas"
    return {
        "ano": ano,
        "codigo": texto(emenda.get("codigo_emenda")),
        "tipo_emenda": tipo_emenda,
        "autor": autor,
        "local": local,
        "funcao": texto(emenda.get("funcao")),
        "cod_autor": texto(emenda.get("autor_codigo")),
        "empenhado": empenhado,
        "pago": pago,
    }, None


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
def ler_remuneracao(registro: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Campos de um mês de remuneração, ou (None, "invalidas"). Regra única de elegibilidade (loader e reconciliação)."""
    if not isinstance(registro, dict):
        return None, "invalidas"
    ano, mes = inteiro_em(registro.get("ano"), ANO_MINIMO, ANO_MAXIMO), inteiro_em(registro.get("mes"), 1, 12)
    bruto = decimal_de(registro.get("salario_bruto"), LIMITE_REMUNERACAO)
    if ano is None or mes is None or bruto is None:
        return None, "invalidas"
    return {
        "ano": ano,
        "mes": mes,
        "bruto": bruto,
        "liquido": decimal_de(registro.get("salario_liquido"), LIMITE_REMUNERACAO),
    }, None


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
        if anterior is not None:  # duas folhas no mesmo mês: vale a de maior bruto, não a última do arquivo
            contagem["repetidas"] += 1
            if anterior["bruto"] >= linha["bruto"]:
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
        if anterior is not None:  # duas declarações do mesmo ano: vale a de maior valor, não a última do arquivo
            contagem["repetidas"] += 1
            if anterior["valor"] >= valor:
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


def ler_doacoes(item: Any) -> Tuple[Optional[int], List[Dict[str, Any]], Optional[str]]:
    """
    (ano, linhas de doador, motivo) de uma prestação do arquivo. Sem ano ou sem lista de doadores o motivo é "invalidas";
    sem proveniência, "sem_proveniencia". Regra única de elegibilidade (loader e reconciliação).
    """
    if not isinstance(item, dict) or not is_trusted(item):
        return None, [], "sem_proveniencia"
    ano = inteiro_em(item.get("ano_eleicao"), ANO_MINIMO, ANO_MAXIMO)
    if ano is None or not isinstance(item.get("doadores"), list):
        return None, [], "invalidas"
    linhas = []
    for doador in item["doadores"]:
        valor = decimal_de(doador.get("valor_doado"), LIMITE_TSE) if isinstance(doador, dict) else None
        if valor is None:
            continue
        linhas.append(
            {
                "ano": ano,
                "nome": nome_sem_cpf(doador.get("nome_doador")) or "Doador não identificado",
                "doc": documento_do_doador(doador.get("cpf_cnpj_doador")),
                "valor": valor,
                "tipo": texto(doador.get("tipo_receita")),
            }
        )
    return ano, linhas, None


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
        # a prestação mais completa (mais linhas e, no empate, maior valor) vale para a (pessoa, ano); a outra é contada
        contagem["prestacao_descartada"] += 1
        if (len(linhas), sum(x["valor"] for x in linhas)) > (len(anteriores), sum(x["valor"] for x in anteriores)):
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
            if (anterior["situacao"], anterior["det"] or "") >= (situacao, linha["det"] or ""):
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
