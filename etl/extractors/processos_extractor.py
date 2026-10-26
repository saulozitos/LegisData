"""
Extrator de processos judiciais: enriquece com o DataJud (CNJ) os números de processo da curadoria.

O DataJud só responde por número de processo e não expõe as partes; por isso ele nunca descobre os processos de uma
pessoa. O vínculo vem de `processos_curados.json`: cada entrada traz a pessoa (os mesmos identificadores das demais
fontes), o número CNJ e o link da fonte oficial que liga o processo à pessoa. Daqui sai `processos_judiciais.json`,
que a carga `processos` do `fin` lê.

A curadoria é a fonte de verdade: o arquivo gerado reflete exatamente o que ela contém e o DataJud confirma. Por isso,
- uma curadoria válida e vazia grava `[]` (é assim que se retira um vínculo errado do dossiê);
- fica de fora, e é contado, o processo com número inválido, link que não é de fonte oficial (`https` de domínio
  público e sem CPF), de um tribunal que o DataJud não cobre (STF, por exemplo), que o DataJud não tem, de documento
  malformado, sem classe oficial, sob sigilo ou cujo documento devolvido não é o número pedido;
- mas se o DataJud não deu resposta conclusiva (429, timeout, HTTP de erro) para algum processo, NADA é gravado e o
  erro sobe: uma falha de rede não pode virar a retirada de processos reais. O mesmo vale para um processo que já
  estava no arquivo gerado e agora "some" do DataJud: retirar um vínculo já publicado só vale por remoção explícita na
  curadoria, nunca por um sinal fraco como a resposta vazia de um tribunal que migrou de sistema.

Nada é inferido sobre o desfecho: o dossiê mostra só o último movimento que o tribunal registrou.
"""

import logging
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from etl.config import PROCESSED_DATA_DIR, PROCESSOS_ARQUIVO, PROCESSOS_CURADORIA_ARQUIVO
from etl.pipelines.loader_helpers import (
    cnj_digitos,
    cnj_valido,
    link_oficial,
    sob_sigilo,
    texto_oficial_sem_cpf,
)
from etl.utils.datafiles import load_json
from etl.utils.datajud_client import (
    DataJudClient,
    ErroDoDataJud,
    deduzir_aliases_datajud,
    parse_cnj_parts,
)
from etl.utils.io_utils import atomic_write_json

logger = logging.getLogger("ProcessosExtractor")

# Campos de identificação da pessoa que a curadoria carrega para o resolvedor de pessoas.
CAMPOS_DA_PESSOA = ("nome_civil", "nome_eleitoral", "camara_id", "senado_id")
# Texto livre do DataJud que vai para o arquivo versionado: sem CPF já aqui (D3), não só na carga.
CAMPOS_DE_TEXTO = ("tribunal", "grau", "classe_assunto", "classe_tpu_nome", "orgao_julgador", "ultimo_movimento")


def cobertura_do_datajud(numero: str) -> bool:
    """O DataJud tem índice para o tribunal do número (o STF e as justiças sem índice público ficam de fora)."""
    partes = parse_cnj_parts(numero)
    return bool(partes and deduzir_aliases_datajud(partes))


def _limpar_textos(resumo: Dict[str, Any]) -> None:
    for campo in CAMPOS_DE_TEXTO:
        resumo[campo] = texto_oficial_sem_cpf(resumo.get(campo))
    assuntos = resumo.get("assuntos_tpu")
    resumo["assuntos_tpu"] = (
        [a for a in (texto_oficial_sem_cpf(x) for x in assuntos) if a] if isinstance(assuntos, list) else []
    )


