"""
Emendas orçamentárias lidas de `fin.emenda`: panorama, busca por localidade e por autor.

Os totais e as quebras (tipo de autor, área, ano, UF) são calculados no banco sobre todas as linhas; só a lista
detalhada é limitada. O tipo de autor e a UF de destino já vêm classificados pela carga do ETL.
"""

from typing import Any, Callable, Dict, List, Optional

from app.core.errors import ErroDeDominio
from app.core.names import strip_accents
from app.core.numeros import pct
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

# Termo de busca curto casa quase tudo e obriga a varrer a tabela inteira; o limite superior fica na rota.
TAMANHO_MINIMO_DA_BUSCA = 2
# Área temática das emendas sem função orçamentária; `financas_service` usa a mesma constante nos agrupamentos do dossiê.
AREA_SEM_FUNCAO = "Outros"
# Uma busca por trecho que não termina neste prazo é cancelada pelo banco e vira pedido de termo mais específico.
TEMPO_MAXIMO_DA_BUSCA_MS = 8000

DICIONARIO_ORCAMENTO = {
    "termos": {
        "custeio": {
            "termo_tecnico": "GND 3 — Despesas Correntes (Custeio)",
            "traducao": "Dinheiro para o dia a dia",
            "explicacao": "Recursos destinados à manutenção de serviços existentes: compra de remédios, merenda escolar, contas de energia de hospitais e insumos de saúde.",
        },
        "investimento": {
            "termo_tecnico": "GND 4 — Despesas de Capital (Investimentos)",
            "traducao": "Obras e Equipamentos",
            "explicacao": "Recursos aplicados na criação de bens duradouros: construção de postos de saúde, escolas, pavimentação de ruas, compra de ambulâncias e tratores.",
        },
        "empenhado": {
            "termo_tecnico": "Valor Empenhado",
            "traducao": "Dinheiro Reservado",
            "explicacao": "O Governo Federal aprovou o projeto e carimbou o recurso no orçamento. É a promessa formal de pagamento assim que a obra ou serviço for concluído.",
        },
        "pago": {
            "termo_tecnico": "Valor Liquidado / Pago",
            "traducao": "Dinheiro Entregue",
            "explicacao": "O serviço ou etapa da obra foi fiscalizado e o valor já caiu efetivamente na conta bancária da prefeitura ou instituição de destino.",
        },
    },
    "linha_do_tempo": [
        {
            "etapa": 1,
            "nome": "Orçado",
            "status": "Planejado",
            "descricao": "Previsto na Lei Orçamentária Anual do Congresso",
        },
        {
            "etapa": 2,
            "nome": "Reservado (Empenhado)",
            "status": "Garantido",
            "descricao": "Recurso aprovado e carimbado pelo Governo Federal",
        },
        {
            "etapa": 3,
            "nome": "Entregue (Pago)",
            "status": "Disponível na Ponta",
            "descricao": "Valor creditado na conta do município ou instituição beneficiada",
        },
    ],
    "areas_tematicas": {
        "Saúde": {"icone": "🩺", "rotulo": "Saúde e Cuidados Básicos"},
        "Educação": {"icone": "🏫", "rotulo": "Educação e Escolas"},
        "Agricultura": {"icone": "🚜", "rotulo": "Agricultura e Produtores Rurais"},
        "Urbanismo": {"icone": "🏙️", "rotulo": "Cidades, Asfalto e Habitação"},
        "Transporte": {"icone": "🛣️", "rotulo": "Estradas e Transportes"},
        "Segurança pública": {"icone": "🛡️", "rotulo": "Segurança e Proteção Comunitária"},
        "Assistência social": {"icone": "🤝", "rotulo": "Assistência Social e Família"},
        "Saneamento": {"icone": "💧", "rotulo": "Água Limpa e Saneamento Básico"},
        "Cultura": {"icone": "🎭", "rotulo": "Cultura e Patrimônio Histórico"},
        "Desporto e lazer": {"icone": "⚽", "rotulo": "Esporte e Lazer Comunitário"},
        "Defesa nacional": {"icone": "🎖️", "rotulo": "Defesa Nacional e Soberania"},
        "Outros": {"icone": "🏛️", "rotulo": "Desenvolvimento Regional e Outras Áreas"},
    },
}

