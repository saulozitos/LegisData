# Pendências de CPF: senadores e presidentes sem identificador

O CPF só entra no banco como HMAC (`CPF_HMAC`, ver `.claude/rules/etl.md`). Para o Senado, que não publica CPF, o HMAC vem do
TSE (`consulta_cand` de 1998 a 2022), ligando o **nome civil completo e a data de nascimento** ao registro de candidatura. Quando
um dos dois falta, ou quando o par não aparece como candidato no TSE, ou o par aponta para mais de um CPF, a pessoa fica sem
`CPF_HMAC` (continua ligada pelo id oficial). Esta lista existe para pesquisar essas pessoas em outras fontes depois (por exemplo
a declaração de bens de outro tribunal, ou o cadastro do Senado por nome completo).

Gerado a partir de `etl/data/processed/senadores_dados_basicos.json`, `senadores_senado.json` e
`parlamentares_legislaturas_anteriores.json` (nome completo e nascimento vêm de `/senador/{codigo}` do Senado) e do índice de
candidatos do TSE. Total de senadores conhecidos nas fontes: 703; sem CPF: 118.

## 1. Senadores sem data de nascimento no Senado (61)

O detalhe do senador no Senado não traz nascimento. Sem ele não há como ligar ao TSE sem risco de homônimo.

| Código do Senado | Nome completo | Nome parlamentar |
|---|---|---|
| 4847 | Salomão Alcolumbre Júnior | Salomão Alcolumbre Júnior |
| 5022 | Janduhy Max Freire de Andrade | Janduhy Max Freire de Andrade |
| 5024 | Gabriel Maia Gelpke | Gabriel Maia Gelpke |
| 5026 | Fernando Carvalho Lage | Fernando Carvalho Lage |
| 5028 | Armando José de Oliveira | Armando José de Oliveira |
| 5032 | Antônio Milton Pessoa Falcão Filho | Antônio Milton Pessoa Falcão Filho |
| 5034 | Fábio Luiz Araújo Lopes de Farias | Fábio Luiz Araújo Lopes de Farias |
| 5036 | José de Macedo Ferreira | José de Macedo Ferreira |
| 5040 | Lirio Albino Parisotto | Lirio Albino Parisotto |
| 5042 | Alzira Ferreira Barros | Alzira Ferreira Barros |
| 5044 | Clécio Luis Vilhena Vieira | Clécio Luis Vilhena Vieira |
| 5046 | Andrelina Barbosa da Cunha | Andrelina Barbosa da Cunha |
| 5050 | Pedro Irno Tonelli | Pedro Irno Tonelli |
| 5054 | Francisco Simeão Rodrigues Neto | Francisco Simeão Rodrigues Neto |
| 5056 | Silvia Nascimento Cardoso dos Santos Cerqueira | Silvia Nascimento Cardoso dos Santos Cerqueira |
| 5058 | Luís Guilherme Gomes Mussi | Luís Guilherme Gomes Mussi |
| 5060 | Olney Ribeiro Botelho | Olney Ribeiro Botelho |
| 5064 | Emir Simão Sader | Emir Simão Sader |
| 5066 | Juçara Feitosa de Oliveira | Juçara Feitosa de Oliveira |
| 5068 | Tânia Cristina Magalhães Bastos e Silva | Tânia Cristina Magalhães Bastos e Silva |
| 5074 | Sander Fraxe Salomao | Sander Fraxe Salomao |
| 5078 | Jose Nagib da Silva Lima | Jose Nagib da Silva Lima |
| 5080 | Pablo Sergio Souza Bezerra | Pablo Sergio Souza Bezerra |
| 5082 | Waldemir Catanho de Sena Júnior | Waldemir Catanho de Sena Júnior |
| 5084 | Veridiana Maria Tonini | Veridiana Maria Tonini |
| 5086 | Miguel Dias de Souza | Miguel Dias de Souza |
| 5088 | Gilberto Corazza | Gilberto Corazza |
| 5090 | José Alberto Wenzel | José Alberto Wenzel |
| 5092 | Luis Carlos Paes de Castro | Luis Carlos Paes de Castro |
| 5094 | Márcio Bergonsi Turra | Márcio Bergonsi Turra |
| 5096 | Wilmar Lacerda | Wilmar Lacerda |
| 5098 | Roberto Wagner Monteiro | Roberto Wagner Monteiro |
| 5104 | Luis Cláudio da Costa Avelar | Luis Cláudio da Costa Avelar |
| 5114 | Paulo Pereira Fíuza Filho | Paulo Pereira Fíuza Filho |
| 5118 | Zonir Freitas Tetila | Zonir Freitas Tetila |
| 5120 | José Antonio Guidoni | José Antonio Guidoni |
| 5122 | Paulo Antenor de Oliveira | Paulo Antenor de Oliveira |
| 5124 | Maria Antonieta Amorim dos Santos | Maria Antonieta Amorim dos Santos |
| 5126 | Enivaldo Euzébio dos Anjos | Enivaldo Euzébio dos Anjos |
| 5128 | Gino Jose Ferreira | Gino Jose Ferreira |
| 5130 | Valério Djalma Cavalcanti Marinho | Valério Djalma Cavalcanti Marinho |
| 5134 | Antônio Marcos Gavazzoni | Antônio Marcos Gavazzoni |
| 5136 | Cesar Antonio de Souza | Cesar Antonio de Souza |
| 5138 | Athos de Almeida Lopes | Athos de Almeida Lopes |
| 5142 | Marta Maria Freire da Costa | Marta Maria Freire da Costa |
| 5146 | Elaine Matozinhos Ribeiro | Elaine Matozinhos Ribeiro |
| 5148 | Elmiro Alves do Nascimento | Elmiro Alves do Nascimento |
| 5152 | Paulo Frateschi | Paulo Frateschi |
| 5154 | Abiancy Cadoso Rosa | Abiancy Cadoso Rosa |
| 5160 | Edivaldo Edilson Pantoja da Silva | Edivaldo Edilson Pantoja da Silva |
| 5162 | Félix Urano Gama de Souza | Félix Urano Gama de Souza |
| 5168 | Aristavora de Souza Santos | Aristavora de Souza Santos |
| 5170 | Agimiro Dias da Costa | Agimiro Dias da Costa |
| 5172 | Sanny Japiassú dos Santos | Sanny Japiassú dos Santos |
| 5174 | Maria de Pompeia Lins Pessoa | Maria de Pompeia Lins Pessoa |
| 5176 | Nestor Duarte Guimarães Neto | Nestor Duarte Guimarães Neto |
| 5180 | José Rodrigues da Silva | José Rodrigues da Silva |
| 5186 | João Claudino Fernandes | João Claudino Fernandes |
| 5190 | Maria Luza de Aquino Machado | Maria Luza de Aquino Machado |
| 5914 | Waldemar de Andrada Ignácio de Oliveira | Waldemar Oliveira |
| 6287 | Marcos de Souza Costa | Marcos de Souza Costa |

