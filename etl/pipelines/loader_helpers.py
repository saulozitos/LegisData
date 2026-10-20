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
from sqlalchemy.exc import DBAPIError

from etl.utils.names import (
    NON_PERSON_AUTHORS,
    build_unique_name_map,
    chave_sigla,
    first_signatory,
    normalize_name_tokens,
    normalize_plain,
)
from etl.utils.provenance import is_trusted
from etl.utils.rotulos import DOADOR_NAO_IDENTIFICADO, FORNECEDOR_NAO_IDENTIFICADO

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


LIMITE_INT4 = 2**31 - 1  # colunas `integer` do Postgres: um valor acima derrubaria a carga inteira


def contagem_int4(valor: Any) -> Optional[int]:
    """Contagem não negativa que cabe numa coluna `integer`; negativa, fracionária, inválida ou acima do teto, None."""
    return inteiro_em(valor, 0, LIMITE_INT4)


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


def soma_na_faixa(valor: Decimal, limite: Decimal) -> Optional[Decimal]:
    """
    Total de várias parcelas já arredondado em centavos, ou None se estoura a faixa da coluna. `decimal_de` limita cada
    parcela; a soma delas (por ano e tipo, por fornecedor, entre fontes, entre linhas repetidas) pode passar do limite
    e, como o Postgres arredonda antes de conferir, um valor logo abaixo dele também estoura: sem esta conferência o
    `numeric field overflow` derrubaria a carga inteira por causa de uma linha.
    """
    centavos = valor.quantize(Decimal("0.01"))
    return centavos if abs(centavos) < limite else None


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
# Formas de CPF reconhecidas (o texto já passou por `_ascii`: dígitos, hífens e espaços Unicode viraram ASCII):
#  - canônica NNN.NNN.NNN-NN, em qualquer vizinhança ("2020-012.345.678-00", "...-00,987..."), até colada a um dígito
#    anterior ("12012.345.678-00" perde o CPF e deixa o "12"): nunca é valor em reais, então é removida sempre, mesmo
#    depois de "R$";
#  - grupos 3-3-3-2 com até 3 caracteres de separação (qualquer um que não seja letra, dígito ou sublinhado, além do
#    próprio sublinhado) ou sem separação, e 10 dígitos seguidos (CPF que perdeu o zero à esquerda). Em texto livre, o separador antes dos dois últimos dígitos
#    nunca é só uma vírgula, porque "123.456.789,00" é valor em reais; em nomes não há valor em reais, e a vírgula vale.
# Data, hora, telefone, lista numerada e número de processo não têm o desenho 3-3-3-2 e ficam intactos. O CNPJ formatado
# vem primeiro na alternância para não ser lido como CPF parcial; CNPJ sem pontuação (14 dígitos) nunca casa porque a
# sequência é limitada por não-dígitos.
_SEP = r"[\W_]{1,3}"
_SEP_FINAL_TEXTO = r"(?:[^\w,]|_){1,3}"
_CNPJ_FORMATADO = r"(?<![0-9])(?P<cnpj>[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2})(?![0-9])"
_CPF_CANONICO = r"[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}(?![0-9])"


def _cpf_agrupado(sep_final: str) -> str:
    return rf"[0-9]{{3}}(?:{_SEP})?[0-9]{{3}}(?:{_SEP})?[0-9]{{3}}(?:{sep_final})?[0-9]{{2}}|[0-9]{{10}}"


_SEQUENCIA_CPF = re.compile(rf"{_CNPJ_FORMATADO}|{_CPF_CANONICO}|(?<![0-9])(?:{_cpf_agrupado(_SEP)})(?![0-9])")
_MASCARA_CPF = re.compile(r"^\*{3}\.[0-9]{3}\.[0-9]{3}-\*{2}$")
TIPOS_DE_AUTOR_INSTITUCIONAL = ("BANCADA_ESTADUAL", "COMISSAO_INSTITUCIONAL", "RELATOR_GERAL")


def so_digitos(valor: Any) -> str:
    return re.sub(r"[^0-9]", "", _ascii(texto(valor))) if valor is not None else ""


