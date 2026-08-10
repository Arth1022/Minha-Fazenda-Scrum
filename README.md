# Arquitetura do Projeto: App de Gestão para Fazendas

> **IMPORTANTE: LEIA ANTES DE COMEÇAR A TRABALHAR**
> Antes de escrever qualquer código ou assumir uma tarefa, é obrigatório ler o nosso **[Guia de Contribuição e Fluxo de Trabalho](./Git_Workflow.md)** localizado na raiz do repositório. Ele define como criamos branches, abrimos Pull Requests e trabalhamos em equipe.

## 1. Visão Geral da Arquitetura

O sistema adota o padrão de sincronização Delta (Changeset), onde o celular atua como fonte primária da verdade no campo, e o servidor centraliza e distribui as atualizações para múltiplos dispositivos.

```text
[ Mobile - React Native App ]
├── UI & Telas (Mapa, Rebanho, Estoque, Máquinas)
├── Lógicas & Mapas (Turf.js Geo Math)
├── Banco de Dados Local (WatermelonDB / SQLite) <--- Fonte Primária de Verdade Offline
└── Sync Engine (Gatilho via NetInfo)
        ▲
        │ (HTTP REST / JSON Sync payload via Push/Pull ao conectar)
        ▼
[ Backend - Spring Boot (Java) ]
├── Endpoints de Autenticação & Sync (/api/v1/sync)
├── Regras de Negócio e Resolução de Conflitos
└── ORM (JPA/Hibernate)
        ▲
        │ (Comunicação segura com banco em nuvem)
        ▼
[ Nuvem - Supabase / PostgreSQL ]
├── Armazenamento Relacional (Tabelas e Relacionamentos)
└── PostGIS (Armazenamento de Polígonos de Talhões e Cercas)
```

---

## 2. Stack Tecnológica & Documentações

### Ferramentas de Desenvolvimento Recomendadas
Para garantir um ambiente de desenvolvimento padronizado e eficiente, recomendamos a utilização das seguintes ferramentas:

