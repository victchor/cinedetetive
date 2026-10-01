/* eslint-disable @next/next/no-img-element -- pôsteres vêm do TMDB com tamanhos variados */
import type { Candidato } from "@/lib/types";

interface Props {
  filme: Candidato;
  destaque?: boolean;
  acoes?: React.ReactNode;
}

function iniciais(titulo: string) {
  return titulo
    .split(/\s+/)
    .filter((p) => p.length > 2)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export default function MovieCard({ filme, destaque, acoes }: Props) {
  const pct = filme.confianca != null ? Math.round(filme.confianca * 100) : null;
  const original = filme.titulo_original && filme.titulo_original !== filme.titulo ? filme.titulo_original : null;

  return (
    <article
      className={`animate-rise flex gap-3 rounded-xl border bg-reel/80 p-3 ${
        destaque ? "border-marquee/50 shadow-[0_0_0_1px_rgb(242_181_68/0.15),0_8px_30px_-12px_rgb(242_181_68/0.35)]" : "border-line"
      }`}
    >
      <div className="relative aspect-[2/3] w-20 shrink-0 overflow-hidden rounded-md bg-film sm:w-24">
        {filme.poster_url ? (
          <img src={filme.poster_url} alt={`Pôster de ${filme.titulo}`} className="h-full w-full object-cover" loading="lazy" />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-1 bg-gradient-to-b from-line/60 to-film text-center">
            <span className="font-display text-2xl text-marquee/80">{iniciais(filme.titulo) || "?"}</span>
            <span className="px-1 text-[9px] uppercase tracking-widest text-muted">sem pôster</span>
          </div>
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <h3 className="font-display text-lg leading-tight text-paper">{filme.titulo}</h3>
        <p className="text-xs text-muted">
          {[original, filme.ano].filter(Boolean).join(" · ")}
          {filme.diretor && <> · dir. {filme.diretor}</>}
        </p>
        {filme.elenco && filme.elenco.length > 0 && (
          <p className="line-clamp-1 text-xs text-paper/70">{filme.elenco.slice(0, 5).join(", ")}</p>
        )}
        {filme.generos && filme.generos.length > 0 && (
          <div className="mt-0.5 flex flex-wrap gap-1">
            {filme.generos.slice(0, 3).map((g) => (
              <span key={g} className="rounded-full border border-line px-2 py-px text-[10px] text-muted">
                {g}
              </span>
            ))}
          </div>
        )}
        {pct != null && (
          <div className="mt-1 flex items-center gap-2" title="Confiança do agente neste candidato">
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-line">
              <div className="h-full rounded-full bg-marquee" style={{ width: `${Math.max(4, pct)}%` }} />
            </div>
            <span className="w-9 text-right font-mono text-[10px] text-muted">{pct}%</span>
          </div>
        )}
        {acoes && <div className="mt-auto flex flex-wrap gap-2 pt-2">{acoes}</div>}
      </div>
    </article>
  );
}
