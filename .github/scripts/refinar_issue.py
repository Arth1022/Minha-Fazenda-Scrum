"""Refina uma issue crua em Historia de Usuario usando a API do Gemini.

Le issue.json, backlog.json e labels.json (gerados pelo gh CLI no workflow) e escreve:
  nova_descricao.md : corpo novo da issue
  novo_titulo.txt   : titulo com o identificador da historia (HU-NN)
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


def montar_esquema(grupos):
    propriedades = {
        "titulo": {
            "type": "string",
            "description": "Titulo curto e especifico, sem o identificador HU",
        },
        "corpo_markdown": {
            "type": "string",
            "description": "A historia completa em Markdown, no formato pedido",
        },
        "issues_relacionadas": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Numeros de issues do backlog que se sobrepoem a esta",
        },
        "tem_perguntas_abertas": {"type": "boolean"},
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
    """Numeracao deterministica: reaproveita o ID se ja existir, senao usa max+1."""
    ja_tem = ID_RE.search(issue["title"] or "")
    if ja_tem:
        return f"HU-{int(ja_tem.group(1)):02d}"

    usados = []
    for outra in backlog:
        achou = ID_RE.search(outra["title"] or "")
        if achou:
            usados.append(int(achou.group(1)))
    return f"HU-{(max(usados) + 1 if usados else 1):02d}"


def montar_prompt(issue, backlog, grupos, story_id):
    outras = [i for i in backlog if i["number"] != issue["number"]]
    if outras:
        lista = "\n".join(
            f"- #{i['number']} [{i['state'].lower()}] {i['title']}" for i in outras
        )
    else:
        lista = "(backlog vazio - esta e a primeira historia do projeto)"

    blocos = []
    for campo, grupo in grupos.items():
        quantidade = (
            "uma ou mais" if grupo["multiplo"] else "exatamente uma"
        )
        opcoes = ", ".join(f"`{l}`" for l in grupo["labels"])
        blocos.append(
            f"### `{campo}` - {grupo['titulo']}\n"
            f"Escolha {quantidade} entre: {opcoes}\n{grupo['guia']}"
        )
    classificacao = "\n\n".join(blocos)

    corpo = (issue["body"] or "").strip() or "(o autor nao escreveu descricao)"

    return f"""Você é o Product Owner do "Minha Fazenda", um aplicativo de gestão para \
produtores rurais brasileiros, conduzido em Scrum.

## Contexto do produto
- Usuários: produtor rural, pecuarista, agrônomo e operador de campo — em geral com \
pouca familiaridade com tecnologia.
- Uso real: celular na mão no meio da lavoura ou do curral, sol forte, mãos sujas, \
às vezes com luva, conexão de dados instável ou inexistente.
- Consequência: tudo precisa ser offline-first, com telas simples, poucos toques, \
textos grandes e linguagem do campo (não use jargão técnico dentro da história).

## Backlog atual (para você NÃO repetir história já existente)
{lista}

## Identificador desta história
Use exatamente `{story_id}`. Ele já foi calculado — não invente outro número.

## Sua tarefa
Transforme a ideia crua abaixo em uma História de Usuário pronta para a Sprint Planning, \
e classifique-a você mesmo nos campos abaixo.

**Título original:** {issue["title"]}
**Ideia original:** {corpo}

## Classificação
Você decide. Julgue pelo esforço real de implementação, não pelo tamanho do texto \
da ideia.

{classificacao}

### `issues_relacionadas`
Números das issues do backlog acima que se sobrepõem a esta (lista vazia se nenhuma).

### `tem_perguntas_abertas`
`true` se restou ambiguidade que o PO precisa responder.

## Regras para o `corpo_markdown`
- Critérios de aceite em Gherkin (**Dado** / **Quando** / **Então**), testáveis e \
observáveis. No máximo 6.
- Pelo menos um critério deve cobrir comportamento sem internet, quando fizer sentido.
- Se algo estiver ambíguo, **não invente requisito** — registre em "Perguntas para o PO".
- Se houver sobreposição com o backlog, cite `#numero` dentro do corpo também.
- Não cite tecnologias, bancos de dados ou integrações que não foram mencionados.
- A seção "Esforço" deve explicar a escolha do tamanho, coerente com o campo `tamanho`.
- Escreva o corpo neste formato exato:

### {story_id} — <título curto e específico>

**Como um** <perfil de usuário do campo>
**Eu quero** <ação concreta>
**Para que** <benefício prático / problema resolvido>

### Critérios de Aceite
- [ ] **Dado** <contexto> **Quando** <ação> **Então** <resultado observável>

### Regras de Negócio
- <regra objetiva, ou "Nenhuma identificada">

### Notas de Campo (offline e usabilidade)
- <o que precisa funcionar sem sinal, o que precisa ser à prova de erro>

### Notas Técnicas
- <o que cada parte da stack escolhida precisa fazer>

### Definição de Pronto
- [ ] Funciona sem conexão e sincroniza quando a internet voltar
- [ ] Testado em tela pequena e sob luz forte
- [ ] <outro item específico desta história>

### Esforço
**<tamanho escolhido>** — <justificativa em uma linha>

### Perguntas para o PO
- <pergunta, ou "Nenhuma — escopo claro">
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
        "temperature": 0.4,
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
    print(f"Refinando issue #{issue['number']} como {story_id} (modelo {MODEL})")

    resultado = chamar_gemini(
        montar_prompt(issue, backlog, grupos, story_id), montar_esquema(grupos)
    )
    original = (issue["body"] or "").strip() or "_(sem descricao original)_"

    relacionadas = resultado.get("issues_relacionadas") or []
    aviso = ""
    if relacionadas:
        refs = ", ".join(f"#{n}" for n in relacionadas)
        aviso = f"> ⚠️ Pode se sobrepor a: {refs}\n\n"
    if resultado.get("tem_perguntas_abertas"):
        aviso += "> ⚠️ Tem pergunta em aberto para o PO — veja o fim da issue.\n\n"

    with open("nova_descricao.md", "w", encoding="utf-8") as f:
        f.write(
            f"{aviso}{resultado['corpo_markdown'].strip()}\n\n---\n\n"
            "<details>\n<summary>Ideia original (antes do refinamento)</summary>\n\n"
            f"{original}\n\n</details>\n\n"
            f"<sub>Refinado automaticamente por {MODEL} — revise antes da Sprint "
            "Planning.</sub>\n"
        )

    titulo = ID_RE.sub("", resultado["titulo"] or "").lstrip(" -—:").strip()
    with open("novo_titulo.txt", "w", encoding="utf-8") as f:
        f.write(f"{story_id} — {titulo}")

    labels = montar_labels(resultado, grupos)
    print(f"Labels: {labels}")
    with open("labels.txt", "w", encoding="utf-8") as f:
        f.write(",".join(labels))


if __name__ == "__main__":
    main()
