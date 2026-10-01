# CineDetetive — web

Front do chat (Next.js + Tailwind + Dexie). Conversas ficam só no IndexedDB do navegador.

```bash
npm install
npm run dev   # http://localhost:3000
```

## Agente real x simulado

| `.env.local`                                   | Comportamento                                 |
| ---------------------------------------------- | --------------------------------------------- |
| `NEXT_PUBLIC_AGENT_URL=` (vazio)               | Usa `lib/mock-agent.ts` (selo "agente simulado") |
| `NEXT_PUBLIC_AGENT_URL=http://localhost:8001`  | Chama o FastAPI de `apps/agent`               |

## Contrato com o agente

Os tipos estão em [`lib/types.ts`](lib/types.ts); o agente deve devolver exatamente isto.

**`POST /v1/chat`** — corpo `ChatRequest`, resposta `text/event-stream`:

```
event: status
data: {"etapa": "Buscando sinopses"}

event: candidates
data: {"candidatos": [{"tmdb_id": 137, "titulo": "Feitiço do Tempo", "ano": 1993, ...}]}

event: clarification
data: {"pergunta": "Lembra a década?"}

event: token
data: {"texto": "Acho que é "}

event: final
data: {"filme": {...} | null, "confianca": "alta" | "media" | "baixa", "estado": {...}, "trace_id": "..."}

event: error
data: {"codigo": "tmdb_indisponivel", "mensagem": "..."}
```

- Todo turno termina com `final` ou `error`; se o stream fechar antes, o front mostra erro.
- `estado` do `final` é gravado no IndexedDB e reenviado na próxima mensagem.
- Os botões "Não é esse" / "Nenhum desses" já colocam os `tmdb_id` em `estado.excluidos`
  antes de enviar a mensagem; o agente deve apenas respeitar a lista (e deduplicar).
- "É esse!" é resolvido só no navegador (não chama o agente).

**`POST /v1/feedback`** — corpo `FeedbackRequest` (`rating` 1 ou -1, `correct_tmdb_id` opcional).

## Arquivos

- `lib/db.ts` — Dexie: stores `sessao`, `conversas`, `mensagens`
- `lib/session.ts` — `session_id` anônimo e `navigator.storage.persist()`
- `lib/agent-client.ts` — `fetch` + leitor de SSE (EventSource não faz POST)
- `lib/use-chat.ts` — envio, streaming, "não é esse", confirmar, tentar de novo
- `components/` — `ChatApp`, `ChatWindow`, `MessageBubble`, `MovieCard`, `FeedbackButtons`, `ConversationList`
