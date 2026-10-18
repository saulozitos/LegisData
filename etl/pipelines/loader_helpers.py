"""
Funções puras da carga (sem acesso a banco): conversões, classificação, resolução de autores e de partidos.
Separadas do `db_loader` para poderem ser testadas sem Postgres e reutilizadas pelos scripts de saneamento.
"""

import math
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from etl.utils.names import (
    NON_PERSON_AUTHORS,
    build_unique_name_map,
    chave_sigla,
    first_signatory,
    normalize_name_tokens,
)
from etl.utils.provenance import is_trusted

# Início da 57ª legislatura (1º/fev/2023): único limite inferior de observação que se conhece para quem está
# "em exercício" quando a fonte não informa a data de filiação/mandato.
LEGISLATURA_ATUAL = 57
LEGISLATURA_ATUAL_INICIO = date(2023, 2, 1)

SEM_PARTIDO = "S.PART."


def texto(valor: Any) -> Optional[str]:
    """Texto sem espaços nas pontas; vazio ou None viram None."""
    if valor is None or not isinstance(valor, (str, int, float)):  # dict/list não viram texto (nem a sua repr)
        return None
    if isinstance(valor, float) and valor != valor:
        return None
    limpo = str(valor).strip()
    return limpo or None


def inteiro(valor: Any) -> Optional[int]:
    """Inteiro ou None para vazio, bool, número com parte fracionária e o que não converte."""
    if valor is None or valor == "" or isinstance(valor, bool):
        return None
    try:
        if isinstance(valor, float) and not valor.is_integer():
            return None
        return int(valor)
    except (TypeError, ValueError, OverflowError):
        return None


def inteiro_em(valor: Any, minimo: int, maximo: int) -> Optional[int]:
    """Inteiro dentro do intervalo fechado [minimo, maximo]; fora dele ou inválido, None."""
    numero = inteiro(valor)
    return numero if numero is not None and minimo <= numero <= maximo else None


def normalizar_sigla_presenca(sigla: Any) -> Optional[str]:
    """Sigla de partido vinda das fontes de presença -> sigla canônica; None quando a fonte não registra partido.

    A Câmara publica "s/partido" para quem não tem partido (vira `S.PART.`) e "sem registro" quando não há informação
    (vira None, pois não é um partido).
    """
    texto = str(sigla).strip() if sigla is not None else ""
    if not texto or texto.lower() == "sem registro":
        return None
    if texto.lower() == "s/partido":
        return SEM_PARTIDO
    return texto


def _dec(value: Any) -> Optional[Decimal]:
    """Decimal a partir de número/str; None/NaN/vazio -> None. Zero legítimo continua sendo Decimal('0')."""
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and not value.strip():
        return None
    try:
        numero = Decimal(str(value))
    except InvalidOperation:
        return None
    return numero if numero.is_finite() else None


# Limites (exclusivos) das colunas monetárias do schema fin: numeric(P,2) comporta valores abaixo de 10**(P-2).
# Janela de anos aceita nas cargas (decisão D8: começa em 1995; o teto barra ano digitado errado)
ANO_MINIMO = 1995
ANO_MAXIMO = 2100
LIMITE_CEAP = Decimal(10) ** 12  # numeric(14,2)
LIMITE_EMENDA = Decimal(10) ** 14  # numeric(16,2)
LIMITE_REMUNERACAO = Decimal(10) ** 10  # numeric(12,2)
LIMITE_TSE = Decimal(10) ** 13  # numeric(15,2)


def decimal_de(value: Any, limite: Decimal = LIMITE_CEAP) -> Optional[Decimal]:
    """Decimal finito e dentro da faixa da coluna (`limite`, exclusivo); qualquer outra coisa vira None."""
    numero = _dec(value)
    return numero if numero is not None and abs(numero) < limite else None