def enriquecer(
    curadoria: List[Any],
    client: Optional[DataJudClient] = None,
    anteriores: Optional[Set[str]] = None,
    hoje: Optional[date] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Os processos da curadoria com os metadados do DataJud, e a contagem do que ficou de fora e por quê. `anteriores` são
    os números (só dígitos) do arquivo gerado na rodada anterior: um deles que o DataJud não encontra agora conta como
    erro (a extração aborta), não como retirada.
    """
    client = client or DataJudClient()
    anteriores = anteriores or set()
    consultado_em = (hoje or date.today()).isoformat()
    contagem: Dict[str, int] = defaultdict(int)
    saida: List[Dict[str, Any]] = []
    for entrada in curadoria:
        if not isinstance(entrada, dict):
            contagem["invalidas"] += 1
            continue
        numero = cnj_valido(entrada.get("numero_processo"))
        vinculo = link_oficial(entrada.get("link_comprovacao"))
        if numero is None or vinculo is None:
            contagem["invalidas"] += 1
            continue
        if not cobertura_do_datajud(numero):
            contagem["sem_cobertura"] += 1
            logger.warning("Processo %s é de um tribunal que o DataJud não cobre; fora da carga.", numero)
            continue
        try:
            origem = client.consultar_processo(numero)
        except ErroDoDataJud as erro:
            contagem["erros"] += 1
            logger.error("%s", erro)
            continue
        if not origem:
            if cnj_digitos(numero) in anteriores:
                contagem["erros"] += 1
                logger.error(
                    "Processo %s já estava na carga e o DataJud não o encontra agora; nada será alterado. Para retirá-lo, "
                    "remova-o da curadoria.",
                    numero,
                )
            else:
                contagem["nao_encontrados"] += 1
                logger.warning("Processo %s não encontrado no DataJud; fora da carga.", numero)
            continue
        try:
            resumo = client.consolidar_resumo_processo(origem)
        except (TypeError, AttributeError, ValueError):
            contagem["malformados"] += 1
            logger.warning("Documento do DataJud malformado para %s; fora da carga.", numero)
            continue
        if cnj_digitos(resumo.get("numero_processo")) != cnj_digitos(numero):
            contagem["divergentes"] += 1
            logger.warning("O DataJud devolveu outro processo para %s; fora da carga.", numero)
            continue
        if sob_sigilo(resumo.pop("nivel_sigilo", None)):
            contagem["sigilosos"] += 1
            logger.warning("Processo %s sob sigilo; fora da carga.", numero)
            continue
        _limpar_textos(resumo)
        if not resumo.get("classe_tpu_nome"):
            contagem["sem_classe"] += 1
            logger.warning("Processo %s sem classe oficial no DataJud; fora da carga.", numero)
            continue
        item = {campo: entrada[campo] for campo in CAMPOS_DA_PESSOA if campo in entrada}
        item.update(resumo)
        # o número é o da curadoria, já validado e no formato CNJ; o do DataJud vem sem pontuação
        item["numero_processo"] = numero
        item["link_comprovacao"] = vinculo
        item["consultado_em"] = consultado_em
        saida.append(item)
    return saida, dict(contagem)


def _numeros_anteriores(caminho: Path) -> Set[str]:
    """Os números (só dígitos) do arquivo gerado antes; ausente ou ilegível, nenhum."""
    anterior = load_json(caminho, None)
    if not isinstance(anterior, list):
        return set()
    return {cnj_digitos(i.get("numero_processo")) for i in anterior if isinstance(i, dict)} - {""}


def extrair(processed_dir: Path = PROCESSED_DATA_DIR, client: Optional[DataJudClient] = None) -> Dict[str, int]:
    """
    Lê a curadoria, consulta o DataJud e grava `processos_judiciais.json`. Curadoria ausente ou que não é uma lista não
    altera nada; processo sem resposta conclusiva do DataJud (ou que sumiu do DataJud depois de publicado) levanta
    `ErroDoDataJud` sem gravar.
    """
    curadoria = load_json(processed_dir / PROCESSOS_CURADORIA_ARQUIVO, None)
    if not isinstance(curadoria, list):
        logger.warning("%s ausente ou inválido; nada foi extraído.", PROCESSOS_CURADORIA_ARQUIVO)
        return {"processos": 0}
    processos, contagem = enriquecer(curadoria, client, _numeros_anteriores(processed_dir / PROCESSOS_ARQUIVO))
    if contagem.get("erros"):
        raise ErroDoDataJud(
            f"{contagem['erros']} processo(s) sem resposta conclusiva do DataJud; {PROCESSOS_ARQUIVO} não foi alterado. "
            "Rode de novo quando o DataJud responder."
        )
    atomic_write_json(processed_dir / PROCESSOS_ARQUIVO, processos)
    return {**contagem, "processos": len(processos)}