## 2. Senadores com nascimento, sem candidatura casada no TSE (57)

Têm nome completo e nascimento, mas o par não aparece em `consulta_cand` 1998 a 2022 (nunca candidatos nesses anos, candidatos antes de 1998 ou depois de 2022, ou nome grafado de outro modo no TSE) ou aponta para mais de um CPF.

| Código do Senado | Nome completo | Nascimento | Nome parlamentar |
|---|---|---|---|
| 2 | Alexandre Alves Costa | 1918-10-13 | Alexandre Costa |
| 5 | Arlindo Porto Neto | 1945-03-27 | Arlindo Porto |
| 6 | Paulo Alberto Artur da Tavola Moretzsonh Monteiro de Barros | 1936-01-03 | Artur da Tavola |
| 14 | Fernando Coutinho Jorge | 1939-05-30 | Coutinho Jorge |
| 15 | Darcy Ribeiro | 1922-10-26 | Darcy Ribeiro |
| 25 | Francelino Pereira dos Santos | 1921-07-02 | Francelino Pereira |
| 33 | Humberto Coutinho de Lucena | 1928-04-22 | Humberto Lucena |
| 39 | Josaphat Ramos Marinho | 1915-10-28 | Josaphat Marinho |
| 41 | José Alves do Nascimento | 1945-01-31 | José Alves |
| 48 | João França Alves | 1939-10-08 | João França |
| 49 | João da Rocha Ribeiro Dias | 1941-01-15 | João Rocha |
| 51 | Júnia Marise Azeredo Coutinho | 1945-06-21 | Junia Marise |
| 55 | Lucídio Portella Nunes | 1922-04-08 | Lucídio Portella |
| 56 | Luís Alberto Martins de Oliveira | 1947-07-02 | Luís Alberto de Oliveira |
| 58 | Lúdio Martins Coelho | 1922-09-22 | Lúdio Coelho |
| 59 | Maria Osmarina Marina Silva Vaz de Lima | 1958-02-08 | Marina Silva |
| 65 | Onofre Quinan | 1926-10-29 | Onofre Quinan |
| 67 | Pedro Franco Piva | 1934-01-06 | Pedro Piva |
| 79 | Antônio Valmir Campelo Bezerra | 1944-10-22 | Valmir Campelo |
| 80 | Vilson Pedro Kleinubing | 1944-09-09 | Vilson Kleinübing |
| 81 | Waldeck Vieira Ornelas | 1945-07-06 | Waldeck Ornelas |
| 85 | José Eduardo de Andrade Vieira | 1938-12-30 | José Eduardo |
| 96 | Djalma Marinho Muniz Falcão | 1933-12-31 | Djalma Falcão |
| 97 | Geraldo Lessa Santos | 1950-01-01 | Geraldo Lessa |
| 143 | José Carlos da Silva Júnior | 1926-06-16 | Silva Júnior |
| 150 | Nivaldo Passos Krüger | 1950-01-01 | Nivaldo Krüger |
| 154 | Clodoaldo da Silva Torres Filho | 1950-09-08 | Clodoaldo Torres |
| 156 | Ricardo Ferreira Santos | 1945-02-07 | Ricardo Santos |
| 159 | Eloi Portella Nunes Sobrinho | 1936-09-23 | Elói Portela |
| 161 | Jônice Siqueira Tristão | 1930-02-01 | Jonice Tristão |
| 162 | Benício Parente de Sampaio | 1951-03-05 | Benício Sampaio |
| 175 | Otoniel Machado Carneiro | 1939-02-17 | Otoniel Machado |
| 184 | Matusalém Gonçalves Fernandes | 1959-02-21 | Fernando Matusalém |
| 193 | José Henrique Carneiro de Loyola | 1932-10-12 | Henrique Loyola |
| 198 | Sandra Zanatta Guidi | 1948-12-28 | Sandra Guidi |
| 206 | José Antônio Totó Aires Cavalcante | 1947-08-12 | Totó Cavalcante |
| 209 | Albino Gonçalves Boaventura | 1922-11-18 | Albino Boaventura |
| 415 | Lael Vieira Varella | 1939-02-19 | Lael Varella |
| 1047 | Thelma Menezes Siqueira Campos Lourenço | 1955-08-28 | Thelma Siqueira Campos |
| 1095 | Elifas Paulo da Silva | 1945-10-25 | Paulo Elifas |
| 3371 | Fátima Cleide Rodrigues da Silva | 1963-01-03 | Fátima Cleide |
| 3552 | Eurípedes Pedro Camargo | 1950-11-09 | Eurípedes Camargo |
| 3619 | Flávio Torres | 1944-11-04 | Flávio Torres |
| 3622 | Adelmir Santana | 1945-04-19 | Adelmir Santana |
| 3652 | João Evangelista da Costa Tenório | 1943-10-25 | João Tenório |
| 4522 | Geovani Pinheiro Borges | 1953-05-16 | Geovani Borges |
| 4873 | José Eduardo Fleury Fernandes Costa | 1952-01-03 | Fleury |
| 4951 | Manoel Angelo Chagas | 1900-01-01 | Manoel Angelo Chagas |
| 5112 | José Antônio Medeiros | 1970-03-19 | José Medeiros |
| 5416 | Francisco Wilson Ribeiro | 1900-01-01 | Francisco Wilson Ribeiro |
| 5418 | Ivanci Magno | 1999-01-01 | Ivanci Magno |
| 5420 | Ubiraci Picanço | 1999-01-01 | Ubiraci Picanço |
| 5599 | Ibanes Taveira da Silva | 1969-06-27 | Pastor Ibanês |
| 5849 | Jose Amauri P. de Araújo | 1960-11-17 | José Amauri |
| 6002 | Marcos Antônio Marinho da Cunha | 1964-06-02 | Marinho Cunha |
| 6348 | Terence Lessa Lopes de Oliveira | 1983-03-20 | Terence Lessa |
| 6361 | Wander de Souza | 1967-04-25 | Wander de Souza |

