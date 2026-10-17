"""sapl.py — coleta as leis municipais do Amazonas cadastradas no SAPL das câmaras (Interlegis).

Fontes (API REST pública do SAPL, /api/norma/normajuridica/):
  Manaus        https://sapl.cmm.am.gov.br        (Câmara Municipal de Manaus; Manaus não publica no diário da AAM)
  9 câmaras     https://sapl.<municipio>.am.leg.br (as únicas com normas cadastradas em 16/10/2026; ver HOSTS)

Só entram leis (ordinária, complementar, delegada, promulgada, orgânica e emendas). Decretos, resoluções,
portarias, atos e erratas ficam de fora. O texto vem do PDF cadastrado no SAPL (campo texto_integral):
camada de texto do PDF quando existe; senão, OCR (Tesseract, português). Sem PDF, a lei entra só com a ementa.

Etapas (retomam de onde pararam):
  python -I scripts/sapl.py indice            — lista as normas de cada SAPL em _indice/sapl_<municipio>.jsonl
  python -I scripts/sapl.py baixar            — baixa o PDF de cada lei e grava municipais/AM/<municipio>/<tipo>/<ano>/*.md
  python -I scripts/sapl.py tudo
  python -I scripts/sapl.py verificar         — índice × arquivos gravados -> municipais/AM/_sapl_verificacao.md
  python -I scripts/sapl.py tudo tefe         — só os municípios cujo slug contém o texto (teste)
  python -I scripts/sapl.py baixar manaus 1/3 — só a parte 1 de 3 (id % 3 == 1): rodar 0/3, 1/3 e 2/3 em paralelo

Dependência fora da biblioteca padrão: PyMuPDF (pymupdf) e o Tesseract com por.traineddata, para o OCR.
Ritmo: uma requisição por vez em cada SAPL, com pausa; os SAPL rodam em paralelo (servidores diferentes).
"""
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from aam import HOJE, INDICE, SAIDA, slug, yaml  # noqa: E402

try:
    import truststore  # a rede da SEINFRA quebra a cadeia de certificados: usar os certificados do Windows
    truststore.inject_into_ssl()
except ImportError:
    pass

PAUSA = 0.5
UA = {"User-Agent": "Mozilla/5.0 (leismunicipais; acervo publico de leis do AM; github.com/leonzordhue/leismunicipais)"}
MAX_OCR = 30  # páginas com OCR por lei; ~5 s por página
TESSDATA = next((p for p in (os.environ.get("TESSDATA_PREFIX"), os.path.expanduser(r"~\tessdata"), r"C:\Program Files\Tesseract-OCR\tessdata")
                 if p and os.path.exists(os.path.join(p, "por.traineddata"))), None)

HOSTS = {  # slug -> (nome do município, SAPL)
    "manaus": ("Manaus", "https://sapl.cmm.am.gov.br"),
    "coari": ("Coari", "https://sapl.coari.am.leg.br"),
    "codajas": ("Codajás", "https://sapl.codajas.am.leg.br"),
    "envira": ("Envira", "https://sapl.envira.am.leg.br"),
    "iranduba": ("Iranduba", "https://sapl.iranduba.am.leg.br"),
    "manacapuru": ("Manacapuru", "https://sapl.manacapuru.am.leg.br"),
    "manicore": ("Manicoré", "https://sapl.manicore.am.leg.br"),
    "novo-airao": ("Novo Airão", "https://sapl.novoairao.am.leg.br"),
    "parintins": ("Parintins", "https://sapl.parintins.am.leg.br"),
    "tefe": ("Tefé", "https://sapl.tefe.am.leg.br"),
}


def classificar(descricao):
    """Descrição do tipo no SAPL (varia por câmara: 'LEI ORDINÁRIA', 'Lei Municipal', 'Emenda à Loman'...) -> (tipo, pasta)."""
    d = slug(descricao)
    if "emenda" in d and ("organica" in d or "loman" in d):
        return "Emenda à Lei Orgânica", "emendas-lei-organica"
    if "organica" in d or d == "loman":
        return "Lei Orgânica", "lei-organica"
    if not d.startswith("lei"):  # decreto-lei, resolução, portaria, ato, errata, regimento, emancipação...
        return None
    if "complementar" in d:
        return "Lei Complementar", "leis-complementares"
    if "delegada" in d:
        return "Lei Delegada", "leis-delegadas"
    if "promulgada" in d:
        return "Lei Promulgada", "leis-promulgadas"
    return "Lei Ordinária", "leis-ordinarias"  # ordinária, municipal, consolidada, 'da Câmara Municipal', 'Lei'


