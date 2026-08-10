# Guia de Contribuição e Fluxo de Trabalho

Este documento define o fluxo de trabalho do nosso repositório, desde a criação de branches até a aprovação de Pull Requests (PRs). É fundamental que toda a equipe siga estas diretrizes para manter o desenvolvimento ágil e organizado.

## 1. Fluxo de Trabalho (Git Workflow)

Nosso ambiente base de integração contínua é a branch **`homolog`**. Todo o seu trabalho deve partir dela.

1. **Iniciando uma Tarefa:** Para cada tarefa que você pegar no quadro, crie uma **nova branch** sempre a partir da branch `homolog` atualizada. **Adendo Importante: Você só deve pegar tarefas que estão no quadro da sprint atual.** Não inicie o desenvolvimento de itens que estão no backlog geral ou previstos para sprints futuras.
2. **Desenvolvimento:** Faça seus commits de forma clara e objetiva na sua branch recém-criada.
3. **Pull Request (PR):** Assim que finalizar a tarefa, abra um Pull Request apontando a sua branch de volta para a `homolog`.
4. **Não bloqueie seu trabalho:** Você **não precisa esperar** o merge do seu PR para continuar trabalhando. Após abrir o PR, volte para a branch `homolog`, dê um `git pull` para garantir que está com a versão mais recente, crie uma nova branch para a próxima tarefa da sprint atual e siga o desenvolvimento.

## 2. Resolução de Conflitos

* **Responsabilidade do Desenvolvedor:** Caso o seu PR apresente conflitos com a `homolog` (por exemplo, se outro dev alterou o mesmo arquivo que você enquanto sua branch estava aberta), **é sua responsabilidade resolver o conflito**.
* **Como fazer:** Atualize sua branch com as novidades da `homolog` (via `git merge homolog` ou `git rebase homolog` na sua branch), resolva os arquivos conflitantes na sua máquina, faça um novo commit e suba as alterações. O PR será atualizado automaticamente.

## 3. Ciclo de Vida do PR

* Quando o seu PR for revisado e aceito, o código será integrado (merged) à `homolog`.
* Após o merge, a sua branch temporária da tarefa **será apagada** do repositório remoto para manter a organização.

## 4. Ócio Produtivo e Autonomia

Terminou suas tarefas, já abriu os PRs e o quadro está livre para você?
* **Assuma novas responsabilidades:** Caso se sinta seguro, você tem total liberdade para puxar tarefas de outras pessoas no quadro. A ideia é que o time se ajude para não travar a esteira de desenvolvimento. Reforçando a regra: **limite-se exclusivamente a assumir tarefas que pertencem à sprint atual**.

---

## 5. Padrões de Nomenclatura de Branches

Para manter a organização, utilizamos prefixos que indicam a natureza do trabalho realizado na branch. Siga os padrões abaixo:

### Histórias e Novas Funcionalidades
* **`hu[numero]/nome-da-historia`**: Para tarefas atreladas a uma História de Usuário (Ex: `hu02/login-offline`).
* **`feat/nome-da-funcionalidade`**: Para novas funcionalidades soltas (Ex: `feat/leitor-qrcode-brincos`).

### Melhorias e Correções
* **`improve/nome-da-melhoria`**: Para melhorias em funcionalidades já existentes (Ex: `improve/performance-lista-gado`).
* **`fix/nome-do-ajuste`**: Para correções de bugs e erros identificados (Ex: `fix/calculo-area-talhao`).
* **`hotfix/nome-do-ajuste`**: Exclusivo para bugs críticos que precisam ser corrigidos com urgência (geralmente apontando para produção, mas aplicável ao fluxo dependendo da gravidade).

### Manutenção e Outros
* **`chore/nome-da-tarefa`**: Para atualizações de bibliotecas, configurações de build ou tarefas que não afetam o código de produção diretamente (Ex: `chore/atualiza-react-native`).
* **`docs/nome-do-documento`**: Para adições ou alterações em documentações (Ex: `docs/arquitetura-offline`).
* **`refactor/nome-do-refactor`**: Para reestruturações de código que não alteram o comportamento da aplicação (Ex: `refactor/hook-sincronizacao`).
