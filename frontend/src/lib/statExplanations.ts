// Dicionário completo de siglas e métricas estatísticas da NFL
// Traduz siglas (EPA, CPOE, aDOT, WOPR, RYBC, RYAC, YAC, PROE, RZ, EWM, Box Count, etc.)
// e oferece explicações pedagógicas em português acessíveis para qualquer usuário.

export const STAT_NAMES: Record<string, string> = {
  // === PASSING (QUARTERBACK) ===
  "passing_yards_avg_3": "Jardas de Passe (Média dos Últimos 3 Jogos)",
  "passing_yards_avg_5": "Jardas de Passe (Média dos Últimos 5 Jogos)",
  "passing_yards_avg_10": "Jardas de Passe (Média dos Últimos 10 Jogos)",
  "passing_yards_season_avg": "Jardas de Passe (Média da Temporada)",
  "passing_yards_shrunk_season_avg": "Jardas de Passe (Média Estabilizada Bayesiana)",
  "passing_yards_std_5": "Desvio Padrão de Jardas de Passe (Consistência nos Últimos 5 Jogos)",
  "attempts_avg_3": "Passes Tentados (Média dos Últimos 3 Jogos)",
  "attempts_avg_5": "Passes Tentados (Média dos Últimos 5 Jogos)",
  "attempts_avg_10": "Passes Tentados (Média dos Últimos 10 Jogos)",
  "attempts_season_avg": "Passes Tentados (Média da Temporada)",
  "completions_avg_3": "Passes Completados (Média dos Últimos 3 Jogos)",
  "completions_avg_5": "Passes Completados (Média dos Últimos 5 Jogos)",
  "completions_avg_10": "Passes Completados (Média dos Últimos 10 Jogos)",
  "completions_season_avg": "Passes Completados (Média da Temporada)",
  "passing_cpoe_avg_5": "CPOE: Acerto de Passe Acima do Esperado (Últimos 5 Jogos)",
  "passing_cpoe_season_avg": "CPOE: Acerto de Passe Acima do Esperado (Média da Temporada)",
  "epa_per_dropback_avg_5": "EPA por Passe: Pontos Esperados Adicionados por Tentativa (Últimos 5 Jogos)",
  "epa_per_dropback_season_avg": "EPA por Passe: Pontos Esperados Adicionados por Tentativa (Média da Temporada)",
  "sack_rate_avg_5": "Taxa de Sacks Sofridos pelo QB (Últimos 5 Jogos)",
  "sack_rate_season_avg": "Taxa de Sacks Sofridos pelo QB (Média da Temporada)",
  "adot_avg_5": "aDOT: Profundidade Média dos Passes Lançados (Últimos 5 Jogos)",
  "adot_season_avg": "aDOT: Profundidade Média dos Passes Lançados (Média da Temporada)",

  // === RUSHING (RUNNING BACK) ===
  "rushing_yards_avg_3": "Jardas Corridas (Média dos Últimos 3 Jogos)",
  "rushing_yards_avg_5": "Jardas Corridas (Média dos Últimos 5 Jogos)",
  "rushing_yards_avg_10": "Jardas Corridas (Média dos Últimos 10 Jogos)",
  "rushing_yards_season_avg": "Jardas Corridas (Média da Temporada)",
  "rushing_yards_shrunk_season_avg": "Jardas Corridas (Média Estabilizada Bayesiana)",
  "rushing_yards_std_5": "Desvio Padrão de Jardas Corridas (Consistência nos Últimos 5 Jogos)",
  "rushing_yards_ewm_3": "Jardas Corridas Ponderadas Recentes (Média Exponencial EWM)",
  "carries_avg_3": "Corridas Tentadas (Média dos Últimos 3 Jogos)",
  "carries_avg_5": "Corridas Tentadas (Média dos Últimos 5 Jogos)",
  "carries_avg_10": "Corridas Tentadas (Média dos Últimos 10 Jogos)",
  "carries_season_avg": "Corridas Tentadas (Média da Temporada)",
  "carries_ewm_3": "Corridas Tentadas Ponderadas (Média Exponencial EWM)",
  "rybc_avg_3": "RYBC: Jardas Antes do Primeiro Contato Defensivo (Últimos 3 Jogos)",
  "ryac_avg_3": "RYAC: Jardas Após o Primeiro Contato Defensivo (Últimos 3 Jogos)",
  "light_box_pct_avg_3": "Caixa Leve: % de Snaps com 6 ou Menos Defensores na Linha (3 Jogos)",
  "avg_box_count_avg_3": "Box Count: Número Médio de Defensores na Linha (3 Jogos)",
  "carry_share_ewm_3": "% de Corridas da Equipe (Tendência Recente Ponderada EWM)",
  "carry_share_shrunk_season_avg": "% de Corridas da Equipe (Média Estabilizada Bayesiana)",
  "rz_carry_share_ewm_3": "Red Zone: % de Corridas nas Últimas 20 Jardas (Tendência Recente EWM)",
  "committee_entropy_avg_3": "Divisão do Comitê: Grau de Rotatividade entre Running Backs (3 Jogos)",
  "light_box_x_def_rush_epa": "Interação: Caixa Defensiva Leve x Eficiência Terrestre Cedida",
  "implied_spread_x_rz_carry_share": "Interação: Vantagem de Placar x Corridas na Red Zone",
  "carry_share_x_backup_injury": "Interação: Expansão de Carga por Lesão de Corredor Companheiro",

  // === RECEIVING (WIDE RECEIVER & TIGHT END) ===
  "receiving_yards_avg_3": "Jardas Recebidas (Média dos Últimos 3 Jogos)",
  "receiving_yards_avg_5": "Jardas Recebidas (Média dos Últimos 5 Jogos)",
  "receiving_yards_avg_10": "Jardas Recebidas (Média dos Últimos 10 Jogos)",
  "receiving_yards_season_avg": "Jardas Recebidas (Média da Temporada)",
  "receiving_yards_shrunk_season_avg": "Jardas Recebidas (Média Estabilizada Bayesiana)",
  "receiving_yards_std_5": "Desvio Padrão de Jardas Recebidas (Consistência nos Últimos 5 Jogos)",
  "targets_avg_3": "Alvos / Passes Direcionados (Média dos Últimos 3 Jogos)",
  "targets_avg_5": "Alvos / Passes Direcionados (Média dos Últimos 5 Jogos)",
  "targets_avg_10": "Alvos / Passes Direcionados (Média dos Últimos 10 Jogos)",
  "targets_season_avg": "Alvos / Passes Direcionados (Média da Temporada)",
  "receptions_avg_3": "Recepções Concluídas (Média dos Últimos 3 Jogos)",
  "receptions_avg_5": "Recepções Concluídas (Média dos Últimos 5 Jogos)",
  "receptions_avg_10": "Recepções Concluídas (Média dos Últimos 10 Jogos)",
  "receptions_season_avg": "Recepções Concluídas (Média da Temporada)",
  "catch_rate_avg_3": "Taxa de Recepção / Aproveitamento de Alvos (Últimos 3 Jogos)",
  "catch_rate_avg_5": "Taxa de Recepção / Aproveitamento de Alvos (Últimos 5 Jogos)",
  "catch_rate_season_avg": "Taxa de Recepção / Aproveitamento de Alvos (Média da Temporada)",
  "receiving_yards_after_catch_avg_3": "YAC: Jardas Conquistadas Após a Recepção (Últimos 3 Jogos)",
  "receiving_yards_after_catch_avg_5": "YAC: Jardas Conquistadas Após a Recepção (Últimos 5 Jogos)",
  "receiving_yards_after_catch_season_avg": "YAC: Jardas Conquistadas Após a Recepção (Média da Temporada)",
  "wopr_avg_5": "WOPR: Índice Ponderado de Oportunidade Ofensiva (Últimos 5 Jogos)",
  "wopr_season_avg": "WOPR: Índice Ponderado de Oportunidade Ofensiva (Média da Temporada)",
  "wopr_ewm_5": "WOPR Ponderado Recente (Média Exponencial EWM)",
  "wopr_shrunk_season_avg": "WOPR Estabilizado Bayesiano (Média da Temporada)",
  "target_share_avg_5": "% de Alvos da Equipe Direcionados ao Atleta (Últimos 5 Jogos)",
  "target_share_season_avg": "% de Alvos da Equipe Direcionados ao Atleta (Média da Temporada)",
  "target_share_ewm_5": "% de Alvos da Equipe (Tendência Recente Ponderada EWM)",
  "target_share_shrunk_season_avg": "% de Alvos da Equipe (Média Estabilizada Bayesiana)",
  "air_yards_share_avg_5": "% de Jardas Aéreas Totais da Equipe (Últimos 5 Jogos)",
  "air_yards_share_season_avg": "% de Jardas Aéreas Totais da Equipe (Média da Temporada)",
  "air_yards_share_ewm_5": "% de Jardas Aéreas Totais (Tendência Recente Ponderada EWM)",
  "receiving_adot_avg_5": "aDOT do Recebedor: Profundidade Média das Rotas Lançadas (Últimos 5 Jogos)",
  "receiving_adot_season_avg": "aDOT do Recebedor: Profundidade Média das Rotas Lançadas (Média da Temporada)",
  "offense_pct_avg_5": "% de Snaps Ofensivos em Campo (Últimos 5 Jogos)",
  "offense_pct_ewm_3": "% de Snaps Ofensivos em Campo (Tendência Recente EWM)",
  "red_zone_targets_avg_5": "Red Zone: Alvos Recebidos nas Últimas 20 Jardas (Últimos 5 Jogos)",
  "rz_efficiency_offense_avg_5": "Eficiência Ofensiva da Equipe na Red Zone (Últimas 20 Jardas)",
  "team_qb_epa_per_dropback_avg_5": "Eficiência do QB Titular: EPA por Passe (Últimos 5 Jogos)",
  "wopr_x_implied_total": "Interação: Volume Esperado (WOPR) x Projeção de Pontos do Ataque",
  "target_share_x_redistribution": "Interação: Alvos Projetados com Ausência de Outros Recebedores",
  "rz_targets_x_rz_efficiency": "Interação: Alvos na Red Zone x Eficiência da Equipe",

  // === DEFENSIVE / OPPONENT (DEFESA ADVERSÁRIA) ===
  "def_pass_yds_allowed_avg_5": "Defesa Adversária: Jardas de Passe Cedidas por Jogo (Últimos 5 Jogos)",
  "def_pass_yds_allowed_season_avg": "Defesa Adversária: Jardas de Passe Cedidas por Jogo (Média da Temporada)",
  "def_rush_yds_allowed_avg_5": "Defesa Adversária: Jardas Corridas Cedidas por Jogo (Últimos 5 Jogos)",
  "def_rush_yds_allowed_season_avg": "Defesa Adversária: Jardas Corridas Cedidas por Jogo (Média da Temporada)",
  "def_pass_epa_allowed_avg_5": "Defesa Adversária: EPA Cedido no Passe (Pontos Esperados - Últimos 5 Jogos)",
  "def_pass_epa_allowed_season_avg": "Defesa Adversária: EPA Cedido no Passe (Pontos Esperados - Média da Temporada)",
  "def_rush_epa_avg_5": "Defesa Adversária: EPA Cedido na Corrida (Pontos Esperados - Últimos 5 Jogos)",
  "def_rush_epa_season_avg": "Defesa Adversária: EPA Cedido na Corrida (Pontos Esperados - Média da Temporada)",
  "def_pressure_rate_generated_avg_5": "Defesa Adversária: Taxa de Pressão Gerada no Quarterback (Últimos 5 Jogos)",
  "def_pressure_rate_generated_season_avg": "Defesa Adversária: Taxa de Pressão Gerada no Quarterback (Média da Temporada)",
  "def_run_stop_rate_avg_5": "Defesa Adversária: Taxa de Paradas Curtas de Corrida (Últimos 5 Jogos)",
  "def_run_stop_rate_season_avg": "Defesa Adversária: Taxa de Paradas Curtas de Corrida (Média da Temporada)",

  // === CONTEXT / VEGAS / ENVIRONMENT ===
  "implied_team_total": "Total Implícito de Pontos da Equipe (Projeção das Casas de Apostas)",
  "total_line": "Linha Total de Pontos da Partida (Over/Under Geral de Pontos)",
  "spread_line": "Spread do Jogo (Handicap de Pontos estipulado pelas Casas de Apostas)",
  "implied_spread": "Handicap / Spread Implícito da Equipe",
  "wind": "Velocidade do Vento no Estádio (em milhas por hora - mph)",
  "weather_temp": "Temperatura Ambiente no Estádio (em graus Fahrenheit - °F)",
  "precipitation_pct": "Probabilidade de Precipitação / Chuva no Estádio (%)",
  "is_turf": "Tipo de Gramado do Estádio (Grama Sintética vs Natural)",
  "days_rest": "Dias de Descanso da Equipe Desde a Última Partida",
  "is_short_week": "Semana Curta de Descanso (Partida realizada com menos de 6 dias de intervalo)",
  "proe_avg_5": "PROE: Taxa de Passes Acima do Esperado pelo Treinador (Últimos 5 Jogos)",
  "neutral_script_pass_rate_avg_5": "Taxa de Passe em Situação Neutra de Placar (Últimos 5 Jogos)",
  "team_plays_per_game_avg_5": "Ritmo Ofensivo: Total de Jogadas Executadas por Partida (5 Jogos)",
  "opp_plays_per_game_avg_5": "Ritmo Permitido pela Defesa: Jogadas Ofertadas ao Adversário por Partida (5 Jogos)",
  "role_stability_score": "Índice de Estabilidade Tática do Jogador no Esquema da Equipe",
  "implied_team_total_x_proe": "Interação: Potencial de Pontos x Agressividade no Passe (PROE)",
  "sack_rate_x_def_pressure": "Interação de Risco: Tendência de Sacks do QB x Pressão da Linha Defensiva",
};

