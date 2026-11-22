"""Funções de apoio para leitura e análise dos microdados da PNS 2019 (IBGE).

O módulo reúne quatro grupos de funções:

1. Leitura do layout (arquivo de input SAS do IBGE) e do dicionário de variáveis.
2. Leitura seletiva do arquivo de microdados em largura fixa.
3. Construção do desfecho e das variáveis derivadas usadas no estudo.
4. Estimação de proporções e médias considerando o desenho amostral complexo
   (estratos, UPAs, pesos calibrados e pós-estratificação), por linearização
   de Taylor.

Os códigos de variáveis seguem o dicionário oficial
``dicionario_PNS_microdados_2019.xls`` (versão de 30/05/2022).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Layout e dicionário
# ---------------------------------------------------------------------------

_SAS_LINE = re.compile(r"\s*@0*(\d+)\s+(\w+)\s+(\$?)(\d+)\.(\d*)")


def ler_layout_sas(caminho: str | Path) -> pd.DataFrame:
    """Lê o arquivo ``input_PNS_2019.txt`` (programa SAS) e devolve o layout.

    Retorna um DataFrame com as colunas ``variavel``, ``inicio`` (base 0),
    ``tamanho``, ``texto`` (True se a variável é lida como caractere) e
    ``decimais``.
    """
    linhas = []
    with open(caminho, encoding="latin1") as f:
        for linha in f:
            m = _SAS_LINE.match(linha)
            if m:
                linhas.append(
                    dict(
                        variavel=m.group(2),
                        inicio=int(m.group(1)) - 1,
                        tamanho=int(m.group(4)),
                        texto=m.group(3) == "$",
                        decimais=int(m.group(5) or 0),
                    )
                )
    return pd.DataFrame(linhas)


def ler_dicionario(caminho: str | Path) -> dict[str, dict]:
    """Lê o dicionário oficial (.xls) e devolve ``{codigo: {descricao, modulo, categorias}}``.

    ``categorias`` é uma lista de pares ``(codigo_categoria, rotulo)`` na ordem
    em que aparecem no dicionário.
    """
    bruto = pd.read_excel(caminho, header=None, engine="xlrd").iloc[5:]
    bruto.columns = ["pos", "tam", "cod", "quesito", "descricao", "categoria", "rotulo"]
    dic: dict[str, dict] = {}
    atual = None
    modulo = None
    for _, r in bruto.iterrows():
        if pd.notna(r.cod):
            atual = dict(
                descricao=" ".join(str(r.descricao).split()),
                modulo=modulo,
                categorias=[],
            )
            dic[str(r.cod).strip()] = atual
            if pd.notna(r.categoria) or pd.notna(r.rotulo):
                atual["categorias"].append((r.categoria, r.rotulo))
        elif atual is not None and (pd.notna(r.categoria) or pd.notna(r.rotulo)):
            atual["categorias"].append((r.categoria, r.rotulo))
        elif pd.notna(r.pos) and pd.isna(r.tam):
            # Linhas de título (Parte/Módulo) só têm texto na primeira coluna.
            modulo = " ".join(str(r.pos).split())
    return dic


def ler_microdados(
    caminho_txt: str | Path, layout: pd.DataFrame, variaveis: list[str]
) -> pd.DataFrame:
    """Lê apenas as ``variaveis`` pedidas do arquivo de largura fixa.

    Todas as colunas são lidas como texto (preservando zeros à esquerda dos
    códigos). Campos vazios viram ``NA``. A conversão numérica é feita depois,
    de forma explícita, por quem usa os dados.
    """
    faltando = set(variaveis) - set(layout.variavel)
    if faltando:
        raise KeyError(f"Variáveis ausentes do layout: {sorted(faltando)}")
    sel = layout.set_index("variavel").loc[variaveis]
    df = pd.read_fwf(
        caminho_txt,
        colspecs=[(i, i + t) for i, t in zip(sel.inicio, sel.tamanho)],
        names=variaveis,
        dtype=str,
        encoding="latin1",
    )
    for c in df.columns:
        df[c] = df[c].str.strip().replace("", pd.NA)
    return df


# ---------------------------------------------------------------------------
# 2. Variáveis derivadas
# ---------------------------------------------------------------------------

REGIOES = {"1": "Norte", "2": "Nordeste", "3": "Sudeste", "4": "Sul", "5": "Centro-Oeste"}

# Exercícios classificados como de intensidade vigorosa no lazer, seguindo o
# critério usado pelo Vigitel/Ministério da Saúde para o quesito P036.
# Os demais tipos (caminhada, hidroginástica, natação etc.) são leves/moderados.
P036_VIGOROSOS = {"03", "04", "05", "06", "12", "13", "15"}


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _cat(valores: pd.Series, mapa: dict, ordem: list[str]) -> pd.Series:
    return pd.Categorical(valores.map(mapa), categories=ordem, ordered=True)


def derivar_variaveis(df: pd.DataFrame) -> pd.DataFrame:
    """Cria o desfecho e as variáveis analíticas a partir dos códigos brutos.

    Espera um DataFrame já restrito aos moradores selecionados com entrevista
    individual realizada (``M001 == '1'``). As colunas originais são mantidas.
    """
    d = df.copy()
    mulher = d["C006"] == "2"

    # Identificação e desenho amostral ------------------------------------
    d["peso"] = _num(d["V00291"])
    d["proj_pop"] = _num(d["V00292"])
    d["idade"] = _num(d["C008"])
    d["adulto"] = d["idade"] >= 18

    # Desfecho --------------------------------------------------------------
    # Q03001 só é perguntado a quem já fez exame de glicemia (Q02901 != 6).
    # Quem nunca fez o exame não pode ter recebido o diagnóstico pelo fluxo do
    # questionário e é tratado como "sem diagnóstico" (mesmo denominador usado
    # pelo IBGE e por Malta et al., 2022). Diabetes exclusivamente gestacional
    # (Q03002 == 1) também é classificado como não caso.
    origem = pd.Series("outro", index=d.index)
    origem[d["Q03001"] == "1"] = "diagnostico_sim"
    origem[(d["Q03001"] == "1") & mulher & (d["Q03002"] == "1")] = "apenas_gestacional"
    origem[d["Q03001"] == "2"] = "diagnostico_nao"
    origem[d["Q03001"].isna() & (d["Q02901"] == "6")] = "nunca_fez_glicemia"
    d["diabetes_origem"] = origem
    d["diabetes"] = (origem == "diagnostico_sim").astype(int)
    d.loc[origem == "outro", "diabetes"] = np.nan  # não esperado; checado no notebook

    # Demográficas ------------------------------------------------------------
    d["sexo"] = _cat(d["C006"], {"1": "Homem", "2": "Mulher"}, ["Homem", "Mulher"])
    d["faixa_etaria"] = pd.cut(
        d["idade"], [18, 25, 40, 60, np.inf], right=False,
        labels=["18 a 24", "25 a 39", "40 a 59", "60 ou mais"],
    )
    d["faixa_etaria_10"] = pd.cut(
        d["idade"], [18, 30, 40, 50, 60, 70, 80, np.inf], right=False,
        labels=["18-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+"],
    )
    d["raca_cor"] = _cat(
        d["C009"],
        {"1": "Branca", "2": "Preta", "4": "Parda", "3": "Amarela/Indígena", "5": "Amarela/Indígena"},
        ["Branca", "Preta", "Parda", "Amarela/Indígena"],
    )
    d["regiao"] = _cat(
        d["V0001"].str[0], REGIOES, ["Norte", "Nordeste", "Sudeste", "Sul", "Centro-Oeste"]
    )
    d["situacao"] = _cat(d["V0026"], {"1": "Urbana", "2": "Rural"}, ["Urbana", "Rural"])

    # Socioeconômicas ---------------------------------------------------------
    d["escolaridade"] = _cat(
        d["VDD004A"],
        {"1": "Sem instrução/fund. incompleto", "2": "Sem instrução/fund. incompleto",
         "3": "Fund. completo/médio incompleto", "4": "Fund. completo/médio incompleto",
         "5": "Médio completo/sup. incompleto", "6": "Médio completo/sup. incompleto",
         "7": "Superior completo"},
        ["Sem instrução/fund. incompleto", "Fund. completo/médio incompleto",
         "Médio completo/sup. incompleto", "Superior completo"],
    )
    d["renda_pc"] = _num(d["VDF003"])
    d["renda_sm"] = _cat(
        d["VDF004"],
        {"1": "Até 1 SM", "2": "Até 1 SM", "3": "Até 1 SM", "4": "Mais de 1 a 3 SM",
         "5": "Mais de 1 a 3 SM", "6": "Mais de 3 a 5 SM", "7": "Mais de 5 SM"},
        ["Até 1 SM", "Mais de 1 a 3 SM", "Mais de 3 a 5 SM", "Mais de 5 SM"],
    )
    trab = pd.Series(pd.NA, index=d.index, dtype="object")
    trab[d["VDE002"] == "1"] = "Ocupado"
    trab[d["VDE002"] == "2"] = "Desocupado"
    trab[d["VDE001"] == "2"] = "Fora da força de trabalho"
    d["trabalho"] = pd.Categorical(trab, ["Ocupado", "Desocupado", "Fora da força de trabalho"])
    d["plano_saude"] = _cat(d["I00102"], {"1": "Sim", "2": "Não"}, ["Não", "Sim"])

    # Comportamentais -----------------------------------------------------------
    fumo = pd.Series(pd.NA, index=d.index, dtype="object")
    fumo[d["P050"].isin(["1", "2"])] = "Fumante"
    fumo[(d["P050"] == "3") & d["P052"].isin(["1", "2"])] = "Ex-fumante"
    fumo[(d["P050"] == "3") & (d["P052"] == "3")] = "Nunca fumou"
    d["tabagismo"] = pd.Categorical(fumo, ["Nunca fumou", "Ex-fumante", "Fumante"])

    alc = pd.Series(pd.NA, index=d.index, dtype="object")
    alc[d["P027"].isin(["1", "2"]) | (d["P03201"] == "2")] = "Não"
    alc[d["P03201"] == "1"] = "Sim"
    d["alcool_abusivo"] = pd.Categorical(alc, ["Não", "Sim"])

    # Atividade física no lazer: >= 150 min/semana de intensidade leve/moderada
    # ou >= 75 min/semana de intensidade vigorosa (minutos vigorosos valem em dobro).
    dias = _num(d["P035"]).where(lambda s: s.between(0, 7))
    horas = _num(d["P03701"]).where(lambda s: s.between(0, 24))
    minutos = _num(d["P03702"]).where(lambda s: s.between(0, 59))
    duracao = horas.fillna(0) * 60 + minutos.fillna(0)
    duracao[horas.isna() & minutos.isna()] = np.nan
    # P035 = 0 ("nunca ou menos de uma vez por semana") pula a pergunta de duração:
    # equivale a 0 minuto semanal, não a informação ausente.
    duracao[dias == 0] = 0
    fator = np.where(d["P036"].isin(P036_VIGOROSOS), 2, 1)
    d["af_lazer_min_sem"] = np.where(d["P034"] == "2", 0, dias * duracao * fator)
    d.loc[~d["P034"].isin(["1", "2"]), "af_lazer_min_sem"] = np.nan
    d["af_lazer_suficiente"] = pd.Categorical(
        np.select(
            [d["af_lazer_min_sem"] >= 150, d["af_lazer_min_sem"] < 150],
            ["Sim", "Não"], default=None),
        ["Não", "Sim"],
    )

    d["sal_alto"] = _cat(d["P02601"], {"1": "Sim", "2": "Sim", "3": "Não", "4": "Não", "5": "Não"}, ["Não", "Sim"])
    for nova, cod in [("frutas_5d", "P018"), ("verduras_5d", "P00901"),
                      ("refrigerante_5d", "P02002"), ("doces_5d", "P02501")]:
        v = _num(d[cod]).where(lambda s: s.between(0, 7))
        d[nova] = pd.Categorical(np.select([v >= 5, v < 5], ["Sim", "Não"], default=None), ["Não", "Sim"])

    # Saúde ---------------------------------------------------------------------
    peso_kg = _num(d["P00104"])
    altura_m = _num(d["P00404"]).where(lambda s: s != 999) / 100
    imc = peso_kg / altura_m**2
    imc[d["P005"] == "1"] = np.nan  # IMC não se aplica a gestantes
    d["imc"] = imc
    d["imc_imputado"] = d["P00405"] == "1"
    d["estado_nutricional"] = pd.cut(
        d["imc"], [0, 18.5, 25, 30, np.inf], right=False,
        labels=["Baixo peso", "Eutrófico", "Sobrepeso", "Obesidade"],
    )

    # Q00201 só é perguntado a quem já mediu a pressão (Q00101 != 6) e Q060 só a
    # quem já mediu o colesterol (Q05901 != 6). Como no desfecho, quem nunca fez a
    # medida é classificado como "sem diagnóstico".
    has = pd.Series(pd.NA, index=d.index, dtype="object")
    has[d["Q00101"] == "6"] = "Não"
    has[d["Q00201"] == "2"] = "Não"
    has[(d["Q00201"] == "1") & mulher & (d["Q00202"] == "1")] = "Não"  # só na gravidez
    has[(d["Q00201"] == "1") & ~(mulher & (d["Q00202"] == "1"))] = "Sim"
    d["hipertensao"] = pd.Categorical(has, ["Não", "Sim"])
    for nova, cod in [("colesterol_alto", "Q060"), ("doenca_coracao", "Q06306"), ("avc", "Q068")]:
        d[nova] = _cat(d[cod], {"1": "Sim", "2": "Não"}, ["Não", "Sim"])
    d.loc[d["Q05901"] == "6", "colesterol_alto"] = "Não"

    d["autoavaliacao_saude"] = _cat(
        d["N001"],
        {"1": "Muito boa/boa", "2": "Muito boa/boa", "3": "Regular", "4": "Ruim/muito ruim", "5": "Ruim/muito ruim"},
        ["Muito boa/boa", "Regular", "Ruim/muito ruim"],
    )

    # Informações usadas apenas para descrição (risco de vazamento) -------------
    d["idade_diagnostico_dm"] = _num(d["Q031"]).where(lambda s: s < 99)
    d["anos_desde_diagnostico_dm"] = d["idade"] - d["idade_diagnostico_dm"]
    d["ultimo_exame_glicemia"] = _cat(
        d["Q02901"],
        {"1": "< 6 meses", "2": "6 meses a < 1 ano", "3": "1 a < 2 anos",
         "4": "2 a < 3 anos", "5": "3 anos ou mais", "6": "Nunca fez"},
        ["< 6 meses", "6 meses a < 1 ano", "1 a < 2 anos", "2 a < 3 anos", "3 anos ou mais", "Nunca fez"],
    )
    return d


# ---------------------------------------------------------------------------
# 3. Estimação com desenho amostral complexo
# ---------------------------------------------------------------------------


class DesenhoAmostral:
    """Desenho amostral da PNS para estimação por linearização de Taylor.

    Parâmetros
    ----------
    dados : DataFrame com TODOS os moradores selecionados entrevistados.
        Subpopulações (ex.: adultos) devem ser tratadas como domínio via
        ``dominio=``, e não filtrando linhas, para preservar a estrutura de
        estratos e UPAs no cálculo da variância.
    estrato, upa, peso : nomes das colunas do desenho.
    pos_estrato : coluna com o domínio de pós-estratificação (V00293). Quando
        informada, a variância incorpora o ajuste de pós-estratificação
        (resíduos centrados dentro de cada pós-estrato), como faz
        ``survey::postStratify`` no R. As estimativas pontuais não mudam,
        pois o peso V00291 já está calibrado.

    A variância usa a aproximação de "com reposição" na seleção das UPAs
    dentro de cada estrato, padrão do Stata (``svy``) e do pacote ``survey``.
    """

    def __init__(self, dados, estrato="V0024", upa="UPA_PNS", peso="peso", pos_estrato="V00293"):
        self.d = dados
        self.estrato = dados[estrato].to_numpy()
        self.upa = dados[upa].to_numpy()
        self.w = dados[peso].to_numpy(dtype=float)
        self.pos = dados[pos_estrato].to_numpy() if pos_estrato else None
        n_upa = pd.Series(self.upa).groupby(self.estrato).nunique()
        if (n_upa < 2).any():
            raise ValueError("Há estratos com uma única UPA; tratar antes de estimar.")
        self.gl = int(pd.Series(self.upa).nunique() - pd.Series(self.estrato).nunique())

    def _variancia_total(self, z: np.ndarray) -> float:
        """Variância do total ponderado de ``z`` (z já é o resíduo linearizado)."""
        if self.pos is not None:
            # Centraliza o resíduo dentro de cada pós-estrato (média ponderada).
            df = pd.DataFrame({"g": self.pos, "wz": self.w * z, "w": self.w})
            media_g = df.groupby("g")["wz"].transform("sum") / df.groupby("g")["w"].transform("sum")
            z = z - media_g.to_numpy()
        t = pd.DataFrame({"h": self.estrato, "u": self.upa, "t": self.w * z})
        tot_upa = t.groupby(["h", "u"], sort=False)["t"].sum().reset_index()
        g = tot_upa.groupby("h")["t"]
        n_h = g.transform("size")
        dev = tot_upa["t"] - g.transform("mean")
        return float((n_h / (n_h - 1) * dev**2).sum())

    def media(self, y, dominio=None) -> dict:
        """Média (ou proporção, se ``y`` for 0/1) ponderada no domínio.

        Observações com ``y`` ausente dentro do domínio são excluídas do domínio
        (análise de casos completos para aquela variável).
        """
        y = np.asarray(y, dtype=float)
        dom = np.ones_like(y, dtype=bool) if dominio is None else np.asarray(dominio, dtype=bool)
        dom = dom & ~np.isnan(y)
        y0 = np.where(dom, y, 0.0)
        N = (self.w * dom).sum()
        est = (self.w * y0).sum() / N
        z = np.where(dom, (y0 - est) / N, 0.0)
        ep = np.sqrt(self._variancia_total(z))
        return dict(estimativa=est, ep=ep, n=int(dom.sum()), N_pop=N)

    def proporcao(self, y, dominio=None, z=1.96) -> dict:
        """Proporção com IC95% no domínio (escala logit, como no Stata ``svy: prop``)."""
        r = self.media(y, dominio)
        p, ep = r["estimativa"], r["ep"]
        if 0 < p < 1:
            lp = np.log(p / (1 - p))
            ep_l = ep / (p * (1 - p))
            ic = 1 / (1 + np.exp(-np.array([lp - z * ep_l, lp + z * ep_l])))
        else:
            ic = np.array([np.nan, np.nan])
        y_arr = np.asarray(y, dtype=float)
        dom = np.ones_like(y_arr, dtype=bool) if dominio is None else np.asarray(dominio, dtype=bool)
        dom = dom & ~np.isnan(y_arr)
        r.update(ic_inf=ic[0], ic_sup=ic[1],
                 total_casos=float((self.w * np.where(dom, y_arr, 0)).sum()),
                 casos_amostra=int(np.nansum(np.where(dom, y_arr, 0))))
        return r

    def prevalencia_por(self, y_col: str, por: str, dominio=None) -> pd.DataFrame:
        """Tabela de prevalência de ``y_col`` (0/1) para cada categoria de ``por``."""
        base = np.ones(len(self.d), bool) if dominio is None else np.asarray(dominio, bool)
        y = self.d[y_col].to_numpy(dtype=float)
        linhas = []
        cats = self.d[por].cat.categories if hasattr(self.d[por], "cat") else sorted(self.d[por].dropna().unique())
        for c in cats:
            r = self.proporcao(y, base & (self.d[por] == c).to_numpy())
            linhas.append(dict(variavel=por, categoria=str(c), **r))
        return pd.DataFrame(linhas)

    def distribuicao(self, col: str, dominio=None) -> pd.DataFrame:
        """Distribuição percentual ponderada das categorias de ``col`` no domínio
        (casos com ``col`` ausente excluídos do denominador)."""
        base = np.ones(len(self.d), bool) if dominio is None else np.asarray(dominio, bool)
        validos = base & self.d[col].notna().to_numpy()
        linhas = []
        for c in self.d[col].cat.categories:
            r = self.proporcao((self.d[col] == c).astype(float).to_numpy(), validos)
            linhas.append(dict(variavel=col, categoria=str(c), n_amostra=r["casos_amostra"],
                               pct=r["estimativa"], ic_inf=r["ic_inf"], ic_sup=r["ic_sup"]))
        return pd.DataFrame(linhas)
