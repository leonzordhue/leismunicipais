"""organicas_planos.py — situação da Lei Orgânica e do Plano Diretor nos 62 municípios do Amazonas.

Lê os .md de municipais/AM e cruza com a MUNIC 2021 do IBGE (_indice/munic2021_plano_diretor_am.csv,
extraída de ftp.ibge.gov.br/Perfil_Municipios/2021/Base_de_Dados/Base_MUNIC_2021_20240425.xlsx,
aba "Legislação e instr de planej", variáveis MLEG01, MLEG011, MLEG012, MLEG013 e MLEG014).
Gera municipais/AM/_organicas_planos_diretores.md e _indice/organicas_planos_diretores.csv.

  python -I scripts/organicas_planos.py
"""
import csv
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from aam import INDICE, SAIDA, slug  # noqa: E402

# Planos diretores citados em fonte confiável, mas sem texto oficial encontrado na internet (26/10/2026).
REFERENCIAS = {
    "Barcelos": "Lei 485/2008 (citada no PMGIRS da SEMA-AM, 2024)",
    "Humaitá": "Lei Complementar 001/2006 (citada no PMGIRS da SEMA-AM, 2024)",
    "Itacoatiara": "Lei 076, de 19/09/2006 (citada em dissertação da UFPA, 2014; texto só em blog, tunelverde-ita.blogspot.com)",
    "Presidente Figueiredo": "Lei 562/2006 (citada no PMGIRS da SEMA-AM, 2024); revisão em curso com o Sebrae desde 2025",
}
# Planos diretores no acervo cuja ementa saiu errada na extração do DOM-AAM (conferido pelo texto).
PD_EXTRA = {
    "AM/jutai/leis-ordinarias/2006/lei-24-2006-874FCE7C.md",  # Lei 024-B/2006, "INSTITUI O PLANO DIRETOR DE JUTAÍ"
    "AM/iranduba/leis-ordinarias/2011/lei-sn-2011-88D8E9F4.md",  # "LEI 129 PLANO DIRETOR"
}
PD = re.compile(r"(?i)(institui|disp[õo]e sobre|cria|aprova|regulamenta)\W+(o\W+)?plano diretor")
LO_MIN = 60000  # caracteres: abaixo disso é emenda, ementa solta ou capa


def ler(p):
    with open(p, encoding="utf-8") as f:
        t = f.read(8192)  # só o cabeçalho; o tamanho vem do disco
    fim = t.find("\n---", 3)
    meta = dict(re.findall(r'^(\w+): "?(.*?)"?$', t[3:fim], re.M))
    return meta, os.path.getsize(p) - fim


def main():
    lo, pd = {}, {}
    for d, _, fs in os.walk(SAIDA):
        for f in fs:
            if not f.endswith(".md") or f.startswith("_"):
                continue
            p = os.path.join(d, f)
            meta, n = ler(p)
            m = meta.get("municipio", "")
            data = meta.get("data") or meta.get("data_publicacao") or meta.get("ano") or ""
            item = (data, os.path.relpath(p, os.path.dirname(SAIDA)).replace("\\", "/"), meta.get("titulo", ""), meta.get("fonte", ""))
            if meta.get("tipo") == "Lei Orgânica" and n > LO_MIN:
                lo[m] = max(lo.get(m, item), item)
            if item[1] in PD_EXTRA or n > 30000 and (meta.get("assunto") == "plano diretor" or PD.search(meta.get("ementa", "") + " " + meta.get("titulo", ""))) \
                    and "plano de aplica" not in meta.get("ementa", "").lower():
                pd[m] = max(pd.get(m, item), item)
    munic = list(csv.DictReader(open(os.path.join(INDICE, "munic2021_plano_diretor_am.csv"), encoding="utf-8")))
    assert len(munic) == 62, len(munic)
    linhas = []
    for r in munic:
        m = r["mun"]
        decl = r["mleg01"] + (f" (lei de {r['mleg011']}" + (f", revisto em {r['mleg013']}" if r["mleg012"] == "Sim" else "") + ")" if r["mleg01"] == "Sim" else
                              (", elaborando" if r["mleg014"] == "Sim" else ""))
        linhas.append({"municipio": m, "populacao_2021": r["pop"], "lei_organica": lo.get(m, ("",) * 4)[1], "lo_titulo": lo.get(m, ("",) * 4)[2],
                       "plano_diretor": pd.get(m, ("",) * 4)[1], "pd_titulo": pd.get(m, ("",) * 4)[2], "pd_referencia_sem_texto": REFERENCIAS.get(m, ""),
                       "munic2021_tem_pd": decl, "obrigatorio_pd": "sim" if int(r["pop"]) > 20000 else "não"})
    with open(os.path.join(INDICE, "organicas_planos_diretores.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0])); w.writeheader(); w.writerows(linhas)
    n_lo = sum(1 for x in linhas if x["lei_organica"])
    n_pd = sum(1 for x in linhas if x["plano_diretor"])
    sim = [x for x in linhas if x["munic2021_tem_pd"].startswith("Sim")]
    out = ["# Lei Orgânica e Plano Diretor dos 62 municípios do Amazonas", "",
           f"Gerado por `scripts/organicas_planos.py`. Texto integral no acervo: **Lei Orgânica em {n_lo} de 62**, **Plano Diretor em {n_pd} de 62**.",
           f"Pela MUNIC 2021 (IBGE), {len(sim)} municípios declaram ter plano diretor; o plano é obrigatório acima de 20 mil habitantes (Estatuto da Cidade, Lei 10.257/2001, art. 41, I).",
           "", "| Município | Pop. 2021 | Lei Orgânica (texto) | Plano Diretor (texto) | MUNIC 2021: tem PD? |", "|---|---:|---|---|---|"]
    for x in linhas:
        # o .md fica em municipais/AM: o link perde o "AM/" inicial
        lo_c = f"[{x['lo_titulo'][:60]}]({x['lei_organica'][3:]})" if x["lei_organica"] else "**falta**"
        pd_c = f"[{x['pd_titulo'][:60]}]({x['plano_diretor'][3:]})" if x["plano_diretor"] else (f"sem texto: {x['pd_referencia_sem_texto']}" if x["pd_referencia_sem_texto"] else "—")
        pop = f"{int(x['populacao_2021']):,}".replace(",", ".")
        out.append(f"| {x['municipio']} | {pop} | {lo_c} | {pd_c} | {x['munic2021_tem_pd']} |")
    out += ["", "Textos com OCR trazem o aviso em `versao_texto`: conferir no PDF original antes de citar."]
    open(os.path.join(SAIDA, "_organicas_planos_diretores.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
    print(f"LO {n_lo}/62, PD {n_pd}/62; MUNIC=Sim sem texto:", [x["municipio"] for x in sim if not x["plano_diretor"]])
    print("LO faltando:", [x["municipio"] for x in linhas if not x["lei_organica"]])


if __name__ == "__main__":
    main()