def cpf_valido(digitos: str) -> bool:
    """11 dígitos com os dois dígitos verificadores de um CPF (e não todos iguais)."""
    if len(digitos) != 11 or not (digitos.isascii() and digitos.isdigit()) or len(set(digitos)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d) * peso for d, peso in zip(digitos[:tamanho], range(tamanho + 1, 1, -1)))
        if int(digitos[tamanho]) != (soma * 10 % 11) % 10:
            return False
    return True


def cnpj_dv_valido(digitos: str) -> bool:
    """14 dígitos com os dois dígitos verificadores de um CNPJ (e não todos iguais)."""
    if len(digitos) != 14 or not (digitos.isascii() and digitos.isdigit()) or len(set(digitos)) == 1:
        return False
    for tamanho, pesos in ((12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)), (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))):
        resto = sum(int(d) * p for d, p in zip(digitos[:tamanho], pesos)) % 11
        if int(digitos[tamanho]) != (0 if resto < 2 else 11 - resto):
            return False
    return True


# Raízes (8 primeiros dígitos) de CNPJs reais que começam com zeros e que, por acaso, também fecham como "000"+CPF. Medidas nos
# dados versionados (Banco do Brasil e dois doadores pessoa jurídica). Só elas escapam da regra "000+CPF é CPF"; qualquer
# outro número de 14 dígitos com enchimento e CPF válido nos 11 últimos é tratado como CPF, mesmo que feche como CNPJ
# (cerca de 1,4% dos CPFs com enchimento "000" fecham o CNPJ por acaso: perder um CNPJ raro é o lado seguro da D3).
RAIZES_ZERADAS_CONHECIDAS = frozenset({"00000000", "00000531", "00070509"})
_MARCADOR_DE_PJ = re.compile(
    r"\b(?:LTDA|EIRELI|EPP|ME|S/?A|S\.A\.?|BANCO|COOPERATIVA|ASSOCIA[CÇ][AÃ]O|FUNDA[CÇ][AÃ]O|PARTIDO|CIA|COMPANHIA|"
    r"EMPRESA|COM[EÉ]RCIO|IND[UÚ]STRIA|COMERCIAL)\b",
    re.IGNORECASE,
)


def nome_de_pj(nome: Any) -> bool:
    """True se o nome traz um marcador de pessoa jurídica (LTDA, S/A, BANCO...): desempata um documento ambíguo."""
    return bool(_MARCADOR_DE_PJ.search(_ascii(texto(nome)))) if nome is not None else False


def cpf_com_zeros(digitos: str, pj: bool = False) -> bool:
    """
    CPF válido nos 11 últimos dígitos com zeros de enchimento à esquerda (0 a quantos forem). Com exatamente 14 dígitos o
    número também pode ser um CNPJ de raiz zerada. Ele só é CNPJ (e não é tocado) se fecha nos dígitos verificadores de
    CNPJ E (a raiz é uma das conhecidas, ou `pj` diz que o nome é de pessoa jurídica). Fecha como CNPJ mas sem nada que
    o confirme: é tratado como CPF.
    """
    if len(digitos) < 11 or not set(digitos[:-11]) <= {"0"} or not cpf_valido(digitos[-11:]):
        return False
    if len(digitos) == 14 and cnpj_dv_valido(digitos) and (pj or digitos[:8] in RAIZES_ZERADAS_CONHECIDAS):
        return False
    return True


def cnpj_do_fornecedor(valor: Any, nome: Any = None) -> Optional[str]:
    """
    Os 14 dígitos de um CNPJ. CPF (11 dígitos), documento truncado, CPF com enchimento de zeros à esquerda (três zeros
    mais um CPF de 11 dígitos, desde que o número não feche como CNPJ) e o CNPJ de enchimento que a Câmara usa para
    lançamentos sem fornecedor ("CELULAR FUNCIONAL", "RAMAL") viram None: CPF nunca é gravado (decisão D3). Não exige que
    o dígito verificador do CNPJ feche (os dados de teste e parte da fonte têm CNPJs que não fecham); só barra o que é
    comprovadamente um CPF. `nome` (opcional) desempata o 14 dígitos que fecha como CNPJ: com marcador de pessoa jurídica
    no nome (LTDA, S/A, BANCO...) ele é CNPJ; sem isso, só as raízes zeradas conhecidas escapam.
    """
    digitos = so_digitos(valor)
    if len(digitos) != 14 or digitos[:12] == "0" * 12:
        return None
    if cpf_com_zeros(digitos, pj=nome_de_pj(nome)):
        return None
    return digitos