export const STAT_DESCRIPTIONS: Record<string, string> = {
  // === EPA (EXPECTED POINTS ADDED) ===
  "epa_per_dropback_avg_5": "EPA significa Expected Points Added (Pontos Esperados Adicionados). Mede o quanto cada jogada de passe aumentou ou diminuiu a probabilidade de pontuação da equipe, levando em conta descida, distância e campo. Valores positivos altos (+0.15 a +0.30) indicam um quarterback de altíssimo impacto; valores negativos indicam perdas de jardas e turnovers prejudiciais.",
  "epa_per_dropback_season_avg": "EPA (Pontos Esperados Adicionados): Eficiência consolidada do passador por jogada de passe ao longo da temporada inteira. Mede a consistência real do QB além das jardas brutas.",
  "team_qb_epa_per_dropback_avg_5": "EPA do Quarterback Titular: Mede a eficiência do lançador da equipe em gerar pontos esperados por tentativa de passe nos últimos 5 jogos. Quanto maior o valor, mais passes precisos e jardas o recebedor tende a acumular no confronto.",
  "def_pass_epa_allowed_avg_5": "EPA Cedido no Passe pela Defesa: Mede os Pontos Esperados Adicionados permitidos pela defesa a cada passe rival nos últimos 5 jogos. IMPORTANTE: para a defesa, quanto MENOR ou mais NEGATIVO (ex: -0.15), melhor ela é (Rank 1 a 10). Valores positivos altos (ex: +0.20) sinalizam uma secundária vazada, excelente cenário para apostas de Over em jardas de passe e recebedores.",
  "def_pass_epa_allowed_season_avg": "EPA Cedido no Passe (Média da Temporada): Eficiência média permitida pela secundária defensiva no ano inteiro. Valores negativos refletem defesas aéreas de elite.",
  "def_rush_epa_avg_5": "EPA Cedido na Corrida pela Defesa: Mede os Pontos Esperados Adicionados permitidos contra corridas adversárias nos últimos 5 jogos. Quanto menor ou mais negativo for o número, mais impenetrável é o muro da linha defensiva contra o jogo terrestre.",
  "def_rush_epa_season_avg": "EPA Cedido na Corrida (Média da Temporada): Eficiência permitida pela defesa em jogadas terrestres durante toda a temporada regular. Essencial para projetar o teto de produção do running back adversário.",

  // === CPOE (COMPLETION PERCENTAGE OVER EXPECTED) ===
  "passing_cpoe_avg_5": "CPOE significa Completion Percentage Over Expected (Taxa de Passes Completados Acima do Esperado). Utiliza rastreamento óptico da NFL para estimar a probabilidade de acerto de cada lançamento (com base na separação do recebedor, velocidade do vento e proximidade do marcador). Se um QB tem CPOE de +5.0%, ele acerta 5% a mais de passes difíceis do que um lançador padrão da liga.",
  "passing_cpoe_season_avg": "CPOE (Média da Temporada): Índice consolidado de precisão do passador no ano, filtrando a dificuldade dos lançamentos tentados e eliminando distorções de passes fáceis de curta distância.",

  // === aDOT (AVERAGE DEPTH OF TARGET) ===
  "adot_avg_5": "aDOT significa Average Depth of Target (Profundidade Média do Alvo). Mede a distância média em jardas que a bola viaja pelo ar, além da linha de scrimmage, antes de chegar ao recebedor nos últimos 5 jogos. Um aDOT alto (11 a 14 jardas) indica um quarterback que ataca o fundo do campo; um aDOT baixo (5 a 8 jardas) indica estilo conservador focado em passes curtos e telas.",
  "adot_season_avg": "aDOT (Profundidade Média do Alvo na Temporada): Média em jardas que a bola viaja pelo ar nos lançamentos do quarterback em todo o ano, refletindo a filosofia agressiva ou cautelosa do ataque.",
  "receiving_adot_avg_5": "aDOT do Recebedor (Profundidade Média dos Alvos Recebidos): Distância média em jardas além da linha de scrimmage em que o recebedor é acionado nos últimos 5 jogos. Recebedores velozes de campo aberto possuem aDOT alto (>12 jardas), exigindo menos recepções para atingir grandes volumes de jardas.",
  "receiving_adot_season_avg": "aDOT do Recebedor na Temporada: Distância média de profundidade das rotas do atleta no consolidado do ano, separando especialistas em rotas profundas de recebedores de posse intermediária.",

  // === WOPR (WEIGHTED OPPORTUNITY RATING) ===
  "wopr_avg_5": "WOPR significa Weighted Opportunity Rating (Índice Ponderado de Oportunidade Ofensiva). É a métrica mais respeitada na análise avançada de recebedores, calculada por: 1.5 x (Participação nos Alvos) + 0.7 x (Participação nas Jardas Aéreas). Valores acima de 0.50 indicam o recebedor titular alfa absoluto da franquia; valores entre 0.35 e 0.49 apontam armas complementares indispensáveis.",
  "wopr_season_avg": "WOPR Consolidado da Temporada: Índice médio de oportunidade e protagonismo no ataque da equipe ao longo de todo o ano. Quanto maior, mais o esquema tático depende deste recebedor.",
  "wopr_ewm_5": "WOPR Ponderado Recente (EWM): Calcula o índice WOPR dando maior peso aos jogos recentes via média exponencial. Permite identificar de imediato recebedores cujo volume cresceu após trocas táticas ou lesões de companheiros.",
  "wopr_shrunk_season_avg": "WOPR Estabilizado Bayesiano: Versão calibrada estatisticamente que equilibra a produção do atleta com padrões históricos estáveis da liga, evitando ilusões causadas por jogos isolados fora da curva.",
  "wopr_x_implied_total": "Interação WOPR x Projeção de Pontos: Cruza o peso ofensivo do recebedor (WOPR) com a expectativa de pontos das casas de apostas para estimar com precisão o volume de jardas projetado na partida.",

  // === TARGET SHARE & AIR YARDS SHARE ===
  "target_share_avg_5": "Target Share (% de Alvos da Equipe): Percentual de todos os passes lançados pela equipe direcionados a este jogador nos últimos 5 jogos. Números acima de 22-25% caracterizam recebedores de primeiro escalão com volume garantido.",
  "target_share_season_avg": "Target Share na Temporada: Média de participação nos passes da equipe durante o ano inteiro.",
  "target_share_ewm_5": "Target Share Ponderado Recente (EWM): Tendência recente da fatia de passes da equipe recebidos, com foco nas semanas mais recentes.",
  "target_share_shrunk_season_avg": "Target Share Estabilizado: Proporção estabilizada de alvos via inferência bayesiana, garantindo maior robustez nas projeções.",
  "target_share_x_redistribution": "Alvos com Redistribuição: Ajuste preditivo que calcula os alvos extras herdados pelo atleta devido a lesões confirmadas de outros recebedores da equipe.",
  "air_yards_share_avg_5": "Air Yards Share (% de Jardas Aéreas): Porcentagem de todas as jardas percorridas pela bola pelo ar pela equipe destinadas a este atleta nos últimos 5 jogos. Revela o monopólio das jogadas explosivas e verticais.",
  "air_yards_share_season_avg": "Air Yards Share na Temporada: Porcentagem consolidada de jardas aéreas totais da franquia destinadas ao atleta no campeonato.",
  "air_yards_share_ewm_5": "Air Yards Share Ponderado Recente (EWM): Tendência da fatia de jardas aéreas nos jogos mais recentes, identificando expansões do papel tático.",

  // === RYBC & RYAC & YAC ===
  "rybc_avg_3": "RYBC significa Rushing Yards Before Contact (Jardas Corridas Antes do Contato). Quantidade média de jardas que o corredor ganha antes de sofrer o primeiro toque de um defensor rival nos últimos 3 jogos. Reflete diretamente a eficiência dos bloqueios da linha ofensiva e a leitura de brechas.",
  "ryac_avg_3": "RYAC significa Rushing Yards After Contact (Jardas Corridas Após o Contato). Média de jardas conquistadas pelo corredor após o impacto inicial com a marcação adversária nos últimos 3 jogos. É o indicador supremo de força física, agressividade e capacidade de quebrar tackles.",
  "receiving_yards_after_catch_avg_3": "YAC significa Yards After Catch (Jardas Conquistadas Após a Recepção). Média de jardas que o recebedor avança com a bola dominada nos braços após efetuar a recepção nos últimos 3 jogos. Sinaliza atletas velozes que criam jardas no campo aberto.",
  "receiving_yards_after_catch_avg_5": "YAC nos Últimos 5 Jogos: Rendimento em jardas ganhas com a bola nas mãos após a pegada nas últimas 5 partidas.",
  "receiving_yards_after_catch_season_avg": "YAC na Temporada: Total acumulado de jardas ganhas após a recepção ao longo do campeonato.",

  // === BOX COUNT & LIGHT BOX ===
  "light_box_pct_avg_3": "Light Box % (Caixa Defensiva Leve): Percentual de corridas em que a defesa adversária posicionou 6 ou menos defensores próximos à linha de scrimmage nos últimos 3 jogos. Caixas leves proporcionam avenidas limpas para ganhos expressivos de jardas pelo chão.",
  "avg_box_count_avg_3": "Box Count Médio: Número médio de defensores adversários postados na caixa (a menos de 7 jardas da linha de scrimmage) nos últimos 3 jogos. Contagens menores (6.0 a 6.4) favorecem corredores velozes; contagens cheias (7 ou 8) desafiam a linha de bloqueio.",
  "light_box_x_def_rush_epa": "Interação Caixa Leve x Defesa Terrestre: Mede como a probabilidade de encontrar caixas defensivas leves compensa ou potencializa o rendimento contra a eficiência da defesa rival.",

  // === RED ZONE & RZ ===
  "rz_carry_share_ewm_3": "RZ significa Red Zone (as últimas 20 jardas antes da linha de gol). RZ Carry Share mede o percentual de corridas da equipe na zona de pontuação executadas por este running back (ponderado por EWM). Identifica o corredor preferido do técnico perto da endzone.",
  "red_zone_targets_avg_5": "Red Zone Targets: Média de passes recebidos pelo jogador dentro das últimas 20 jardas do campo nos últimos 5 jogos. Fundamental para avaliar o favoritismo a marcar touchdowns e a soma de recepções vitais.",
  "rz_efficiency_offense_avg_5": "Eficiência da Equipe na Red Zone: Taxa com que o ataque converte idas às últimas 20 jardas em touchdowns completos nos últimos 5 jogos.",
  "rz_targets_x_rz_efficiency": "Interação Red Zone: Avalia em conjunto o volume individual de alvos na área de pontuação com o aproveitamento tático coletivo do ataque.",
  "implied_spread_x_rz_carry_share": "Interação Handicap x Red Zone: Correlaciona o favoritismo no placar com as chances de corridas na linha de gol (equipes favoritas chegam mais à red zone e gastam o relógio correndo).",

  // === PROE & GAME SCRIPT ===
  "proe_avg_5": "PROE significa Pass Rate Over Expected (Taxa de Passes Acima do Esperado). Mede o percentual de jogadas em que o treinador optou por passar a bola comparado à média estatística da NFL para a mesma situação de placar, tempo e jardas restantes. PROE positivo (+4% a +8%) indica ataque aéreo super agressivo; PROE negativo (-5%) indica ataques conservadores focados na corrida.",
  "neutral_script_pass_rate_avg_5": "Taxa de Passe em Situação Neutra: Frequência com que o ataque passa a bola quando a partida está equilibrada (diferença de 1 a 7 pontos no placar). Revela a verdadeira identidade do time sem a distorção do desespero de final de jogo.",
  "implied_team_total_x_proe": "Interação Total de Pontos x PROE: Cruza a expectativa de pontos das casas com a agressividade de passe do treinador para antecipar o número total de tentativas aéreas do confronto.",

  // === SACKS & PRESSURE & RUN STOP ===
  "sack_rate_avg_5": "Sack Rate (Taxa de Sacks Sofridos): Porcentagem de jogadas de passe em que o quarterback é derrubado atrás da linha de scrimmage nos últimos 5 jogos. Sacks desperdiçam descidas e reduzem as jardas líquidas do jogo aéreo.",
  "sack_rate_season_avg": "Sack Rate na Temporada: Taxa consolidada de sacks sofridos pelo passador durante toda a temporada.",
  "def_pressure_rate_generated_avg_5": "Taxa de Pressão Gerada pela Defesa: Porcentagem de jogadas de passe em que a defesa pressionou, bateu ou derrubou o QB rival nos últimos 5 jogos. Taxas acima de 33% caracterizam linhas defensivas de elite que provocam erros e passes incompletos.",
  "def_pressure_rate_generated_season_avg": "Taxa de Pressão Gerada na Temporada: Eficiência contínua da defesa em acelerar as decisões do quarterback adversário durante todo o ano.",
  "sack_rate_x_def_pressure": "Índice de Vulnerabilidade a Pressão: Avalia o risco de colapso do pocket cruzando a lentidão do QB em se livrar da bola com a ferocidade do pass rush da defesa rival.",
  "def_run_stop_rate_avg_5": "Run Stop Rate (Taxa de Paradas Curtas de Corrida): Porcentagem de corridas adversárias em que os defensores impediram o corredor de conseguir um ganho positivo satisfatório para o ataque. Quanto mais alta a taxa, mais difícil é correr contra essa defesa.",
  "def_run_stop_rate_season_avg": "Run Stop Rate na Temporada: Solidez defensiva no combate a corridas nas imediações da linha de scrimmage ao longo do ano.",

  // === DEFENSIVE YARDS ALLOWED ===
  "def_pass_yds_allowed_avg_5": "Jardas de Passe Cedidas pela Defesa: Média de jardas aéreas permitidas aos adversários por jogo nos últimos 5 confrontos. Defesas com números altos (>245 yds/j) oferecem terreno fértil para apostas de Over em passes e recepções.",
  "def_pass_yds_allowed_season_avg": "Jardas de Passe Cedidas na Temporada: Média de jardas aéreas cedidas pela defesa por jogo em toda a temporada regular.",
  "def_rush_yds_allowed_avg_5": "Jardas Corridas Cedidas pela Defesa: Média de jardas terrestres permitidas por jogo nos últimos 5 confrontos. Números acima de 125 yds/j indicam defesas vulneráveis contra o jogo corrido.",
  "def_rush_yds_allowed_season_avg": "Jardas Corridas Cedidas na Temporada: Média de jardas terrestres permitidas pela defesa por partida ao longo do campeonato.",

  // === CARRIES & COMMITTEE & ROLES ===
  "offense_pct_avg_5": "% de Snaps Ofensivos: Percentual de jogadas ofensivas do time em que o atleta esteve em campo nos últimos 5 jogos. Indica se ele é titular absoluto ou peça de rotação.",
  "offense_pct_ewm_3": "% de Snaps Ofensivos (EWM): Tendência recente de presença em campo ponderada exponencialmente, capturando mudanças recentes de rotação.",
  "carry_share_ewm_3": "Carry Share (% de Corridas da Equipe - EWM): Proporção das tentativas de corrida da equipe concentradas neste jogador nos jogos recentes. Corredores de elite monopolizam mais de 65% das corridas.",
  "carry_share_shrunk_season_avg": "Carry Share Estabilizado: Proporção média de corridas do atleta ajustada por inferência bayesiana para eliminar distorções de jogos isolados.",
  "carry_share_x_backup_injury": "Expansão de Carga por Lesão: Estima as corridas extras absorvidas pelo jogador após lesão confirmada de um companheiro de posição.",
  "committee_entropy_avg_3": "Entropia do Comitê de Corredores: Mede o grau de divisão de corridas entre os running backs do time nos últimos 3 jogos. Entropia baixa (<0.40) indica um titular absoluto com todas as corridas; entropia alta (>0.80) indica comitê igualitário que divide a produção.",
  "role_stability_score": "Índice de Estabilidade Tática: Pontuação matemática que mede a constância do papel do jogador no plano de jogo ao longo das semanas. Notas altas (>0.80) garantem previsibilidade nas projeções.",

  // === STANDARD PASSING STATS ===
  "passing_yards_avg_3": "Média de jardas de passe conquistadas por jogo nos últimos 3 jogos disputados.",
  "passing_yards_avg_5": "Média de jardas de passe conquistadas por partida nos últimos 5 jogos disputados.",
  "passing_yards_avg_10": "Média de jardas de passe conquistadas nos últimos 10 confrontos.",
  "passing_yards_season_avg": "Média de jardas de passe por partida ao longo de toda a temporada regular.",
  "passing_yards_shrunk_season_avg": "Média estabilizada de jardas de passe: estimativa bayesiana que combina a média do quarterback com a média histórica da liga, excelente para inícios de temporada.",
  "passing_yards_std_5": "Desvio padrão das jardas de passe nos últimos 5 jogos: avalia a regularidade do passador. Desvios pequenos indicam performances estáveis e previsíveis.",
  "attempts_avg_3": "Média de passes tentados por partida nos últimos 3 jogos disputados.",
  "attempts_avg_5": "Média de passes tentados por jogo nos últimos 5 jogos disputados.",
  "attempts_avg_10": "Média de passes tentados por partida nos últimos 10 confrontos.",
  "attempts_season_avg": "Média de passes tentados por jogo em toda a temporada.",
  "completions_avg_3": "Média de passes completados com sucesso por partida nos últimos 3 jogos.",
  "completions_avg_5": "Média de passes completados por partida nos últimos 5 jogos disputados.",
  "completions_avg_10": "Média de passes completados nos últimos 10 jogos.",
  "completions_season_avg": "Média de passes completados por partida ao longo de toda a temporada.",

  // === STANDARD RUSHING STATS ===
  "rushing_yards_avg_3": "Média de jardas terrestres ganhas por partida nos últimos 3 jogos disputados.",
  "rushing_yards_avg_5": "Média de jardas terrestres ganhas por partida nos últimos 5 jogos disputados.",
  "rushing_yards_avg_10": "Média de jardas terrestres obtidas nas últimas 10 partidas.",
  "rushing_yards_season_avg": "Média de jardas de corrida por jogo na temporada regular.",
  "rushing_yards_shrunk_season_avg": "Média estabilizada de jardas terrestres: estimativa bayesiana que equilibra a média do atleta com padrões históricos para evitar superestimações.",
  "rushing_yards_std_5": "Desvio padrão de jardas corridas nos últimos 5 jogos: indica o grau de oscilação na produção terrestre do corredor.",
  "rushing_yards_ewm_3": "Jardas corridas ponderadas recentes (EWM): média móvel que atribui maior relevância aos jogos mais recentes do corredor.",
  "carries_avg_3": "Média de tentativas de corrida por jogo nos últimos 3 jogos disputados.",
  "carries_avg_5": "Média de tentativas de corrida por partida nos últimos 5 jogos disputados.",
  "carries_avg_10": "Média de tentativas de corrida por partida nos últimos 10 confrontos.",
  "carries_season_avg": "Média de corridas tentadas por jogo durante a temporada completa.",
  "carries_ewm_3": "Tentativas de corrida ponderadas recentes (EWM), refletindo a carga recente de trabalho do atleta.",

  // === STANDARD RECEIVING STATS ===
  "receiving_yards_avg_3": "Média de jardas de recepção ganhas por jogo nos últimos 3 jogos disputados.",
  "receiving_yards_avg_5": "Média de jardas de recepção ganhas por partida nos últimos 5 jogos disputados.",
  "receiving_yards_avg_10": "Média de jardas de recepção obtidas nas últimas 10 partidas.",
  "receiving_yards_season_avg": "Média de jardas recebidas por jogo ao longo de toda a temporada regular.",
  "receiving_yards_shrunk_season_avg": "Média estabilizada de jardas recebidas: projeção bayesiana equilibrada com a média histórica da liga.",
  "receiving_yards_std_5": "Desvio padrão de jardas recebidas nos últimos 5 jogos: avalia a regularidade do recebedor semana a semana.",
  "targets_avg_3": "Média de passes lançados na direção do jogador por jogo nos últimos 3 jogos disputados.",
  "targets_avg_5": "Média de passes direcionados ao jogador por partida nas últimas 5 semanas.",
  "targets_avg_10": "Média de passes direcionados ao atleta nos últimos 10 jogos disputados.",
  "targets_season_avg": "Média de alvos recebidos por confronto ao longo de toda a temporada.",
  "receptions_avg_3": "Média de recepções completadas por jogo nos últimos 3 jogos disputados.",
  "receptions_avg_5": "Média de passes recebidos com sucesso por jogo nas últimas 5 partidas.",
  "receptions_avg_10": "Média de recepções concluídas nos últimos 10 jogos disputados.",
  "receptions_season_avg": "Média de recepções por partida em toda a temporada.",
  "catch_rate_avg_3": "Catch Rate (Taxa de Aproveitamento de Alvos): Porcentagem de passes direcionados que foram recebidos com sucesso nos últimos 3 jogos.",
  "catch_rate_avg_5": "Catch Rate nos últimos 5 jogos: Eficiência na recepção de passes lançados na sua direção.",
  "catch_rate_season_avg": "Catch Rate na Temporada: Taxa consolidada de conversão de alvos em recepções completadas.",

  // === VEGAS & CONTEXT ===
  "implied_team_total": "Total Implícito de Pontos: Expectativa de pontos que a equipe deve marcar na partida estipulada pelas casas de apostas. Valores altos (>25 pontos) indicam grande produção ofensiva esperada.",
  "total_line": "Linha Total de Pontos (Over/Under do Jogo): Previsão combinada de pontos da partida pelas casas de apostas. Totais elevados (>48 pontos) sugerem partidas abertas e favoráveis para apostas no Over.",
  "spread_line": "Linha de Spread (Handicap): Margem de vitória esperada pelas casas de apostas. Times muito favoritos tendem a correr no 2º tempo para queimar o relógio; azarões passam a bola com mais frequência para tentar a virada.",
  "implied_spread": "Handicap Implícito: Vantagem ou desvantagem de pontos projetada pelas casas para a equipe do atleta.",
  "team_plays_per_game_avg_5": "Ritmo Ofensivo: Total de jogadas de ataque realizadas por jogo nas últimas 5 partidas. Times velozes criam mais chances para acumular jardas.",
  "opp_plays_per_game_avg_5": "Ritmo Defensivo Rival: Quantidade de jogadas ofensivas permitidas pela defesa adversária por jogo. Defesas desgastadas passam mais tempo em campo sofrendo investidas.",
  "wind": "Velocidade do Vento no Estádio (mph): Ventos acima de 15 a 20 mph desestabilizam a trajetória da bola e reduzem drasticamente passes longos.",
  "weather_temp": "Temperatura no Estádio (°F): Temperaturas abaixo de 32°F (0°C) deixam a bola mais rígida e dificultam recepções de alta velocidade.",
  "precipitation_pct": "Probabilidade de Chuva (%): Clima chuvoso aumenta a probabilidade de erros de manuseio e favorece planos de jogo focados na corrida.",
  "is_turf": "Tipo de Gramado: Grama artificial (Turf) proporciona maior tração e velocidade em comparação à grama natural (Grass).",
  "days_rest": "Dias de Descanso: Intervalo em dias desde a última partida. Mais descanso favorece a recuperação física do atleta.",
  "is_short_week": "Semana Curta de Descanso: Partidas jogadas com menos de 6 dias de descanso (ex: quinta-feira), cenário que costuma afetar o ritmo inicial dos ataques.",
};

