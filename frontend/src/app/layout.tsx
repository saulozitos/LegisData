import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LegisData",
  description: "Plataforma Open-Source de Transparência e Inteligência Política. Auditoria de mandatos, custos de gabinete (CEAP), emendas orçamentárias, votações nominais e indicadores macroeconômicos brasileiros.",
  keywords: ["LegisData", "transparência pública", "política brasileira", "gastos parlamentares", "emendas", "economia", "ficha limpa"],
  authors: [{ name: "Saulo Araujo Campos" }],
  openGraph: {
    title: "LegisData",
    description: "Plataforma Open-Source de Transparência e Inteligência Política.",
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
        <div className="flex-1">
          {children}
        </div>
        <footer className="border-t border-slate-900 bg-slate-950/90 py-6 text-center text-xs text-slate-400">
          <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-slate-400">
              <span className="w-2 h-2 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50" />
              <span>Dados Abertos Oficiais: TSE, Câmara dos Deputados, Senado Federal, BCB, IBGE, INPE e IPEA</span>
            </div>
            <p className="font-medium text-slate-300">
              LegisData © 2026. Idealizado e desenvolvido por Saulo Araujo Campos. Licenciado sob GNU AGPLv3.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