def _ascii(valor: Any) -> str:
    """
    Texto com qualquer dígito Unicode (árabe-índico, largura total...) trocado pelo dígito ASCII equivalente, hífens
    Unicode (U+2010, travessão, sinal de menos) trocados por '-', pontos médios por '.', espaços Unicode por espaço
    comum, caracteres invisíveis de formatação (largura zero, hífen suave) e marcas combinantes (U+034F, U+0301 que o NFKC
    não recompôs, seletores de variação) removidos e as "letras" Hangul que só ocupam
    espaço (U+115F, U+1160, U+3164, U+FFA0) trocadas por espaço, para não esconderem um separador de CPF.
    """
    normal = unicodedata.normalize("NFKC", str(valor or ""))
    saida = []
    for c in normal:
        categoria = unicodedata.category(c)
        if unicodedata.decimal(c, None) is not None:
            saida.append(str(unicodedata.decimal(c)))
        elif categoria == "Pd" or c == "\u2212":
            saida.append("-")
        elif c in "\u00b7\u2027\u2219\u22c5":
            saida.append(".")
        elif categoria in ("Zs", "Zl", "Zp") or c in "\u115f\u1160\u3164\uffa0":
            saida.append(" ")
        elif categoria not in (
            "Cf",
            "Mn",
            "Me",
        ):  # formatação invisível e marcas combinantes não separam dígitos de um CPF
            saida.append(c)
    return "".join(saida)


def _sem_cpf(achado: "re.Match[str]") -> str:
    if achado.group("cnpj"):  # CNPJ formatado fica, salvo se for um CPF com zeros de enchimento (que o CNPJ não fecha)
        return " " if cpf_com_zeros(so_digitos(achado.group("cnpj"))) else achado.group(0)
    return " "


def nome_do_fornecedor(valor: Any) -> str:
    """Nome do fornecedor sem CPF embutido (MEI aparece como 'NOME 09876543200' na fonte); vazio vira o rótulo padrão."""
    return nome_sem_cpf(valor) or FORNECEDOR_NAO_IDENTIFICADO


# Número de 12 dígitos colado ao nome de pessoa física na CEAP (visto nos dados reais: "FULANO DE TAL 500600700800").
# Não é CNPJ (14) nem CPF (11) e não dá para saber se é um CPF com enchimento ou outro documento pessoal: por precaução
# (decisão D3) ele sai do nome, junto com as variantes com ponto ou hífen entre os grupos ("12.345.678.901",
# "12345-678901", "1234.5678.9012") que somam 11 ou 12 dígitos. Fica o que parece outra coisa: CNPJ (14 dígitos, ou 13
# quando perdeu o zero inicial), data, ano ou lista de anos ("LOJA 2020 2021", "ARENA 2020-2021-2022") e telefone.
_DOCUMENTO_PESSOAL = re.compile(r"(?<![0-9])(?:[0-9]{12}|[0-9]+(?:[.\-][0-9]+){1,5})(?![0-9])")


def _tira_documento_pessoal(achado: "re.Match[str]") -> str:
    grupos = re.split(r"[.\-]", achado.group(0))
    total = sum(len(g) for g in grupos)
    so_anos = len(grupos) > 1 and all(len(g) == 4 and g[:2] in ("19", "20") for g in grupos)
    return " " if total in (11, 12) and not so_anos else achado.group(0)


# Qualquer sequência de dígitos com separadores entre os grupos (agrupamentos 4-4-3 ou 2-3-3-3, um dígito por espaço,
# separador largo, zeros de enchimento antes). Só sai quando é comprovadamente um CPF: os 11 últimos dígitos passam nos
# dígitos verificadores e o que vem antes são só zeros de enchimento. Vírgula e barra NÃO são separador: cada lado delas
# é avaliado sozinho (um CPF seguido de ", 2" ou de " / 2024" não escapa), e o CNPJ formatado e o valor em reais ficam
# inteiros porque nenhum de seus lados soma 11 dígitos. Linear: dígitos e separadores são classes disjuntas.
_DIGITOS_SEPARADOS = re.compile(r"(?<![0-9])[0-9]+(?:(?:[^\w,/]|_)+[0-9]+)*(?![0-9])")


