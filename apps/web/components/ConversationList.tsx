"use client";

import { useLiveQuery } from "dexie-react-hooks";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apagarConversa, db } from "@/lib/db";

interface Props {
  conversaId: string | null;
  onNavegar: () => void;
}

function quando(ts: number) {
  const dias = Math.floor((Date.now() - ts) / 86_400_000);
  if (dias === 0) return "Hoje";
  if (dias === 1) return "Ontem";
  if (dias < 7) return "Esta semana";
  if (dias < 30) return "Este mês";
  return "Mais antigas";
}

export default function ConversationList({ conversaId, onNavegar }: Props) {
  const router = useRouter();
  const conversas = useLiveQuery(() => db.conversas.orderBy("atualizada_em").reverse().toArray(), []);

  if (!conversas) return null;

  if (conversas.length === 0) {
    return <p className="px-3 py-6 text-center text-xs text-muted">Suas investigações aparecem aqui.</p>;
  }

  return (
    <nav aria-label="Conversas" className="flex flex-col gap-0.5">
      {conversas.map((c, i) => {
        const grupo = quando(c.atualizada_em);
        const mostrarGrupo = i === 0 || grupo !== quando(conversas[i - 1].atualizada_em);
        const ativa = c.id === conversaId;
        return (
          <div key={c.id}>
            {mostrarGrupo && (
              <p className="px-3 pb-1 pt-4 text-[10px] font-semibold uppercase tracking-widest text-muted/70">{grupo}</p>
            )}
            <div
              className={`group relative flex items-center rounded-lg transition ${
                ativa ? "bg-reel text-paper" : "text-paper/75 hover:bg-reel/60 hover:text-paper"
              }`}
            >
              <Link href={`/c/${c.id}`} onClick={onNavegar} className="flex min-w-0 flex-1 flex-col px-3 py-2">
                <span className="truncate text-sm">{c.titulo}</span>
                {c.status === "resolvida" && c.filme_resolvido && (
                  <span className="truncate text-[11px] text-ok/90">✔ {c.filme_resolvido.titulo}</span>
                )}
              </Link>
              <button
                onClick={async () => {
                  if (!confirm(`Apagar "${c.titulo}" deste navegador?`)) return;
                  await apagarConversa(c.id);
                  if (ativa) router.push("/");
                }}
                aria-label={`Apagar conversa ${c.titulo}`}
                className="mr-1 rounded p-1.5 text-muted opacity-0 transition hover:text-nope focus:opacity-100 group-hover:opacity-100"
              >
                <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
          </div>
        );
      })}
    </nav>
  );
}
