import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LegisData | Plataforma de Transparência e Inteligência Política",
  description: "LegisData combate a desinformação cruzando economia, meio ambiente, votações nominais, custos de mandato (CEAP), emendas parlamentares e checagem de ficha limpa.",
  keywords: ["LegisData", "transparência pública", "política brasileira", "gastos parlamentares", "emendas", "economia", "ficha limpa"],
  authors: [{ name: "LegisData Team" }],
  openGraph: {
    title: "LegisData - Inteligência e Transparência Política",
    description: "Plataforma analítica aberta: atuação parlamentar, custos da CEAP, trilha de emendas e indicadores macroeconômicos brasileiros.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR" className="dark h-full antialiased">
      <body className="min-h-full flex flex-col bg-slate-950 text-slate-100 selection:bg-emerald-500 selection:text-black">
        {children}
      </body>
    </html>
  );
}