def _digitos_de_cpf(bruto: str) -> bool:
    """True se a sequência (com separadores) é um CPF válido, com ou sem zeros de enchimento à esquerda."""
    return cpf_com_zeros(re.sub(r"[^0-9]", "", bruto))


def _tira_cpf_valido_separado(achado: "re.Match[str]") -> str:
    return " " if _digitos_de_cpf(achado.group(0)) else achado.group(0)


def cpfs_validos_em(valor: Any) -> int:
    """Quantos CPFs válidos o texto carrega, nas formas de separador que o saneamento (`nome_sem_cpf`) remove."""
    normal = _ascii(texto(valor))
    return sum(1 for achado in _DIGITOS_SEPARADOS.finditer(normal) if _digitos_de_cpf(achado.group(0)))


_CORRIDOS_12_A_14 = re.compile(r"(?<![0-9])[0-9]{12,14}(?![0-9])")
_CNPJ_FORMATADO_RE = re.compile(_CNPJ_FORMATADO)


_URL = re.compile(r"https?://\S+")


def cpfs_suspeitos_em(valor: Any, janelas: bool = True) -> int:
    """
    Para a guarda de D3 dos arquivos versionados, que precisa ser mais desconfiada que o saneamento: além de
    `cpfs_validos_em`, conta o CNPJ formatado que é "000"+CPF e qualquer janela de 11 dígitos com CPF válido dentro de um
    número corrido de 12 a 14 dígitos (um CPF colado a outros dígitos), exceto o de 14 que fecha como CNPJ. As janelas
    (`janelas=True`) valem para código escrito à mão; em dados (JSON/CSV/docs) códigos de emenda e de processo somam 12 a 14
    dígitos e dariam falso positivo, então a guarda as desliga ali. Endereços (URLs) não entram nas janelas.
    """
    normal = _ascii(texto(valor))
    achados = cpfs_validos_em(valor)
    achados += sum(1 for m in _CNPJ_FORMATADO_RE.finditer(normal) if cpf_com_zeros(so_digitos(m.group("cnpj"))))
    if not janelas:
        return achados
    for m in _CORRIDOS_12_A_14.finditer(_URL.sub(" ", normal)):
        d = m.group(0)
        if len(d) == 14 and cnpj_dv_valido(d):
            continue
        achados += any(cpf_valido(d[i : i + 11]) for i in range(len(d) - 10))
    return achados


def nome_sem_cpf(valor: Any) -> Optional[str]:
    """Nome de pessoa ou empresa sem CPF (nem número de documento pessoal de 11 ou 12 dígitos) embutido; None se nada sobra."""
    # primeiro o CPF comprovado por dígito verificador em qualquer agrupamento (leva junto os zeros de enchimento), depois as
    # formas do desenho 3-3-3-2 e, por fim, o número de 11 ou 12 dígitos de documento pessoal
    sem_cpf = _DIGITOS_SEPARADOS.sub(_tira_cpf_valido_separado, _ascii(texto(valor)))
    sem_cpf = _SEQUENCIA_CPF.sub(_sem_cpf, sem_cpf)
    limpo = " ".join(_DOCUMENTO_PESSOAL.sub(_tira_documento_pessoal, sem_cpf).split())
    return limpo or None


# CPF em texto livre (descrição de bens, detalhes de certidão): as mesmas formas dos nomes, sem cortar valores em reais
# nem números maiores. A forma canônica sai sempre. Fora dela, a sequência é preservada quando:
#  - vem precedida de "R$" ("R$ 12345678900"; mas "R$" seguido da forma canônica NÃO protege o CPF);
#  - são só dígitos corridos (10 ou 11) seguidos de vírgula e 1 ou 2 dígitos ("12345678900,50"); com separadores entre
#    os grupos ("111 222 333 44,50") o CPF sai. Uma lista de CPFs separados por vírgula também sai, porque o que vem
#    depois da vírgula tem mais de dois dígitos.
# O separador antes dos dois últimos dígitos nunca é só uma vírgula (`_SEP_FINAL_TEXTO`), então "1.234.567.890,12" e
# "123.456.789,00" não casam o desenho 3-3-3-2.
_CPF_EM_TEXTO = re.compile(
    rf"(?P<canon>{_CPF_CANONICO})"
    rf"|(?P<moeda>R\$\s*(?!{_CPF_CANONICO}))?(?:{_CNPJ_FORMATADO}"
    rf"|(?<![0-9])(?:{_cpf_agrupado(_SEP_FINAL_TEXTO)})(?![0-9]))"
)
_CASA_DECIMAL = re.compile(r",[0-9]{1,2}(?![0-9])")


