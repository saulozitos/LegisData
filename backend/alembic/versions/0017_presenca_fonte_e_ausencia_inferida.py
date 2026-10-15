"""Presença com origem registrada, falta inferida e ponte do legado sem apagar outras fontes.

- `leg.presenca.fonte_id` diz de onde veio cada linha (portal da Câmara, arquivos de eventos, Senado, legado).
- `AUSENCIA_INFERIDA` é a falta deduzida (parlamentar em exercício sem presença em dia de sessão deliberativa do
  plenário) em períodos em que a fonte não publica falta nem justificativa; nunca se mistura com a falta oficial.
- A ponte do legado passa a substituir só as linhas que ela mesma gravou (antes truncava a tabela inteira) e nunca
  sobrepõe uma linha de fonte oficial para o mesmo parlamentar e dia.

Revision ID: 0017
Revises: 0016
"""

import importlib.util
from pathlib import Path

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def _ponte_anterior() -> str:
    caminho = Path(__file__).with_name("0016_autoria_implicita_legado.py")
    spec = importlib.util.spec_from_file_location("_rev0016", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.PONTE_LEG


def _ponte_nova() -> str:
    fn = _ponte_anterior()
    antigo_truncate = "    TRUNCATE leg.presenca;\n"
    antigo_insert = (
        "    INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo, mandato_id, justificativa)\n"
        '    SELECT DISTINCT ON (pe.id, c.id, r."dataSessao") pe.id, c.id, r."dataSessao", r."tipoPresenca"::text, '
        "ml.mandato_id, r.justificativa\n"
    )
    novo_insert = (
        "    INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo, mandato_id, justificativa, "
        "fonte_id)\n"
        '    SELECT DISTINCT ON (pe.id, c.id, r."dataSessao") pe.id, c.id, r."dataSessao", r."tipoPresenca"::text, '
        "ml.mandato_id, r.justificativa, v_fonte\n"
    )
    fim_insert = '    ORDER BY pe.id, c.id, r."dataSessao", r.id;\n'
    assert antigo_truncate in fn and antigo_insert in fn and fim_insert in fn
    fn = fn.replace(antigo_truncate, "    DELETE FROM leg.presenca WHERE fonte_id = v_fonte;\n")
    fn = fn.replace(antigo_insert, novo_insert)
    fn = fn.replace(fim_insert, '    ORDER BY pe.id, c.id, r."dataSessao", r.id\n    ON CONFLICT DO NOTHING;\n')
    return fn


def upgrade() -> None:
    op.execute("ALTER TABLE leg.presenca ADD COLUMN fonte_id smallint REFERENCES etl.fonte(id)")
    op.execute("UPDATE leg.presenca SET fonte_id = (SELECT id FROM etl.fonte WHERE codigo = 'LEGADO')")
    op.execute("INSERT INTO ref.tipo_presenca (codigo, presente) VALUES ('AUSENCIA_INFERIDA', false)")
    op.execute(_ponte_nova())
    op.execute("SELECT etl.sincronizar_legado_leg()")


def downgrade() -> None:
    raise NotImplementedError("Migração 0017 não é reversível.")
