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

import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from etl.config import (  # noqa: F401 - CHAVES_* são reexportadas para quem já importa daqui
    CASAS_DO_CONGRESSO,
    CEAP_ARQUIVO,
    CHAVES_DO_TIMER,
    CHAVES_ESTATICAS,
    EMENDAS_ARQUIVO,
    PROCESSED_DATA_DIR,
)
from etl.pipelines.loader_helpers import (
    LIMITE_CEAP,
    LIMITE_EMENDA,
    TIPOS_DE_AUTOR_INSTITUCIONAL,
    chave_da_prestacao,
    contagem_int4,
    descricao_do_erro,
    fornecedores_do_parlamentar,
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
from etl.pipelines.semeadura_das_financas import SQL_FONTES_DO_TIMER, fontes_do_timer  # noqa: F401 - reexportadas
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_json

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Connection, Engine  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

logger = logging.getLogger("FinancasLoader")

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
# Emendas com autor identificado: o upsert regrava `pessoa_id`, então um resolvedor degradado (que não acha ninguém) não
# encolhe a tabela, mas desliga as emendas de quem já estava ligado. Esta contagem alimenta a mesma guarda.
_SQL_CONTAGEM_EMENDAS_IDENTIFICADAS = "SELECT count(*) FROM fin.emenda WHERE autor_situacao = 'IDENTIFICADO'"
_SQL_DELETE = {
    "fin.despesa_cota": "DELETE FROM fin.despesa_cota",
    "fin.remuneracao": "DELETE FROM fin.remuneracao",
    "fin.declaracao_patrimonio": "DELETE FROM fin.declaracao_patrimonio",
    "fin.doacao_campanha": "DELETE FROM fin.doacao_campanha",
    "fin.certidao": "DELETE FROM fin.certidao",
    "fin.despesa_cota_fornecedor": "DELETE FROM fin.despesa_cota_fornecedor",
    "fin.despesa_cota_resumo": "DELETE FROM fin.despesa_cota_resumo",
}


def _recusa_encolhimento(rotulo: str, existentes: int, novas: int) -> None:
    """Levanta RuntimeError se `novas` é menos de FRACAO_MINIMA de `existentes` (e há o bastante para valer a guarda)."""
    if existentes < MINIMO_PARA_GUARDA or novas >= existentes * FRACAO_MINIMA:
        return
    if os.environ.get(VARIAVEL_ACEITAR_ENCOLHIMENTO) == "1":
        logger.warning(
            "%s: %d -> %d linhas (encolhimento aceito por %s).",
            rotulo,
            existentes,
            novas,
            VARIAVEL_ACEITAR_ENCOLHIMENTO,
        )
        return
    raise RuntimeError(
        f"{rotulo}: a carga traria {novas} linhas e o banco tem {existentes}; nada foi alterado. "
        f"Se a redução é legítima, rode de novo com {VARIAVEL_ACEITAR_ENCOLHIMENTO}=1."
    )


def _protege_anos_da_ceap(conn: Connection, despesas: List[Dict[str, Any]]) -> None:
    """
    Recusa (sem tocar no banco) a carga da CEAP que deixaria sem gasto um ano que o `fin` já tem, por fonte (Câmara/Senado).
    A guarda por quantidade de linhas não vê isso: uma carga manual desde 2018 seguida da atualização diária (que começa em
    2019) perde o ano inteiro de 2018 com uma redução pequena no total. `LEGISDATA_ACEITAR_ENCOLHIMENTO=1` libera.
    """
    existentes = {
        (int(f), int(ano))
        for f, ano in conn.execute(text("SELECT DISTINCT fonte_id, ano FROM fin.despesa_cota WHERE valor_liquido <> 0"))
    }
    novos = {(int(x["f"]), int(x["ano"])) for x in despesas if x["valor"] != 0}
    perdidos = existentes - novos
    if not perdidos:
        return
    nomes = {f: casa for f, casa in ((f, _casa_da_fonte_id(conn, f)) for f in {f for f, _ in perdidos})}
    rotulo = "; ".join(f"{nomes[f]}: {sorted(a for g, a in perdidos if g == f)}" for f in sorted(nomes))
    if os.environ.get(VARIAVEL_ACEITAR_ENCOLHIMENTO) == "1":
        logger.warning(
            "fin.despesa_cota: a carga remove anos já carregados (%s); aceito por %s.",
            rotulo,
            VARIAVEL_ACEITAR_ENCOLHIMENTO,
        )
        return
    raise RuntimeError(
        f"fin.despesa_cota: a carga deixaria sem gasto anos que o banco já tem ({rotulo}); nada foi alterado. "
        f"Se a remoção é legítima, rode de novo com {VARIAVEL_ACEITAR_ENCOLHIMENTO}=1."
    )


def _casa_da_fonte_id(conn: Connection, fonte_id: int) -> str:
    codigo = conn.execute(text("SELECT codigo FROM etl.fonte WHERE id = :i"), {"i": fonte_id}).scalar()
    return _CASA_DA_FONTE.get(str(codigo), str(codigo))


def _protege_contra_encolhimento(conn: Connection, tabela: str, novas: int) -> None:
    """Levanta RuntimeError (sem tocar no banco) se a carga reduziria `tabela` a menos de FRACAO_MINIMA do que existe."""
    _recusa_encolhimento(tabela, int(conn.execute(text(_SQL_CONTAGEM[tabela])).scalar() or 0), novas)


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


def _ler_arquivo(
    processed_dir: Path, arquivo: str, aceita: Callable[[Any], bool]
) -> Tuple[Any, Optional[Dict[str, int]]]:
    """
    Lê o arquivo da carga e diz se ele serve: (dados, None) quando `aceita`; senão (None, resultado) com
    `arquivo_ausente` para o que não existe e `formato_invalido` (mais um aviso no log) para o que existe mas tem o tipo
    errado ou nenhuma proveniência. Passo comum às seis cargas, que nunca apagam nada nesses casos.
    """
    dados = _arquivo(processed_dir, arquivo)
    if aceita(dados):
        return dados, None
    if dados is None:
        return None, {"arquivo_ausente": 1}
    logger.warning("%s com formato ou proveniência inválidos; carga pulada.", arquivo)
    return None, {"formato_invalido": 1}


def _carga_simples(
    conn: Connection,
    processed_dir: Path,
    *,
    arquivo: str,
    aceita: Callable[[Any], bool],
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
    dados, recusa = _ler_arquivo(processed_dir, arquivo, aceita)
    if recusa is not None:
        return recusa
    linhas, contagem = montar(dados, ResolvedorDePessoas(conn), _fontes(conn)[fonte])
    if not linhas:
        logger.warning("%s sem nenhum registro utilizável (%s); o banco não foi alterado.", rotulo, contagem)
        return {**contagem, chave_total: 0}
    _substituir(conn, [(tabela, insercao, linhas)])
    return {**contagem, chave_total: len(linhas)}


# ── CEAP ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _fonte_da_ceap(dados: Dict[str, Any]) -> str:
    """
    A casa de origem do registro: o `cargo` que a extração grava (SENADOR ou DEPUTADO_FEDERAL). Uma conta da Câmara ligada
    por nome (sem `camara_id`) continua sendo da Câmara; sem `cargo`, vale o identificador que o registro carrega.
    """
    cargo = dados.get("cargo")
    if cargo == "SENADOR":
        return FONTE_CEAP_SENADO
    if cargo == "DEPUTADO_FEDERAL":
        return FONTE_CEAP_CAMARA
    return FONTE_CEAP_CAMARA if dados.get("camara_id") else FONTE_CEAP_SENADO


_CASA_DA_FONTE = {FONTE_CEAP_CAMARA: "camara", FONTE_CEAP_SENADO: "senado"}


def anos_publicados_da_ceap(engine: Engine) -> Dict[str, Set[int]]:
    """
    Os anos em que o `fin` já tem gasto da CEAP, por casa ("camara"/"senado"). É o que a atualização diária usa para não
    tratar como "ainda sem arquivo" um ano que já foi carregado (o arquivo processado do git não serve: o deploy o devolve
    ao retrato antigo).
    """
    consulta = text(
        "SELECT f.codigo, d.ano FROM fin.despesa_cota d JOIN etl.fonte f ON f.id = d.fonte_id "
        "WHERE d.valor_liquido <> 0 GROUP BY f.codigo, d.ano"
    )
    publicados: Dict[str, Set[int]] = {casa: set() for casa in CASAS_DO_CONGRESSO}
    with engine.connect() as conexao:
        for codigo, ano in conexao.execute(consulta):
            if codigo in _CASA_DA_FONTE:
                publicados[_CASA_DA_FONTE[codigo]].add(int(ano))
    return publicados


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
            "total_fora_da_faixa": 0,
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
        fonte_id = fontes[_fonte_da_ceap(dados)]
        contagem["parlamentares"] += 1
        despesas += [
            {"p": pessoa, "ano": ano, "tipo": tipo, "valor": valor, "f": fonte_id}
            for (ano, tipo), valor in valores.items()
        ]
        if valores:  # fornecedores e quantidade de notas só valem ao lado de um gasto que a entrada realmente somou
            fornecedores += [{"p": pessoa, "f": fonte_id, **x} for x in fornecedores_do_parlamentar(dados)]
            notas = contagem_int4(dados.get("total_notas"))
            # quantidade desconhecida não vira zero: a linha com `notas` None só marca a pessoa para `resumos_completos`
            resumos.append({"p": pessoa, "notas": notas, "f": fonte_id})
    return despesas, fornecedores, resumos, contagem


def carregar_ceap(conn: Connection, processed_dir: Path) -> Dict[str, int]:
    ceap, recusa = _ler_arquivo(processed_dir, CEAP_ARQUIVO, lambda dados: isinstance(dados, dict))
    if recusa is not None:
        return recusa
    despesas, fornecedores, resumos, contagem = linhas_da_ceap(ceap, ResolvedorDePessoas(conn), _fontes(conn))
    if not despesas:
        logger.warning("CEAP sem nenhum registro utilizável (%s); o banco não foi alterado.", contagem)
        return {**contagem, "despesas": 0}
    # Duas entradas do arquivo podem resolver para a mesma pessoa (Câmara e Senado, ou variantes do nome): `somar_linhas`
    # deixa uma linha por chave em cada tabela e a guarda de encolhimento olha o tamanho final.
    despesas, repetidas = somar_linhas(despesas, ("p", "ano", "tipo"), ("valor",))
    fornecedores, _ = somar_linhas(fornecedores, ("p", "grupo"), ("valor", "notas"))
    # a soma entre fontes (Câmara + Senado) também precisa caber na coluna. Um total que não cabe deixa o gasto da pessoa
    # incompleto, e gasto parcial não vale como total: ela sai inteira (despesas, fornecedores e resumo).
    fora_da_faixa = [x for x in despesas + fornecedores if soma_na_faixa(x["valor"], LIMITE_CEAP) is None]
    sem_gasto_completo = {x["p"] for x in fora_da_faixa}
    despesas = [x for x in despesas if x["p"] not in sem_gasto_completo]
    fornecedores = [x for x in fornecedores if x["p"] not in sem_gasto_completo]
    resumos = [x for x in resumos if x["p"] not in sem_gasto_completo]
    contagem["soma_fora_da_faixa"] = len(fora_da_faixa)
    contagem["pessoas_sem_gasto_completo"] = len(sem_gasto_completo)
    if sem_gasto_completo:
        logger.warning(
            "CEAP: %d pessoa(s) com total fora da faixa da coluna ficaram sem gasto.", len(sem_gasto_completo)
        )
    if not despesas:
        logger.warning("CEAP sem despesa que caiba na faixa (%s); o banco não foi alterado.", contagem)
        return {**contagem, "despesas": 0}
    completos, resumo_incompleto = resumos_completos(resumos)
    resumos, _ = somar_linhas(completos, ("p",), ("notas",))
    if repetidas:
        logger.warning(
            "CEAP: %d linhas repetidas na mesma fonte (variantes do nome); ficou a de maior valor.", repetidas
        )
    contagem["mesma_fonte_repetida"] = repetidas
    contagem["resumo_incompleto"] = resumo_incompleto
    _protege_anos_da_ceap(conn, despesas)  # antes de qualquer DELETE: a recusa não deixa o banco pela metade
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
        if tipo_autor in TIPOS_DE_AUTOR_INSTITUCIONAL:
            situacao, pessoa = "INSTITUCIONAL", None
        else:
            resolucao = resolvedor.por_nome([autor], ano)
            situacao, pessoa = resolucao.situacao, resolucao.pessoa_id
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
    emendas, recusa = _ler_arquivo(processed_dir, EMENDAS_ARQUIVO, lambda dados: isinstance(dados, list))
    if recusa is not None:
        return recusa
    linhas, contagem = linhas_das_emendas(emendas, ResolvedorDePessoas(conn), _fontes(conn)[FONTE_EMENDAS])
    if not linhas:
        logger.warning("Emendas sem nenhum registro utilizável (%s); o banco não foi alterado.", contagem)
        return {**contagem, "emendas": 0}
    _protege_contra_encolhimento(conn, "fin.emenda", len(linhas))
    _recusa_encolhimento(
        "fin.emenda (autor identificado)",
        int(conn.execute(text(_SQL_CONTAGEM_EMENDAS_IDENTIFICADAS)).scalar() or 0),
        sum(1 for x in linhas if x["situacao"] == "IDENTIFICADO"),
    )
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


# CEAP e emendas são atualizadas todo dia pelo timer (arquivos extraídos na hora); as demais só mudam com o commit que
# traz um arquivo novo. O deploy usa esta divisão para não devolver CEAP e emendas ao retrato do git.
# (definidas em `etl.config`, leves, para a política de semeadura não precisar importar este módulo inteiro)


# ── Quem é dono da fonte: a atualização diária (extração fresca) ou o retrato do git ───────────────────────────────────
# O deploy precisa saber, por fonte, se o `fin` já traz dado MAIS NOVO que o git (então não pode semeá-la de novo). O sinal
# vai para o próprio banco, na MESMA transação da carga: volta junto com um backup restaurado, e uma carga que falhou não
# deixa sinal. Cada carga de CEAP ou de emendas que gravou linhas escreve uma linha em `etl.execucao` (estágio CARREGAR,
# status OK) com `parametros = {"carga", "fresca", "origem"}`: `fresca = "true"` quando veio de uma extração nova e
# `"false"` quando veio do retrato do git (que revoga a posse). Vale a ÚLTIMA linha de cada carga. INVARIANTE: essas
# linhas não podem ser expurgadas como histórico comum, ou o deploy volta a semear do git em silêncio.
_CONTAGEM_DA_FONTE = {"ceap": "despesas", "emendas": "emendas"}


def registrar_carga(conn: Connection, chave: str, resultado: Any, fresca: bool, origem: str) -> None:
    """Registra de onde veio o dado de uma fonte do timer. Só conta se a carga de fato gravou linhas."""
    campo = _CONTAGEM_DA_FONTE.get(chave)
    gravadas = resultado.get(campo) if campo and isinstance(resultado, dict) else None
    if not isinstance(gravadas, int) or isinstance(gravadas, bool) or gravadas <= 0:
        return
    conn.execute(
        text(
            "INSERT INTO etl.execucao (estagio, finalizado_em, status, linhas_gravadas, parametros) "
            "VALUES ('CARREGAR', now(), 'OK', :n, CAST(:p AS jsonb))"
        ),
        {
            "n": min(gravadas, 2**31 - 1),
            "p": json.dumps({"fresca": "true" if fresca else "false", "carga": chave, "origem": origem}),
        },
    )


def registrar_carga_fresca(conn: Connection, chave: str, resultado: Any, origem: str = "financas_atualizacao") -> None:
    """Hook de `carregar`: o dado acabou de vir de uma extração nova (a atualização diária ou o `run_etl --ceap`)."""
    registrar_carga(conn, chave, resultado, True, origem)


def registrar_carga_do_git(conn: Connection, chave: str, resultado: Any, origem: str = "deploy") -> None:
    """Hook de `carregar`: o dado veio do retrato do git (semeadura do deploy, recarga manual). Revoga a posse do timer."""
    registrar_carga(conn, chave, resultado, False, origem)


def carregar(
    engine: Engine,
    processed_dir: Optional[Path] = None,
    chaves: Optional[Iterable[str]] = None,
    ao_confirmar: Optional[Callable[[Connection, str, Any], None]] = None,
) -> Dict[str, Any]:
    """
    Executa as cargas (todas, ou só as `chaves`), cada uma na sua transação; uma que falha não impede as demais e o erro
    sobe no fim. Chave desconhecida levanta ValueError antes de tocar no banco. `ao_confirmar(conn, chave, resultado)`
    roda DENTRO da transação da chave, depois de a carga gravar: o que ele grava vale ou some junto com a carga.
    """
    pasta = Path(processed_dir or PROCESSED_DATA_DIR)
    escolhidas = None if chaves is None else tuple(chaves)
    if escolhidas is not None:
        desconhecidas = [c for c in escolhidas if c not in {chave for chave, _ in CARGAS}]
        if desconhecidas:
            raise ValueError(f"cargas de finanças desconhecidas: {desconhecidas}")
    resultados: Dict[str, Any] = {}
    falhas: List[str] = []
    for chave, funcao in CARGAS:
        if escolhidas is not None and chave not in escolhidas:
            continue
        try:
            with engine.begin() as conn:
                resultados[chave] = funcao(conn, pasta)
                if ao_confirmar is not None:
                    ao_confirmar(conn, chave, resultados[chave])
            logger.info("Finanças — %s: %s", chave, resultados[chave])
        except Exception as exc:  # noqa: BLE001 - isolada de propósito; relatada abaixo
            # o erro do banco traz os valores da linha no DETAIL: só a descrição saneada vai para o log e para o erro final
            descricao = descricao_do_erro(exc)
            logger.error(
                "Carga de finanças '%s' falhou: %s", chave, descricao, exc_info=not isinstance(exc, DBAPIError)
            )
            falhas.append(f"{chave}: {descricao}")
    if falhas:
        raise RuntimeError("; ".join(falhas))
    return resultados
