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
| [Diário Oficial dos Municípios do AM (AAM/SIGPub)](https://www.diariomunicipal.com.br/aam/) | 61 municípios, sem Manaus; prefeituras e câmaras; matérias desde 2009 | em coleta (`scripts/aam.py`) |
| SAPL das câmaras (`sapl.<municipio>.am.leg.br`) | 26 câmaras com o sistema; só 9 com normas cadastradas (≈ 11 mil, a maior parte de Manacapuru) | a fazer |
| Manaus (DOM Manaus / CMM) | Manaus não publica no diário da AAM | a fazer |

O diário da AAM é a fonte principal, porque é o meio oficial de publicação dos atos desses municípios.
A coleta só pega o que foi publicado nele, então leis anteriores à adesão de cada município (≈ 2009–2013)
ficam de fora.

## Estrutura

```
municipais/AM/<municipio>/
  leis-ordinarias/AAAA/*.md
  leis-complementares/AAAA/*.md
  lei-organica/  emendas-lei-organica/  leis-promulgadas/  leis-delegadas/
municipais/AM/_falhas.jsonl          o que não entrou, e por quê
_indice/aam.jsonl                    índice bruto das matérias com "LEI" no título (uma por linha)
scripts/aam.py                       coleta no diário da AAM
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
```

Só usa a biblioteca padrão do Python. Faz uma requisição por vez, com pausa, para não pesar no servidor
da AAM.

O que é descartado: matérias que só citam lei no título (extratos, editais, termos, anexos), além de
projeto de lei, veto, autógrafo e errata.