def _tira_cpf_do_texto(achado: "re.Match[str]") -> str:
    if achado.group("canon"):
        return " "
    if achado.group("cnpj"):  # CNPJ formatado fica, salvo se for um CPF com zeros de enchimento
        return " " if cpf_com_zeros(so_digitos(achado.group("cnpj"))) else achado.group(0)
    if achado.group("moeda"):
        return achado.group(0)
    # só dígitos corridos seguidos de vírgula e 1 ou 2 dígitos são valor em reais; com separadores entre os grupos não
    if achado.group(0).isdigit() and _CASA_DECIMAL.match(achado.string, achado.end()):
        return achado.group(0)
    return " "


def texto_sem_cpf(valor: Any) -> Optional[str]:
    """
    Texto livre da fonte sem CPF embutido (decisão D3); None quando não sobra nada. Contrato: só as formas do desenho
    3-3-3-2 (e dez dígitos corridos) saem, preservando valores em reais; é mais frouxo que `nome_sem_cpf`, que também
    tira o CPF comprovado por dígito verificador em qualquer agrupamento. Campo livre que pode trazer documento solto
    (nome de pessoa, razão social) deve passar por `nome_sem_cpf`.
    """
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
        return None if cpf_com_zeros(so_digitos(bruto)) else bruto  # CPF com enchimento na coluna de CNPJ não passa
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
        # só acento, caixa e pontuação: `normalize_name_tokens` tira honoríficos e faria "DISTRITO FEDERAL" virar "DISTRITO"
        return UF_POR_NOME.get(normalize_plain(bruto[:-4]).upper())
    sufixo = re.search(r"\s-\s([A-Z]{2})$", bruto)
    return sufixo.group(1) if sufixo and sufixo.group(1) in _UFS else None


# ── Elegibilidade dos registros das fontes de finanças: regra única do loader e da reconciliação ─────────────────────
# Contrato comum: `ler_*(registro) -> (campos | None, motivo | None)`. Com campos, o motivo é None; sem eles, o motivo
# ("sem_proveniencia", "sem_identificador", "sem_detalhe_por_ano" ou "invalidas") diz por que o registro ficou de fora e
# vira chave da contagem de cada carga. `ler_registros_da_remuneracao` é a mesma regra no nível do arquivo.
def _totais_da_ceap(dados: Dict[str, Any]) -> Dict[Tuple[int, str], Decimal]:
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


def valores_da_ceap(dados: Dict[str, Any]) -> Dict[Tuple[int, str], Decimal]:
    """Total por (ano, tipo de despesa) de um parlamentar do arquivo, só os que cabem na coluna."""
    totais = _totais_da_ceap(dados)
    return {chave: total for chave, valor in totais.items() if (total := soma_na_faixa(valor, LIMITE_CEAP)) is not None}


def ler_ceap(dados: Any) -> Tuple[Optional[Dict[Tuple[int, str], Decimal]], Optional[str]]:
    """
    Totais por (ano, tipo) de um parlamentar do arquivo, ou (None, motivo) quando ele não entra: "sem_proveniencia",
    "sem_identificador" (sem id não há como saber a fonte, Câmara ou Senado), "sem_detalhe_por_ano" ou
    "total_fora_da_faixa" (um total de ano e tipo que não cabe na coluna: gasto parcial não vale como total). É a regra única
    de elegibilidade: a reconciliação usa esta mesma função.
    """
    if not isinstance(dados, dict) or not is_trusted(dados):
        return None, "sem_proveniencia"
    if not (dados.get("camara_id") or dados.get("senado_id")):
        return None, "sem_identificador"
    por_ano_tipo = dados.get("por_ano_tipo")
    if not isinstance(por_ano_tipo, dict) or not por_ano_tipo:
        return None, "sem_detalhe_por_ano"
    if any(soma_na_faixa(total, LIMITE_CEAP) is None for total in _totais_da_ceap(dados).values()):
        # o total de um (ano, tipo) que não cabe na coluna deixaria o gasto da pessoa incompleto: ela não entra
        return None, "total_fora_da_faixa"
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