_ESTADOS_MAP = {
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


_UFS = frozenset(_ESTADOS_MAP.values())


def _extrair_uf_bancada(nome_limpo: str) -> str:
    # do nome mais longo para o mais curto: "PARANA" e "PARAIBA" contêm "PARA", "MATO GROSSO DO SUL" contém "MATO GROSSO"
    for estado, uf in sorted(_ESTADOS_MAP.items(), key=lambda par: -len(par[0])):
        if estado in nome_limpo:
            return uf
    return "NACIONAL"


def _traduzir_comissao(nome_limpo: str) -> str:
    traducoes = {
        "SAUDE": "Comissão de Saúde",
        "EDUC": "Comissão de Educação e Cultura",
        "CONST": "Comissão de Constituição e Justiça",
        "ASSUNTOS ECONOMICOS": "Comissão de Assuntos Econômicos",
        "FINANCAS": "Comissão de Finanças e Tributação",
        "AGRICULTURA": "Comissão de Agricultura e Reforma Agrária",
        "MEIO AMBIENTE": "Comissão de Meio Ambiente",
        "SEGURANCA": "Comissão de Segurança Pública",
        "INFRA-ESTRUTURA": "Comissão de Serviços de Infraestrutura",
        "INTEGRACAO": "Comissão de Integração Nacional",
        "DIREITOS HUMANOS": "Comissão de Direitos Humanos",
        "VIACAO": "Comissão de Viação e Transportes",
        "DESENVOLVIMENTO URBANO": "Comissão de Desenvolvimento Urbano",
        "MULHER": "Comissão de Defesa dos Direitos da Mulher",
    }
    for termo, amigavel in traducoes.items():
        if termo in nome_limpo:
            return amigavel
    return "Comissão Temática do Congresso"


_META_TIPO_AUTOR: Dict[str, Dict[str, str]] = {
    "BANCADA_ESTADUAL": {
        "categoria": "Bancada Estadual",
        "descricao_amigavel": "Recurso definido por votação coletiva de deputados e senadores da bancada deste estado.",
        "icone": "🗺️",
    },
    "RELATOR_GERAL": {
        "categoria": "Relator-Geral do Orçamento",
        "descricao_amigavel": "Recurso alocado pela Comissão Mista de Planos, Orçamentos Públicos e Fiscalização da União.",
        "icone": "⚖️",
    },
    "COMISSAO_INSTITUCIONAL": {
        "categoria": "Comissão Temática",
        "descricao_amigavel": "Verba institucional aprovada por consenso dos membros da {amigavel}.",
        "icone": "🏛️",
    },
    "INDIVIDUAL": {
        "categoria": "Parlamentar Individual",
        "descricao_amigavel": "Recurso da cota orçamentária individual de livre indicação constitucional do parlamentar.",
        "icone": "👤",
    },
}


def meta_do_tipo_de_autor(tipo_autor: str) -> Dict[str, str]:
    """Categoria, ícone e descrição fixos de um tipo de autor (a descrição da comissão leva o nome dela em `{amigavel}`)."""
    return _META_TIPO_AUTOR.get(tipo_autor, _META_TIPO_AUTOR["INDIVIDUAL"])


def perfil_do_autor(autor_nome: str, tipo_autor: str) -> Dict[str, Any]:
    """Descrição humanizada do autor, a partir do tipo que o ETL gravou em `fin.emenda.tipo_autor`."""
    norm = strip_accents(autor_nome or "").upper()
    tipo = tipo_autor if tipo_autor in _META_TIPO_AUTOR else "INDIVIDUAL"
    meta = _META_TIPO_AUTOR[tipo]
    if tipo == "BANCADA_ESTADUAL":
        uf = _extrair_uf_bancada(norm)
        amigavel, uf_referencia = f"Bancada Estadual ({uf})", uf
    elif tipo == "RELATOR_GERAL":
        amigavel, uf_referencia = "Relator-Geral do Orçamento", "BR"
    elif tipo == "COMISSAO_INSTITUCIONAL":
        amigavel, uf_referencia = _traduzir_comissao(norm), "BR"
    else:
        amigavel, uf_referencia = (autor_nome or "").title(), None
    return {
        "tipo_autor": tipo,
        "categoria": meta["categoria"],
        "nome_tecnico": autor_nome,
        "nome_amigavel": amigavel,
        "uf_referencia": uf_referencia,
        "descricao_amigavel": meta["descricao_amigavel"].format(amigavel=amigavel),
        "icone": meta["icone"],
    }


def _area(area: str) -> Dict[str, str]:
    return DICIONARIO_ORCAMENTO["areas_tematicas"].get(area, {"icone": "🏛️", "rotulo": area})


def _por_area(linhas: List[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "area": r.area,
            "rotulo": _area(r.area)["rotulo"],
            "icone": _area(r.area)["icone"],
            "total_empenhado": float(r.empenhado),
            "total_pago": float(r.pago),
            "quantidade": int(r.quantidade),
        }
        for r in linhas
    ]


def resumo(db: Session) -> Dict[str, Any]:
    """Panorama geral das emendas: totais, tipo de autor, área, ano e as dez UFs mais beneficiadas."""
    total = db.execute(
        text("SELECT count(*) AS n, sum(valor_empenhado) AS emp, sum(valor_pago) AS pago FROM fin.emenda")
    ).one()
    if not total.n:
        raise ErroDeDominio(404, "Dados de emendas orçamentárias não encontrados.")
    empenhado, pago = float(total.emp), float(total.pago)

    por_tipo_autor: Dict[str, Any] = {}
    for r in db.execute(
        text(
            "SELECT tipo_autor, sum(valor_empenhado) AS emp, sum(valor_pago) AS pago, count(*) AS n FROM fin.emenda "
            "GROUP BY tipo_autor ORDER BY tipo_autor"
        )
    ):
        meta = meta_do_tipo_de_autor(r.tipo_autor)
        por_tipo_autor[r.tipo_autor] = {
            "total_empenhado": float(r.emp),
            "total_pago": float(r.pago),
            "quantidade": int(r.n),
            "categoria": meta["categoria"],
            "icone": meta["icone"],
            "descricao": meta["descricao_amigavel"].format(amigavel="Comissão Temática do Congresso"),
        }

    areas = db.execute(
        text(
            "SELECT coalesce(funcao, :sem_funcao) AS area, sum(valor_empenhado) AS empenhado, sum(valor_pago) AS pago, "
            "count(*) AS quantidade FROM fin.emenda GROUP BY 1 ORDER BY pago DESC, 1"
        ),
        {"sem_funcao": AREA_SEM_FUNCAO},
    ).all()
    anos = db.execute(
        text(
            "SELECT ano, sum(valor_empenhado) AS emp, sum(valor_pago) AS pago, count(*) AS n FROM fin.emenda "
            "GROUP BY ano ORDER BY ano"
        )
    ).all()
    ufs = db.execute(
        text(
            "SELECT uf, sum(valor_empenhado) AS emp, sum(valor_pago) AS pago, count(*) AS n FROM fin.emenda "
            "WHERE uf IS NOT NULL GROUP BY uf ORDER BY pago DESC, uf LIMIT 10"
        )
    ).all()
    return {
        "estatisticas_gerais": {
            "total_emendas": int(total.n),
            "total_reservado_empenhado_brl": round(empenhado, 2),
            "total_entregue_pago_brl": round(pago, 2),
            "taxa_execucao_pago_pct": pct(pago, empenhado),
        },
        "por_tipo_autor": por_tipo_autor,
        "por_area_tematica": _por_area(areas),
        "por_ano": {
            str(r.ano): {"total_empenhado": float(r.emp), "total_pago": float(r.pago), "quantidade": int(r.n)}
            for r in anos
        },
        "top_ufs": [
            {"uf": r.uf, "total_empenhado": float(r.emp), "total_pago": float(r.pago), "quantidade": int(r.n)}
            for r in ufs
        ],
        "dicionario": DICIONARIO_ORCAMENTO,
    }


def _termo_valido(valor: str, sujeito: str, complemento: str) -> str:
    """
    Termo da busca sem espaços nas pontas; levanta 400 para caractere nulo ou menos de `TAMANHO_MINIMO_DA_BUSCA`
    caracteres. `sujeito` abre a mensagem do caractere inválido ("A localidade") e `complemento` fecha a do tamanho
    ("da localidade").
    """
    termo = valor.strip()
    if "\x00" in termo:
        raise ErroDeDominio(400, f"{sujeito} contém caractere inválido.")
    if len(termo) < TAMANHO_MINIMO_DA_BUSCA:
        raise ErroDeDominio(400, f"Informe ao menos {TAMANHO_MINIMO_DA_BUSCA} caracteres {complemento}.")
    return termo


# Emendas que casam com a busca ficam numa tabela temporária da transação (some no commit/rollback): as consultas de
# agregação leem dela, sem levar dezenas de milhares de ids para o Python e de volta como literal de array.
_ALVO = "emenda_alvo"
_ALVO_CRIA = text("CREATE TEMP TABLE IF NOT EXISTS emenda_alvo (id bigint PRIMARY KEY) ON COMMIT DELETE ROWS")
_ALVO_LIMPA = text("DELETE FROM emenda_alvo")


def _prepara_busca(db: Session) -> None:
    """Esvazia a tabela de alvos e liga o limite de tempo da busca (vale só na transação corrente)."""
    db.execute(text("SELECT set_config('statement_timeout', :ms, true)"), {"ms": str(TEMPO_MAXIMO_DA_BUSCA_MS)})
    db.execute(_ALVO_CRIA)
    db.execute(_ALVO_LIMPA)


def _com_limite_de_tempo(db: Session, busca: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    """Roda a busca; se o banco a cancela por demora (SQLSTATE 57014), pede um termo mais específico (400)."""
    try:
        return busca()
    except OperationalError as erro:
        if getattr(erro.orig, "pgcode", None) != "57014":
            raise
        db.rollback()
        raise ErroDeDominio(400, "A busca é ampla demais; informe um termo mais específico.") from erro


def _areas(db: Session) -> List[Any]:
    """Valores por área temática das emendas escolhidas."""
    return db.execute(
        text(
            "SELECT coalesce(funcao, :sem_funcao) AS area, sum(valor_empenhado) AS empenhado, sum(valor_pago) AS pago, "
            "count(*) AS quantidade FROM fin.emenda WHERE id IN (SELECT id FROM emenda_alvo) "
            "GROUP BY 1 ORDER BY pago DESC, 1"
        ),
        {"sem_funcao": AREA_SEM_FUNCAO},
    ).all()


def _estagio(valor_pago: Any) -> str:
    return "Dinheiro Entregue" if valor_pago > 0 else "Dinheiro Reservado"


def _item_da_emenda(r: Any) -> Dict[str, Any]:
    """Campos que a emenda da busca por localidade e a da busca por autor têm em comum."""
    return {
        "codigo_emenda": r.codigo_emenda,
        "ano": r.ano,
        "area_tematica": r.area,
        "area_rotulo": _area(r.area)["rotulo"],
        "area_icone": _area(r.area)["icone"],
        "valor_reservado_empenhado": float(r.valor_empenhado),
        "valor_entregue_pago": float(r.valor_pago),
        "estagio": _estagio(r.valor_pago),
    }


def _sigla_da_busca(termo: str) -> Optional[str]:
    """UF que o termo nomeia (a sigla ou o nome do estado por extenso, sem acento nem caixa), ou None."""
    if termo.upper() in _UFS:
        return termo.upper()
    return _ESTADOS_MAP.get(strip_accents(termo).upper())


def _seleciona_por_localidade(db: Session, termo: str) -> None:
    """
    Emendas cujo destino casa com a busca. Sigla de estado (SP, MG...) vale pela coluna `uf`, que cobre o estado inteiro
    ("SÃO PAULO (UF)") e os seus municípios ("CAMPINAS - SP"); "AL" não pode virar um trecho que casa SALVADOR e NATAL.
    O nome do estado por extenso ("Distrito Federal", "São Paulo") vale como a sigla. Qualquer outro termo é busca por
    trecho do nome, sem acento nem caixa.
    """
    db.execute(
        text(
            "INSERT INTO emenda_alvo SELECT id FROM fin.emenda "
            "WHERE (CAST(:sigla AS text) IS NOT NULL AND uf = CAST(:sigla AS text)) "
            "OR (CAST(:sigla AS text) IS NULL AND ref.contem_texto(localidade_destino, :termo))"
        ),
        {"sigla": _sigla_da_busca(termo), "termo": termo},
    )


def _seleciona_por_autor(db: Session, termo: str) -> None:
    db.execute(
        text(
            "INSERT INTO emenda_alvo SELECT id FROM fin.emenda "
            "WHERE ref.contem_texto(autor_texto, :termo) OR autor_codigo = :termo"
        ),
        {"termo": termo},
    )


def por_localidade(db: Session, localidade: str, limite: int) -> Dict[str, Any]:
    """Emendas destinadas a uma cidade ou estado (sigla ou nome do estado, ou trecho do nome sem acento nem caixa)."""
    termo = _termo_valido(localidade, "A localidade", "da localidade")

    def busca() -> Dict[str, Any]:
        _prepara_busca(db)
        _seleciona_por_localidade(db, termo)
        total = db.execute(
            text(
                "SELECT count(*) AS n, sum(valor_empenhado) AS emp, sum(valor_pago) AS pago FROM fin.emenda "
                "WHERE id IN (SELECT id FROM emenda_alvo)"
            )
        ).one()
        if not total.n:
            raise ErroDeDominio(404, "Nenhuma emenda encontrada para essa localidade.")
        empenhado, pago = float(total.emp), float(total.pago)
        areas = _areas(db)
        linhas = db.execute(
            text(
                "SELECT codigo_emenda, ano, coalesce(funcao, :sem_funcao) AS area, tipo_emenda, valor_empenhado, "
                "valor_pago, autor_texto, tipo_autor FROM fin.emenda WHERE id IN (SELECT id FROM emenda_alvo) "
                "ORDER BY ano DESC, valor_pago DESC, id LIMIT :limite"
            ),
            {"sem_funcao": AREA_SEM_FUNCAO, "limite": limite},
        ).all()
        if not linhas:  # uma carga confirmada entre as consultas esvaziou o resultado
            raise ErroDeDominio(404, "Nenhuma emenda encontrada para essa localidade.")
        return {
            "localidade_pesquisada": localidade,
            "total_emendas_encontradas": int(total.n),
            "total_reservado_empenhado_brl": round(empenhado, 2),
            "total_entregue_pago_brl": round(pago, 2),
            "taxa_execucao_pct": pct(pago, empenhado),
            "divisao_por_area": _por_area(areas),
            "emendas": [{**_item_da_emenda(r), "autor": perfil_do_autor(r.autor_texto, r.tipo_autor)} for r in linhas],
            "dicionario": DICIONARIO_ORCAMENTO["termos"],
        }

    return _com_limite_de_tempo(db, busca)


def por_autor(db: Session, autor: str, limite: int) -> Dict[str, Any]:
    """Emendas de um autor (parlamentar, comissão ou bancada), pelo trecho do nome ou pelo código do autor."""
    termo = _termo_valido(autor, "O autor", "do autor")

    def busca() -> Dict[str, Any]:
        _prepara_busca(db)
        _seleciona_por_autor(db, termo)
        total = db.execute(
            text(
                "SELECT count(*) AS n, sum(valor_empenhado) AS emp, sum(valor_pago) AS pago, "
                "count(DISTINCT autor_texto) AS autores FROM fin.emenda WHERE id IN (SELECT id FROM emenda_alvo)"
            )
        ).one()
        if not total.n:
            raise ErroDeDominio(404, "Nenhuma emenda encontrada para esse autor.")
        empenhado, pago = float(total.emp), float(total.pago)
        autores = db.execute(
            text(
                "SELECT autor_texto, (array_agg(tipo_autor ORDER BY valor_pago DESC, id))[1] AS tipo_autor, "
                "count(*) AS quantidade FROM fin.emenda WHERE id IN (SELECT id FROM emenda_alvo) "
                "GROUP BY autor_texto ORDER BY sum(valor_pago) DESC, autor_texto LIMIT 10"
            )
        ).all()
        destinos = db.execute(
            text(
                "SELECT localidade_destino AS localidade, sum(valor_empenhado) AS total_empenhado, "
                "sum(valor_pago) AS total_pago, count(*) AS quantidade FROM fin.emenda "
                "WHERE id IN (SELECT id FROM emenda_alvo) GROUP BY 1 ORDER BY total_pago DESC, 1 LIMIT 10"
            )
        ).all()
        areas = _areas(db)
        linhas = db.execute(
            text(
                "SELECT codigo_emenda, ano, localidade_destino, coalesce(funcao, :sem_funcao) AS area, "
                "valor_empenhado, valor_pago, autor_texto, tipo_autor FROM fin.emenda "
                "WHERE id IN (SELECT id FROM emenda_alvo) ORDER BY ano DESC, valor_pago DESC, id LIMIT :limite"
            ),
            {"sem_funcao": AREA_SEM_FUNCAO, "limite": limite},
        ).all()
        if not linhas:  # uma carga confirmada entre as consultas esvaziou o resultado
            raise ErroDeDominio(404, "Nenhuma emenda encontrada para esse autor.")
        return {
            "autor_pesquisado": autor,
            # nome e tipo vêm da mesma emenda (a de maior valor pago no ano mais recente), nunca de linhas diferentes
            "perfil_autor": perfil_do_autor(linhas[0].autor_texto, linhas[0].tipo_autor),
            # a busca por trecho pode reunir autores diferentes ("SILVA"); os totais abaixo somam todos eles
            "quantidade_autores": int(total.autores),
            "autores_encontrados": [
                {**perfil_do_autor(r.autor_texto, r.tipo_autor), "quantidade": int(r.quantidade)} for r in autores
            ],
            "total_emendas_enviadas": int(total.n),
            "total_reservado_empenhado_brl": round(empenhado, 2),
            "total_entregue_pago_brl": round(pago, 2),
            "taxa_execucao_pct": pct(pago, empenhado),
            "top_destinos": [
                {
                    "localidade": r.localidade,
                    "total_empenhado": float(r.total_empenhado),
                    "total_pago": float(r.total_pago),
                    "quantidade": int(r.quantidade),
                }
                for r in destinos
            ],
            "por_area_tematica": _por_area(areas),
            "emendas": [{**_item_da_emenda(r), "localidade_destino": r.localidade_destino} for r in linhas],
        }

    return _com_limite_de_tempo(db, busca)
