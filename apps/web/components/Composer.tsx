"use client";

import { useEffect, useRef, useState } from "react";
import { LIMITE_MENSAGEM } from "@/lib/use-chat";

interface Props {
  ocupado: boolean;
  placeholder: string;
  onEnviar: (texto: string) => void;
  onParar: () => void;
}

export default function Composer({ ocupado, placeholder, onEnviar, onParar }: Props) {
  const [texto, setTexto] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [texto]);

  useEffect(() => {
    if (!ocupado) ref.current?.focus();
  }, [ocupado]);

  function enviar() {
    if (ocupado || !texto.trim()) return;
    onEnviar(texto);
    setTexto("");
  }

  const restantes = LIMITE_MENSAGEM - texto.length;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        enviar();
      }}
      className="relative flex items-end gap-2 rounded-2xl border border-line bg-film p-2 transition focus-within:border-marquee/50"
    >
      <label htmlFor="mensagem" className="sr-only">
        Descreva o filme
      </label>
      <textarea
        id="mensagem"
        ref={ref}
        rows={1}
        value={texto}
        maxLength={LIMITE_MENSAGEM}
        placeholder={placeholder}
        onChange={(e) => setTexto(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            enviar();
          }
        }}
        className="max-h-[200px] flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-relaxed text-paper outline-none placeholder:text-muted/70"
      />
      {restantes < 150 && (
        <span className={`absolute -top-5 right-2 font-mono text-[10px] ${restantes < 30 ? "text-nope" : "text-muted"}`}>
          {restantes}
        </span>
      )}
      {ocupado ? (
        <button
          type="button"
          onClick={onParar}
          aria-label="Parar resposta"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-line text-paper hover:bg-reel"
        >
          <span className="block h-3 w-3 rounded-sm bg-paper" />
        </button>
      ) : (
        <button
          type="submit"
          disabled={!texto.trim()}
          aria-label="Enviar"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-marquee text-ink transition hover:bg-marquee-deep disabled:bg-line disabled:text-muted"
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2.2}>
            <path d="M12 19V5M5 12l7-7 7 7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}
    </form>
  );
}