## 3. Presidentes

Os presidentes vêm de `presidentes_historico.json` (arquivo curado, sem id oficial) e são ligados ao TSE pelo nome civil completo e pela data de nascimento. Dos cinco presidentes do período (nove mandatos), quatro têm `CPF_HMAC`. Fica sem CPF:

| Presidente | Nascimento no arquivo curado | Nascimento no TSE (`consulta_cand`) | Situação |
|---|---|---|---|
| Luiz Inácio Lula da Silva | 1945-10-27 | 1945-10-06 (candidaturas de 1998, 2002, 2006, 2018 e 2022) | Data divergente: o par nome + nascimento não casa, então não há CPF. |

Os demais conferem com o TSE: Fernando Henrique Cardoso (1931-06-18), Dilma Vana Rousseff (1947-12-14), Michel Miguel Elias Temer Lulia (1940-09-23) e Jair Messias Bolsonaro (1955-03-21).

Para o Lula, a biografia oficial indica 27 de outubro de 1945 e o TSE registra 6 de outubro de 1945. A decisão de qual data vale é humana: enquanto isso não for resolvida, o ETL não força o casamento (nome igual não prova a pessoa). A divergência também faz o patrimônio do Lula depender do casamento por nome e cargo nacional (`tse_core.casar_candidatos`).
