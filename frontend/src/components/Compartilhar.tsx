import { useState } from 'react';
import { Download, Link2 } from 'lucide-react';
import { baixarCartao, type DadosDoCartao } from '@/lib/compartilhar';

interface CompartilharProps {
  /** Endereço que abre exatamente esta consulta. */
  link: string;
  /** Dados do cartão em imagem; sem eles, só o botão de link aparece. */
  cartao?: DadosDoCartao | null;
  nomeDoArquivo?: string;
}

/** Botões para copiar o link direto da consulta e baixar um cartão em imagem com fonte, data, período e etapa. */
export default function Compartilhar({ link, cartao, nomeDoArquivo = 'legisdata' }: CompartilharProps) {
  const [aviso, setAviso] = useState<string | null>(null);

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setAviso('Link copiado.');
    } catch {
      setAviso(`Não consegui copiar sozinho. Copie o endereço: ${link}`);
    }
  };

  const baixar = async () => {
    if (!cartao) return;
    try {
      const ok = await baixarCartao(cartao, nomeDoArquivo);
      setAviso(ok ? 'Cartão baixado.' : 'Este navegador não consegue gerar a imagem.');
    } catch {
      setAviso('Não foi possível gerar o cartão: faltam dados da fonte.');
    }
  };

  return (
    <div className="flex items-center gap-2 flex-wrap text-xs">
      <button
        type="button"
        onClick={copiar}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-slate-700 bg-slate-900 text-slate-200 hover:border-cyan-400"
      >
        <Link2 className="w-3.5 h-3.5" aria-hidden="true" />
        Copiar link
      </button>
      {cartao && (
        <button
          type="button"
          onClick={baixar}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-slate-700 bg-slate-900 text-slate-200 hover:border-cyan-400"
        >
          <Download className="w-3.5 h-3.5" aria-hidden="true" />
          Baixar cartão
        </button>
      )}
      {aviso && (
        <span role="status" className="text-slate-400">
          {aviso}
        </span>
      )}
    </div>
  );
}
