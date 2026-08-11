"""Organiza uma issue crua em Historia de Usuario usando a API do Gemini.

O script e propositalmente simples: ele NAO reescreve a ideia do autor. Ele so faz tres coisas:
  1. Numera a historia (HU-nnn), sem reaproveitar numero de historia ja apagada -
     usa sempre o maior numero ja existente no backlog + 1.
  2. Corrige erros de portugues no titulo e em cada tarefa.
  3. Classifica a historia nas labels do repositorio.

A descricao original e dividida em tarefas por virgula (ou por linha, se nao houver virgula) -
cada pedaco vira um item da lista sob "O que precisa ser feito:". O modelo so pode corrigir
ortografia/gramatica de cada item; ele nao pode juntar, quebrar, remover ou inventar tarefas.
Os criterios de aceitacao NAO sao gerados aqui de proposito - invente-los seria reescrever a
ideia do autor; o time preenche essa secao no refinamento.

Le issue.json, backlog.json e labels.json (gerados pelo gh CLI no workflow) e escreve:
  nova_descricao.md : corpo novo da issue (lista de tarefas)
  novo_titulo.txt   : titulo com o identificador da historia (HU-nnn)
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
        "labels": ["PP", "P", "M", "G", "GG"],
        "multiplo": False,
        "titulo": "Tamanho (esforco estimado)",
        "guia": (
            "- `PP`: trivial, poucas horas. Uma tela ja existente, um campo a mais.\n"
            "- `P`: pequeno, cerca de um dia. Um fluxo simples, sem regra complicada.\n"
            "- `M`: medio, dois a tres dias. Algumas telas ou uma regra de negocio com jeito.\n"
            "- `G`: grande, ocupa boa parte de uma sprint de foco.\n"
            "- `GG`: nao cabe numa sprint. Se escolher GG, sugira a quebra dentro do corpo."
        ),
    },
    "camada": {
        "labels": ["front", "back", "back-complexo", "back-end", "infra"],
        "multiplo": False,
        "titulo": "Camada",
        "guia": (
            "O app e local-first (React Native + WatermelonDB/SQLite, tudo offline no aparelho),\n"
            "entao `back` quase sempre NAO e servidor - e a camada de dados e logica que roda no\n"
            "proprio celular.\n"
            "- `front`: telas, componentes, navegacao (React Native).\n"
            "- `back`: dados locais - schema WatermelonDB, models, CRUD, calculos e regras\n"
            "  que rodam no aparelho.\n"
            "- `back-complexo`: tarefa de back pesada o bastante para virar issue propria\n"
            "  (cache de mapa offline, motor de sync, agendamento de notificacoes).\n"
            "- `back-end`: servidor de verdade (Spring Boot / Firebase). So aparece nas\n"
            "  historias de sincronizacao e login.\n"
            "- `infra`: build, assinatura e publicacao nas lojas.\n"
            "Escolha a camada onde esta o maior peso do trabalho. Se a historia tem tela E\n"
            "dados locais, ela deveria ser duas issues - escolha a dominante e sugira a\n"
            "quebra dentro do corpo."
        ),
    },
    "modulo": {
        "labels": [
            "fundação",
            "mapa",
            "estoque",
            "plantação",
            "máquinas",
            "rebanho",
            "tratamento",
            "qr-code",
            "home",
            "sincronização",
            "publicação",
            "refinamento",
        ],
        "multiplo": False,
        "titulo": "Modulo do app",
        "guia": (
            "- `fundação`: estrutura base do projeto, persistencia local, navegacao base.\n"
            "- `mapa`: mapa de satelite, perimetro, talhoes e cercas.\n"
            "- `estoque`: insumos, saldo e baixa automatica.\n"
            "- `plantação`: plantio por talhao, atividades, lembretes e carencia.\n"
            "- `máquinas`: tratores, implementos, manutencao e abastecimento.\n"
            "- `rebanho`: cadastro e listagem dos animais.\n"
            "- `tratamento`: vacinas, vermifugos e medicacao do rebanho.\n"
            "- `qr-code`: leitura de QR e QR por animal.\n"
            "- `home`: tela inicial, atalhos e avisos.\n"
            "- `sincronização`: login, API de sync, conflitos e multi-dispositivo.\n"
            "- `publicação`: onboarding, build de release e lojas.\n"
            "- `refinamento`: testes, correcao de bugs e padronizacao de UX/UI."
        ),
    },
    "tecnicas": {
        "labels": ["offline", "dados", "cálculo", "notificação", "geo", "sync", "câmera", "auth"],
        "multiplo": True,
        "opcional": True,
        "titulo": "Marcadores tecnicos",
        "guia": (
            "- `offline`: o ponto central da historia e funcionar sem internet.\n"
            "- `dados`: cria ou altera dado persistido (model, schema, migration, CRUD).\n"
            "- `cálculo`: tem conta a fazer (area, comprimento, quantidade, data).\n"
            "- `notificação`: agenda ou dispara notificacao local.\n"
            "- `geo`: mexe com coordenadas, poligonos ou GPS.\n"
            "- `sync`: faz parte da sincronizacao com a nuvem.\n"
            "- `câmera`: usa a camera do aparelho.\n"
            "- `auth`: cadastro, login ou sessao.\n"
            "Marque so o que realmente se aplica. E normal uma historia nao ter nenhum -\n"
            "nesse caso devolva uma lista vazia."
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
                "minItems": 0 if grupo.get("opcional") else 1,
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
        return f"HU-{int(ja_tem.group(1)):03d}"

    usados = set()
    for outra in backlog:
        achou = ID_RE.search(outra["title"] or "")
        if achou:
            usados.add(int(achou.group(1)))

    proximo = 1
    while proximo in usados:
        proximo += 1
    return f"HU-{proximo:03d}"


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
        if not grupo["multiplo"]:
            quantidade = "exatamente uma"
        elif grupo.get("opcional"):
            quantidade = "zero ou mais"
        else:
            quantidade = "uma ou mais"
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
        f.write(f"O que precisa ser feito:\n{corpo_lista}\n")

    titulo = ID_RE.sub("", resultado.get("titulo") or "").lstrip(" -—:").strip()
    if not titulo:
        titulo = (issue["title"] or "").strip()
    with open("novo_titulo.txt", "w", encoding="utf-8") as f:
        f.write(f"{story_id} — {titulo}")

    labels = montar_labels(resultado, grupos)
    print(f"Labels: {labels}")
    with open("labels.txt", "w", encoding="utf-8") as f:
        f.write(",".join(labels))


if __name__ == "__main__":
    main()
