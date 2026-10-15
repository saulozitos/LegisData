"""Ponte do legado adota partido do schema novo que já existe com a mesma sigla.

O ETL em lote cria em `core.partido` partidos extintos ou ausentes do legado (catálogo falso). Quando uma carga do ETL
antigo cria depois o mesmo partido no legado (ex.: PHS), o upsert por `uid` colidia com a unicidade da sigla e a ponte
inteira falhava. Agora a ponte troca o `uid` do partido já existente pelo id do legado antes do upsert (o `uid` não é
chave estrangeira de nenhuma tabela).

Revision ID: 0020
Revises: 0019
"""

import importlib.util
from pathlib import Path

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def _ponte_anterior() -> str:
    caminho = Path(__file__).with_name("0011_historico_mandatos_camara.py")
    spec = importlib.util.spec_from_file_location("_rev0011", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.PONTE_CORE


ADOTAR = """    -- partido criado antes pelo ETL em lote com a mesma sigla: adota o id do legado em vez de colidir
    UPDATE core.partido c SET uid = p.id
    FROM public.partidos_politicos p
    WHERE c.sigla = p.sigla AND c.uid <> p.id
      AND NOT EXISTS (SELECT 1 FROM public.partidos_politicos x WHERE x.id = c.uid)
      AND NOT EXISTS (SELECT 1 FROM core.partido y WHERE y.uid = p.id);
"""


def upgrade() -> None:
    fn = _ponte_anterior()
    marcador = "    INSERT INTO core.partido (uid, sigla, nome, numero_eleitoral, data_fundacao, data_extincao, ideologia_texto, lema)\n"
    assert fn.count(marcador) == 1
    op.execute(fn.replace(marcador, ADOTAR + marcador))


def downgrade() -> None:
    raise NotImplementedError("Migração 0020 não é reversível.")
