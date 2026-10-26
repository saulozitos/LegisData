"""
Extrator de processos judiciais: enriquece com o DataJud (CNJ) os números de processo da curadoria.

O DataJud só responde por número de processo e não expõe as partes; por isso ele nunca descobre os processos de uma
pessoa. O vínculo vem de `processos_curados.json`: cada entrada traz a pessoa (os mesmos identificadores das demais
fontes), o número CNJ e o link da fonte oficial que liga o processo à pessoa. Daqui sai `processos_judiciais.json`,
que a carga `processos` do `fin` lê.

A curadoria é a fonte de verdade: o arquivo gerado reflete exatamente o que ela contém e o DataJud confirma. Por isso,
- uma curadoria válida e vazia grava `[]` (é assim que se retira um vínculo errado do dossiê);
- fica de fora, e é contado, o processo com número inválido, link que não é `http(s)`, que o DataJud não tem, de
  documento malformado, sem classe oficial, sob sigilo ou cujo documento devolvido não é o número pedido;
- mas se o DataJud não deu resposta conclusiva (429, timeout, HTTP de erro) para algum processo, NADA é gravado e o
  erro sobe: uma falha de rede não pode virar a retirada de processos reais.

Nada é inferido sobre o desfecho: o dossiê mostra só o último movimento que o tribunal registrou.
"""

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from etl.config import PROCESSED_DATA_DIR, PROCESSOS_ARQUIVO, PROCESSOS_CURADORIA_ARQUIVO
from etl.pipelines.loader_helpers import cnj_valido, link_http
from etl.utils.datafiles import load_json
from etl.utils.datajud_client import DataJudClient, ErroDoDataJud
from etl.utils.io_utils import atomic_write_json

logger = logging.getLogger("ProcessosExtractor")

PROVENIENCIA_DATAJUD = "CNJ / DataJud (Base Nacional de Dados do Poder Judiciário)"
# Campos de identificação da pessoa que a curadoria carrega para o resolvedor de pessoas.
CAMPOS_DA_PESSOA = ("nome_civil", "nome_eleitoral", "camara_id", "senado_id")


def _sob_sigilo(nivel: Any) -> bool:
    """Sigilo informado e diferente de zero. Um valor que não se lê como número também conta: na dúvida, não publica."""
    if nivel is None or isinstance(nivel, bool):
        return nivel is True
    try:
        return int(str(nivel).strip()) != 0
    except ValueError:
        return True


def enriquecer(
    curadoria: List[Any], client: Optional[DataJudClient] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Os processos da curadoria com os metadados do DataJud, e a contagem do que ficou de fora e por quê."""
    client = client or DataJudClient()
    contagem: Dict[str, int] = defaultdict(int)
    saida: List[Dict[str, Any]] = []
    for entrada in curadoria:
        if not isinstance(entrada, dict):
            contagem["invalidas"] += 1
            continue
        numero = cnj_valido(entrada.get("numero_processo"))
        vinculo = link_http(entrada.get("link_comprovacao"))
        if numero is None or vinculo is None:
            contagem["invalidas"] += 1
            continue
        try:
            origem = client.consultar_processo(numero)
        except ErroDoDataJud as erro:
            contagem["erros"] += 1
            logger.error("%s", erro)
            continue
        if not origem:
            contagem["nao_encontrados"] += 1
            logger.warning("Processo %s não encontrado no DataJud; fora da carga.", numero)
            continue
        try:
            resumo = client.consolidar_resumo_processo(origem)
        except (TypeError, AttributeError, ValueError):
            contagem["malformados"] += 1
            logger.warning("Documento do DataJud malformado para %s; fora da carga.", numero)
            continue
        if re.sub(r"[^0-9]", "", str(resumo.get("numero_processo") or "")) != re.sub(r"[^0-9]", "", numero):
            contagem["divergentes"] += 1
            logger.warning("O DataJud devolveu outro processo para %s; fora da carga.", numero)
            continue
        if _sob_sigilo(resumo.pop("nivel_sigilo", None)):
            contagem["sigilosos"] += 1
            logger.warning("Processo %s sob sigilo; fora da carga.", numero)
            continue
        if not resumo.get("classe_tpu_nome"):
            contagem["sem_classe"] += 1
            logger.warning("Processo %s sem classe oficial no DataJud; fora da carga.", numero)
            continue
        item = {campo: entrada[campo] for campo in CAMPOS_DA_PESSOA if campo in entrada}
        item.update(resumo)
        # o número é o da curadoria, já validado e no formato CNJ; o do DataJud vem sem pontuação
        item["numero_processo"] = numero
        item["link_comprovacao"] = vinculo
        item["fonte"] = PROVENIENCIA_DATAJUD
        item["is_synthetic"] = False
        saida.append(item)
    return saida, dict(contagem)


def extrair(processed_dir: Path = PROCESSED_DATA_DIR, client: Optional[DataJudClient] = None) -> Dict[str, int]:
    """
    Lê a curadoria, consulta o DataJud e grava `processos_judiciais.json`. Curadoria ausente ou que não é uma lista não
    altera nada; processo sem resposta conclusiva do DataJud levanta `ErroDoDataJud` sem gravar.
    """
    curadoria = load_json(processed_dir / PROCESSOS_CURADORIA_ARQUIVO, None)
    if not isinstance(curadoria, list):
        logger.warning("%s ausente ou inválido; nada foi extraído.", PROCESSOS_CURADORIA_ARQUIVO)
        return {"processos": 0}
    processos, contagem = enriquecer(curadoria, client)
    if contagem.get("erros"):
        raise ErroDoDataJud(
            f"{contagem['erros']} processo(s) sem resposta conclusiva do DataJud; {PROCESSOS_ARQUIVO} não foi alterado. "
            "Rode de novo quando o DataJud responder."
        )
    atomic_write_json(processed_dir / PROCESSOS_ARQUIVO, processos)
    return {**contagem, "processos": len(processos)}
