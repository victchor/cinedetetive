import ChatApp from "@/components/ChatApp";

// O layout fica montado entre "/" e "/c/[conversaId]", então o streaming
// não é interrompido quando a primeira mensagem cria a conversa e troca a URL.
export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <ChatApp />
      {children}
    </>
  );
}