| Ferramenta | Propósito no Projeto | Link para Download |
| :--- | :--- | :--- |
| **Visual Studio Code (VS Code)** | IDE principal recomendada para o desenvolvimento do Frontend (React Native). | [Baixar VS Code](https://code.visualstudio.com/Download) |
| **Android Studio** | Essencial para emulação de dispositivos Android e compilação nativa. | [Baixar Android Studio](https://developer.android.com/studio) |
| **Expo Go / Expo CLI** | Ferramentas para facilitar a visualização e emulação do app mobile durante o desenvolvimento. | [Documentação Expo](https://docs.expo.dev/get-started/installation/) |
| **GitHub Desktop** | Interface gráfica para facilitar o gerenciamento do versionamento (Git) e criação de PRs. | [Baixar GitHub Desktop](https://desktop.github.com/) |
| **Node.js (LTS)** | Ambiente de execução JavaScript necessário para rodar o empacotador do React Native e gerenciadores de pacotes (npm/yarn). | [Baixar Node.js](https://nodejs.org/) |
| **Java Development Kit (JDK) 21** | O backend em Spring Boot utilizará o Java na versão 21. | [Baixar JDK 21 (Oracle)](https://www.oracle.com/java/technologies/downloads/#java21) \| [OpenJDK 21](https://jdk.java.net/21/) |
| **IntelliJ IDEA / Eclipse** | IDEs recomendadas para o desenvolvimento do Backend em Java. | [Baixar IntelliJ](https://www.jetbrains.com/idea/download/) |

### Frontend Mobile (React Native)

| Biblioteca / Ferramenta | Propósito no Projeto | Link Oficial |
| :--- | :--- | :--- |
| **React Native** | Framework principal para construção do app iOS/Android. | [reactnative.dev](https://reactnative.dev/) |
| **TypeScript** | Tipagem estática para garantir segurança no código. | [typescriptlang.org](https://www.typescriptlang.org/) |
| **WatermelonDB** | Banco de dados local reativo sobre SQLite, essencial para o modo offline e motor de sincronização. | [watermelondb.dev](https://watermelondb.dev/) |
| **Axios** | Cliente HTTP para as chamadas da API de sincronização. | [axios-http.com](https://axios-http.com/) |
| **TanStack Query (v5)** | Gerenciamento de estado de requisições, cache e re-tentativas. | [tanstack.com/query](https://tanstack.com/query/latest) |
| **React Native NetInfo** | Monitoramento de conexão (dispara o Sync ao detectar 4G/Wi-Fi). | [react-native-netinfo](https://github.com/react-native-netinfo/react-native-netinfo) |
| **React Native Mapbox** | Renderização de mapas offline via satélite. | [rnmapbox.github.io](https://rnmapbox.github.io/) |
| **Turf.js** | Cálculos de área em hectares e extensão de cercas localmente, sem API. | [turfjs.org](https://turfjs.org/) |
| **Vision Camera** | Leitura rápida de QR Code no campo (Brincos do gado). | [react-native-vision-camera.com](https://react-native-vision-camera.com/) |
| **Notifee** | Notificações locais sem internet (Lembretes de carência e manutenção). | [notifee.app](https://notifee.app/) |
| **React Hook Form + Zod** | Gerenciamento e validação de formulários com alta performance. | [react-hook-form.com](https://react-hook-form.com/) \| [zod.dev](https://zod.dev/) |
| **NativeWind** | Estilização via Tailwind CSS nativo para interfaces de alto contraste. | [nativewind.dev](https://www.nativewind.dev/) |

### Backend, API & Banco de Dados

| Biblioteca / Ferramenta | Propósito no Projeto | Link Oficial |
| :--- | :--- | :--- |
| **Spring Boot (Java 21)** | Backend enterprise para processar integrações, autenticação e regras de negócio. | [spring.io/projects/spring-boot](https://spring.io/projects/spring-boot) |
| **Supabase** | Provedor de Banco de Dados Serverless. | [supabase.com](https://supabase.com/) |
| **PostgreSQL** | Banco de dados relacional (Motor base do Supabase). | [postgresql.org](https://www.postgresql.org/) |
| **PostGIS** | Extensão para PostgreSQL usada para gerenciar dados geoespaciais (Mapas e Talhões). | [postgis.net](https://postgis.net/) |

---

## 3. Estrutura de Pastas Sugerida (Mobile)

Para manter o código escalável entre os desenvolvedores, utilizamos uma arquitetura modular por funcionalidade (Feature-Based):

```text
src/
├── assets/         # Ícones, imagens, fontes
├── components/     # Componentes reusáveis de UI (Button, Card, Input)
├── database/
│   ├── schema.ts   # Definição das tabelas WatermelonDB
│   ├── models/     # Entidades (Animal.ts, Stock.ts)
│   └── sync.ts     # Lógica do Sync Engine (Pull & Push)
├── modules/        # Módulos isolados por negócio
│   ├── map/        # Mapas, cálculo de Talhões e Cercas
│   ├── herd/       # Gado, QR Code e Histórico
│   ├── stock/      # Inventário e Baixa de Insumos
│   ├── treatment/  # Vacinas, Antibióticos e Lembretes
│   └── machinery/  # Manutenções de Tratores
├── services/       # Clientes de API, Auth e Configurações Globais
├── utils/          # Helpers, Conversores de Hectare e Geometria
└── App.tsx         # Ponto de entrada
```

---

## 4. Fluxo de Sincronização Local-First

O comportamento de sincronização entre o aplicativo e a nuvem opera da seguinte forma:

1. **Alteração Offline:** O usuário realiza uma ação (ex: registrar plantio). O dado é salvo instantaneamente no **WatermelonDB**. A UI reflete a mudança imediatamente, sem telas de carregamento travando o uso.
2. **Monitoramento:** O `NetInfo` detecta a reconexão com a rede.
3. **Push para Nuvem:** O WatermelonDB agrega todos os registros novos/alterados em um único payload JSON e aciona um `POST /api/v1/sync/push` no **Spring Boot**. O backend valida e consolida os dados no **Supabase**.
4. **Pull da Nuvem:** O app realiza um `GET /api/v1/sync/pull?last_pulled_at=DATA` no **Spring Boot**. O servidor retorna apenas o que foi alterado por outros dispositivos desde aquela data. O WatermelonDB processa esses dados e atualiza o estado local.
