# Termo de Uso

Atenção!

API Pública do Datajud está estritamente sujeito às regras e condições estabelecidas em nosso [Termo de Uso](https://formularios.cnj.jus.br/wp-content/uploads/2023/11/Termos-de-uso-api-publica-V1.2.pdf). Além disso, reforçamos aqui algumas das responsabilidades quanto ao cosumo dos dados da API Pública:

- **1.2 O usuário manifestará tacitamente sua aceitação às condições deste termo ao utilizar a interface;**
- **3.2. O usuário da API pública se responsabiliza pelo uso da interface e das informações, pesquisas, documentos ou qualquer espécie de informação derivada de seu uso;**
- **3.3. A API é fornecida exclusivamente para fins legais, não comerciais e autorizados, sendo seu uso indevido, abusivo, ilegal, malicioso ou imoral estritamente proibido**;
- **3.6. O CNJ não garante a precisão, integridade ou atualidade dos dados fornecidos pela API;**
- **3.8. O usuário concorda em não modificar, distribuir, vender ou explorar comercialmente a API ou qualquer informação derivada dela;**
- **3.9. O usuário concorda em dar ciência ao CNJ de qualquer informação, notícia, estudo, relatório ou documento de qualquer natureza que seja disponibilizado ao público em geral.**

É importante destacar que o simples ato de consumir a API implica automaticamente na aceitação integral das cláusulas presentes no referido Termo de Uso. Recomendamos enfaticamente que todos os usuários revisem cuidadosamente o documento antes de utilizar a API para garantir a compreensão das responsabilidades, diretrizes e restrições associadas ao seu uso.

### Baixar o Termo de Uso

- [Termos-de-uso-api-publica-V1.2.pdf](https://formularios.cnj.jus.br/wp-content/uploads/2023/11/Termos-de-uso-api-publica-V1.2.pdf)

# Acesso

A API Pública do Datajud é uma ferramenta que disponibiliza ao público o acesso aos metadados dos processos públicos dos tribunais do judiciário brasileiro. Os dados disponibilizados pela API são de origem da Base Nacional de Dados do Poder Judiciário – Datajud e atendem aos critérios estabelecidos [Portaria Nº 160 de 09/09/2020](https://atos.cnj.jus.br/atos/detalhar/3453).

## API Key

A autenticação da API Pública do Datajud é realizada através de uma **Chave Pública**, gerada e disponibilizada pelo DPJ/CNJ. A chave vigente estará sempre acessível nesta seção da Wiki, garantindo transparência e facilitando seu acesso. Importante ressaltar que, por razões de segurança e gestão do sistema, a chave poderá ser alterada pelo CNJ a qualquer momento.

Para incorporar a API Key em suas requisições, utilize o formato "Authorization: APIKey [Chave Pública]" no cabeçalho da requisição.

- **APIKey atual**:
  - Authorization: APIKey **cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw==**

## Endpoints

A API Pública do Datajud oferece várias rotas para pesquisa de informações processuais devido à natureza e organização do Judiciário brasileiro. A url principal de acesso é a url `[https://api-publica.datajud.cnj.jus.br/](https://api-publica.datajud.cnj.jus.br/)` e deverá ser seguida de um aliase correspondente ao Tribunal que deseja obter os dados processuais.

**Exemplo**
O endpoint do Tribunal Regional Federal da 1ª Região é `[https://api-publica.datajud.cnj.jus.br/api_publica_trf1/](https://api-publica.datajud.cnj.jus.br/api_publica_trf1/)`.

Abaixo segue a relação de tribunais/aliases para pesquisa processual:

### Tribunais Superiores

| Tribunal                      | Url                                                          |
| ----------------------------- | ------------------------------------------------------------ |
| Tribunal Superior do Trabalho | [https://api-publica.datajud.cnj.jus.br/api_publica_tst/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tst/_search) |
| Tribunal Superior Eleitoral   | [https://api-publica.datajud.cnj.jus.br/api_publica_tse/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tse/_search) |
| Tribunal Superior de Justiça  | [https://api-publica.datajud.cnj.jus.br/api_publica_stj/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_stj/_search) |
| Tribunal Superior Militar     | [https://api-publica.datajud.cnj.jus.br/api_publica_stm/_search](https://api-publica.datajud.cnj.jus.br/api_publica_stm/_search) |

### Justiça Federal

| Tribunal                               | Url                                                          |
| -------------------------------------- | ------------------------------------------------------------ |
| Tribunal Regional Federal da 1ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trf1/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trf1/_search) |
| Tribunal Regional Federal da 2ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trf2/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trf2/_search) |
| Tribunal Regional Federal da 3ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trf3/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trf3/_search) |
| Tribunal Regional Federal da 4ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trf4/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trf4/_search) |
| Tribunal Regional Federal da 5ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trf5/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trf5/_search) |
| Tribunal Regional Federal da 6ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trf6/_search](https://api-publica.datajud.cnj.jus.br/api_publica_trf6/_search) |

### Justiça Estadual

| Tribunal                                 | Url                                                          |
| ---------------------------------------- | ------------------------------------------------------------ |
| Tribunal de Justiça do Acre              | [https://api-publica.datajud.cnj.jus.br/api_publica_tjac/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjac/_search) |
| Tribunal de Justiça de Alagoas           | [https://api-publica.datajud.cnj.jus.br/api_publica_tjal/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjal/_search) |
| Tribunal de Justiça do Amazonas          | [https://api-publica.datajud.cnj.jus.br/api_publica_tjam/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjam/_search) |
| Tribunal de Justiça do Amapá             | [https://api-publica.datajud.cnj.jus.br/api_publica_tjap/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjap/_search) |
| Tribunal de Justiça da Bahia             | [https://api-publica.datajud.cnj.jus.br/api_publica_tjba/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjba/_search) |
| Tribunal de Justiça do Ceará             | [https://api-publica.datajud.cnj.jus.br/api_publica_tjce/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjce/_search) |
| TJ do Distrito Federal e Territórios     | [https://api-publica.datajud.cnj.jus.br/api_publica_tjdft/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjdft/_search) |
| Tribunal de Justiça do Espírito Santo    | [https://api-publica.datajud.cnj.jus.br/api_publica_tjes/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjes/_search) |
| Tribunal de Justiça do Goiás             | [https://api-publica.datajud.cnj.jus.br/api_publica_tjgo/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjgo/_search) |
| Tribunal de Justiça do Maranhão          | [https://api-publica.datajud.cnj.jus.br/api_publica_tjma/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjma/_search) |
| Tribunal de Justiça de Minas Gerais      | [https://api-publica.datajud.cnj.jus.br/api_publica_tjmg/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjmg/_search) |
| TJ do Mato Grosso de Sul                 | [https://api-publica.datajud.cnj.jus.br/api_publica_tjms/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjms/_search) |
| Tribunal de Justiça do Mato Grosso       | [https://api-publica.datajud.cnj.jus.br/api_publica_tjmt/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjmt/_search) |
| Tribunal de Justiça do Pará              | [https://api-publica.datajud.cnj.jus.br/api_publica_tjpa/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjpa/_search) |
| Tribunal de Justiça da Paraíba           | [https://api-publica.datajud.cnj.jus.br/api_publica_tjpb/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjpb/_search) |
| Tribunal de Justiça de Pernambuco        | [https://api-publica.datajud.cnj.jus.br/api_publica_tjpe/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjpe/_search) |
| Tribunal de Justiça do Piauí             | [https://api-publica.datajud.cnj.jus.br/api_publica_tjpi/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjpi/_search) |
| Tribunal de Justiça do Paraná            | [https://api-publica.datajud.cnj.jus.br/api_publica_tjpr/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjpr/_search) |
| Tribunal de Justiça do Rio de Janeiro    | [https://api-publica.datajud.cnj.jus.br/api_publica_tjrj/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjrj/_search) |
| TJ do Rio Grande do Norte                | [https://api-publica.datajud.cnj.jus.br/api_publica_tjrn/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjrn/_search) |
| Tribunal de Justiça de Rondônia          | [https://api-publica.datajud.cnj.jus.br/api_publica_tjro/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjro/_search) |
| Tribunal de Justiça de Roraima           | [https://api-publica.datajud.cnj.jus.br/api_publica_tjrr/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjrr/_search) |
| Tribunal de Justiça do Rio Grande do Sul | [https://api-publica.datajud.cnj.jus.br/api_publica_tjrs/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjrs/_search) |
| Tribunal de Justiça de Santa Catarina    | [https://api-publica.datajud.cnj.jus.br/api_publica_tjsc/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjsc/_search) |
| Tribunal de Justiça de Sergipe           | [https://api-publica.datajud.cnj.jus.br/api_publica_tjse/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjse/_search) |
| Tribunal de Justiça de São Paulo         | [https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search) |
| Tribunal de Justiça do Tocantins         | [https://api-publica.datajud.cnj.jus.br/api_publica_tjto/_search](https://api-publica.datajud.cnj.jus.br/api_publica_tjto/_search) |

### Justiça do Trabalho

| Tribunal                                    | Url                                                          |
| ------------------------------------------- | ------------------------------------------------------------ |
| Tribunal Regional do Trabalho da 1ª Região  | [https://api-publica.datajud.cnj.jus.br/api_publica_trt1/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt1/_search) |
| Tribunal Regional do Trabalho da 2ª Região  | [https://api-publica.datajud.cnj.jus.br/api_publica_trt2/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt2/_search) |
| Tribunal Regional do Trabalho da 3ª Região  | [https://api-publica.datajud.cnj.jus.br/api_publica_trt3/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt3/_search) |
| Tribunal Regional do Trabalho da 4ª Região  | [https://api-publica.datajud.cnj.jus.br/api_publica_trt4/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt4/_search) |
| Tribunal Regional do Trabalho da 5ª Região  | [https://api-publica.datajud.cnj.jus.br/api_publica_trt5/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt5/_search) |
| Tribunal Regional do Trabalho da 6ª Região  | [https://api-publica.datajud.cnj.jus.br/api_publica_trt6/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt6/_search) |
| Tribunal Regional do Trabalho da 7ª Região  | [https://api-publica.datajud.cnj.jus.br/api_publica_trt7/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt7/_search) |
| Tribunal Regional do Trabalho da 8ª Região  | [https://api-publica.datajud.cnj.jus.br/api_publica_trt8/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt8/_search) |
| Tribunal Regional do Trabalho da 9ª Região  | [https://api-publica.datajud.cnj.jus.br/api_publica_trt9/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt9/_search) |
| Tribunal Regional do Trabalho da 10ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt10/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt10/_search) |
| Tribunal Regional do Trabalho da 11ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt11/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt11/_search) |
| Tribunal Regional do Trabalho da 12ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt12/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt12/_search) |
| Tribunal Regional do Trabalho da 13ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt13/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt13/_search) |
| Tribunal Regional do Trabalho da 14ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt14/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt14/_search) |
| Tribunal Regional do Trabalho da 15ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt15/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt15/_search) |
| Tribunal Regional do Trabalho da 16ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt16/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt16/_search) |
| Tribunal Regional do Trabalho da 17ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt17/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt17/_search) |
| Tribunal Regional do Trabalho da 18ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt18/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt18/_search) |
| Tribunal Regional do Trabalho da 19ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt19/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt19/_search) |
| Tribunal Regional do Trabalho da 20ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt20/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt20/_search) |
| Tribunal Regional do Trabalho da 21ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt21/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt21/_search) |
| Tribunal Regional do Trabalho da 22ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt22/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt22/_search) |
| Tribunal Regional do Trabalho da 23ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt23/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_trt23/_search) |
| Tribunal Regional do Trabalho da 24ª Região | [https://api-publica.datajud.cnj.jus.br/api_publica_trt24/_search](https://api-publica.datajud.cnj.jus.br/api_publica_trt24/_search) |

### Justiça Eleitoral

| Tribunal                                           | Url                                                          |
| -------------------------------------------------- | ------------------------------------------------------------ |
| Tribunal Regional Eleitoral do Acre                | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-ac/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-ac/_search) |
| Tribunal Regional Eleitoral de Alagoas             | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-al/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-al/_search) |
| Tribunal Regional Eleitoral do Amazonas            | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-am/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-am/_search) |
| Tribunal Regional Eleitoral do Amapá               | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-ap/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-ap/_search) |
| Tribunal de Justiça da Bahia                       | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-ba/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-ba/_search) |
| Tribunal Regional Eleitoral do Ceará               | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-ce/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-ce/_search) |
| Tribunal Regional Eleitoral do Distrito Federal    | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-dft/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-dft/_search) |
| Tribunal Regional Eleitoral do Espírito Santo      | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-es/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-es/_search) |
| Tribunal Regional Eleitoral do Goiás               | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-go/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-go/_search) |
| Tribunal Regional Eleitoral do Maranhão            | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-ma/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-ma/_search) |
| Tribunal Regional Eleitoral de Minas Gerais        | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-mg/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-mg/_search) |
| Tribunal Regional Eleitoral do Mato Grosso de Sul  | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-ms/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-ms/_search) |
| Tribunal Regional Eleitoral do Mato Grosso         | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-mt/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-mt/_search) |
| Tribunal Regional Eleitoral do Pará                | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-pa/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-pa/_search) |
| Tribunal Regional Eleitoral da Paraíba             | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-pb/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-pb/_search) |
| Tribunal Regional Eleitoral de Pernambuco          | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-pe/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-pe/_search) |
| Tribunal Regional Eleitoral do Piauí               | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-pi/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-pi/_search) |
| Tribunal Regional Eleitoral do Paraná              | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-pr/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-pr/_search) |
| Tribunal Regional Eleitoral do Rio de Janeiro      | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-rj/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-rj/_search) |
| Tribunal Regional Eleitoral do Rio Grande do Norte | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-rn/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-rn/_search) |
| Tribunal Regional Eleitoral de Rondônia            | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-ro/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-ro/_search) |
| Tribunal Regional Eleitoral de Roraima             | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-rr/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-rr/_search) |
| Tribunal Regional Eleitoral do Rio Grande do Sul   | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-rs/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-rs/_search) |
| Tribunal Regional Eleitoral de Santa Catarina      | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-sc/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-sc/_search) |
| Tribunal Regional Eleitoral de Sergipe             | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-se/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-se/_search) |
| Tribunal Regional Eleitoral de São Paulo           | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-sp/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tre-sp/_search) |
| Tribunal Regional Eleitoral do Tocantins           | [https://api-publica.datajud.cnj.jus.br/api_publica_tre-to/_search](https://api-publica.datajud.cnj.jus.br/api_publica_tre-to/_search) |

### Justiça Militar

| Tribunal                                      | Url                                                          |
| --------------------------------------------- | ------------------------------------------------------------ |
| Tribunal Justiça Militar de Minas Gerais      | [https://api-publica.datajud.cnj.jus.br/api_publica_tjmmg/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjmmg/_search) |
| Tribunal Justiça Militar do Rio Grande do Sul | [https://api-publica.datajud.cnj.jus.br/api_publica_tjmrs/_search](https://www.google.com/search?q=https://api-publica.datajud.cnj.jus.br/api_publica_tjmrs/_search) |
| Tribunal Justiça Militar de São Paulo         | [https://api-publica.datajud.cnj.jus.br/api_publica_tjmsp/_search](https://api-publica.datajud.cnj.jus.br/api_publica_tjmsp/_search) |

# Exemplos

As possibilidades de pesquisas na API Pública não estão restritas apenas aos exemplos aba seguir. Para a obtenção de resultados mais satisfatórios em suas pesquisas, recomenda-se a utilização dos diversos atributos dos metadados processuais listados no [Glossário de Dados](https://datajud-wiki.cnj.jus.br/api-publica/glossario) desta wiki.

# Ex. 1 - Pesquisar pelo número de processo

No exemplo abaixo é realizada a consulta de um processo judicial utilizando a **numeração única do processo** como parâmetro de pesquisa no tribunal do TRF1.

## POST /api_publica_tribunal/_search

- Postman
- Python
- R

Python com Requests

```python
import requests
import json

url = "https://api-publica.datajud.cnj.jus.br/api_publica_trf1/_search"

payload = json.dumps({
  "query": {
    "match": {
      "numeroProcesso": "00008323520184013202"
    }
  }
})

#Substituir <API Key> pela Chave Pública
headers = {
  'Authorization': 'ApiKey <API Key>',
  'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)
```



## Resposta

A resposta esperado é um JSON com os metadados de 1 ou mais processos conforme o critério da busca:

JSON com os metadados processuais

```json
{
    "took": 6679,
    "timed_out": false,
    "_shards": {
        "total": 7,
        "successful": 7,
        "skipped": 0,
        "failed": 0
    },
    "hits": {
        "total": {
            "value": 1,
            "relation": "eq"
        },
        "max_score": 13.917725,
        "hits": [
            {
                "_index": "api_publica_trf1",
                "_type": "_doc",
                "_id": "TRF1_436_JE_16403_00008323520184013202",
                "_score": 13.917725,
                "_source": {
                    "numeroProcesso": "00008323520184013202",
                    "classe": {
                        "codigo": 436,
                        "nome": "Procedimento do Juizado Especial Cível"
                    },
                    "sistema": {
                        "codigo": 1,
                        "nome": "Pje"
                    },
                    "formato": {
                        "codigo": 1,
                        "nome": "Eletrônico"
                    },
                    "tribunal": "TRF1",
                    "dataHoraUltimaAtualizacao": "2023-07-21T19:10:08.483Z",
                    "grau": "JE",
                    "@timestamp": "2023-08-14T11:50:51.994Z",
                    "dataAjuizamento": "2018-10-29T00:00:00.000Z",
                    "movimentos": [
                        {
                            "complementosTabelados": [
                                {
                                    "codigo": 2,
                                    "valor": 1,
                                    "nome": "competência exclusiva",
                                    "descricao": "tipo_de_distribuicao_redistribuicao"
                                }
                            ],
                            "codigo": 26,
                            "nome": "Distribuição",
                            "dataHora": "2018-10-30T14:06:24.000Z"
                        },
                        ...
                        {
                            "codigo": 14732,
                            "nome": "Conversão de Autos Físicos em Eletrônicos",
                            "dataHora": "2020-08-05T01:15:18.000Z"
                        }
                    ],
                    "id": "TRF1_436_JE_16403_00008323520184013202",
                    "nivelSigilo": 0,
                    "orgaoJulgador": {
                        "codigoMunicipioIBGE": 5128,
                        "codigo": 16403,
                        "nome": "JEF Adj - Tefé"
                    },
                    "assuntos": [
                        {
                            "codigo": 6177,
                            "nome": "Concessão"
                        }
                    ]
                }
            }
        ]
    }
}
```

# Ex. 2 - Pesquisar por Classe Processual e Órgão Julgador

No exemplo abaixo é realizada a consulta de processos que possuam a Classe Processual **1116 – "Execução Fiscal"** do Órgão Julgador **13597 - VARA DE EXECUÇÃO FISCAL DO DF** no tribunal **TJDFT**.

## POST /api_publica_tribunal/_search

- Postman
- Python
- R

Python com Requests

```python
import requests
import json

url = "https://api-publica.datajud.cnj.jus.br/api_publica_tjdft/_search"

payload = json.dumps({
    "query": {
        "bool": {
            "must": [
                {"match": {"classe.codigo": 1116}},
                {"match": {"orgaoJulgador.codigo": 13597}}
            ]
        }
    }
}
)

#Substituir <API Key> pela Chave Pública
headers = {
  'Authorization': 'ApiKey <API Key>',
  'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)
```



## Resposta

A resposta esperado é um JSON com os metadados de 1 ou mais processos conforme o critério da busca:

JSON com os metadados processuais

```json
{
    "took": 213,
    "timed_out": false,
    "_shards": {
        "total": 3,
        "successful": 3,
        "skipped": 0,
        "failed": 0
    },
    "hits": {
        "total": {
            "value": 10000,
            "relation": "gte"
        },
        "max_score": 2.0,
        "hits": [
            {
                "_index": "api_publica_tjdft",
                "_type": "_doc",
                "_id": "TJDFT_1116_G1_13597_07223914020178070001",
                "_score": 2.0,
                "_source": {
                    "classe": {
                        "codigo": 1116,
                        "nome": "Execução Fiscal"
                    },
                    "numeroProcesso": "07223914020178070001",
                    "sistema": {
                        "codigo": 1,
                        "nome": "Pje"
                    },
                    "formato": {
                        "codigo": 1,
                        "nome": "Eletrônico"
                    },
                    "tribunal": "TJDFT",
                    "dataHoraUltimaAtualizacao": "2022-09-06T12:03:20.257Z",
                    "grau": "G1",
                    "@timestamp": "2023-04-13T17:59:46.214Z",
                    "dataAjuizamento": "2017-08-21T10:05:32.000Z",
                    "movimentos": [
                        {
                            "complementosTabelados": [
                                {
                                    "codigo": 2,
                                    "valor": 2,
                                    "nome": "sorteio",
                                    "descricao": "tipo_de_distribuicao_redistribuicao"
                                }
                            ],
                            "codigo": 26,
                            "nome": "Distribuição",
                            "dataHora": "2017-08-21T10:05:32.000Z"
                        },
                        ...
                        {
                            "codigo": 11382,
                            "nome": "Bloqueio/penhora on line",
                            "dataHora": "2022-07-13T07:25:59.000Z"
                        },
                        {
                            "codigo": 132,
                            "nome": "Recebimento",
                            "dataHora": "2022-07-13T07:26:00.000Z"
                        }
                    ],
                    "id": "TJDFT_1116_G1_13597_07223914020178070001",
                    "nivelSigilo": 0,
                    "orgaoJulgador": {
                        "codigoMunicipioIBGE": 5300108,
                        "codigo": 13597,
                        "nome": "VARA DE EXECU??O FISCAL DO DF"
                    },
                    "assuntos": [
                        [
                            {
                                "codigo": 6017,
                                "nome": "Dívida Ativa (Execução Fiscal)"
                            }
                        ]
                    ]
                }
            },
            {
                "_index": "api_publica_tjdft",
                "_type": "_doc",
                "_id": "TJDFT_1116_G1_13597_00073039720138070015",
                "_score": 2.0,
                "_source": {
                    "classe": {
                        "codigo": 1116,
                        "nome": "Execução Fiscal"
                    },
                    "numeroProcesso": "00073039720138070015",
                    "sistema": {
                        "codigo": 1,
                        "nome": "Pje"
                    },
                    "formato": {
                        "codigo": 1,
                        "nome": "Eletrônico"
                    },
                    "tribunal": "TJDFT",
                    "dataHoraUltimaAtualizacao": "2022-09-06T17:26:23.938Z",
                    "grau": "G1",
                    "@timestamp": "2023-04-13T18:02:23.754Z",
                    "dataAjuizamento": "2019-05-30T03:17:56.000Z",
                    "movimentos": [
                        {
                            "complementosTabelados": [
                                {
                                    "codigo": 2,
                                    "valor": 1,
                                    "nome": "competência exclusiva",
                                    "descricao": "tipo_de_distribuicao_redistribuicao"
                                }
                            ],
                            "codigo": 26,
                            "nome": "Distribuição",
                            "dataHora": "2013-02-18T13:17:23.000Z"
                        },
                        ...
                        {
                            "codigo": 245,
                            "nome": "Provisório",
                            "dataHora": "2019-05-30T11:10:02.000Z"
                        }
                    ],
                    "id": "TJDFT_1116_G1_13597_00073039720138070015",
                    "nivelSigilo": 0,
                    "orgaoJulgador": {
                        "codigoMunicipioIBGE": 5300108,
                        "codigo": 13597,
                        "nome": "VARA DE EXECU??O FISCAL DO DF"
                    },
                    "assuntos": [
                        [
                            {
                                "codigo": 6017,
                                "nome": "Dívida Ativa (Execução Fiscal)"
                            }
                        ],
                        [
                            {
                                "codigo": 10394,
                                "nome": "Dívida Ativa não-tributária"
                            }
                        ]
                    ]
                }
            }
            ...
        ]
    }
}
```

# Ex. 3 - Exemplo 3: Pesquisa com paginação (search_after):

Por padrão, as pesquisas na API do Elasticsearch retornam até 10 registros por solicitação. No entanto, é possível aumentar o número de registros retornados utilizando o parâmetro "size" de paginação dos registros. Esse parâmetro permite especificar quantos resultados devem ser retornados por página, variando de 10 até 10.000 registros por página.

Quando se tem uma necessidade de percorrer uma maior quantidade de resultados, é possível fazer uso do recurso "search_after". Esse recurso é prioritariamente recomendado para paginação de dados, pois permite que a API do Datajud continue a partir do ponto onde a última página parou, sem a necessidade de recarregar todos os resultados a cada nova página. O "search_after" é um ponteiro que aponta para o último registro retornado na página anterior e pode ser informado como parâmetro para a próxima solicitação, permitindo que a API retorne os resultados seguintes.

É importante ressaltar que a utilização do "search_after" não prejudica a performance da API na busca de grandes volumes de dados, pois permite que a API do Datajud execute consultas de forma mais eficiente, sem a necessidade de recarregar todos os resultados em cada página. Combinando o uso do parâmetro "size" com o "search_after", é possível percorrer grandes volumes de dados de forma eficiente e com baixo impacto no desempenho da API.

Para paginar os resultados utilizando o search_after, é necessário a utilização da ordenação (sort) dos dados utilizando o atributo **“@timestamp”** conforme exemplo abaixo:

Query DSL

```json
{
 "size": 100,
 "query": {
 "bool": {
 "must": [
  {"match": {"classe.codigo": 1116}},
  {"match": {"orgaoJulgador.codigo": 13597}}
 ]
 }
},
"sort": [
{
 "@timestamp": {
 "order": "asc"
  }
 }
 ]
}
```



Após a primeira consulta, a resposta da API incluirá um array chamado "sort" que contém os valores do campo de ordenação para cada documento retornado. Esse array pode ser utilizado como o valor do parâmetro "search_after" na próxima consulta, juntamente com o parâmetro "size" que define a quantidade de documentos a serem retornados na próxima página

Query DSL

```json
{
  "_index" : "api_publica_tjdft",
  "_type" : "_doc",
  "_id" : "TJDFT_1116_G1_13597_00356079220168070018",
  "_score" : null,
  "_source" : {...},
  "sort" : [
     1681366085550
  ]
}
```



Para buscar os próximos 100 processos, basta adicionar o parâmetro "search_after" na próxima consulta, utilizando o valor do campo “sort” do último documento retornado na página anterior conforme exemplo abaixo:

Query DSL

```json
{
  "size": 100,
  "query": {
  "bool": {
    "must": [
     {"match": {"classe.codigo": 1116}},
     {"match": {"orgaoJulgador.codigo": 13597}}
  ]
}
},
 "sort": [
 {
  "@timestamp": {
  "order": "asc"
  }
  }
],
  "search_after": [ 1681366085550 ]
}
```



Observe que o valor do campo "search_after" é um array com os valores do campo de ordenação para o último documento retornado na página anterior. É importante lembrar que o "search_after" deve ser utilizado em conjunto com o "sort" e o "size" para garantir uma paginação eficiente dos resultados.



# Glossário de Dados

O glossário de dados da API Pública do Datajud oferece de maneira detalhada os termos, conceitos e estruturas de dados específicos dessa API. A compreensão desse glossário é essencial para otimizar suas consultas, pois ele oferece uma referência sobre como os dados estão organizados e como podem ser acessados. Isso não só agiliza suas pesquisas, mas também garante a precisão e relevância dos resultados obtidos.

Portanto, recomendamos enfaticamente a exploração e compreensão do glossário como um passo essencial para aproveitar plenamente os recursos da API.

| Atributos                                      | Tipo          | Descrição                                                    |
| ---------------------------------------------- | ------------- | ------------------------------------------------------------ |
| **id**                                         | text/keyword  | Identificador da origem do processo no Datajud - Chave **Tribunal_Classe_Grau_OrgaoJulgador_NumeroProcesso** |
| **tribunal**                                   | text/keyword  | Identificação do Tribunal pela sigla                         |
| **numeroProcesso**                             | text/keyword  | Numeração Única (CNJ) do processo sem formatação             |
| **dataAjuizamento**                            | datetime      | Data de ajuizamento da capa do processo                      |
| **grau**                                       | text/keyword  | Identificação do instância/grau (G1, G2, JE, etc...)         |
| **nivelSigilo**                                | long          | Nível de sigilo                                              |
| **formato**                                    | **object{}**  | **Identificação de processo Físico ou Eletrônico**           |
| **formato.codigo**                             | long          | Código de identificação do formato do processo               |
| **formato.nome**                               | text/keyword  | Identificação se é Físico ou Eletrônico                      |
| **sistema**                                    | **object{}**  | **Sistema processual de origem do processo no Tribunal**     |
| **sistema.codigo**                             | long          | Código do sistema processual                                 |
| **sistema.nome**                               | text/keyword  | Descrição do sistema processual                              |
| **classe**                                     | **object{}**  | **Classe Processual conforme TPU**                           |
| **classe.codigo**                              | long          | Código da classe processual                                  |
| **classe.nome**                                | text/keyword  | Descrição da classe processual                               |
| **assuntos**                                   | **array []**  | **Assuntos do Processo conforme TPU**                        |
| **assuntos.codigo**                            | **long**      | Código do assunto                                            |
| **assuntos.nome**                              | text/keyword  | Descrição do assunto                                         |
| **orgaoJulgador**                              | **object {}** | **Órgão Julgador**                                           |
| **orgaoJulgador.codigo**                       | long          | Código da serventia/vara atual do processo                   |
| **orgaoJulgador.nome**                         | text/keyword  | Nome da serventia/vara                                       |
| **orgaoJulgador.codigoMunicipioIBGE**          | long          | Identificação do município pelo código do IBGE               |
| **movimentos**                                 | **array []**  | **Movimentos Processuais**                                   |
| **movimentos.codigo**                          | long          | Código da movimentação processual conforme TPU               |
| **movimentos.nome**                            | text/keyword  | Descrição da movimentação                                    |
| **movimentos.dataHora**                        | datetime      | Data e hora da ocorrência de movimentação                    |
| **movimentos.complementosTabelados**           | **array []**  | **Lista de complementos tabelados daquela movimentação**     |
| **movimentos.complementosTabelados.codigo**    | long          | Código da variável de movimento tabelado                     |
| **movimentos.complementosTabelados.descricao** | text/keyword  | Descrição da variável do movimento tabelado                  |
| **movimentos.complementosTabelados.valor**     | long          | Código do complemento tabelado                               |
| **movimentos.complementosTabelados.nome**      | text/keyword  | Descrição do complemento tabelado                            |
| **movimentos.orgaoJulgador**                   | object {}**   | **Órgão julgador do movimento**                              |
| **movimentos.orgaoJulgador.codigoOrgao**       | long          | Código da serventia/vara do movimento                        |
| **movimentos.orgaoJulgador.nomeOrgao**         | text/keyword  | Nome da serventia/vara                                       |

Os atributos abaixo são utilizados para controle interno da aplicação:

| Atributos                     | Tipo     | Descrição                                                   |
| ----------------------------- | -------- | ----------------------------------------------------------- |
| **dataHoraUltimaAtualizacao** | datetime | Milisegundos do atributo *millisInsercao* da origem do dado |
| **@timestamp**                | datetime | *Timestamp* da atualização do documento no índice           |

# Considerações Finais

A API Pública do Datajud suporta parâmetros de buscas e agregações no padrão do Elasticsearch, tornando a busca de dados mais eficiente e precisa. Para mais detalhes sobre como utilizar esses recursos, é possível consultar o guia [Search your data | Elasticsearch Guide](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-your-data.html).

A versão atual da API está em fase Beta de testes, e permite o acesso público aos metadados de processos judiciais em todo o Brasil. Os dados fornecidos pela API são provenientes da **Base Nacional de Dados do Poder Judiciário (Datajud)**, mas com a devida proteção aos processos sigilosos e dados de partes.

Desenvolvedores e pesquisadores podem utilizar a API para acessar informações de capas processuais e movimentações relacionadas a processos judiciais em todas as instâncias do Judiciário brasileiro. Os dados disponibilizados podem ser utilizados para diversas finalidades, tais como pesquisas acadêmicas, desenvolvimento de aplicativos que facilitem o acesso à informação jurídica, observando os critérios estabelecidos no [Termo de Uso](https://datajud-wiki.cnj.jus.br/api-publica/termo-uso).