"""
Pessoas e mandatos: deputados e senadores em exercício, presidentes e ministros da Fazenda (arquivo curado) e os
ex-parlamentares das legislaturas anteriores. Nenhum CPF é lido (decisão D3): o arquivo de presidentes traz o campo e ele
não passa daqui.

A pessoa é identificada pelo id oficial da casa (`CAMARA_ID`, `SENADO_ID`); presidentes e ministros, que não têm id oficial,
pela chave curada (`CURADORIA_ID`: o nome civil normalizado, no arquivo curado com fonte registrada).
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from etl.carga.base import Resultado, contagem_de, criar_rejeitos, executar_sql, ler_rejeitos, tabela_temporaria
from etl.pipelines.loader_helpers import _to_date, inteiro, legislatura_datas
from etl.utils.datafiles import load_deputados, load_json, load_senadores

logger = logging.getLogger("CargaPessoas")

CAMARA, SENADO = "CAMARA", "SENADO"
ARQUIVO_ANTERIORES = "parlamentares_legislaturas_anteriores.json"

COLUNAS_PESSOA = {
    "fonte": "text",
    "id_tipo": "text",
    "id_valor": "text",
    "prioridade": "int",
    "nome_exibicao": "text",
    "nome_civil": "text",
    "sexo": "text",
    "data_nascimento": "date",
    "data_falecimento": "date",
    "uf_nascimento": "text",
    "municipio_nascimento": "text",
    "foto_url": "text",
    "biografia": "text",
    "email": "text",
    "gabinete_sala": "text",
    "gabinete_telefone": "text",
}
COLUNAS_MANDATO = {
    "id_tipo": "text",
    "id_valor": "text",
    "cargo": "text",
    "uf": "text",
    "partido_sigla": "text",
    "condicao": "text",
    "numero_mandato": "int",
    "ano_eleicao": "int",
    "inicio": "date",
    "fim": "date",
    "motivo_encerramento": "text",
    "ref_mandato": "text",
    "rotulo": "text",
    "fonte": "text",
    "sobrescreve": "boolean",
}
COLUNAS_CPF = {"id_tipo": "text", "id_valor": "text", "cpf_hmac": "text", "origem": "text"}
COLUNAS_MINISTRO = {
    "ref_mandato": "text",
    "nome": "text",
    "inicio": "date",
    "fim": "date",
    "orgao": "text",
    "economia": "boolean",
}
MOTIVOS_DO_PRESIDENTE = {"CONCLUIDO": "CONCLUIDO", "IMPEACHMENT": "IMPEACHMENT", "RENUNCIA": "RENUNCIA"}


def _texto(valor: Any) -> Optional[str]:
    """Texto como veio; vazio vira nulo (desconhecido é nulo, nunca texto vazio)."""
    if valor is None or (isinstance(valor, float) and valor != valor):
        return None
    texto = str(valor).strip()
    return texto or None


def _data(valor: Any) -> Optional[str]:
    convertida = _to_date(valor)
    return convertida.isoformat() if convertida else None


@dataclass
class Lote:
    """O que os arquivos trazem de pessoas e mandatos; a primeira fonte a citar um campo vale para ele."""

    pessoas: Dict[Tuple[str, str], Dict[str, Any]] = field(default_factory=dict)
    mandatos: Dict[Tuple[Any, ...], Dict[str, Any]] = field(default_factory=dict)
    ministros: List[Dict[str, Any]] = field(default_factory=list)
    cpfs: List[Dict[str, Any]] = field(default_factory=list)  # HMAC do CPF por id oficial (nunca o CPF)
    siglas: Set[str] = field(default_factory=set)
    lidas: int = 0

    def pessoa(self, fonte: str, id_tipo: str, id_valor: Any, prioridade: int, **campos: Any) -> None:
        chave = (id_tipo, str(id_valor))
        atual = self.pessoas.get(chave)
        novo = {"fonte": fonte, "id_tipo": id_tipo, "id_valor": str(id_valor), "prioridade": prioridade, **campos}
        if atual is None:
            self.pessoas[chave] = novo
            return
        for coluna, valor in novo.items():
            if atual.get(coluna) is None and valor is not None:
                atual[coluna] = valor
        atual["prioridade"] = max(atual["prioridade"], prioridade)

    def mandato(self, fonte: str, id_tipo: str, id_valor: Any, cargo: str, sobrescreve: bool, **campos: Any) -> None:
        chave = (
            id_tipo,
            str(id_valor),
            cargo,
            campos.get("ano_eleicao"),
            campos.get("numero_mandato", 1),
            campos.get("ref_mandato"),
        )
        if chave in self.mandatos:
            return
        sigla = campos.get("partido_sigla")
        if sigla:
            self.siglas.add(sigla)
        self.mandatos[chave] = {
            "fonte": fonte,
            "id_tipo": id_tipo,
            "id_valor": str(id_valor),
            "cargo": cargo,
            "sobrescreve": sobrescreve,
            "numero_mandato": 1,
            **campos,
        }


def _linha(dados: Dict[str, Any], colunas: Iterable[str]) -> List[Any]:
    return [dados.get(c) for c in colunas]


# ---------------------------------------------------------------------------------------------------- leitura
def ler_deputados(lote: Lote, data_dir: Path) -> None:
    for d in load_deputados(data_dir):
        lote.lidas += 1
        legislatura = inteiro(d.get("id_legislatura"))
        uf, partido = _texto(d.get("uf")), _texto(d.get("partido_sigla"))
        biografia = f"Deputado Federal pela UF {uf} ({partido})." if uf or partido else None
        lote.pessoa(
            "CAMARA_API",
            "CAMARA_ID",
            d["camara_id"],
            1,
            nome_exibicao=_texto(d.get("nome_eleitoral")) or _texto(d.get("nome_civil")),
            nome_civil=_texto(d.get("nome_civil")),
            sexo=_texto(d.get("sexo")),
            data_nascimento=_data(d.get("data_nascimento")),
            uf_nascimento=_texto(d.get("uf_nascimento")),
            municipio_nascimento=_texto(d.get("municipio_nascimento")),
            foto_url=_texto(d.get("foto_url")),
            biografia=biografia,
            email=_texto(d.get("email")),
            gabinete_sala=_texto(d.get("gabinete_sala")),
            gabinete_telefone=_texto(d.get("gabinete_telefone")),
        )
        if legislatura:
            inicio, fim = legislatura_datas(legislatura)
            lote.mandato(
                "CAMARA_API", "CAMARA_ID", d["camara_id"], "DEPUTADO_FEDERAL", False, uf=uf, partido_sigla=partido,
                condicao="TITULAR", ano_eleicao=inicio.year - 1, inicio=inicio.isoformat(), fim=fim.isoformat(),
            )  # fmt: skip
        if partido:
            lote.siglas.add(partido)


def ler_senadores(lote: Lote, data_dir: Path) -> None:
    for s in load_senadores(data_dir):
        lote.lidas += 1
        uf, partido = _texto(s.get("uf")), _texto(s.get("partido_sigla"))
        lote.pessoa(
            "SENADO_API",
            "SENADO_ID",
            s["senado_id"],
            1,
            nome_exibicao=_texto(s.get("nome_eleitoral")) or _texto(s.get("nome_civil")),
            nome_civil=_texto(s.get("nome_civil")),
            sexo=_texto(s.get("sexo")),
            data_nascimento=_data(s.get("data_nascimento")),
            uf_nascimento=_texto(s.get("uf_nascimento")),
            municipio_nascimento=_texto(s.get("municipio_nascimento")),
            foto_url=_texto(s.get("foto_url")),
            biografia=f"Senador Federal pela UF {uf} ({partido})." if uf or partido else None,
            email=_texto(s.get("email")),
            gabinete_sala=_texto(s.get("gabinete_sala")),
            gabinete_telefone=_texto(s.get("gabinete_telefone")),
        )
        inicio, fim = _to_date(s.get("mandato_inicio")), _to_date(s.get("mandato_fim"))
        if inicio is None and s.get("legislatura_inicio"):
            inicio = legislatura_datas(int(s["legislatura_inicio"]))[0]
        if fim is None and s.get("legislatura_fim"):
            fim = legislatura_datas(int(s["legislatura_fim"]))[1]
        if inicio is not None:  # sem data de início na fonte não há mandato: nada de data inventada
            suplente = "suplente" in str(s.get("condicao_mandato") or "").lower()
            lote.mandato(
                "SENADO_API", "SENADO_ID", s["senado_id"], "SENADOR", True, uf=uf, partido_sigla=partido,
                condicao="SUPLENTE" if suplente else "TITULAR", ano_eleicao=inicio.year - 1,
                inicio=inicio.isoformat(), fim=fim.isoformat() if fim else None,
            )  # fmt: skip
        if partido:
            lote.siglas.add(partido)


def ler_cpfs(lote: Lote, data_dir: Path) -> None:
    """HMAC do CPF por id oficial (`cpf_identificadores.json`, gerado pelo extrator de CPF); arquivo ausente = sem CPF."""
    for item in load_json(Path(data_dir) / "cpf_identificadores.json", []) or []:
        if isinstance(item, dict) and item.get("cpf_hmac") and item.get("id_tipo") and item.get("id_valor") is not None:
            lote.cpfs.append({k: _texto(item.get(k)) for k in COLUNAS_CPF})


def ler_presidentes(lote: Lote, data_dir: Path) -> None:
    for p in load_json(Path(data_dir) / "presidentes_historico.json", []) or []:
        lote.lidas += 1
        chave = "pessoa:" + str(p["nome_civil"])
        lote.pessoa(
            "CURADORIA",
            "CURADORIA_ID",
            chave,
            1,
            nome_exibicao=_texto(p.get("nome_eleitoral")) or _texto(p.get("nome_civil")),
            nome_civil=_texto(p.get("nome_civil")),
            sexo=_texto(p.get("genero")),
            data_nascimento=_data(p.get("data_nascimento")),
            data_falecimento=_data(p.get("data_falecimento")),
            uf_nascimento=_texto(p.get("naturalidade_uf")),
            municipio_nascimento=_texto(p.get("naturalidade_municipio")),
            foto_url=_texto(p.get("foto_url")),
            biografia=f"Presidente da República. Eleição: {p.get('ano_eleicao')}. Status: {p.get('status_mandato')}.",
        )
        status = p.get("status_mandato")
        referencia = p["id_referencia"]
        lote.mandato(
            "CURADORIA", "CURADORIA_ID", chave, "PRESIDENTE", True, uf="BR", partido_sigla=_texto(p.get("partido_sigla")),
            condicao="TITULAR", numero_mandato=p.get("mandato_numero") or 1, ano_eleicao=p.get("ano_eleicao"),
            inicio=_data(p.get("data_inicio")), fim=_data(p.get("data_fim")),
            motivo_encerramento=MOTIVOS_DO_PRESIDENTE.get(status), ref_mandato=referencia,
            rotulo=_texto(p.get("rotulo_mandato")),
        )  # fmt: skip
        for m in p.get("ministros_fazenda_chave") or []:
            lote.ministros.append(
                {
                    "ref_mandato": referencia,
                    "nome": m["nome"],
                    "inicio": _data(m.get("inicio")),
                    "fim": _data(m.get("fim")),
                    "orgao": "Ministério da Fazenda",
                    "economia": True,
                }
            )


def ler_anteriores(lote: Lote, data_dir: Path, votantes: Set[int]) -> None:
    """Ex-deputados e ex-senadores (titulares; suplente só se votou). Mandatos de legislaturas anteriores, a partir de 1995."""
    dados = load_json(Path(data_dir) / ARQUIVO_ANTERIORES, None)
    if not isinstance(dados, dict) or not dados.get("fonte") or dados.get("is_synthetic"):
        logger.warning("%s ausente ou sem proveniência: ex-parlamentares não carregados.", ARQUIVO_ANTERIORES)
        return
    for d in dados.get("deputados") or []:
        lote.lidas += 1
        if not d.get("camara_id"):
            continue
        parlamentar_da_camara(lote, d["camara_id"], d, d.get("legislaturas") or [], "CAMARA_API", 0)
    for s in dados.get("senadores") or []:
        lote.lidas += 1
        if not s.get("senado_id"):
            continue
        parlamentar_do_senado(lote, s["senado_id"], s, s.get("mandatos") or [], "SENADO_API", 0, votantes)


def ler_senadores_basicos(lote: Lote, data_dir: Path) -> None:
    """Quem só consta nos votos e na presença do Senado: identidade (nome completo, nascimento) sem mandato."""
    dados = load_json(Path(data_dir) / "senadores_dados_basicos.json", None)
    if not isinstance(dados, dict) or not dados.get("fonte") or dados.get("is_synthetic"):
        return
    for s in dados.get("senadores") or []:
        if not s.get("senado_id"):
            continue
        lote.pessoa(
            "SENADO_API", "SENADO_ID", s["senado_id"], 0,
            nome_exibicao=_texto(s.get("nome")), nome_civil=_texto(s.get("nome_civil")), sexo=_texto(s.get("sexo")),
            data_nascimento=_data(s.get("data_nascimento")), uf_nascimento=_texto(s.get("uf_nascimento")),
            municipio_nascimento=_texto(s.get("municipio_nascimento")),
        )  # fmt: skip


def parlamentar_da_camara(
    lote: Lote, camara_id: Any, info: Dict[str, Any], legislaturas: List[int], fonte: str, prioridade: int
) -> None:
    uf, partido = _texto(info.get("uf")), _texto(info.get("partido") or info.get("partido_sigla"))
    lote.pessoa(
        fonte, "CAMARA_ID", camara_id, prioridade,
        nome_exibicao=_texto(info.get("nome") or info.get("nome_eleitoral")), nome_civil=_texto(info.get("nome_civil")),
        foto_url=_texto(info.get("foto_url")),
    )  # fmt: skip
    for numero in legislaturas:
        legislatura = inteiro(numero)
        if not legislatura:
            continue
        inicio, fim = legislatura_datas(legislatura)
        if fim < date(1995, 1, 1):
            continue
        lote.mandato(
            fonte, "CAMARA_ID", camara_id, "DEPUTADO_FEDERAL", False, uf=uf, partido_sigla=partido, condicao="TITULAR",
            ano_eleicao=inicio.year - 1, inicio=inicio.isoformat(), fim=fim.isoformat(),
        )  # fmt: skip


def parlamentar_do_senado(
    lote: Lote,
    senado_id: Any,
    info: Dict[str, Any],
    mandatos: List[Dict[str, Any]],
    fonte: str,
    prioridade: int,
    votantes: Set[int],
) -> None:
    sid = inteiro(senado_id)
    partido = _texto(info.get("partido_sigla") or info.get("partido"))
    validos = [
        m
        for m in mandatos
        if "suplente" not in str(m.get("participacao") or "").lower() or (sid is not None and sid in votantes)
    ]
    if not validos:
        return  # suplente que nunca votou não teve atuação a registrar
    lote.pessoa(
        fonte, "SENADO_ID", senado_id, prioridade,
        nome_exibicao=_texto(info.get("nome") or info.get("nome_eleitoral")), nome_civil=_texto(info.get("nome_civil")),
        foto_url=_texto(info.get("foto_url")), sexo=_texto(info.get("sexo")),
        data_nascimento=_data(info.get("data_nascimento")), uf_nascimento=_texto(info.get("uf_nascimento")),
        municipio_nascimento=_texto(info.get("municipio_nascimento")),
    )  # fmt: skip
    for m in sorted(validos, key=lambda x: str(x.get("inicio") or "")):
        inicio, fim = _to_date(m.get("inicio")), _to_date(m.get("fim"))
        if inicio is None or (fim or inicio) < date(1995, 1, 1):
            continue
        suplente = "suplente" in str(m.get("participacao") or "").lower()
        lote.mandato(
            fonte, "SENADO_ID", senado_id, "SENADOR", False, uf=_texto(m.get("uf")) or _texto(info.get("uf")),
            partido_sigla=partido, condicao="SUPLENTE" if suplente else "TITULAR",
            ano_eleicao=inicio.year - 1, inicio=inicio.isoformat(), fim=fim.isoformat() if fim else None,
        )  # fmt: skip


# ---------------------------------------------------------------------------------------------------- gravação
def gravar_lote(cursor: Any, lote: Lote) -> Resultado:
    criar_rejeitos(cursor)
    tabela_temporaria(cursor, "_in_pessoa", COLUNAS_PESSOA, (_linha(p, COLUNAS_PESSOA) for p in lote.pessoas.values()))
    tabela_temporaria(
        cursor, "_in_mandato", COLUNAS_MANDATO, (_linha(m, COLUNAS_MANDATO) for m in lote.mandatos.values())
    )
    tabela_temporaria(cursor, "_in_ministro", COLUNAS_MINISTRO, (_linha(m, COLUNAS_MINISTRO) for m in lote.ministros))
    tabela_temporaria(cursor, "_in_cpf", COLUNAS_CPF, (_linha(c, COLUNAS_CPF) for c in lote.cpfs))
    executar_sql(cursor, "pessoas")
    rejeitos = ler_rejeitos(cursor)
    return Resultado(
        contagem_de(len(lote.mandatos) + len(lote.ministros), rejeitos),
        extras={"pessoas": len(lote.pessoas), "mandatos": len(lote.mandatos), "ministros": len(lote.ministros)},
    )


def carregar_pessoas(cursor: Any, data_dir: Path, votantes: Optional[Set[int]] = None) -> Resultado:
    lote = Lote()
    ler_deputados(lote, data_dir)
    ler_senadores(lote, data_dir)
    ler_presidentes(lote, data_dir)
    ler_anteriores(lote, data_dir, votantes or set())
    ler_cpfs(lote, data_dir)
    return gravar_lote(cursor, lote)
