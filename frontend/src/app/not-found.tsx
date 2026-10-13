import Link from "next/link";
import Header from "@/components/Header";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Header />
      <main id="main-content" className="flex-1 flex items-center justify-center px-4">
        <div className="max-w-md text-center space-y-4">
          <h1 className="text-2xl font-bold text-slate-100">Página não encontrada</h1>
          <p className="text-sm text-slate-300">O endereço acessado não existe no LegisData.</p>
          <Link
            href="/"
            className="inline-block px-4 py-2 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-200 text-sm font-semibold transition-colors"
          >
            Voltar ao painel
          </Link>
        </div>
      </main>
    </div>
  );
}