// Formata o nome de qualquer estatística, expandindo siglas e sufixos
export function formatStatName(key: string): string {
  if (STAT_NAMES[key]) {
    return STAT_NAMES[key];
  }

  // Fallback inteligente com expansão sistemática de siglas
  let name = key;

  // Prefixos defensivos
  if (name.startsWith("def_")) {
    name = "Defesa: " + name.slice(4);
  }

  // Siglas centrais
  name = name
    .replace(/_epa_allowed/g, " EPA Cedido (Pontos Esperados)")
    .replace(/_epa_per_dropback/g, " EPA por Passe (Pontos Esperados)")
    .replace(/_cpoe/g, " CPOE (Acerto Acima do Esperado)")
    .replace(/_adot/g, " aDOT (Profundidade do Alvo)")
    .replace(/_wopr/g, " WOPR (Oportunidade Ponderada)")
    .replace(/_rybc/g, " RYBC (Jardas Antes do Contato)")
    .replace(/_ryac/g, " RYAC (Jardas Após Contato)")
    .replace(/_yac/g, " YAC (Jardas Pós-Recepção)")
    .replace(/_proe/g, " PROE (Taxa de Passe Acima do Esperado)")
    .replace(/_rz_/g, " Red Zone (Últimas 20 Jardas) ")
    .replace(/_pressure_rate/g, " Taxa de Pressão no QB")
    .replace(/_run_stop_rate/g, " Taxa de Paradas Curtas de Corrida")
    .replace(/_box_count/g, " Defensores na Linha (Box Count)")
    .replace(/_committee_entropy/g, " Entropia de Corredores (Divisão de Carga)")
    .replace(/_shrunk_season_avg/g, " (Média Estabilizada Bayesiana)")
    .replace(/_ewm_(\d+)/g, " (Tendência Recente $1J - EWM)")
    .replace(/_avg_(\d+)/g, " (Últimos $1 Jogos)")
    .replace(/_season_avg/g, " (Média da Temporada)")
    .replace(/_/g, " ")
    .trim();

  return name.charAt(0).toUpperCase() + name.slice(1);
}

