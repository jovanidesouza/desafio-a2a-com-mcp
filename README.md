# A Ponte: Central de Salas (Hill Valley Tech)

Entrega do desafio "A Ponte: um agente A2A com MCP por dentro". Um servidor MCP
em Streamable HTTP expõe as salas de reunião como tools e resource; um agente
consome esse servidor por dentro (host MCP) e se oferece ao mundo por fora
(servidor A2A), costurando o `input_required` do MRTR com a Task do A2A.

- `servidor-mcp/` — servidor MCP (porta `7301`, endpoint `/mcp`)
- `agente/` — agente A2A (porta `7300`, endpoint `/a2a` e card em `/.well-known/agent-card.json`)

## Como rodar

Requer Python 3.10+. Os comandos abaixo partem de um clone limpo do repositório.

### 1. Gerar e exportar o segredo do `requestState`

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Exporte o valor gerado (nunca o commite):

```bash
export REQUEST_STATE_SECRET="<cole aqui o valor gerado>"
```

No PowerShell (Windows): `$env:REQUEST_STATE_SECRET = "<valor>"`.

### 2. Subir o servidor MCP (porta 7301)

Em um terminal, com `REQUEST_STATE_SECRET` exportado nele:

```bash
cd servidor-mcp
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
python -m servidor_mcp.main
```

### 3. Subir o agente (porta 7300)

Em outro terminal (não precisa do `REQUEST_STATE_SECRET`, só o servidor MCP usa):

```bash
cd agente
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
python -m agente.main
```

O agente aponta para `http://localhost:7301` por padrão; use a variável `MCP_URL`
para mudar. As portas dos dois processos também são configuráveis via
`MCP_PORT` e `AGENTE_PORT`, mas o padrão já é `7301`/`7300`, como o validador espera.

### 4. Rodar o validador

Com os dois processos acima no ar (e recém-iniciados: o validador cria reservas
que mudam o resultado de uma execução para a outra):

```bash
python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301
```

## Onde a ponte acontece

Todo o cruzamento entre os dois protocolos está isolado em
[agente/src/agente/ponte.py](agente/src/agente/ponte.py):

- `_iniciar()` chama `reservar_sala` no servidor MCP; quando a resposta traz
  `resultType: "input_required"`, a função `_pausar()` é quem transforma isso em
  `TASK_STATE_INPUT_REQUIRED` — guarda o `requestState` recebido dentro de
  `task.pendencia` (nunca exposto fora do processo) e escreve a linha exata
  `alternativas: <ids>` como mensagem da Task.
- `_continuar()` é o outro lado da costura: ao receber `escolha=<valor>` para uma
  Task pausada, ela monta `inputResponses` com a mesma chave que veio em
  `inputRequests` e chama `ClienteMCP.chamar_tool(...)` de novo — gerando
  internamente **um id de JSON-RPC novo** (`_novo_id()` em
  [agente/src/agente/mcp_client.py](agente/src/agente/mcp_client.py)) — levando
  o `requestState` ecoado sem nenhuma modificação. A resposta completa vira
  `TASK_STATE_COMPLETED` (com o artifact `reserva`) ou, no caso de
  `escolha=recusar`, `TASK_STATE_CANCELED`.

Do lado do servidor, o ponto simétrico é `_retomar()` em
[servidor-mcp/src/servidor_mcp/tools.py](servidor-mcp/src/servidor_mcp/tools.py):
ele abre o `requestState` (`request_state.abrir`), ignora qualquer argumento que
o cliente tenha reenviado e reconstrói o pedido original só a partir do que foi
selado.

## Decisões técnicas

- **Integridade do `requestState`**: payload JSON (legível, a spec não exige
  sigilo) com os campos para reconstruir o pedido + `exp`, codificado em
  base64url e assinado com **HMAC-SHA256** sobre `REQUEST_STATE_SECRET`
  (`hmac.compare_digest` na verificação, para evitar timing attack). Formato:
  `v1.<payload-base64url>.<assinatura-base64url>`. Ver
  [servidor-mcp/src/servidor_mcp/request_state.py](servidor-mcp/src/servidor_mcp/request_state.py).
  Qualquer alteração de um único caractere no payload ou na assinatura invalida
  o HMAC e devolve `-32602`.
- **TTL**: 10 minutos (dentro da janela de 5–30 min pedida no enunciado).
- **Onde mora o estado**: o `requestState` não depende de nada guardado em
  memória pelo servidor MCP — tudo que é preciso para concluir o retry (tool,
  argumentos originais, alternativas calculadas, chave da elicitation) viaja
  dentro dele. É por isso que ele sobrevive a um restart do processo (testado
  manualmente: gerar o estado, matar e subir o servidor de novo, retomar com o
  mesmo `requestState` — a reserva conclui normalmente).
