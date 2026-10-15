"""aam.py — coleta as leis municipais do Amazonas no Diário Oficial dos Municípios (AAM / SIGPub).

Fonte: https://www.diariomunicipal.com.br/aam/ — diário oficial de 61 municípios do AM (todos menos Manaus),
prefeituras e câmaras, matérias desde 2009 (Lei Municipal de adesão, ex.: Jutaí Lei 123/2011).

Etapas (as duas retomam de onde pararam):
  python -I scripts/aam.py indice   — busca título "LEI" em cada entidade e grava _indice/aam.jsonl
  python -I scripts/aam.py baixar   — baixa o HTML de cada lei e grava municipais/AM/<municipio>/<tipo>/<ano>/*.md
  python -I scripts/aam.py tudo
  python -I scripts/aam.py indice Parintins   — só as entidades cujo nome contém o texto (teste)

Ritmo: 1 requisição por vez, com pausa (PAUSA), para não pesar no servidor da AAM.
"""
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from html.parser import HTMLParser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(BASE_DIR)
SITE = "https://www.diariomunicipal.com.br"
INDICE = os.path.join(RAIZ, "_indice")
SAIDA = os.path.join(RAIZ, "municipais", "AM")
PAUSA = 0.8
UA = {"User-Agent": "Mozilla/5.0 (leismunicipais; acervo publico de leis do AM; github.com/leonzordhue/leismunicipais)"}
HOJE = time.strftime("%Y-%m-%d")

# Vocabulário de tipos (título da matéria -> tipo canônico, pasta). Ordem importa: o mais específico primeiro.
TIPOS = [
    (r"EMENDA\s+(?:A|À)?\s*LEI\s+ORG[AÂ]NICA", "Emenda à Lei Orgânica", "emendas-lei-organica"),
    (r"LEI\s+ORG[AÂ]NICA", "Lei Orgânica", "lei-organica"),
    (r"LEI\s+COMPLEMENTAR", "Lei Complementar", "leis-complementares"),
    (r"LEI\s+PROMULGADA", "Lei Promulgada", "leis-promulgadas"),
    (r"LEI\s+DELEGADA", "Lei Delegada", "leis-delegadas"),
    (r"LEI(?:\s+MUNICIPAL|\s+ORDIN[AÁ]RIA)?\s*(?:N[º°oO.]|Nº|\d)", "Lei Ordinária", "leis-ordinarias"),
]


def get(url, tentativas=4):
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # rede instável: espera e tenta de novo
            if i == tentativas - 1:
                raise
            print(f"    erro {type(e).__name__}, nova tentativa em {10 * (i + 1)} s", flush=True)
            time.sleep(10 * (i + 1))


def slug(s):
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def classificar(titulo):
    """Só aceita matéria cujo título COMEÇA pela norma (descarta extrato de contrato que cita lei etc.)."""
    t = titulo.upper().strip()
    if re.match(r"\W*(PROJETO|MENSAGEM|VETO|AUTÓGRAFO|AUTOGRAFO|ERRATA|AVISO|EXTRATO)", t):
        return None
    for rx, tipo, pasta in TIPOS:
        if re.match(r"\W*" + rx, t):
            return tipo, pasta
    return None


def numero_ano(titulo):
    m = re.search(r"N[º°oO.]*\s*([\d][\d\.]*)\s*(?:[/\-–,]\s*(\d{4}|\d{2}\b))?", titulo, re.I)
    if not m:
        return "", ""
    num = m.group(1).replace(".", "").lstrip("0") or "0"
    ano = m.group(2) or ""
    if not ano:  # "EMENDA ... Nº 16, DE 09 DE JUNHO DE 2026"
        m2 = re.search(r"\bDE\s+(\d{4})\b", titulo, re.I)
        ano = m2.group(1) if m2 else ""
    if len(ano) == 2:
        ano = ("20" if int(ano) <= int(HOJE[2:4]) else "19") + ano
    return num, ano


# ---------------------------------------------------------------- etapa 1: índice
def entidades():
    p = get(SITE + "/aam/pesquisar")
    corpo = re.search(r'name="busca_avancada\[entidade\]"[^>]*>(.*?)</select>', p, re.S).group(1)
    ents = [(i, html.unescape(n).strip()) for i, n in re.findall(r'<option value="(\d+)"[^>]*>([^<]*)', corpo)]
    return [e for e in ents if e[1].startswith(("Município de", "Câmara Municipal de"))]


CARD = re.compile(r'<li class="materia-card">(.*?)</li>', re.S)


def campo(rx, s):
    m = re.search(rx, s, re.S)
    return html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""