def get(url, binario=False, tentativas=5):
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                b = r.read()
                return b if binario else json.loads(b)
        except urllib.error.HTTPError as e:
            if e.code == 404 or i == tentativas - 1:
                raise
        except Exception:
            if i == tentativas - 1:
                raise
        time.sleep(10 * (i + 1))


def _https(u):
    return (u or "").replace("http://", "https://", 1)


# ---------------------------------------------------------------- etapa 1: índice
def indice(s):
    nome, host = HOSTS[s]
    tipos = {t["id"]: t["descricao"] for t in get(host + "/api/norma/tiponormajuridica/?page_size=100")["results"]}
    normas, page = [], 1
    while page:
        j = get(f"{host}/api/norma/normajuridica/?page_size=100&page={page}")
        for r in j["results"]:
            r["tipo_descricao"] = tipos.get(r["tipo"], "")
            normas.append(r)
        page = j["pagination"]["next_page"]
        time.sleep(PAUSA)
    os.makedirs(INDICE, exist_ok=True)
    with open(os.path.join(INDICE, f"sapl_{s}.jsonl"), "w", encoding="utf-8") as f:
        for r in normas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    leis = sum(1 for r in normas if classificar(r["tipo_descricao"]))
    log(f"{nome}: {len(normas)} normas no SAPL, {leis} leis")


# ---------------------------------------------------------------- etapa 2: baixar e converter
_VOCAB = set()
_VOCAB_TRAVA = threading.Lock()


