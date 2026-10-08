# Política de Segurança (Security Policy) - LegisData

A segurança dos dados públicos, das informações processadas e da infraestrutura do projeto **LegisData** é tratada com máxima seriedade e prioridade. Agradecemos o apoio da comunidade de segurança e dos desenvolvedores em nos ajudar a manter o ecossistema protegido.

---

## 1. Versões Suportadas

Apenas a versão mais recente em desenvolvimento na branch principal (`main`) recebe patches ativos de segurança.

| Versão / Componente | Suportado |
| ------------------- | --------- |
| `main` (Backend)    | :white_check_mark: |
| `main` (Frontend)   | :white_check_mark: |
| Versões Legadas     | :x:                |

---

## 2. Como Reportar uma Vulnerabilidade (Divulgação Responsável)

Se você identificou uma vulnerabilidade de segurança, falha de infraestrutura ou exposição de dados no LegisData:

> [!CAUTION]
> **NÃO ABRA UMA ISSUE PÚBLICA NO GITHUB** para relatar vulnerabilidades de segurança ou credenciais expostas. O relato público coloca em risco todos os usuários e a infraestrutura antes que uma correção possa ser disponibilizada.

### Canais Privados de Comunicação

Por favor, reporte a falha de forma privada através de um dos seguintes canais:

1. **GitHub Private Vulnerability Reporting (Recomendado):**
   - Acesse a aba **Security** do repositório no GitHub.
   - Clique em **Advisories** -> **Report a vulnerability**.
   - Isso abrirá uma discussão privada e criptografada diretamente com os mantenedores.

2. **E-mail de Segurança:**
   - Envie um e-mail com os detalhes para: **`contatosauloaraujo@gmail.com`**.
   - Assunto: `[Vulnerabilidade de Segurança] Resumo do problema`.

---

## 3. Informações a Incluir no Relatório

Para nos ajudar a reproduzir e solucionar o problema o mais rápido possível, inclua no seu reporte:

- **Descrição detalhada** da vulnerabilidade e do impacto potencial.
- **Passo a passo para reprodução** ou script de Prova de Conceito (PoC).
- **Componentes afetados** (ex: API Backend, Banco de Dados Postgres, Frontend Web, Workflows de CI/CD, Imagens Docker).
- Qualquer sugestão de correção ou mitigação temporária, se disponível.

---

## 4. Nosso Processo e Prazos

- **Confirmação de recebimento:** Nos comprometemos a responder o mais rápido possível confirmando o recebimento do relatório.
- **Triagem e Avaliação:** Analisaremos o impacto e a severidade o mais rápido possível.
- **Correção:** Trabalharemos em um patch de segurança em um branch privado ou Security Advisory privado.
- **Divulgação Coordenada:** Uma vez lançado o patch, creditaremos os pesquisadores que seguiram as diretrizes de divulgação responsável no changelog do projeto.
