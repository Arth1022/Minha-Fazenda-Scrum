"""Organiza uma issue crua em Historia de Usuario usando a API do Gemini.

O script e propositalmente simples: ele NAO reescreve a ideia do autor. Ele so faz tres coisas:
  1. Numera a historia (HUnnn), sem reaproveitar numero de historia ja apagada -
     usa sempre o maior numero ja existente no backlog + 1.
  2. Corrige erros de portugues no titulo e em cada tarefa.
  3. Classifica a historia nas labels do repositorio.

A descricao original e dividida em tarefas por virgula (ou por linha, se nao houver virgula) -
cada pedaco vira um item da lista. O modelo so pode corrigir ortografia/gramatica de cada
item; ele nao pode juntar, quebrar, remover ou inventar tarefas.

Le issue.json, backlog.json e labels.json (gerados pelo gh CLI no workflow) e escreve:
  nova_descricao.md : corpo novo da issue (lista de tarefas)
  novo_titulo.txt   : titulo com o identificador da historia (HUnnn)
  labels.txt        : labels escolhidas pelo modelo, separadas por virgula

As labels vem do proprio repositorio em tempo de execucao. GRUPOS abaixo so diz
o QUE cada grupo significa; se uma label for renomeada no GitHub, o script segue
funcionando desde que o nome continue batendo (a comparacao ignora maiusculas).
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

ID_RE = re.compile(r"\bHU[-\s]?(\d+)", re.IGNORECASE)

GRUPOS = {
    "tamanho": {
        "labels": ["PP", "P", "G", "GG"],
        "multiplo": False,
        "titulo": "Tamanho (esforco estimado)",
        "guia": (
            "- `PP`: ajuste trivial, poucas horas. Uma tela ja existente, um campo a mais.\n"
            "- `P`: cabe folgado numa sprint. Um fluxo simples, sem regra complicada.\n"
            "- `G`: ocupa boa parte da sprint. Varias telas ou regra de negocio densa.\n"
            "- `GG`: nao cabe numa sprint. Se escolher GG, sugira a quebra dentro do corpo."
        ),
    },
    "stack": {
        "labels": ["Front-End", "Back-End", "DataBase"],
        "multiplo": True,
        "titulo": "Stack envolvida",
        "guia": (
            "- `Front-End`: tem tela, formulario, navegacao ou interacao do usuario.\n"
            "- `Back-End`: tem regra de negocio, API, calculo, notificacao ou sincronizacao.\n"
            "- `DataBase`: cria/altera dado persistido, novo cadastro ou migracao.\n"
            "Escolha todas que se aplicam - a maioria das historias tem mais de uma."
        ),
    },
    "tipo": {
        "labels": ["Melhoria", "Bug", "Documentação"],
        "multiplo": False,
        "titulo": "Tipo de trabalho",
        "guia": (
            "- `Melhoria`: funcionalidade nova ou evolucao de algo existente (caso comum).\n"
            "- `Bug`: algo que ja existe e esta funcionando errado.\n"
            "- `Documentação`: material de apoio, manual, documentacao do projeto."
        ),
    },
}


def resolver_grupos(labels_do_repo):
    """Casa GRUPOS com as labels que realmente existem no repo, mantendo a grafia de la."""
    por_nome = {l["name"].lower(): l["name"] for l in labels_do_repo}
    resolvidos = {}
    for campo, grupo in GRUPOS.items():
        existentes = [por_nome[n.lower()] for n in grupo["labels"] if n.lower() in por_nome]
        if existentes:
            resolvidos[campo] = {**grupo, "labels": existentes}
        else:
            print(
                f"aviso: nenhuma label do grupo '{campo}' existe no repo; "
                "o modelo nao vai classificar esse grupo",
                file=sys.stderr,
            )
    return resolvidos


def montar_esquema(grupos, n_tarefas):
    propriedades = {
        "titulo": {
            "type": "string",
            "description": (
                "O mesmo titulo original, apenas com erros de portugues corrigidos. "
                "Nao invente um titulo novo. Sem o identificador HU."
            ),
        },
        "tarefas": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": n_tarefas,
            "maxItems": n_tarefas,
            "description": (
                "Exatamente as mesmas tarefas de entrada, na mesma ordem, apenas com "
                "erros de portugues corrigidos. Nao junte, nao separe, nao invente."
            ),
        },
    }
    for campo, grupo in grupos.items():
        if grupo["multiplo"]:
            propriedades[campo] = {
                "type": "array",
                "items": {"type": "string", "enum": grupo["labels"]},
            }
        else:
            propriedades[campo] = {"type": "string", "enum": grupo["labels"]}

    return {
        "type": "object",
        "properties": propriedades,
        "required": list(propriedades),
    }


def carregar():
    def ler(nome):
        with open(nome, encoding="utf-8") as f:
            return json.load(f)

    return ler("issue.json"), ler("backlog.json"), ler("labels.json")


def definir_id(issue, backlog):
    """Numeracao deterministica: reaproveita o ID se ja existir, senao preenche o buraco.

    `backlog` vem de `gh issue list --state all`, que so lista issues que ainda
    existem (abertas ou fechadas) - uma issue apagada de verdade some dessa lista.
    Por isso o proximo numero e sempre o MENOR numero que nao esta mais em uso:
    se HU001 existe e HU002 foi apagada, a proxima historia volta a ser HU002
    (nao pula pra HU003).
    """
    ja_tem = ID_RE.search(issue["title"] or "")
    if ja_tem:
        return f"HU{int(ja_tem.group(1)):03d}"

    usados = set()
    for outra in backlog:
        achou = ID_RE.search(outra["title"] or "")
        if achou:
            usados.add(int(achou.group(1)))

    proximo = 1
    while proximo in usados:
        proximo += 1
    return f"HU{proximo:03d}"


def dividir_tarefas(descricao, titulo_reserva):
    """Quebra a descricao crua em tarefas, sem reescrever nada.

    Separador e virgula OU quebra de linha (o autor pode usar qualquer um dos dois,
    ou os dois). Se a descricao vier vazia, usa o titulo como unica tarefa - assim a
    historia sempre tem pelo menos uma linha no corpo.
    """
    texto = (descricao or "").strip()
    if not texto:
        return [titulo_reserva.strip()] if titulo_reserva.strip() else []

    pedacos = re.split(r"[,\n]+", texto)
    tarefas = [p.strip(" \t-*•") for p in pedacos]
    tarefas = [t for t in tarefas if t]
    return tarefas or [texto]


def montar_prompt(issue, grupos, story_id, tarefas):
    blocos = []
    for campo, grupo in grupos.items():
        quantidade = "uma ou mais" if grupo["multiplo"] else "exatamente uma"
        opcoes = ", ".join(f"`{l}`" for l in grupo["labels"])
        blocos.append(
            f"### `{campo}` - {grupo['titulo']}\n"
            f"Escolha {quantidade} entre: {opcoes}\n{grupo['guia']}"
        )
    classificacao = "\n\n".join(blocos)

    tarefas_texto = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(tarefas))

    return f"""Você é o Product Owner do "Minha Fazenda", um aplicativo de gestão para \