def indice(filtro=""):
    os.makedirs(INDICE, exist_ok=True)
    feitos_f = os.path.join(INDICE, "aam_entidades_ok.txt")
    feitos = set(open(feitos_f, encoding="utf-8").read().split("\n")) if os.path.exists(feitos_f) else set()
    ents = [e for e in entidades() if filtro.lower() in e[1].lower()]
    print(f"{len(ents)} entidades (municípios e câmaras); já feitas: {len(feitos & {e[0] for e in ents})}", flush=True)
    with open(os.path.join(INDICE, "aam.jsonl"), "a", encoding="utf-8") as out:
        for eid, nome in ents:
            if eid in feitos:
                continue
            pagina, total, n = 1, None, 0
            while True:
                q = {"busca_avancada[dataInicio]": "2009-01-01", "busca_avancada[dataFim]": HOJE,
                     "busca_avancada[titulo]": "LEI", "busca_avancada[entidade]": eid,
                     "busca_avancada[ordenacao]": "", "busca_avancada[pagina]": str(pagina), "busca_avancada[Enviar]": ""}
                p = get(SITE + "/aam/pesquisar?" + urllib.parse.urlencode(q))
                time.sleep(PAUSA)
                if total is None:
                    m = re.search(r"de <strong>([\d\.]+)</strong>\s*matérias", p)
                    total = int(m.group(1).replace(".", "")) if m else 0
                cards = CARD.findall(p)
                for c in cards:
                    out.write(json.dumps({
                        "codigo": campo(r"<code>([^<]+)</code>", c),
                        "titulo": campo(r'materia-card__titulo">\s*<a[^>]*>(.*?)</a>', c),
                        "entidade": campo(r'materia-card__entidade">(.*?)</span>', c),
                        "entidade_id": eid,
                        "orgao": campo(r'materia-card__orgao">(.*?)</span>', c),
                        "circulacao": campo(r"<dt>Circulação</dt>\s*<dd>(.*?)</dd>", c),
                        "edicao": campo(r"<dt>Edição</dt>\s*<dd>(.*?)</dd>", c),
                    }, ensure_ascii=False) + "\n")
                n += len(cards)
                if not cards or n >= total:
                    break
                pagina += 1
            out.flush()
            with open(feitos_f, "a", encoding="utf-8") as f:
                f.write(eid + "\n")
            print(f"  {nome}: {n} matérias", flush=True)