def vocabulario():
    """Palavras (3+ letras, minúsculas) que aparecem 3+ vezes nas leis do diário da AAM, que são texto digital.
    O Tesseract 'inventa' palavras plausíveis no manuscrito ('Comsânios', 'Amasdras'); o vocabulário as separa."""
    cache = os.path.join(INDICE, "vocabulario_aam.txt")
    with _VOCAB_TRAVA:
        if not _VOCAB and os.path.exists(cache):
            _VOCAB.update(open(cache, encoding="utf-8").read().split())
        if not _VOCAB:
            from collections import Counter
            c = Counter()
            for d, _, fs in os.walk(SAIDA):
                for f in fs:
                    if f.endswith(".md") and "-sapl" not in f:
                        c.update(re.findall(r"[a-zà-ÿ]{3,}", open(os.path.join(d, f), encoding="utf-8").read().lower()))
            _VOCAB.update(w for w, n in c.items() if n >= 3)
            with open(cache, "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(_VOCAB)))
    return _VOCAB


def legivel(texto):
    """Fração das palavras de 3+ letras que existem no vocabulário do acervo. Texto bom > 0,8; manuscrito < 0,5."""
    toks = re.findall(r"[a-zà-ÿ]{3,}", texto.lower())
    if len(toks) < 10:  # página curta (assinatura, carimbo, numeração): não dá para julgar
        return None
    v = vocabulario()
    return sum(t in v for t in toks) / len(toks)


def pdf_para_texto(dados):
    """Camada de texto do PDF; página sem texto (digitalizada) passa por OCR, e o OCR ilegível (manuscrito,
    cópia ruim) é descartado. Devolve (texto, modos) com modos ⊆ {'pdf', 'ocr', 'ilegivel'}."""
    import pymupdf
    doc = pymupdf.open(stream=dados, filetype="pdf")
    partes, modos, nocr = [], set(), 0
    for pg in doc:
        blocos = [b[4] for b in pg.get_text("blocks") if b[6] == 0]
        nota, modo = legivel(" ".join(blocos)), "pdf"
        # página-imagem, ou camada de texto ruim (OCR antigo, só o carimbo do SAPL): refaz o OCR e fica com o melhor.
        # Calibração (Novo Airão, 52 leis): manuscrito 0,27-0,40; datilografado com OCR antigo 0,45-0,75; digital > 0,8.
        if (nota is None or nota < 0.75) and TESSDATA and nocr >= MAX_OCR:
            modos.add("limite")  # anexos digitalizados (LOA, PPA, plantas): além do limite, fica a camada de texto, se houver
        elif (nota is None or nota < 0.75) and TESSDATA:
            nocr += 1
            tp = pg.get_textpage_ocr(language="por", dpi=200, full=True, tessdata=TESSDATA)
            b2 = [b[4] for b in pg.get_text("blocks", textpage=tp) if b[6] == 0]
            n2 = legivel(" ".join(b2))
            if n2 is not None and (nota is None or n2 > nota):
                blocos, nota, modo = b2, n2, "ocr"
        if nota is not None and nota < 0.45:
            if any(b.strip() for b in blocos):
                modos.add("ilegivel")
            continue
        modos.add(modo)
        for b in blocos:
            t = re.sub(r"[ \t]*\n[ \t]*", " ", b).strip()
            t = re.sub(r"\s{2,}", " ", t)
            if t:
                partes.append(t)
    doc.close()
    return "\n\n".join(partes), modos


def numero(r):
    n = re.sub(r"[.\s]", "", str(r.get("numero") or "")).lstrip("0")
    return re.sub(r"[^0-9A-Za-z\-]", "", n) or "sn"


def baixar(s, falhas, trava, parte=(0, 1)):
    nome, host = HOSTS[s]
    p = os.path.join(INDICE, f"sapl_{s}.jsonl")
    normas = [json.loads(l) for l in open(p, encoding="utf-8")]
    alvos = []
    for r in normas:
        c = classificar(r["tipo_descricao"])
        if not c or r["id"] % parte[1] != parte[0]:
            continue
        tipo, pasta = c
        ano = str(r.get("ano") or (r.get("data") or "")[:4] or "sem-ano")
        num = numero(r)
        destino = os.path.join(SAIDA, s, pasta, ano, f"{slug(tipo).split('-')[0]}-{num}-{ano}-sapl{r['id']}.md")
        if not os.path.exists(destino):
            alvos.append((r, tipo, ano, num, destino))
    log(f"{nome}: {len(alvos)} leis a baixar")
    n = nf = 0
    for r, tipo, ano, num, destino in alvos:
        pdf, modo, corpo = _https(r.get("texto_integral")), set(), ""
        try:
            if pdf:
                corpo, modo = pdf_para_texto(get(pdf, binario=True))
                time.sleep(PAUSA)
        except Exception as e:
            with trava:
                falhas.write(json.dumps({"municipio": nome, "sapl_id": r["id"], "titulo": r["__str__"], "pdf": pdf,
                                         "erro": f"{type(e).__name__}: {e}"[:300]}, ensure_ascii=False) + "\n")
                falhas.flush()
            nf += 1
            continue  # sem gravar: a próxima execução tenta de novo
        if not pdf:
            versao = "sem texto: o SAPL não tem o PDF desta lei (só a ementa)"
        elif not corpo.strip():
            versao = ("sem texto: PDF manuscrito ou ilegível para o OCR (ler o arquivo)" if "ilegivel" in modo
                      else "sem texto: PDF sem camada de texto e sem OCR")
        else:
            m = modo - {"limite", "ilegivel"}
            versao = ("texto do PDF cadastrado no SAPL" if m == {"pdf"} else
                      "OCR do PDF digitalizado cadastrado no SAPL (pode ter erros)" if m == {"ocr"} else
                      "texto do PDF cadastrado no SAPL, com OCR nas páginas digitalizadas (pode ter erros)")
            if "ilegivel" in modo:
                versao += "; páginas manuscritas ou ilegíveis omitidas (ler o arquivo)"
        if "limite" in modo:
            versao += f"; OCR só nas {MAX_OCR} primeiras páginas digitalizadas, o resto (anexos) não convertido (ler o arquivo)"
        veic = (r.get("veiculo_publicacao") or "").strip()
        cab = [
            "---",
            f"titulo: {yaml(r['__str__'])}",
            'uf: "AM"',
            f"municipio: {yaml(nome)}",
            f"tipo: {yaml(tipo)}",
            f"numero: {yaml(num if num != 'sn' else '')}",
            f"ano: {yaml(ano)}",
            f"data: {r.get('data') or ''}",
            f"ementa: {yaml(re.sub(r'\s+', ' ', r.get('ementa') or '').strip())}",
            f"entidade: {yaml('Câmara Municipal de ' + nome)}",
            f"tipo_sapl: {yaml(r['tipo_descricao'])}",
            f"publicacao: {yaml(veic)}",
            f"data_publicacao: {r.get('data_publicacao') or ''}",
            f"fonte: {yaml(host + '/norma/' + str(r['id']))}",
            f"arquivo: {yaml(pdf)}",
            f"sapl_id: {r['id']}",
            f"versao_texto: {yaml(versao)}",
            f"baixado_em: {HOJE}",
            "---",
            f"# {r['__str__']}",
            "",
        ]
        if (r.get("ementa") or "").strip():
            cab += [f"_{re.sub(r'\s+', ' ', r['ementa']).strip()}_", ""]
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(cab) + "\n" + (corpo or f"> {versao}. Ver `fonte`.") + "\n")
        n += 1
        if n % 100 == 0:
            log(f"{nome}: {n}/{len(alvos)} ({nf} falhas)")
    log(f"{nome}: pronto, {n} leis novas, {nf} falhas")