produtores rurais brasileiros, conduzido em Scrum.

## Identificador desta história
Use exatamente `{story_id}`. Ele já foi calculado — não invente outro número.

## Sua tarefa (seja literal, não reescreva a ideia)
O autor já dividiu a ideia em tarefas abaixo. Sua única tarefa em relação a elas é \
corrigir ortografia e gramática, mantendo o sentido original de cada uma. \
Não junte duas tarefas em uma, não separe uma tarefa em duas, não invente tarefas \
novas, não remova nenhuma e não mude a ordem. A lista de saída precisa ter \
exatamente {len(tarefas)} item(ns), na mesma ordem.

O mesmo vale para o título: só corrija erros de português, sem reescrevê-lo.

**Título original:** {issue["title"]}

**Tarefas originais (já divididas pelo autor):**
{tarefas_texto}

## Classificação
Depois de corrigir o texto, classifique a história nos campos abaixo. Julgue pelo \
esforço real de implementação, considerando que os usuários são produtores rurais \
com pouca familiaridade com tecnologia e que o app precisa funcionar offline.

{classificacao}
"""


def extrair_texto(resposta):
    candidatos = resposta.get("candidates") or []
    if not candidatos:
        raise RuntimeError(
            f"a API nao retornou candidatos. promptFeedback={resposta.get('promptFeedback')}"
        )

    candidato = candidatos[0]
    partes = (candidato.get("content") or {}).get("parts") or []
    # modelos com raciocinio devolvem partes de "thought" que nao sao a resposta
    texto = "".join(p.get("text", "") for p in partes if not p.get("thought"))

    if not texto.strip():
        raise RuntimeError(
            f"resposta vazia (finishReason={candidato.get('finishReason')})"
        )
    return texto.strip()


def chamar_gemini(prompt, esquema):
    api_key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    config = {
        "temperature": 0.1,
        "maxOutputTokens": 8192,
        "responseMimeType": "application/json",
        "responseSchema": esquema,
    }
    if MODEL.startswith("gemini-2.5-flash"):
        config["thinkingConfig"] = {"thinkingBudget": 0}

    dados = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

    erro = None
    for tentativa in range(1, 4):
        try:
            req = urllib.request.Request(url, data=dados, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as r:
                bruto = extrair_texto(json.loads(r.read().decode("utf-8")))
                return json.loads(bruto)
        except urllib.error.HTTPError as e:
            erro = f"HTTP {e.code} - {e.read().decode('utf-8', 'replace')[:600]}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except json.JSONDecodeError as e:
            erro = f"o modelo nao devolveu JSON valido: {e}"
        except Exception as e:  # timeout, rede, resposta inesperada
            erro = f"{type(e).__name__}: {e}"

        if tentativa < 3:
            print(f"tentativa {tentativa} falhou ({erro}); repetindo...", file=sys.stderr)
            time.sleep(5 * tentativa)

    raise RuntimeError(f"Gemini falhou apos 3 tentativas - {erro}")


def montar_labels(resultado, grupos):
    """So aceita label que existe no grupo; o resto e descartado sem quebrar o run."""
    escolhidas = []
    for campo, grupo in grupos.items():
        valores = resultado.get(campo) or []
        if not grupo["multiplo"]:
            valores = [valores] if valores else []

        validas = {l.lower(): l for l in grupo["labels"]}
        for valor in valores:
            if not isinstance(valor, str):
                continue
            oficial = validas.get(valor.strip().lower())
            if oficial and oficial not in escolhidas:
                escolhidas.append(oficial)
            elif not oficial:
                print(f"aviso: label '{valor}' ignorada (fora do grupo '{campo}')",
                      file=sys.stderr)
    return escolhidas


def main():
    issue, backlog, labels_do_repo = carregar()
    grupos = resolver_grupos(labels_do_repo)
    story_id = definir_id(issue, backlog)
    tarefas_originais = dividir_tarefas(issue["body"], issue["title"] or "")
    print(f"Refinando issue #{issue['number']} como {story_id} (modelo {MODEL}, "
          f"{len(tarefas_originais)} tarefa(s))")

    resultado = chamar_gemini(
        montar_prompt(issue, grupos, story_id, tarefas_originais),
        montar_esquema(grupos, len(tarefas_originais)),
    )

    tarefas_final = resultado.get("tarefas") or []
    valido = (
        len(tarefas_final) == len(tarefas_originais)
        and all(isinstance(t, str) and t.strip() for t in tarefas_final)
    )
    if not valido:
        print(
            "aviso: o modelo devolveu uma lista de tarefas inconsistente; "
            "mantendo o texto original sem correcao",
            file=sys.stderr,
        )
        tarefas_final = tarefas_originais

    corpo_lista = "\n".join(f"- {t.strip()}" for t in tarefas_final)

    with open("nova_descricao.md", "w", encoding="utf-8") as f:
        f.write(f"{corpo_lista}\n")

    titulo = ID_RE.sub("", resultado.get("titulo") or "").lstrip(" -—:").strip()
    if not titulo:
        titulo = (issue["title"] or "").strip()
    with open("novo_titulo.txt", "w", encoding="utf-8") as f:
        f.write(f"{story_id} - {titulo}")

    labels = montar_labels(resultado, grupos)
    print(f"Labels: {labels}")
    with open("labels.txt", "w", encoding="utf-8") as f:
        f.write(",".join(labels))


if __name__ == "__main__":
    main()
