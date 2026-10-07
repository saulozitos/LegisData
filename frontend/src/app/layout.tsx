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
          <div className="max-w-7xl mx-auto px-4 flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2 text-slate-400">
              <span className="w-2 h-2 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50" />
              <span>Dados Abertos Oficiais: TSE, Câmara dos Deputados, Senado Federal, BCB, IBGE, INPE e IPEA</span>
            </div>
            <div className="flex flex-wrap items-center justify-center gap-3">
              <p className="font-medium text-slate-300">
                LegisData © 2026. Idealizado e desenvolvido por Saulo Araujo Campos. Licenciado sob GNU AGPLv3.
              </p>
              <a
                href="https://github.com/saulozitos/LegisData"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 text-slate-300 hover:text-white transition-all text-xs font-semibold group shadow-sm"
                title="Ver código-fonte do LegisData no GitHub"
              >
                <svg
                  className="w-4 h-4 fill-current text-slate-400 group-hover:text-emerald-400 transition-colors"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    clipRule="evenodd"
                    d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                  />
                </svg>
                <span>GitHub</span>
              </a>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