// Retorna uma explicação detalhada e pedagógica em português para qualquer estatística
export function getStatDescription(key: string): string {
  if (STAT_DESCRIPTIONS[key]) {
    return STAT_DESCRIPTIONS[key];
  }

  // Fallback explicativo inteligente com detecção de siglas
  const explanations: string[] = [];

  if (key.includes("epa")) {
    explanations.push("EPA significa Expected Points Added (Pontos Esperados Adicionados), medindo a contribuição real de cada jogada para a probabilidade de pontuação da equipe.");
  }
  if (key.includes("cpoe")) {
    explanations.push("CPOE significa Completion Percentage Over Expected, calculando o acerto de passes além do esperado matemático da NFL.");
  }
  if (key.includes("adot")) {
    explanations.push("aDOT significa Average Depth of Target, representando a distância média em jardas que o passe viajou pelo ar.");
  }
  if (key.includes("wopr")) {
    explanations.push("WOPR é o Índice Ponderado de Oportunidade Ofensiva (1.5x Alvos + 0.7x Jardas Aéreas), avaliando o protagonismo do recebedor no time.");
  }
  if (key.includes("rybc")) {
    explanations.push("RYBC significa Rushing Yards Before Contact (Jardas Antes do Contato), medindo a qualidade dos bloqueios antes do primeiro toque defensivo.");
  }
  if (key.includes("ryac")) {
    explanations.push("RYAC significa Rushing Yards After Contact (Jardas Após Contato), demonstrando a força do corredor em quebrar tackles.");
  }
  if (key.includes("proe")) {
    explanations.push("PROE significa Pass Rate Over Expected, medindo a disposição do treinador em chamar passes acima do padrão esperado para aquele placar e tempo de jogo.");
  }
  if (key.includes("rz") || key.includes("red_zone")) {
    explanations.push("Red Zone refere-se às últimas 20 jardas do campo antes da linha de gol, área crítica onde a marcação se fecha e o volume de pontuação se define.");
  }
  if (key.includes("ewm")) {
    explanations.push("EWM significa Exponential Weighted Moving Average (Média Móvel Ponderada), atribuindo mais peso às semanas recentes para capturar o momento atual.");
  }
  if (key.includes("def_")) {
    explanations.push("Esta é uma métrica da defesa adversária. Em estatísticas cedidas (jardas/EPA), valores mais baixos indicam defesas mais duras e desfavoráveis ao Over.");
  }

  if (explanations.length > 0) {
    return explanations.join(" ");
  }

  return "Métrica estatística calculada com base no histórico recente de atuações do jogador e no esquema tático das equipes.";
}
