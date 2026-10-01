"use client";

import { useEffect, useState } from "react";
import { ehSafari, obterSessao } from "@/lib/session";

const CHAVE = "cinedetetive:aviso-armazenamento";

/** Avisa quando o navegador pode apagar o histórico (sem storage.persist ou Safari). */
export default function StorageNotice() {
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    let dispensado = false;
    try {
      dispensado = localStorage.getItem(CHAVE) === "1";
    } catch {}
    if (dispensado) return;

    obterSessao().then((s) => {
      if (ehSafari()) {
        setAviso("O Safari apaga dados de sites que você não visita por cerca de 7 dias. Seu histórico pode sumir.");
      } else if (!s.persistente) {
        setAviso("Seu histórico fica só neste navegador e pode ser apagado se faltar espaço ou numa guia anônima.");
      }
    });
  }, []);

  if (!aviso) return null;

  return (
    <div className="mx-3 mb-2 rounded-lg border border-marquee/30 bg-marquee/10 p-2.5 text-[11px] leading-relaxed text-paper/80">
      <p>{aviso}</p>
      <button
        className="mt-1 text-marquee hover:underline"
        onClick={() => {
          try {
            localStorage.setItem(CHAVE, "1");
          } catch {}
          setAviso(null);
        }}
      >
        Entendi
      </button>
    </div>
  );
}