TIPO_RECEITA_AGREGADA = "agregado"  # comparado sem caixa: a fonte marca a linha "Demais doadores" com este tipo
_DEMAIS_DOADORES = re.compile(r"\(\s*([0-9]{1,10})\s*\)\s*$")  # até 10 dígitos: o teto de `integer` é checado depois


def _quantidade_agregada(achado: "re.Match[str]") -> Optional[int]:
    """N de "Demais doadores (N)": de 1 até o teto de `integer`; zero ou acima dele, desconhecido."""
    numero = contagem_int4(achado.group(1))
    return numero if numero is not None and numero >= 1 else None


def ler_doacoes(item: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Uma prestação do arquivo: `{"ano": ano, "linhas": [linhas de doador]}`, ou (None, motivo) com "sem_proveniencia" ou
    "invalidas" (sem ano ou sem lista de doadores). Regra única de elegibilidade (loader e reconciliação).
    """
    if not isinstance(item, dict) or not is_trusted(item):
        return None, "sem_proveniencia"
    ano = inteiro_em(item.get("ano_eleicao"), ANO_MINIMO, ANO_MAXIMO)
    if ano is None or not isinstance(item.get("doadores"), list):
        return None, "invalidas"
    linhas = []
    for doador in item["doadores"]:
        valor = decimal_de(doador.get("valor_doado"), LIMITE_TSE) if isinstance(doador, dict) else None
        if valor is None:
            continue
        tipo = texto(doador.get("tipo_receita"))
        agregado = (tipo or "").casefold() == TIPO_RECEITA_AGREGADA
        achado = _DEMAIS_DOADORES.search(texto(doador.get("nome_doador")) or "") if agregado else None
        linhas.append(
            {
                "ano": ano,
                "nome": nome_sem_cpf(doador.get("nome_doador")) or DOADOR_NAO_IDENTIFICADO,
                "doc": documento_do_doador(doador.get("cpf_cnpj_doador")),
                "valor": valor,
                "tipo": tipo,
                "agregado": agregado,
                # a linha agregada vale por todos os doadores que a fonte juntou ("Demais doadores (26)"); nula se não vier N
                "qtd": (_quantidade_agregada(achado) if achado else None) if agregado else 1,
            }
        )
    return {"ano": ano, "linhas": linhas}, None


def ler_patrimonio(item: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Campos de uma declaração de bens, ou (None, "sem_proveniencia" | "invalidas"). Regra única de elegibilidade."""
    if not isinstance(item, dict) or not is_trusted(item):
        return None, "sem_proveniencia"
    ano = inteiro_em(item.get("ano_eleicao"), ANO_MINIMO, ANO_MAXIMO)
    valor = decimal_de(item.get("valor_declarado_brl"), LIMITE_TSE)
    if ano is None or valor is None:
        return None, "invalidas"
    return {
        "ano": ano,
        "valor": valor,
        "qtd": contagem_int4(item.get("quantidade_bens")),
        "det": texto_sem_cpf(item.get("detalhes_bens")),
    }, None


def ler_certidao(item: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Campos de uma situação de registro do TSE, ou (None, "sem_proveniencia" | "invalidas"). Regra única."""
    if not isinstance(item, dict) or not is_trusted(item):
        return None, "sem_proveniencia"
    orgao, tipo, situacao = texto(item.get("orgao")), texto(item.get("tipo_certidao")), texto(item.get("status_ficha"))
    if not (orgao and tipo and situacao):
        return None, "invalidas"
    return {
        "orgao": orgao,
        "tipo": tipo,
        "situacao": situacao,
        "det": texto_sem_cpf(item.get("detalhes")),
        "proc": texto_sem_cpf(item.get("numero_processo")),
    }, None


def ler_registros_da_remuneracao(corpo: Any) -> Tuple[Optional[List[Any]], Optional[str]]:
    """
    Nível de arquivo: os meses de remuneração, ou (None, "sem_proveniencia") quando o arquivo não é um objeto ou não
    tem proveniência oficial (a carga inteira é pulada). Cada mês passa depois por `ler_remuneracao`.
    """
    if not isinstance(corpo, dict) or not is_trusted(corpo):
        return None, "sem_proveniencia"
    registros = corpo.get("registros")
    return (registros if isinstance(registros, list) else []), None


# ── Consolidação das linhas de finanças: funções puras, testáveis sem Postgres ────────────────────────────────────────
def grupo_do_fornecedor(cnpj: Optional[str], nome: str) -> str:
    """
    Chave do fornecedor: o CNPJ ou, sem ele, o nome. É o espelho Python da coluna gerada `grupo` de
    `fin.despesa_cota_fornecedor` (`coalesce(cnpj::text, 'nome:' || nome)`); um teste confere que as duas coincidem.
    """
    return cnpj or f"nome:{nome}"


def fornecedores_do_parlamentar(dados: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fornecedores de uma entrada, com o mesmo CNPJ em grafias diferentes unido (fica o nome de maior valor)."""
    agrupados: Dict[str, Dict[str, Any]] = {}
    lista_fornecedores = dados.get("fornecedores")
    for item in (lista_fornecedores if isinstance(lista_fornecedores, dict) else {}).values():
        if not isinstance(item, dict):
            continue
        valor_dec = decimal_de(item.get("total"))
        if valor_dec is None:
            continue
        nome = nome_do_fornecedor(item.get("nome"))
        cnpj = cnpj_do_fornecedor(item.get("cnpj_cpf"), nome)
        notas = contagem_int4(item.get("notas"))
        grupo = grupo_do_fornecedor(cnpj, nome)
        # `maior` é o maior valor de uma única grafia: o nome mostrado é o dela, e no empate vale o nome (não a ordem)
        acumulado = agrupados.setdefault(
            grupo, {"grupo": grupo, "nome": nome, "cnpj": cnpj, "valor": Decimal(0), "notas": 0, "maior": valor_dec}
        )
        acumulado["valor"] += valor_dec
        acumulado["notas"] = soma_ou_desconhecido(acumulado["notas"], notas)
        if (valor_dec, nome) > (acumulado["maior"], acumulado["nome"]):
            acumulado["nome"], acumulado["maior"] = nome, valor_dec
    return [
        {k: v for k, v in x.items() if k != "maior"}
        for x in agrupados.values()
        if soma_na_faixa(x["valor"], LIMITE_CEAP) is not None  # fornecedor cuja soma estoura a coluna fica de fora
    ]


def resumos_completos(resumos: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """
    Resumos de quem tem a quantidade de notas conhecida em TODAS as entradas (Câmara e Senado) que somaram gasto. Uma
    contagem parcial ao lado do gasto completo enganaria, então a pessoa fica sem resumo. Devolve também quantas ficaram.
    """
    incompletas = {r["p"] for r in resumos if r["notas"] is None}
    return [r for r in resumos if r["p"] not in incompletas and r["notas"] is not None], len(incompletas)


def chave_de_desempate(linha: Dict[str, Any], *campos: str) -> Tuple[Any, ...]:
    """
    Ordem total entre duas linhas que disputam a mesma chave: os campos na ordem dada, com o desconhecido (None) abaixo de
    qualquer valor. O resultado não depende da ordem em que o arquivo traz as linhas.
    """
    return tuple((0, "") if linha[c] is None else (1, linha[c]) for c in campos)


def soma_ou_desconhecido(a: Any, b: Any) -> Any:
    """
    Soma de duas parcelas; se qualquer uma é desconhecida (None) o total também é: parcial nunca vale como total. Uma
    soma inteira acima do teto de `integer` também é desconhecida, pois não caberia na coluna.
    """
    if a is None or b is None:
        return None
    total = a + b
    return None if isinstance(total, int) and total > LIMITE_INT4 else total


def somar_linhas(
    linhas: List[Dict[str, Any]], chave: Tuple[str, ...], somas: Tuple[str, ...]
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Junta linhas de mesma chave e devolve também quantas linhas repetiram a chave na MESMA fonte. Dentro de uma fonte
    a repetição é o mesmo dado sob outra grafia do nome, então fica a linha de maior valor; entre fontes diferentes
    (Câmara e Senado) os campos numéricos se somam (desconhecido em qualquer parcela deixa o total desconhecido).
    Nos empates e na escolha da linha que define os demais campos (nome, fonte) decide o conteúdo da linha, nunca a
    ordem em que o arquivo ou as fontes aparecem. A escolha é POR TABELA: despesa, fornecedor e resumo de uma mesma
    pessoa podem sair de entradas repetidas diferentes (caso raro: duas entradas da mesma casa resolvidas para a mesma
    pessoa). Para o resumo de notas vale a regra mais cautelosa, em `resumos_completos`: qualquer entrada com a
    quantidade desconhecida tira o resumo da pessoa.
    """

    def ordem(linha: Dict[str, Any]) -> Tuple[Any, ...]:
        return chave_de_desempate(linha, *somas, *sorted(set(linha) - set(somas)))

    por_fonte: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    repetidas = 0
    for linha in linhas:
        k = (tuple(linha[c] for c in chave), linha["f"])
        atual = por_fonte.get(k)
        if atual is None:
            por_fonte[k] = dict(linha)
            continue
        repetidas += 1
        if ordem(linha) > ordem(atual):
            por_fonte[k] = dict(linha)
    grupos: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    for (k, _fonte), linha in por_fonte.items():
        grupos.setdefault(k, []).append(linha)
    unicas = []
    for candidatas in grupos.values():
        vencedora = max(candidatas, key=ordem)
        base = dict(vencedora)
        for outra in candidatas:
            if outra is not vencedora:
                for campo in somas:
                    base[campo] = soma_ou_desconhecido(base[campo], outra[campo])
        unicas.append(base)
    return unicas, repetidas


def manter_a_melhor(
    unicas: Dict[Any, Dict[str, Any]], chave: Any, linha: Dict[str, Any], campos: Tuple[str, ...]
) -> bool:
    """
    Guarda `linha` em `unicas[chave]` e devolve True se a chave já existia (registro repetido). Entre duas linhas da mesma
    chave vale a de maior `chave_de_desempate(campos)`, nunca a ordem em que o arquivo as traz.
    """
    anterior = unicas.get(chave)
    if anterior is None:
        unicas[chave] = linha
        return False
    if chave_de_desempate(linha, *campos) > chave_de_desempate(anterior, *campos):
        unicas[chave] = linha
    return True


def chave_da_prestacao(linhas: List[Dict[str, Any]]) -> Tuple[Any, ...]:
    """Ordem total entre prestações do mesmo (pessoa, ano): quantidade, soma e, no empate, o conteúdo das linhas."""
    conteudo = sorted((x["nome"], x["doc"] or "", str(x["valor"]), x["tipo"] or "") for x in linhas)
    return len(linhas), sum((x["valor"] for x in linhas), Decimal(0)), conteudo


def descricao_do_erro(exc: Exception) -> str:
    """
    Texto do erro que pode ir para o log e para a saída do deploy. O erro do Postgres traz um `DETAIL: Failing row
    contains (...)` com os valores da linha (o `hide_parameters` do engine não o esconde), então dele só saem o tipo, a
    mensagem principal e o nome da restrição (para erro de dado, classe 22, só o tipo, o SQLSTATE e a coluna). Os demais erros (as mensagens da própria carga) saem como são.
    """
    if isinstance(exc, DBAPIError):
        diag = getattr(exc.orig, "diag", None)
        sqlstate = getattr(exc.orig, "pgcode", None) or ""
        restricao = getattr(diag, "constraint_name", None)
        coluna = getattr(diag, "column_name", None)
        if sqlstate.startswith("22"):
            # erro de dado (classe 22): a mensagem principal costuma citar o valor ofendido, ex. `invalid input syntax
            # for type integer: "<valor>"`. Ficam o tipo, o SQLSTATE e, se houver, a coluna.
            return f"{type(exc).__name__}: erro de dado (SQLSTATE {sqlstate})" + (
                f" na coluna {coluna}" if coluna else ""
            )
        principal = getattr(diag, "message_primary", None) or "erro do banco"
        return f"{type(exc).__name__}: {principal}" + (f" (restrição {restricao})" if restricao else "")
    return str(exc)