# ---------------------------------------------------------------- etapa 2: baixar e converter
class ParaMarkdown(HTMLParser):
    """Converte o HTML da matéria (p, b/strong, i/em, br, h*, table) em Markdown simples."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.linha, self.celulas, self.tabela = [], [], None, []
        self.ignorar = 0  # dentro de <style>/<script>

    def _quebra(self):
        t = re.sub(r"[ \t ]+", " ", "".join(self.linha)).strip()
        t = re.sub(r"\*\*\s*\*\*", "", t)
        if t:
            self.out.append(t)
        self.linha = []

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.ignorar += 1
        elif tag in ("b", "strong"):
            self.linha.append("**")
        elif tag in ("i", "em"):
            self.linha.append("_")
        elif tag == "br":
            self._quebra()
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
            self._quebra()
        elif tag == "tr":
            self.celulas = []
        elif tag in ("td", "th"):
            self._quebra()

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.ignorar = max(0, self.ignorar - 1)
        elif tag in ("b", "strong"):
            self.linha.append("**")
        elif tag in ("i", "em"):
            self.linha.append("_")
        elif tag in ("td", "th") and self.celulas is not None:
            self.celulas.append(re.sub(r"\s+", " ", "".join(self.linha)).strip().replace("|", "/"))
            self.linha = []
        elif tag == "tr" and self.celulas is not None:
            self.tabela.append(self.celulas)
            self.celulas = None
        elif tag == "table":
            if self.tabela:
                w = max(len(r) for r in self.tabela)
                linhas = ["| " + " | ".join(r + [""] * (w - len(r))) + " |" for r in self.tabela]
                linhas.insert(1, "|" + " --- |" * w)
                self.out.append("\n".join(linhas))
            self.tabela = []
        elif tag in ("p", "div", "li") or tag.startswith("h"):
            self._quebra()

    def handle_data(self, data):
        if not self.ignorar:
            self.linha.append(data)

    def texto(self):
        self._quebra()
        return "\n\n".join(self.out)


def converter(pagina):
    m = re.search(r'<div class="materia">(.*?)<footer', pagina, re.S)
    if not m:
        return ""
    p = ParaMarkdown()
    p.feed(m.group(1))
    return p.texto()


def ementa_de(texto, titulo):
    """Heurística: 1º parágrafo depois do título que não seja fórmula de promulgação."""
    for par in texto.split("\n\n")[1:8]:
        s = par.strip("*_ ").strip()
        if s.upper().startswith(titulo.upper()[:12]):
            # ementa colada ao título: "LEI COMPLEMENTAR Nº 024/2018-PGMP ALTERA O QUADRO..."
            s = re.sub(r"^.*?N[º°oO.]*\s*[\d\.]+\s*(?:[/\-–]\s*\d{2,4})?(?:\s*[/\-–]\s*[A-Z]{2,6}\b)?"
                       r"(?:,?\s*DE\s+\d{1,2}\s+DE\s+\w+\s+DE\s+\d{4})?\s*[\-–,:.]?\s*", "", s, count=1, flags=re.I)
        if len(s) < 20:
            continue
        if re.match(r"(O|A)\s+(PREFEIT|PRESIDENT|CIDAD|C[AÂ]MARA|VICE)|FA[ÇC]O SABER|FAZ SABER|LEI:|Art\.", s, re.I):
            break
        return s.replace('"', "'")
    return ""


def yaml(v):
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def baixar():
    with open(os.path.join(INDICE, "aam.jsonl"), encoding="utf-8") as f:
        itens = {}
        for linha in f:
            d = json.loads(linha)
            itens[d["codigo"]] = d  # o mesmo código pode vir de duas entidades? fica o último
    alvos = []
    for d in itens.values():
        c = classificar(d["titulo"])
        if c:
            alvos.append((d, c))
    print(f"{len(itens)} matérias no índice; {len(alvos)} são leis", flush=True)
    nomes = dict(entidades())
    os.makedirs(SAIDA, exist_ok=True)
    falhas = open(os.path.join(SAIDA, "_falhas.jsonl"), "a", encoding="utf-8")
    t0, n = time.time(), 0
    for d, (tipo, pasta) in alvos:
        ent = nomes.get(d["entidade_id"], d["entidade"])  # o cartão às vezes vem em MAIÚSCULAS; a lista não
        mun = re.sub(r"^(Município de|Câmara Municipal de)\s+", "", ent, flags=re.I)
        num, ano = numero_ano(d["titulo"])
        circ = d["circulacao"]  # dd/mm/aaaa
        data_pub = f"{circ[6:10]}-{circ[3:5]}-{circ[0:2]}" if re.match(r"\d\d/\d\d/\d{4}", circ) else ""
        ano = ano or data_pub[:4] or "sem-ano"
        nome = f"{slug(tipo).split('-')[0]}-{num or 'sn'}-{ano}-{d['codigo']}.md"
        destino = os.path.join(SAIDA, slug(mun), pasta, ano, nome)
        if os.path.exists(destino):
            continue
        try:
            pag = get(f"{SITE}/aam/download/materia/{d['codigo']}")
            time.sleep(PAUSA)
            corpo = converter(pag)
            if not corpo:
                raise ValueError("matéria sem corpo")
        except Exception as e:
            falhas.write(json.dumps({"codigo": d["codigo"], "titulo": d["titulo"], "erro": str(e)}, ensure_ascii=False) + "\n")
            falhas.flush()
            continue
        cab = [
            "---",
            f"titulo: {yaml(d['titulo'])}",
            'uf: "AM"',
            f"municipio: {yaml(mun)}",
            f"tipo: {yaml(tipo)}",
            f"numero: {yaml(num)}",
            f"ano: {yaml(ano)}",
            f"ementa: {yaml(ementa_de(corpo, d['titulo']))}",
            f"entidade: {yaml(ent)}",
            f"orgao: {yaml(d['orgao'])}",
            f"publicacao: {yaml('DOM-AAM ed. ' + d['edicao'])}",
            f"data_publicacao: {data_pub}",
            f"fonte: {yaml(SITE + '/aam/materia/' + d['codigo'])}",
            f"codigo_sigpub: {yaml(d['codigo'])}",
            'versao_texto: "original (publicação no DOM-AAM)"',
            f"baixado_em: {HOJE}",
            "---",
            f"# {d['titulo']}",
            "",
        ]
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(cab) + "\n" + corpo + "\n")
        n += 1
        if n % 200 == 0:
            print(f"  {n} leis gravadas ({time.time() - t0:.0f} s)", flush=True)
    print(f"pronto: {n} leis novas", flush=True)


if __name__ == "__main__":
    etapa = sys.argv[1] if len(sys.argv) > 1 else ""
    if etapa in ("indice", "tudo"):
        indice(sys.argv[2] if len(sys.argv) > 2 else "")
    if etapa in ("baixar", "tudo"):
        baixar()
    if etapa not in ("indice", "baixar", "tudo"):
        print(__doc__)
