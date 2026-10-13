/**
 * Schemas de validação em runtime via Zod para as respostas da API Oficial do LegisData.
 * Garante tipagem estrita e rejeita dados corrompidos ou mal formatados antes da renderização.
 */

import { z } from "zod";

export const PoliticianItemSchema = z.object({
  id: z.string(),
  nome_eleitoral: z.string(),
  nome_civil: z.string(),
  partido_sigla: z.string(),
  cargo: z.string(),
  uf: z.string(),
  foto_url: z.string().nullable().optional(),
});

export const PoliticiansSearchResponseSchema = z.object({
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
  politicos: z.array(PoliticianItemSchema),
});

export const PresidentialMandateListItemSchema = z.object({
  id: z.string(),
  nome: z.string(),
  partido: z.string(),
  inicio: z.string(),
  fim: z.string().nullable(),
  foto_url: z.string().nullable().optional(),
});

export const StateTransferItemSchema = z.object({
  uf: z.string(),
  estado_nome: z.string(),
  regiao: z.string(),
  area_tematica: z.string(),
  valor_pago_brl: z.number(),
  populacao_estimada: z.number().nullable().optional(),
  valor_per_capita_brl: z.number().nullable().optional(),
});

export const FederalTransfersResponseSchema = z.object({
  mandato_id: z.string(),
  periodo: z.string(),
  periodo_inicio: z.string().nullable().optional(),
  periodo_fim: z.string().nullable().optional(),
  meses_cobertos: z.number().nullable().optional(),
  cobertura_parcial: z.boolean().nullable().optional(),
  total_repassado_brl: z.number(),
  areas_resumo: z.record(z.string(), z.number()),
  regioes_resumo: z.record(z.string(), z.number()),
  por_uf: z.array(StateTransferItemSchema),
});

export const EmendasResumoSchema = z.object({
  estatisticas_gerais: z.object({
    total_emendas: z.number(),
    total_reservado_empenhado_brl: z.number(),
    total_entregue_pago_brl: z.number(),
    taxa_execucao_pago_pct: z.number(),
  }),
  por_tipo_autor: z.record(
    z.string(),
    z.object({
      total_empenhado: z.number(),
      total_pago: z.number(),
      quantidade: z.number(),
      categoria: z.string(),
      icone: z.string(),
      descricao: z.string(),
    })
  ),
  por_area_tematica: z.array(
    z.object({
      area: z.string(),
      rotulo: z.string(),
      icone: z.string(),
      total_empenhado: z.number(),
      total_pago: z.number(),
      quantidade: z.number(),
    })
  ),
  por_ano: z.record(z.string(), z.object({ total_empenhado: z.number(), total_pago: z.number(), quantidade: z.number() })),
  top_ufs: z.array(z.object({ uf: z.string(), total_empenhado: z.number(), total_pago: z.number(), quantidade: z.number() })),
  dicionario: z.any(),
});

/**
 * Validador genérico que garante conformidade em runtime
 */
export function validateResponse<T>(schema: z.ZodType<T>, data: unknown, contextName = "API Response"): T {
  const result = schema.safeParse(data);
  if (!result.success) {
    console.error(`[Zod ValidationError] Falha de validação em ${contextName}:`, result.error.format());
    throw new Error(`Dados inválidos retornados pela API (${contextName})`);
  }
  return result.data;
}
