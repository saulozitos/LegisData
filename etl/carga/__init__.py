"""
Carga direta: arquivo da fonte oficial -> tabelas finais (`core`, `leg`, `fin`), sem staging nem fusão.

Cada recurso (`partidos`, `pessoas`, `filiacoes`...) é uma função que, numa única transação: despeja o que leu do arquivo
numa tabela TEMPORÁRIA da própria transação (`COPY`), roda um arquivo SQL (`etl/carga/sql`) que grava com
`INSERT ... ON CONFLICT` pela chave natural, e devolve a contagem. O Python lê arquivo e converte valores de uma linha só;
quem decide a que pessoa, partido ou proposição o registro se refere é o SQL, pelo identificador oficial. Nome nunca cria
nem une pessoa.

`etl.corte` guarda, por fonte e recurso, até que data já se baixou. O corte só avança quando a transação confirma.
"""
