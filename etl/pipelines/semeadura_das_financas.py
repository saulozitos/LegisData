"""
Política de semeadura das finanças num lugar só: quais tabelas dizem que o `fin` "tem" a CEAP e as emendas, e de quem é o
dado de cada uma (o timer diário ou o retrato do git, segundo o sinal que a carga grava em `etl.execucao`).

O `deploy.sh` repete em bash as consultas daqui (ele decide antes de a imagem nova existir) e um teste confere que o texto
é o mesmo; a tabela de decisão (`modo_de_semeadura`) também é repetida lá e conferida nas 16 combinações. Módulo leve:
não importa nenhum loader.
"""

from typing import Iterable, Optional, Set, Tuple

from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

# O que cada fonte do timer guarda no `fin`: a fonte "tem dado" se todas as tabelas dela têm linhas.
TABELAS_DA_CEAP = ("despesa_cota", "despesa_cota_fornecedor", "despesa_cota_resumo")
TABELAS_DAS_EMENDAS = ("emenda",)


def sql_fin_tem(tabelas: Iterable[str], operador: str = "and") -> str:
    """A consulta "o `fin` tem dados nestas tabelas?": `and` pede todas, `or` basta uma. O deploy.sh repete estas consultas."""
    return f" {operador} ".join(f"exists(select 1 from fin.{t})" for t in tabelas)


SQL_FIN_TEM_CEAP = sql_fin_tem(TABELAS_DA_CEAP)
SQL_FIN_TEM_EMENDAS = sql_fin_tem(TABELAS_DAS_EMENDAS)
SQL_FIN_TEM_ALGUM_DADO = sql_fin_tem(TABELAS_DA_CEAP + TABELAS_DAS_EMENDAS, "or")

# Quem é dono da fonte: a última linha de cada carga em `etl.execucao` (estágio CARREGAR, status OK) diz se o dado veio de uma
# extração fresca (`fresca = 'true'`) ou do retrato do git (`'false'`, que revoga a posse). INVARIANTE: essas linhas não
# podem ser expurgadas como histórico comum, ou o deploy volta a semear do git em silêncio. `parametros->>'fonte'` é a chave
# que versões anteriores deste branch gravavam; as linhas antigas continuam valendo (a linha nova prevalece).
SQL_FONTES_DO_TIMER = (
    "select coalesce(string_agg(carga, ' '), '') from ("
    "select distinct on (c) c as carga, fresca from ("
    "select coalesce(parametros->>'carga', parametros->>'fonte') as c, parametros->>'fresca' as fresca, id "
    "from etl.execucao where estagio = 'CARREGAR' and status = 'OK') x "
    "where c is not null order by c, id desc) t where fresca = 'true'"
)


def estado_do_fin(engine: Engine) -> Tuple[bool, bool]:
    """(tem CEAP, tem emendas) no `fin`. Sem o schema `fin`, (False, False)."""
    with engine.connect() as conexao:
        if not conexao.execute(text("select to_regclass('fin.emenda') is not null")).scalar():
            return False, False
        return (
            bool(conexao.execute(text(f"select {SQL_FIN_TEM_CEAP}")).scalar()),
            bool(conexao.execute(text(f"select {SQL_FIN_TEM_EMENDAS}")).scalar()),
        )


def fontes_do_timer(engine: Engine) -> Set[str]:
    """As cargas (ceap, emendas) cuja última entrada em `etl.execucao` veio de uma extração fresca."""
    with engine.connect() as conexao:
        return set(str(conexao.execute(text(SQL_FONTES_DO_TIMER)).scalar() or "").split())


def modo_de_semeadura(tem_ceap: bool, tem_emendas: bool, ceap_do_timer: bool, emendas_do_timer: bool) -> Optional[str]:
    """
    Qual fonte o git precisa semear. Uma fonte só fica de fora quando o `fin` tem dado dela E o timer a assumiu (carregou
    dela uma extração fresca): fora disso o único dado que existe é o retrato do git. Devolve o modo ("completa",
    "sem_emendas", "sem_ceap") ou None quando nada precisa ser semeado. O `decidir_financas` do deploy.sh repete esta
    tabela (um teste confere as 16 combinações).
    """
    semear_ceap = not (tem_ceap and ceap_do_timer)
    semear_emendas = not (tem_emendas and emendas_do_timer)
    if semear_ceap and semear_emendas:
        return "completa"
    if semear_ceap:
        return "sem_emendas"
    if semear_emendas:
        return "sem_ceap"
    return None
