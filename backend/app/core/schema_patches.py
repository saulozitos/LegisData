"""DDL idempotente para colunas adicionadas depois da criação inicial das tabelas.

`Base.metadata.create_all` não altera tabelas existentes; estas instruções são
executadas no startup da API (app/main.py) e antes da carga do ETL
(etl/pipelines/db_loader.py), para que a ordem de execução não importe.
"""

EMENDAS_CEAP_DDL = [
    # Rótulos oficiais de tipo têm até 58 caracteres
    'ALTER TABLE emendas_parlamentares ALTER COLUMN "tipoEmenda" TYPE VARCHAR(100);',
    'ALTER TABLE emendas_parlamentares ADD COLUMN IF NOT EXISTS "valorLiquidado" NUMERIC(15, 2);',
    'ALTER TABLE emendas_parlamentares ADD COLUMN IF NOT EXISTS "municipioIbge" VARCHAR(10);',
    'ALTER TABLE emendas_parlamentares ADD COLUMN IF NOT EXISTS "uf" VARCHAR(30);',
    'ALTER TABLE emendas_parlamentares ADD COLUMN IF NOT EXISTS "codigoAutorSiafi" VARCHAR(20);',
    'ALTER TABLE emendas_parlamentares ADD COLUMN IF NOT EXISTS "nomeAutorFonte" VARCHAR(255);',
    'ALTER TABLE emendas_parlamentares ADD COLUMN IF NOT EXISTS "fonteUrl" TEXT;',
    'ALTER TABLE despesas_cota_parlamentar ADD COLUMN IF NOT EXISTS "fonteUrl" TEXT;',
    'ALTER TABLE despesas_cota_parlamentar ADD COLUMN IF NOT EXISTS "idDocumentoFonte" VARCHAR(100);',
]
