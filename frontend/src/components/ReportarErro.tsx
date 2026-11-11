import { useId, useState } from 'react';
import { Flag } from 'lucide-react';
import { enviarRelatoDeErro, type AlvoDoRelato } from '@/services/api';

interface ReportarErroProps {
  alvoTipo: AlvoDoRelato;
  /** Identificador do político, da votação, da proposição ou do painel consultado. */
  alvoId?: string | null;
  /** Nome legível do alvo, para a equipe achar o registro sem consulta. */
  alvoRotulo?: string | null;
  /** Parte da tela onde a pessoa viu o problema (ex.: "Histórico partidário"). */
  secao?: string | null;
  /** Texto do botão; padrão "Encontrou uma informação incorreta?". */
  rotulo?: string;
}

/** "Encontrou uma informação incorreta?" já ligado ao que a pessoa está consultando. */
export default function ReportarErro({ alvoTipo, alvoId, alvoRotulo, secao, rotulo }: ReportarErroProps) {
  const [aberto, setAberto] = useState(false);
  const [descricao, setDescricao] = useState('');
  const [contato, setContato] = useState('');
  const [isca, setIsca] = useState('');
  const [estado, setEstado] = useState<'ocioso' | 'enviando' | 'enviado' | 'erro'>('ocioso');
  const [mensagem, setMensagem] = useState<string | null>(null);
  const id = useId();

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    setEstado('enviando');
    setMensagem(null);
    try {
      const resposta = await enviarRelatoDeErro({
        alvo_tipo: alvoTipo,
        alvo_id: alvoId ?? null,
        alvo_rotulo: alvoRotulo ?? null,
        secao: secao ?? null,
        descricao: descricao.trim(),
        contato: contato.trim() || null,
        pagina: typeof window === 'undefined' ? null : window.location.href.slice(0, 500),
        website: isca || null,
      });
      setEstado('enviado');
      setMensagem(resposta.mensagem);
      setDescricao('');
      setContato('');
    } catch (erro) {
      setEstado('erro');
      setMensagem(erro instanceof Error ? erro.message : 'Não foi possível enviar o relato agora.');
    }
  };

  if (!aberto) {
    return (
      <button
        type="button"
        onClick={() => setAberto(true)}
        className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-amber-300 underline-offset-2 hover:underline"
      >
        <Flag className="w-3.5 h-3.5" aria-hidden="true" />
        {rotulo ?? 'Encontrou uma informação incorreta?'}
      </button>
    );
  }

  return (
    <form
      onSubmit={enviar}
      aria-label="Relatar informação incorreta"
      className="rounded-xl border border-amber-500/30 bg-slate-950/70 p-3 space-y-2.5 text-xs"
    >
      <p className="font-semibold text-slate-200">
        Relatar informação incorreta
        {alvoRotulo ? <span className="font-normal text-slate-400">: {alvoRotulo}</span> : null}
        {secao ? <span className="font-normal text-slate-400"> ({secao})</span> : null}
      </p>
      <div>
        <label htmlFor={`${id}-descricao`} className="block text-slate-300 mb-1">
          O que está errado e qual seria o correto?
        </label>
        <textarea
          id={`${id}-descricao`}
          value={descricao}
          onChange={(e) => setDescricao(e.target.value)}
          required
          minLength={10}
          maxLength={2000}
          rows={4}
          className="w-full rounded-lg bg-slate-900 border border-slate-700 p-2 text-slate-100 focus:outline-none focus:ring-2 focus:ring-cyan-400"
        />
        <p className="text-[11px] text-slate-400 mt-1">Se puder, cite a fonte da informação correta. Não escreva CPF.</p>
      </div>
      <div>
        <label htmlFor={`${id}-contato`} className="block text-slate-300 mb-1">
          E-mail para retorno (opcional)
        </label>
        <input
          id={`${id}-contato`}
          type="email"
          value={contato}
          onChange={(e) => setContato(e.target.value)}
          maxLength={200}
          className="w-full rounded-lg bg-slate-900 border border-slate-700 p-2 text-slate-100 focus:outline-none focus:ring-2 focus:ring-cyan-400"
        />
      </div>
      {/* campo-isca: escondido de quem usa a tela */}
      <div aria-hidden="true" style={{ position: 'absolute', left: '-10000px' }}>
        <label>
          Não preencha
          <input tabIndex={-1} autoComplete="off" value={isca} onChange={(e) => setIsca(e.target.value)} />
        </label>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="submit"
          disabled={estado === 'enviando' || descricao.trim().length < 10}
          className="px-3 py-1.5 rounded-lg bg-amber-500 text-slate-950 font-bold disabled:opacity-50"
        >
          {estado === 'enviando' ? 'Enviando...' : 'Enviar relato'}
        </button>
        <button type="button" onClick={() => setAberto(false)} className="px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300">
          Fechar
        </button>
        {mensagem && (
          <span role={estado === 'erro' ? 'alert' : 'status'} className={estado === 'erro' ? 'text-rose-300' : 'text-emerald-300'}>
            {mensagem}
          </span>
        )}
      </div>
    </form>
  );
}
