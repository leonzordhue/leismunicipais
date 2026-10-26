# Leis municipais do Amazonas em Markdown

Leis dos municípios do Amazonas convertidas de fontes oficiais para Markdown, com cabeçalho YAML e link
para a publicação original. Segue o mesmo formato de [ctresb/leis](https://github.com/ctresb/leis)
(federal e estaduais), para que as duas bases possam ser buscadas juntas.

> [!IMPORTANT]
> Os textos têm caráter informativo e **não substituem a publicação no Diário Oficial**. São
> conversões automáticas. Confira sempre o link `fonte` do cabeçalho antes de citar.

## Fontes

| Fonte | Cobertura | Situação |
| --- | --- | --- |
| [Diário Oficial dos Municípios do AM (AAM/SIGPub)](https://www.diariomunicipal.com.br/aam/) | 61 municípios, sem Manaus; prefeituras e câmaras; matérias desde 2009 | 9.258 leis (`scripts/aam.py`) |
| [SAPL da Câmara Municipal de Manaus](https://sapl.cmm.am.gov.br) | Manaus, leis desde os anos 1940 (7.532 leis no SAPL em 16/10/2026) | completo, 0 faltando no `sapl.py verificar` (17/10/2026) |
| SAPL das câmaras (`sapl.<municipio>.am.leg.br`) | 9 câmaras com normas cadastradas: Coari, Codajás, Envira, Iranduba, Manacapuru, Manicoré, Novo Airão, Parintins e Tefé (6.962 leis; outras ≈ 20 câmaras têm o sistema vazio) | completo, 0 faltando no `sapl.py verificar` (17/10/2026) |

Nos municípios que estão nas duas fontes, a mesma lei pode aparecer duas vezes (uma do diário, uma do SAPL), lado a
lado na mesma pasta. O sufixo do arquivo diz a origem: `-<codigo_sigpub>.md` (AAM) ou `-sapl<id>.md` (SAPL).

### SAPL: de onde vem o texto

O SAPL guarda o PDF que a câmara cadastrou (campo `texto_integral`). O `sapl.py` usa a camada de texto do PDF. Quando
a página é imagem, ou quando a camada de texto é ruim (OCR antigo), refaz o OCR com o Tesseract (português) e fica com
o melhor dos dois. Para medir a qualidade, usa a fração das palavras que existem no vocabulário das leis do diário da AAM.
Página abaixo de 0,45 (manuscrito, cópia ilegível) é omitida, porque o OCR de manuscrito produz palavras inventadas.
Calibração em Novo Airão: manuscrito de 0,27 a 0,40; datilografado com OCR antigo de 0,45 a 0,75; digital acima de 0,8.
O campo `versao_texto` diz o que aconteceu com cada lei:

- `texto do PDF cadastrado no SAPL`;
- `OCR do PDF digitalizado ...` ou `... com OCR nas páginas digitalizadas` (pode ter erros de OCR);
- `... páginas manuscritas ou ilegíveis omitidas` ou `sem texto: PDF manuscrito ou ilegível` (ler o `arquivo`);
- `sem texto: o SAPL não tem o PDF desta lei` (só a ementa).

A `ementa` do SAPL é a cadastrada pela câmara, e não uma extração por heurística. O cabeçalho do SAPL traz ainda
`data` (data da lei), `tipo_sapl` (tipo como a câmara o cadastrou), `arquivo` (PDF) e `sapl_id`.

O diário da AAM é a fonte principal, porque é o meio oficial de publicação dos atos desses municípios.
A coleta só pega o que foi publicado nele, então leis anteriores à adesão de cada município (≈ 2009–2013)
ficam de fora.

## Estrutura

```
municipais/AM/<municipio>/
  leis-ordinarias/AAAA/*.md
  leis-complementares/AAAA/*.md
  lei-organica/  emendas-lei-organica/  leis-promulgadas/  leis-delegadas/
municipais/AM/_falhas.jsonl          o que não entrou do diário da AAM, e por quê
municipais/AM/_falhas_sapl.jsonl     o mesmo para o SAPL (a próxima execução tenta de novo)
_indice/aam.jsonl                    índice bruto das matérias com "LEI" no título (uma por linha)
scripts/aam.py                       coleta no diário da AAM
scripts/sapl.py                      coleta nos SAPL (Manaus e câmaras)
_indice/sapl_<municipio>.jsonl       índice bruto das normas de cada SAPL
```

Nome do arquivo: `<tipo>-<numero>-<ano>-<codigo_sigpub>.md`. O código SIGPub entra no nome porque a mesma
lei pode ser republicada (retificação, republicação por incorreção). As versões ficam lado a lado.

## Formato

```markdown
---
titulo: "LEI Nº 1.064/2026/PGMP"
uf: "AM"
municipio: "Parintins"
tipo: "Lei Ordinária"
numero: "1064"
ano: "2026"
ementa: "INSTITUI O PROGRAMA DE VALORIZAÇÃO E MEMÓRIA DOS COMPOSITORES ..."
entidade: "Município de Parintins"
orgao: "PROCURADORIA GERAL DO MUNICIPIO"
publicacao: "DOM-AAM ed. 4200"
data_publicacao: 2026-09-25
fonte: "https://www.diariomunicipal.com.br/aam/materia/E8A3032A"
codigo_sigpub: "E8A3032A"
versao_texto: "original (publicação no DOM-AAM)"
baixado_em: 2026-10-15
---
# LEI Nº 1.064/2026/PGMP
```

`tipo` usa o mesmo vocabulário do ctresb/leis. A `ementa` é extraída por heurística: é o primeiro parágrafo
depois do título que não seja fórmula de promulgação. Pode vir vazia.

## Como reproduzir

```
python -I scripts/aam.py indice      # lista as matérias com "LEI" no título, por entidade (retoma)
python -I scripts/aam.py baixar      # baixa e converte cada lei (retoma; pula o que já existe)
python -I scripts/sapl.py indice     # lista as normas de cada SAPL em _indice/sapl_<municipio>.jsonl
python -I scripts/sapl.py baixar     # baixa o PDF de cada lei e converte (retoma; pula o que já existe)
python -I scripts/sapl.py baixar manaus 0/4   # só a parte 0 de 4; rodar 0/4 a 3/4 em paralelo
```

O `sapl.py` precisa do PyMuPDF (`pip install pymupdf`) e do Tesseract com `por.traineddata`.

O `aam.py` só usa a biblioteca padrão do Python. Faz uma requisição por vez, com pausa, para não pesar no servidor
da AAM.

O que é descartado: matérias que só citam lei no título (extratos, editais, termos, anexos), além de
projeto de lei, veto, autógrafo e errata.