def verificar():
    """Confere índice × arquivos gravados (cada lei do SAPL tem exatamente um .md) e resume a origem do texto."""
    from collections import Counter
    linhas, ok = [], True
    total = Counter()
    for s, (nome, host) in HOSTS.items():
        p = os.path.join(INDICE, f"sapl_{s}.jsonl")
        if not os.path.exists(p):
            continue
        ids = {json.loads(l)["id"] for l in open(p, encoding="utf-8") if classificar(json.loads(l)["tipo_descricao"])}
        achados, versoes = Counter(), Counter()
        for d, _, fs in os.walk(os.path.join(SAIDA, s)):
            for f in fs:
                m = re.search(r"-sapl(\d+)\.md$", f)
                if m:
                    achados[int(m.group(1))] += 1
                    v = re.search(r'^versao_texto: "([^"]*)"', open(os.path.join(d, f), encoding="utf-8").read(), re.M).group(1)
                    versoes[v.split(";")[0].split(" (")[0]] += 1
        faltam, sobram, dup = ids - set(achados), set(achados) - ids, [i for i, n in achados.items() if n > 1]
        ok &= not (faltam or sobram or dup)
        total.update(versoes)
        linhas.append(f"| {nome} | {len(ids)} | {sum(achados.values())} | {len(faltam)} | {len(sobram)} | {len(dup)} | "
                      + "; ".join(f"{v}: {n}" for v, n in versoes.most_common()) + " |")
    o = [f"# SAPL: verificação ({time.strftime('%d/%m/%Y %H:%M')})", "",
         f"Resultado: **{'OK' if ok else 'FALHA'}** (toda lei do índice tem exatamente um arquivo, e nenhum arquivo sobra)", "",
         "| Município | Leis no SAPL | Arquivos | Faltam | Sobram | Duplicados | Origem do texto |", "|---|---|---|---|---|---|---|"]
    o += linhas + ["", "Total por origem do texto: " + "; ".join(f"{v}: {n}" for v, n in total.most_common())]
    with open(os.path.join(SAIDA, "_sapl_verificacao.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(o) + "\n")
    print("\n".join(o))
    return ok


_LOG = threading.Lock()


def log(msg):
    linha = f"{time.strftime('%H:%M:%S')} {msg}"
    with _LOG:
        print(linha, flush=True)
        with open(os.path.join(INDICE, "sapl.log"), "a", encoding="utf-8") as f:
            f.write(linha + "\n")


def _teste_classificar():
    casos = {"Lei Ordinária": "Lei Ordinária", "LEI ORDINÁRIA": "Lei Ordinária", "Lei Municipal": "Lei Ordinária",
             "Lei": "Lei Ordinária", "Lei da Câmara Municipal": "Lei Ordinária", "Lei Consolidada": "Lei Ordinária",
             "Lei Ordinária (Promulgada)": "Lei Promulgada", "LEI DELEGADA": "Lei Delegada",
             "Lei Complementar Municipal": "Lei Complementar", "Emenda à Loman": "Emenda à Lei Orgânica",
             "EMENDA À LEI ORGÂNICA": "Emenda à Lei Orgânica", "Emenda a Lei Orgânica": "Emenda à Lei Orgânica",
             "Loman": "Lei Orgânica", "Lei Orgânica Municipal": "Lei Orgânica", "Decreto Lei": None,
             "Decreto Legislativo": None, "Resolução": None, "Portaria": None, "Errata": None,
             "Emancipação do Iranduba": None, "Regimento Interno": None, "Ação Direta de Inconstitucionalidade": None}
    for d, esperado in casos.items():
        c = classificar(d)
        assert (c[0] if c else None) == esperado, (d, c)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    _teste_classificar()
    etapa = sys.argv[1] if len(sys.argv) > 1 else ""
    alvo = [s for s in HOSTS if (sys.argv[2] if len(sys.argv) > 2 else "") in s]
    parte = tuple(map(int, sys.argv[3].split("/"))) if len(sys.argv) > 3 else (0, 1)
    if etapa == "verificar":
        sys.exit(0 if verificar() else 1)
    if etapa not in ("indice", "baixar", "tudo"):
        print(__doc__)
        sys.exit()
    os.makedirs(INDICE, exist_ok=True)
    with ThreadPoolExecutor(len(alvo)) as ex:
        if etapa in ("indice", "tudo"):
            list(ex.map(indice, alvo))
        if etapa in ("baixar", "tudo"):
            trava = threading.Lock()
            with open(os.path.join(SAIDA, "_falhas_sapl.jsonl"), "a", encoding="utf-8") as falhas:
                for fut in [ex.submit(baixar, s, falhas, trava, parte) for s in alvo]:
                    fut.result()
