"""
Pessoas e mandatos: deputados e senadores em exercício, presidentes e ministros da Fazenda (arquivo curado) e os
ex-parlamentares das legislaturas anteriores. O CPF nunca é lido (decisão D3): o arquivo de presidentes traz o campo e ele
não passa daqui. O que liga as fontes pelo CPF é o HMAC dele (`cpf_identificadores.json`, `ler_cpfs`), nunca o número.

A pessoa é identificada pelo id oficial da casa (`CAMARA_ID`, `SENADO_ID`); presidentes e ministros, que não têm id oficial,
pela chave curada (`CURADORIA_ID`: o nome civil normalizado, no arquivo curado com fonte registrada).
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from etl.carga.base import (
    Resultado,
    contagem_de,
    criar_rejeitos,
    escalar,
    executar_sql,
    ler_rejeitos,
    tabela_temporaria,
)
from etl.extractors.votacoes_extractor import ARQUIVO_ANTERIORES
from etl.pipelines.loader_helpers import (
    _to_date,
    ano_da_eleicao,
    data_iso,
    inteiro,
    legislatura_datas,
    texto_ou_none,
)
from etl.utils.datafiles import load_deputados, load_json, load_senadores

logger = logging.getLogger("CargaPessoas")

CAMARA, SENADO = "CAMARA", "SENADO"
ARQUIVO_SENADORES_BASICOS = "senadores_dados_basicos.json"
ARQUIVO_FILIACOES_SENADO = "senadores_filiacoes.json"
# "Sem partido" não é partido: o período fica sem filiação (desconhecido), em vez de virar uma sigla
SEM_PARTIDO = {"S/PARTIDO", "S.PART.", "SEM PARTIDO"}

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
COLUNAS_FILIACAO_SENADO = {"id_valor": "text", "partido_sigla": "text", "inicio": "date", "fim": "date"}
COLUNAS_MINISTRO = {
    "ref_mandato": "text",
    "nome": "text",
    "inicio": "date",
    "fim": "date",
    "orgao": "text",
    "economia": "boolean",
}
MOTIVOS_DO_PRESIDENTE = {"CONCLUIDO": "CONCLUIDO", "IMPEACHMENT": "IMPEACHMENT", "RENUNCIA": "RENUNCIA"}


def _biografia_do_presidente(eleicao: Any, status: Any) -> str:
    partes = ["Presidente da República."]
    if texto_ou_none(eleicao):
        partes.append(f"Eleição: {texto_ou_none(eleicao)}.")
    if texto_ou_none(status):
        partes.append(f"Status: {texto_ou_none(status)}.")
    return " ".join(partes)


def _biografia(cargo: str, uf: Optional[str], partido: Optional[str]) -> Optional[str]:
    """Texto só com o que a fonte informa: sem UF ou sem partido a parte some, nunca vira 'None'."""
    if uf and partido:
        return f"{cargo} pela UF {uf} ({partido})."
    if uf:
        return f"{cargo} pela UF {uf}."
    if partido:
        return f"{cargo} ({partido})."
    return None


@dataclass
class Lote:
    """O que os arquivos trazem de pessoas e mandatos; a primeira fonte a citar um campo vale para ele."""

    pessoas: Dict[Tuple[str, str], Dict[str, Any]] = field(default_factory=dict)
    mandatos: Dict[Tuple[Any, ...], Dict[str, Any]] = field(default_factory=dict)
    ministros: List[Dict[str, Any]] = field(default_factory=list)
    cpfs: List[Dict[str, Any]] = field(default_factory=list)  # HMAC do CPF por id oficial (nunca o CPF)
    filiacoes_senado: List[Dict[str, Any]] = field(default_factory=list)  # partido do senador por período
    siglas: Set[str] = field(default_factory=set)
    rejeitos: Dict[str, int] = field(default_factory=dict)  # registros que nem chegam ao SQL, com o motivo

    def rejeitar(self, motivo: str, quantas: int = 1) -> None:
        if quantas > 0:
            self.rejeitos[motivo] = self.rejeitos.get(motivo, 0) + quantas

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
def _sem_identificador(data_dir: Path, arquivo: str, chave: str) -> int:
    """Registros do arquivo sem o id oficial: `dedupe_by_key` os descarta em silêncio, e aqui eles contam como rejeitados."""
    bruto = load_json(Path(data_dir) / arquivo, []) or []
    return sum(1 for r in bruto if isinstance(r, dict) and r.get(chave) is None)


def ler_deputados(lote: Lote, data_dir: Path) -> None:
    lote.rejeitar("SEM_IDENTIFICADOR", _sem_identificador(data_dir, "deputados_camara.json", "camara_id"))
    for d in load_deputados(data_dir):
        if not d.get("camara_id"):
            lote.rejeitar("SEM_IDENTIFICADOR")
            continue
        legislatura = inteiro(d.get("id_legislatura"))
        uf, partido = texto_ou_none(d.get("uf")), texto_ou_none(d.get("partido_sigla"))
        biografia = _biografia("Deputado Federal", uf, partido)
        lote.pessoa(
            "CAMARA_API",
            "CAMARA_ID",
            d["camara_id"],
            1,
            nome_exibicao=texto_ou_none(d.get("nome_eleitoral")) or texto_ou_none(d.get("nome_civil")),
            nome_civil=texto_ou_none(d.get("nome_civil")),
            sexo=texto_ou_none(d.get("sexo")),
            data_nascimento=data_iso(d.get("data_nascimento")),
            uf_nascimento=texto_ou_none(d.get("uf_nascimento")),
            municipio_nascimento=texto_ou_none(d.get("municipio_nascimento")),
            foto_url=texto_ou_none(d.get("foto_url")),
            biografia=biografia,
            email=texto_ou_none(d.get("email")),
            gabinete_sala=texto_ou_none(d.get("gabinete_sala")),
            gabinete_telefone=texto_ou_none(d.get("gabinete_telefone")),
        )
        if legislatura:
            inicio, fim = legislatura_datas(legislatura)
            lote.mandato(
                "CAMARA_API", "CAMARA_ID", d["camara_id"], "DEPUTADO_FEDERAL", False, uf=uf, partido_sigla=partido,
                condicao="TITULAR", ano_eleicao=ano_da_eleicao(inicio), inicio=inicio.isoformat(), fim=fim.isoformat(),
            )  # fmt: skip
        if partido:
            lote.siglas.add(partido)


def ler_senadores(lote: Lote, data_dir: Path) -> None:
    lote.rejeitar("SEM_IDENTIFICADOR", _sem_identificador(data_dir, "senadores_senado.json", "senado_id"))
    for s in load_senadores(data_dir):
        if not s.get("senado_id"):
            lote.rejeitar("SEM_IDENTIFICADOR")
            continue
        uf, partido = texto_ou_none(s.get("uf")), texto_ou_none(s.get("partido_sigla"))
        lote.pessoa(
            "SENADO_API",
            "SENADO_ID",
            s["senado_id"],
            1,
            nome_exibicao=texto_ou_none(s.get("nome_eleitoral")) or texto_ou_none(s.get("nome_civil")),
            nome_civil=texto_ou_none(s.get("nome_civil")),
            sexo=texto_ou_none(s.get("sexo")),
            data_nascimento=data_iso(s.get("data_nascimento")),
            uf_nascimento=texto_ou_none(s.get("uf_nascimento")),
            municipio_nascimento=texto_ou_none(s.get("municipio_nascimento")),
            foto_url=texto_ou_none(s.get("foto_url")),
            biografia=_biografia("Senador Federal", uf, partido),
            email=texto_ou_none(s.get("email")),
            gabinete_sala=texto_ou_none(s.get("gabinete_sala")),
            gabinete_telefone=texto_ou_none(s.get("gabinete_telefone")),
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
                condicao="SUPLENTE" if suplente else "TITULAR", ano_eleicao=ano_da_eleicao(inicio),
                inicio=inicio.isoformat(), fim=fim.isoformat() if fim else None,
            )  # fmt: skip
        if partido:
            lote.siglas.add(partido)


def ler_cpfs(lote: Lote, data_dir: Path) -> None:
    """HMAC do CPF por id oficial (`cpf_identificadores.json`, gerado pelo extrator de CPF); arquivo ausente = sem CPF."""
    for item in load_json(Path(data_dir) / "cpf_identificadores.json", []) or []:
        if isinstance(item, dict) and item.get("cpf_hmac") and item.get("id_tipo") and item.get("id_valor") is not None:
            lote.cpfs.append({k: texto_ou_none(item.get(k)) for k in COLUNAS_CPF})


def ler_presidentes(lote: Lote, data_dir: Path) -> None:
    for p in load_json(Path(data_dir) / "presidentes_historico.json", []) or []:
        nome_civil = texto_ou_none(p.get("nome_civil"))
        if not nome_civil or not p.get("id_referencia"):  # a chave curada vem do nome civil: sem ele não há identidade
            lote.rejeitar("SEM_IDENTIFICADOR")
            continue
        chave = "pessoa:" + nome_civil
        lote.pessoa(
            "CURADORIA",
            "CURADORIA_ID",
            chave,
            1,
            nome_exibicao=texto_ou_none(p.get("nome_eleitoral")) or texto_ou_none(p.get("nome_civil")),
            nome_civil=nome_civil,
            sexo=texto_ou_none(p.get("genero")),
            data_nascimento=data_iso(p.get("data_nascimento")),
            data_falecimento=data_iso(p.get("data_falecimento")),
            uf_nascimento=texto_ou_none(p.get("naturalidade_uf")),
            municipio_nascimento=texto_ou_none(p.get("naturalidade_municipio")),
            foto_url=texto_ou_none(p.get("foto_url")),
            biografia=_biografia_do_presidente(p.get("ano_eleicao"), p.get("status_mandato")),
        )
        status = p.get("status_mandato")
        referencia = p["id_referencia"]
        lote.mandato(
            "CURADORIA", "CURADORIA_ID", chave, "PRESIDENTE", True, uf="BR", partido_sigla=texto_ou_none(p.get("partido_sigla")),
            condicao="TITULAR", numero_mandato=p.get("mandato_numero") or 1, ano_eleicao=p.get("ano_eleicao"),
            inicio=data_iso(p.get("data_inicio")), fim=data_iso(p.get("data_fim")),
            motivo_encerramento=MOTIVOS_DO_PRESIDENTE.get(status), ref_mandato=referencia,
            rotulo=texto_ou_none(p.get("rotulo_mandato")),
        )  # fmt: skip
        for m in p.get("ministros_fazenda_chave") or []:
            lote.ministros.append(
                {
                    "ref_mandato": referencia,
                    "nome": m["nome"],
                    "inicio": data_iso(m.get("inicio")),
                    "fim": data_iso(m.get("fim")),
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
        if not d.get("camara_id"):
            lote.rejeitar("SEM_IDENTIFICADOR")
            continue
        parlamentar_da_camara(lote, d["camara_id"], d, d.get("legislaturas") or [], "CAMARA_API", 0)
    for s in dados.get("senadores") or []:
        if not s.get("senado_id"):
            lote.rejeitar("SEM_IDENTIFICADOR")
            continue
        parlamentar_do_senado(lote, s["senado_id"], s, s.get("mandatos") or [], "SENADO_API", 0, votantes)


def ler_senadores_basicos(lote: Lote, data_dir: Path) -> None:
    """Quem só consta nos votos e na presença do Senado: identidade (nome completo, nascimento) sem mandato."""
    dados = load_json(Path(data_dir) / ARQUIVO_SENADORES_BASICOS, None)
    if not isinstance(dados, dict) or not dados.get("fonte") or dados.get("is_synthetic"):
        return
    for s in dados.get("senadores") or []:
        if not s.get("senado_id"):
            continue
        lote.pessoa(
            "SENADO_API", "SENADO_ID", s["senado_id"], 0,
            nome_exibicao=texto_ou_none(s.get("nome")), nome_civil=texto_ou_none(s.get("nome_civil")), sexo=texto_ou_none(s.get("sexo")),
            data_nascimento=data_iso(s.get("data_nascimento")), uf_nascimento=texto_ou_none(s.get("uf_nascimento")),
            municipio_nascimento=texto_ou_none(s.get("municipio_nascimento")),
        )  # fmt: skip


def ler_filiacoes_senadores(lote: Lote, data_dir: Path) -> None:
    """Partido do senador em cada período (`senadores_filiacoes.json`); arquivo ausente ou sem proveniência = sem períodos."""
    dados = load_json(Path(data_dir) / ARQUIVO_FILIACOES_SENADO, None)
    if not isinstance(dados, dict) or not dados.get("fonte") or dados.get("is_synthetic"):
        return
    for s in dados.get("senadores") or []:
        if not isinstance(s, dict) or not s.get("senado_id"):
            continue
        for f in s.get("filiacoes") or []:
            sigla, inicio, fim = texto_ou_none(f.get("sigla")), _to_date(f.get("inicio")), _to_date(f.get("fim"))
            if not sigla or sigla.upper() in SEM_PARTIDO or inicio is None:
                continue
            if (fim or inicio) < date(1995, 1, 1):
                continue
            lote.siglas.add(sigla)
            lote.filiacoes_senado.append(
                {
                    "id_valor": str(s["senado_id"]),
                    "partido_sigla": sigla,
                    "inicio": inicio.isoformat(),
                    "fim": fim.isoformat() if fim else None,
                }
            )


def parlamentar_da_camara(
    lote: Lote, camara_id: Any, info: Dict[str, Any], legislaturas: List[int], fonte: str, prioridade: int
) -> None:
    uf, partido = texto_ou_none(info.get("uf")), texto_ou_none(info.get("partido") or info.get("partido_sigla"))
    lote.pessoa(
        fonte, "CAMARA_ID", camara_id, prioridade,
        nome_exibicao=texto_ou_none(info.get("nome") or info.get("nome_eleitoral")), nome_civil=texto_ou_none(info.get("nome_civil")),
        foto_url=texto_ou_none(info.get("foto_url")),
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
            ano_eleicao=ano_da_eleicao(inicio), inicio=inicio.isoformat(), fim=fim.isoformat(),
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
    partido = texto_ou_none(info.get("partido_sigla") or info.get("partido"))
    validos = [
        m
        for m in mandatos
        if "suplente" not in str(m.get("participacao") or "").lower() or (sid is not None and sid in votantes)
    ]
    if not validos:
        return  # suplente que nunca votou não teve atuação a registrar
    lote.pessoa(
        fonte, "SENADO_ID", senado_id, prioridade,
        nome_exibicao=texto_ou_none(info.get("nome") or info.get("nome_eleitoral")), nome_civil=texto_ou_none(info.get("nome_civil")),
        foto_url=texto_ou_none(info.get("foto_url")), sexo=texto_ou_none(info.get("sexo")),
        data_nascimento=data_iso(info.get("data_nascimento")), uf_nascimento=texto_ou_none(info.get("uf_nascimento")),
        municipio_nascimento=texto_ou_none(info.get("municipio_nascimento")),
    )  # fmt: skip
    por_eleicao: Dict[int, int] = (
        {}
    )  # exercícios da mesma pessoa na mesma eleição (titular e suplente, ou duas suplências)
    for m in sorted(validos, key=lambda x: str(x.get("inicio") or "")):
        inicio, fim = _to_date(m.get("inicio")), _to_date(m.get("fim"))
        if inicio is None or (fim or inicio) < date(1995, 1, 1):
            continue
        suplente = "suplente" in str(m.get("participacao") or "").lower()
        ano = ano_da_eleicao(inicio)
        por_eleicao[ano] = por_eleicao.get(ano, 0) + 1
        lote.mandato(
            fonte, "SENADO_ID", senado_id, "SENADOR", False, uf=texto_ou_none(m.get("uf")) or texto_ou_none(info.get("uf")),
            partido_sigla=partido, condicao="SUPLENTE" if suplente else "TITULAR", numero_mandato=por_eleicao[ano],
            ano_eleicao=ano, inicio=inicio.isoformat(), fim=fim.isoformat() if fim else None,
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
    tabela_temporaria(
        cursor,
        "_in_filiacao_senador",
        COLUNAS_FILIACAO_SENADO,
        (_linha(f, COLUNAS_FILIACAO_SENADO) for f in lote.filiacoes_senado),
    )
    executar_sql(cursor, "pessoas")
    rejeitos = ler_rejeitos(cursor)
    for motivo, quantas in lote.rejeitos.items():
        rejeitos[motivo] = rejeitos.get(motivo, 0) + quantas
    lidas = len(lote.mandatos) + len(lote.ministros) + sum(lote.rejeitos.values())
    # gravadas é medida: os mandatos e ministros que sobraram no SQL depois de tirar os rejeitados
    gravadas = escalar(cursor, "SELECT (SELECT count(*) FROM _m) + (SELECT count(*) FROM _min)")
    return Resultado(
        contagem_de(lidas, rejeitos, int(gravadas)),
        extras={"pessoas": len(lote.pessoas), "mandatos": len(lote.mandatos), "ministros": len(lote.ministros)},
    )


def carregar_pessoas(cursor: Any, data_dir: Path, votantes: Optional[Set[int]] = None) -> Resultado:
    lote = Lote()
    ler_deputados(lote, data_dir)
    ler_senadores(lote, data_dir)
    ler_presidentes(lote, data_dir)
    ler_anteriores(lote, data_dir, votantes or set())
    ler_cpfs(lote, data_dir)
    ler_senadores_basicos(lote, data_dir)
    ler_filiacoes_senadores(lote, data_dir)
    return gravar_lote(cursor, lote)