- **Task store do agente**: dicionário em memória (`ArmazemDeTasks` em
  [agente/src/agente/tasks.py](agente/src/agente/tasks.py)), por processo. Não
  precisa sobreviver a um restart — só o `requestState` do MCP precisa, e isso
  já é garantido pelo HMAC acima, não pelo agente.
- **Limitação real do SDK `mcp` (documentada aqui, não contornada reescrevendo o
  protocolo)**: a versão publicada mais recente do pacote `mcp` no momento desta
  entrega (`1.30.0`) não implementa o envelope MRTR deste desafio —
  `resultType`, `inputRequests` e `requestState` no nível do `CallToolResult`, e
  os códigos `-32020`/`-32021`. O `CallToolResult` real do SDK só tem `content`,
  `structuredContent` e `isError`; o recurso assíncrono mais próximo
  (`mcp.server.experimental.tasks`) é um mecanismo de polling via `tasks/result`,
  de forma e propósito diferentes do MRTR síncrono descrito aqui. Por isso o
  dispatcher JSON-RPC de `/mcp` (em
  [servidor-mcp/src/servidor_mcp/rpc.py](servidor-mcp/src/servidor_mcp/rpc.py))
  é escrito à mão, reaproveitando do SDK oficial o que de fato se aplica: os
  schemas em `schemas.py` são gerados com `pydantic` (a mesma biblioteca que o
  `mcp` usa por baixo para `inputSchema`/`outputSchema`), e a forma dos objetos
  de elicitation em `tools.py` segue `mcp.types.ElicitRequestFormParams` e
  `ElicitationCapability`.
- **Sem LLM**: o agente decide por regra fixa (`formato.py` faz o parse do
  pedido e da escolha); o mesmo pedido sempre produz o mesmo resultado.

## Saída do validador

Execução contra os dois processos recém-iniciados:

```
trace-id desta execucao: 9041a8a8ef2069443bda022e3ba5728b
procure esse valor no stderr do servidor MCP para conferir a propagacao do traceparent.

PASS 01 tools/list traz as tres tools
PASS 02 toda tool tem inputSchema de objeto
PASS 03 listar_salas devolve structuredContent e o mesmo JSON em texto
PASS 04 _meta sem protocolVersion devolve -32602 e HTTP 400
PASS 05 _meta sem clientCapabilities devolve -32602 e HTTP 400
PASS 06 tool inexistente e recusada, por -32602 ou por isError
PASS 07 resources/read de politica://uso devolve a politica
PASS 08 resources/read de URI inexistente devolve -32602
PASS 09 sala inexistente devolve isError com a mensagem exata
PASS 10 fora da janela devolve isError com a mensagem exata
PASS 11 duracao acima de 2h devolve isError com a mensagem exata
PASS 12 intervalo invertido devolve isError com a mensagem exata
PASS 13 conflito devolve input_required com inputRequests e requestState
PASS 14 a elicitation e form mode e oferece as alternativas na ordem certa
PASS 15 conflito sem a capability elicitation devolve -32021 e HTTP 400
PASS 16 retry com inputResponses e requestState conclui a reserva
PASS 17 requestState adulterado e rejeitado com -32602
PASS 18 argumentos adulterados no retry nao tomam efeito
PASS 19 recusa conclui sem reservar e sem isError
PASS 20 conflito sem alternativa possivel devolve isError com a mensagem exata

PASS 21 agent card responde 200 no well-known com JSON
PASS 22 o card declara a interface JSON-RPC com url e versao 1.0
PASS 23 o card declara a skill reservar-sala
PASS 24 SendMessage com sala livre conclui a Task
PASS 25 o artifact chama reserva e traz a versao da politica
PASS 26 GetTask devolve id, contextId e estado corrente
PASS 27 SendMessage com sala ocupada pausa a Task
PASS 28 a Task pausada lista as alternativas na ordem certa
PASS 29 escolha fora do enum mantem a Task pausada
PASS 30 a continuacao conclui a Task na sala escolhida
PASS 31 SendMessage em Task terminal e recusado
PASS 32 a recusa termina a Task em CANCELED
PASS 33 duas Tasks pausadas ao mesmo tempo concluem cada uma com a sua reserva
PASS 34 nenhuma resposta A2A carrega o requestState
PASS 35 sala inexistente termina a Task em FAILED com a mensagem da tool
PASS 36 o agente e deterministico: o mesmo pedido produz a mesma pausa

resumo: 36 passaram, 0 falharam, de 36 verificacoes
```