def _texto_ou_none(value: Any) -> Optional[str]:
    """Texto aparado; None/NaN/vazio -> None (CSV do pandas devolve NaN para célula vazia)."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    texto = str(value).strip()
    return texto or None


def _to_date(value: Any) -> Optional[date]:
    """Converte 'AAAA-MM-DD...' / date / datetime em date; vazio/NaN/'none' -> None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    texto = str(value).strip()
    if not texto or texto.lower() in ("none", "nan", "nat"):
        return None
    try:
        return datetime.strptime(texto[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _to_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    texto = str(value).strip()
    try:
        return datetime.fromisoformat(texto) if "T" in texto else datetime.strptime(texto[:10], "%Y-%m-%d")
    except ValueError:
        return None


def legislatura_datas(numero: int) -> Tuple[date, date]:
    """Início e fim (1º/fev a 31/jan) de uma legislatura. A 57ª vai de 2023-02-01 a 2027-01-31."""
    ano_inicio = LEGISLATURA_ATUAL_INICIO.year + 4 * (int(numero) - LEGISLATURA_ATUAL)
    return date(ano_inicio, 2, 1), date(ano_inicio + 4, 1, 31)


def classify_proposition_impact(tipo: str, numero: int, ano: int, titulo: str, ementa: str):
    """
    Classifica a proposição em eixos temáticos por palavras-chave. Sem correspondência devolve (None, None):
    antes, o eixo era `(numero + ano) % 5`, ou seja, um eixo ALEATÓRIO atribuído como se fosse análise.
    """
    t = f"{titulo} {ementa}".lower()
    tipo = (tipo or "").upper()

    # 1. Matérias estruturantes explícitas — por (tipo, número, ano), não só pelo número
    if (tipo == "PLP" and numero == 93 and ano == 2023) or "arcabouço fiscal" in t or "regime fiscal sustentável" in t:
        return "Responsabilidade Fiscal", "Responsabilidade Fiscal, Regulação Macroeconômica"
    if (
        (tipo == "PEC" and numero == 45 and ano == 2019)
        or "reforma tributária" in t
        or ("tributária" in t and "consumo" in t)
    ):
        return "Tributação & Renda", "Tributação & Renda, Desoneração Corporativa"
    if (tipo == "MPV" and numero == 1172 and ano == 2023) or "salário mínimo" in t:
        return "Transferência de Renda", "Transferência de Renda, Direitos Trabalhistas, Tributação & Renda"
    if (tipo == "MPV" and numero == 1184 and ano == 2023) or "fundos exclusivos" in t or "offshores" in t:
        return "Tributação & Renda", "Tributação & Renda, Regulação de Mercado"

    # Heurística temática neutra
    if any(k in t for k in ["renda", "social", "pobreza", "bolsa família", "benefício", "assistência"]):
        return "Transferência de Renda", "Transferência de Renda, Bem-estar Social"
    if any(k in t for k in ["trabalho", "trabalhador", "emprego", "clt", "salário", "jornada"]):
        return "Direitos Trabalhistas", "Direitos Trabalhistas, Relações de Trabalho"
    if any(k in t for k in ["imposto", "tribut", "icms", "ipi", "taxa", "receita"]):
        return "Tributação & Renda", "Tributação & Renda, Finanças Públicas"
    if any(k in t for k in ["desonera", "incentivo fiscal", "crédito", "empresa", "corporat", "setor produtivo"]):
        return "Desoneração Corporativa", "Desoneração Corporativa, Estímulo Econômico"
    if any(k in t for k in ["fiscal", "orçamento", "gasto", "dívida", "lrf", "meta fiscal"]):
        return "Responsabilidade Fiscal", "Responsabilidade Fiscal, Contas Públicas"
    if any(k in t for k in ["concorrência", "tarifa", "agência", "mercado", "comércio", "regulamenta"]):
        return "Regulação de Mercado", "Regulação de Mercado, Ambiente de Negócios"
    if any(k in t for k in ["penal", "crime", "segurança", "polícia", "justiça", "pena"]):
        return "Segurança & Cidadania", "Segurança & Cidadania, Direitos Fundamentais"
    if any(k in t for k in ["obra", "transporte", "energia", "saneamento", "rodovia", "infraestrutura"]):
        return "Infraestrutura & Desenvolvimento", "Infraestrutura & Desenvolvimento"

    return None, None


# Padrões dos contatos que versões anteriores do loader INVENTAVAM a partir do id do parlamentar.
_EMAIL_INVENTADO = re.compile(r"^(dep|sen)\.\d+@(camara|senado)\.leg\.br$")
_SALA_INVENTADA = re.compile(r"^(Anexo IV, Gabinete \d+|Ala Filinto Müller, Gabinete \d{2})$")
_TEL_INVENTADO = re.compile(r"^\(61\) (3215-5\d{3}|3303-\d{4})$")


def limpar_contatos_inventados(pol: Any) -> bool:
    """Remove contatos que carregam o padrão exato dos valores sintéticos antigos. Devolve True se limpou algo."""
    alterou = False
    if pol.email and _EMAIL_INVENTADO.match(pol.email):
        pol.email = None
        alterou = True
    if pol.cabinet_room and _SALA_INVENTADA.match(pol.cabinet_room):
        pol.cabinet_room = None
        if pol.cabinet_phone and _TEL_INVENTADO.match(pol.cabinet_phone):
            pol.cabinet_phone = None
        alterou = True
    return alterou


def resolve_party_id(party_map: Dict[str, Any], sigla: Optional[str]) -> Optional[Any]:
    """Resolve sigla -> id de partido (exata, depois maiúscula). Sigla vazia => 'Sem Partido'."""
    if not sigla or (isinstance(sigla, float) and sigla != sigla):
        return party_map.get(SEM_PARTIDO)
    sigla = str(sigla).strip()
    return party_map.get(sigla) or party_map.get(sigla.upper())


class AuthorResolver:
    """
    Resolve o nome de autor de uma proposição para um Politician.id.

    Ordem: (1) ids oficiais; (2) nome do PRIMEIRO signatário igual ao nome eleitoral/civil bruto;
    (3) igualdade do nome normalizado; (4) igualdade do CONJUNTO de tokens. Em (2)-(4) o nome precisa ser
    único na base: homônimos resolvem para None. A regra antiga "tokens do nome eleitoral ⊂ tokens do autor
    com até 1 token extra" ligava "Flávio Dino" a "Flávio Bolsonaro" e "Gil Diniz" a "Gil"; foi removida.
    """

    def __init__(self, politicians: Iterable[Any], deputy_map: Dict[int, Any], senator_map: Dict[int, Any]):
        self.deputy_map = deputy_map
        self.senator_map = senator_map
        pols = list(politicians)
        self.raw = build_unique_name_map(
            [(p.id, (p.electoral_name or "").strip()) for p in pols if p.electoral_name]
            + [(p.id, (p.civil_name or "").strip()) for p in pols if p.civil_name]
        )
        # chave bruta (sem normalização agressiva) -> id único
        self.raw_exact: Dict[str, Any] = {}
        contagem: Dict[str, set] = {}
        for p in pols:
            for nome in (p.electoral_name, p.civil_name):
                if nome:
                    contagem.setdefault(nome.strip(), set()).add(p.id)
        self.raw_exact = {k: next(iter(v)) for k, v in contagem.items() if len(v) == 1}

        tokens: Dict[frozenset, set] = {}
        for p in pols:
            for nome in (p.electoral_name, p.civil_name):
                toks = frozenset(normalize_name_tokens(nome).split()) if nome else frozenset()
                if len(toks) >= 2:
                    tokens.setdefault(toks, set()).add(p.id)
        self.token_sets = {k: next(iter(v)) for k, v in tokens.items() if len(v) == 1}

    def resolve(
        self,
        autor_nome_raw: Optional[str],
        camara_id: Optional[int] = None,
        senado_id: Optional[int] = None,
    ) -> Optional[Any]:
        if camara_id and camara_id in self.deputy_map:
            return self.deputy_map[camara_id]
        if senado_id and senado_id in self.senator_map:
            return self.senator_map[senado_id]
        if not autor_nome_raw:
            return None

        primeiro = first_signatory(autor_nome_raw)
        for candidato in (autor_nome_raw.strip(), primeiro):
            if candidato in self.raw_exact:
                return self.raw_exact[candidato]

        norm = normalize_name_tokens(primeiro)
        if not norm or norm in NON_PERSON_AUTHORS:
            return None
        if norm in self.raw:
            return self.raw[norm]

        toks = frozenset(norm.split())
        if len(toks) >= 2 and toks in self.token_sets:
            return self.token_sets[toks]
        return None


# ── composição do Congresso ──────────────────────────────────────────────────────────────────────────────────────
ALINHAMENTOS = {"BASE_GOVERNO", "INDEPENDENTE_CENTRO", "OPOSICAO", "NAO_CLASSIFICADO"}


def bancadas_da_casa(casa: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Une as bancadas exibidas (`cadeiras`) e as eleitas segundo o TSE (`cadeiras_tse`) por partido. A união usa a chave
    normalizada da sigla ('PCdoB' da curadoria e 'PC DO B' do TSE são o mesmo partido); a sigla gravada é a da curadoria.
    """
    por_partido: Dict[str, Dict[str, Any]] = {}
    for b in (x for x in casa.get("bancadas") or [] if isinstance(x, dict)):
        sigla = texto(b.get("partido"))
        if not sigla:
            continue
        alinhamento = texto(b.get("alinhamento")) or "NAO_CLASSIFICADO"
        por_partido[chave_sigla(sigla)] = {
            "sigla": sigla,
            "cadeiras": inteiro(b.get("cadeiras")),
            "cadeiras_tse": None,
            "alinhamento": alinhamento if alinhamento in ALINHAMENTOS else "NAO_CLASSIFICADO",
            "cor_hex": texto(b.get("cor_hex")),
        }
    for b in (x for x in casa.get("bancadas_eleitas_tse") or [] if isinstance(x, dict)):
        sigla = texto(b.get("partido"))
        if not sigla:
            continue
        linha = por_partido.setdefault(
            chave_sigla(sigla),
            {"sigla": sigla, "cadeiras": None, "cadeiras_tse": None, "alinhamento": None, "cor_hex": None},
        )
        linha["cadeiras_tse"] = inteiro(b.get("cadeiras"))
    linhas = [b for b in por_partido.values() if b["cadeiras"] is not None or b["cadeiras_tse"] is not None]
    # a ordem da curadoria (desempates entre partidos de mesmo tamanho) é preservada
    for ordem, linha in enumerate(linhas):
        linha["ordem"] = ordem
    return linhas


def validar_soma_das_bancadas(bancadas: List[Dict[str, Any]], total: int, rotulo: str) -> None:
    """A soma das cadeiras exibidas não pode passar do total da Casa (a menos seria só parte sem classificação)."""
    soma = sum(b["cadeiras"] or 0 for b in bancadas)
    if soma > total:
        raise ValueError(f"Composição de '{rotulo}': as bancadas somam {soma} cadeiras, mais que o total ({total})")


# ── PNAD ─────────────────────────────────────────────────────────────────────────────────────────────────────────
DISTRIBUICOES_PNAD = (
    "domicilios_renda_total",
    "pessoas_renda_domiciliar",
    "pessoas_renda_per_capita",
    "ocupados_renda_trabalho",
)
N_FAIXAS_PNAD = 8
SOMA_PERCENTUAL_TOLERANCIA = 1.0  # pontos percentuais de folga para o arredondamento


def percentual_valido(valor: Any) -> Optional[List[float]]:
    """Lista de 8 percentuais numéricos e finitos que somam cerca de 100; qualquer outra coisa é None."""
    if not isinstance(valor, list) or len(valor) != N_FAIXAS_PNAD:
        return None
    try:
        numeros = [float(v) for v in valor]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(n) for n in numeros):
        return None
    return numeros if abs(sum(numeros) - 100.0) <= SOMA_PERCENTUAL_TOLERANCIA else None


def ano_pnad_valido(ano: Any, entrada: Any) -> bool:
    """
    O ano só entra com chave entre 1995 e 2100, visita (1 a 5), salário mínimo positivo e as duas distribuições usadas
    nas classes (domicílios e pessoas). Nada é presumido: sem visita no arquivo, o ano é pulado.
    """
    if inteiro_em(ano, 1995, 2100) is None or not isinstance(entrada, dict):
        return False
    if inteiro_em(entrada.get("visita"), 1, 5) is None:
        return False
    try:
        salario = float(entrada.get("salario_minimo_brl"))
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(salario) and salario > 0):
        return False
    nacional = entrada.get("nacional")
    if not isinstance(nacional, dict):
        return False
    return all(
        isinstance(nacional.get(c), dict) and percentual_valido(nacional[c].get("percentual")) is not None
        for c in ("domicilios_renda_total", "pessoas_renda_domiciliar")
    )


def linhas_pnad_do_ano(entrada: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Uma linha por escopo (BR ou UF) e distribuição com percentuais válidos."""
    escopos = {"BR": entrada.get("nacional") or {}}
    uf_do_ano = entrada.get("uf")
    for uf, dados in uf_do_ano.items() if isinstance(uf_do_ano, dict) else []:
        escopos[str(uf).upper()] = dados or {}
    linhas = []
    for escopo, dados in escopos.items():
        for distribuicao in DISTRIBUICOES_PNAD:
            info = dados.get(distribuicao) if isinstance(dados, dict) else None
            percentual = percentual_valido(info.get("percentual")) if isinstance(info, dict) else None
            if percentual is None:
                continue
            linhas.append(
                {
                    "escopo": escopo,
                    "distribuicao": distribuicao,
                    "total": info.get("total_estimado"),
                    "media": info.get("media_nominal_brl"),
                    "percentual": percentual,
                }
            )
    return linhas


# ── Finanças (schema `fin`) ──────────────────────────────────────────────────────────────────────────────────────────
UF_POR_NOME = {
    "ACRE": "AC",
    "ALAGOAS": "AL",
    "AMAPA": "AP",
    "AMAZONAS": "AM",
    "BAHIA": "BA",
    "CEARA": "CE",
    "DISTRITO FEDERAL": "DF",
    "ESPIRITO SANTO": "ES",
    "GOIAS": "GO",
    "MARANHAO": "MA",
    "MATO GROSSO": "MT",
    "MATO GROSSO DO SUL": "MS",
    "MINAS GERAIS": "MG",
    "PARA": "PA",
    "PARAIBA": "PB",
    "PARANA": "PR",
    "PERNAMBUCO": "PE",
    "PIAUI": "PI",
    "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS",
    "RONDONIA": "RO",
    "RORAIMA": "RR",
    "SANTA CATARINA": "SC",
    "SAO PAULO": "SP",
    "SERGIPE": "SE",
    "TOCANTINS": "TO",
}
_UFS = frozenset(UF_POR_NOME.values())
# CPF solto no nome (MEI vem como "NOME 012.345.678-00" ou "NOME 09876543200"): 10 ou 11 dígitos, juntos ou separados por
# até 3 caracteres entre ponto, hífen, barra, vírgula, dois-pontos, sublinhado e espaço (por exemplo " - "). Dígitos de
# outros alfabetos, de largura total e hífens Unicode viram ASCII antes (`_ascii`). O CNPJ formatado vem primeiro na alternância para não ser lido
# como um CPF parcial; CNPJ sem pontuação (14 dígitos) nunca casa porque a sequência exige 10 ou 11 no total.
_SEQUENCIA_CPF = re.compile(
    r"(?<![0-9])(?P<cnpj>[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2})(?![0-9])"
    r"|(?<![0-9])(?:[0-9][\s.\-/_,:]{0,3}){9,10}[0-9](?![0-9])"
)
_MASCARA_CPF = re.compile(r"^\*{3}\.[0-9]{3}\.[0-9]{3}-\*{2}$")
TIPOS_DE_AUTOR_INSTITUCIONAL = ("BANCADA_ESTADUAL", "COMISSAO_INSTITUCIONAL", "RELATOR_GERAL")


def so_digitos(valor: Any) -> str:
    return re.sub(r"[^0-9]", "", _ascii(valor)) if valor is not None else ""


def cnpj_do_fornecedor(valor: Any) -> Optional[str]:
    """
    Os 14 dígitos de um CNPJ. CPF (11 dígitos), documento truncado e o CNPJ de enchimento que a Câmara usa para
    lançamentos sem fornecedor ("CELULAR FUNCIONAL", "RAMAL") viram None: CPF nunca é gravado (decisão D3).
    """
    digitos = so_digitos(valor)
    if len(digitos) != 14 or digitos[:12] == "0" * 12:
        return None
    return digitos


def _ascii(valor: Any) -> str:
    """
    Texto com qualquer dígito Unicode (árabe-índico, largura total...) trocado pelo dígito ASCII equivalente, hífens
    Unicode (U+2010, travessão, sinal de menos) trocados por '-' e espaços Unicode por espaço comum.
    """
    normal = unicodedata.normalize("NFKC", str(valor or ""))
    saida = []
    for c in normal:
        if unicodedata.decimal(c, None) is not None:
            saida.append(str(unicodedata.decimal(c)))
        elif unicodedata.category(c) == "Pd" or c == "\u2212":
            saida.append("-")
        elif unicodedata.category(c) in ("Zs", "Zl", "Zp"):
            saida.append(" ")
        else:
            saida.append(c)
    return "".join(saida)


def _sem_cpf(achado: "re.Match[str]") -> str:
    trecho = achado.group(0)
    return trecho if achado.group("cnpj") or len(so_digitos(trecho)) not in (10, 11) else " "


def nome_do_fornecedor(valor: Any) -> str:
    """Nome do fornecedor sem CPF embutido (MEI aparece como 'NOME 09876543200' na fonte); vazio vira o rótulo padrão."""
    limpo = " ".join(_SEQUENCIA_CPF.sub(_sem_cpf, _ascii(texto(valor))).split())
    return limpo or "Fornecedor não identificado"


def nome_sem_cpf(valor: Any) -> Optional[str]:
    """Nome de pessoa ou empresa sem CPF embutido; None quando não sobra nada."""
    limpo = " ".join(_SEQUENCIA_CPF.sub(_sem_cpf, _ascii(texto(valor))).split())
    return limpo or None


# CPF em texto livre (descrição de bens, detalhes de certidão): 10 ou 11 dígitos com até 3 separadores entre eles, como na
# regra dos nomes, mas sem cortar valores em reais nem números maiores:
#  - "R$ 12345678900" (precedido do símbolo da moeda) é preservado;
#  - o lookbehind recusa começo no meio de um número ("1.234.567.890,00": dígito + ponto/vírgula/hífen antes) e o
#    lookahead recusa fim antes de casa decimal ("890,00") ou de mais um dígito;
#  - CNPJ formatado vem primeiro na alternância e nunca é cortado.
# CPF colado a letra, vírgula, ponto ou hífen de rótulo ("CPF-012.345.678-00", "Réu,012.345.678-00") é removido.
_CPF_EM_TEXTO = re.compile(
    r"(?P<moeda>R\$\s*)?(?:(?<![0-9])(?P<cnpj>[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2})(?![0-9])"
    r"|(?<![0-9])(?<![0-9][.,\-])(?:[0-9][\s.\-/_,:]{0,3}){9,10}[0-9](?![0-9])(?![.,][0-9]))"
)


def _tira_cpf_do_texto(achado: "re.Match[str]") -> str:
    return achado.group(0) if achado.group("moeda") or achado.group("cnpj") else " "


def texto_sem_cpf(valor: Any) -> Optional[str]:
    """Texto livre da fonte sem CPF embutido (decisão D3); None quando não sobra nada."""
    bruto = texto(valor)
    if bruto is None:
        return None
    limpo = " ".join(_CPF_EM_TEXTO.sub(_tira_cpf_do_texto, _ascii(bruto)).split())
    return limpo or None


_CNPJ_CANONICO = re.compile(r"(?:[0-9]{14}|[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2})")


def documento_do_doador(valor: Any) -> Optional[str]:
    """
    Documento do doador como o TSE publica: CNPJ inteiro (14 dígitos, sem pontuação ou no formato NN.NNN.NNN/NNNN-NN)
    ou CPF já mascarado ('***.060.603-**'). CPF completo (11 dígitos, ou 10 quando perdeu o zero à esquerda) é mascarado
    aqui. Qualquer outro formato, inclusive máscara parcial e CNPJ com pontuação fora do padrão, vira None: CPF nunca é
    gravado (decisão D3) e o texto cru nunca passa adiante.
    """
    bruto = texto(valor)
    if bruto is None:
        return None
    mascara = _ascii(
        bruto
    )  # a máscara da fonte com dígitos de outro alfabeto vira ASCII (o CHECK do banco só aceita [0-9])
    if _MASCARA_CPF.fullmatch(mascara):
        return mascara
    if _CNPJ_CANONICO.fullmatch(bruto):
        return bruto
    if "*" in bruto:
        return None
    digitos = so_digitos(bruto)
    if len(digitos) in (10, 11) and re.fullmatch(r"[0-9.\-\s]+", bruto):
        digitos = digitos.zfill(11)
        return f"***.{digitos[3:6]}.{digitos[6:9]}-**"
    return None


def tipo_do_autor(autor: Any, tipo_emenda: Any) -> str:
    """Tipo de autor da emenda: bancada estadual, relator-geral, comissão ou parlamentar individual."""
    nome = normalize_name_tokens(texto(autor) or "")
    tipo = texto(tipo_emenda) or ""
    if "bancada" in nome or tipo == "Emenda de Bancada":
        return "BANCADA_ESTADUAL"
    if "relator" in nome or tipo == "Emenda de Relator":
        return "RELATOR_GERAL"
    if nome.startswith(("com ", "comissao")) or tipo == "Emenda de Comissão":
        return "COMISSAO_INSTITUCIONAL"
    return "INDIVIDUAL"


def uf_da_localidade(localidade: Any) -> Optional[str]:
    """
    UF do destino da emenda: 'SÃO PAULO (UF)' é o estado e 'CAMPINAS - SP' é um município. Região, 'Nacional',
    'MÚLTIPLO' e 'Exterior' não têm UF (None).
    """
    bruto = texto(localidade)
    if bruto is None:
        return None
    if bruto.upper().endswith("(UF)"):
        return UF_POR_NOME.get(normalize_name_tokens(bruto[:-4]).upper())
    sufixo = re.search(r"\s-\s([A-Z]{2})$", bruto)
    return sufixo.group(1) if sufixo and sufixo.group(1) in _UFS else None


# ── Elegibilidade dos registros das fontes de finanças: regra única do loader e da reconciliação ─────────────────────
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


def ler_ceap(dados: Any) -> Tuple[Optional[Dict[Tuple[int, str], Decimal]], Optional[str]]:
    """
    Totais por (ano, tipo) de um parlamentar do arquivo, ou (None, motivo) quando ele não entra: "sem_proveniencia",
    "sem_identificador" (sem id não há como saber a fonte, Câmara ou Senado) ou "sem_detalhe_por_ano". É a regra única
    de elegibilidade: a reconciliação usa esta mesma função.
    """
    if not isinstance(dados, dict) or not is_trusted(dados):
        return None, "sem_proveniencia"
    if not (dados.get("camara_id") or dados.get("senado_id")):
        return None, "sem_identificador"
    por_ano_tipo = dados.get("por_ano_tipo")
    if not isinstance(por_ano_tipo, dict) or not por_ano_tipo:
        return None, "sem_detalhe_por_ano"
    return valores_da_ceap(dados), None


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
