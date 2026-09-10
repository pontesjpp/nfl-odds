# Spec de Features Adicionais — Modelos de EV (Passing / Rushing / Receiving Yards)

## Contexto para a IA que vai implementar

Este documento descreve novas features a adicionar aos três modelos de predição
(`passing_yards`, `rushing_yards`, `receiving_yards`) de um sistema de EV para
props de NFL.

**Regra fundamental de pipeline:** o processamento roda **semanalmente**, de
forma incremental. A cada nova semana, um jogo a mais já aconteceu para cada
jogador/time. Isso significa que:

1. Todas as features de janela móvel (`_avg_3`, `_avg_5`, `_avg_10`,
   `_season_avg`, EWM) devem ser **recalculadas do zero a cada rodada**,
   usando sempre os dados disponíveis **até o kickoff da semana alvo,
   exclusive** — nunca incluir o jogo que está sendo previsto (evitar
   data leakage).
2. Nenhuma feature pode usar informação que só existe **depois** do jogo
   (ex.: stats reais da própria partida, linha de fechamento de um jogo já
   iniciado, injury report atualizado pós-jogo).
3. Para as linhas de mercado (`total_line`, `spread_line`, etc.), usar o
   snapshot da linha no momento em que o modelo roda (ex.: linha do dia
   anterior ou closing line da semana anterior — definir um ponto de corte
   consistente e documentar qual é).
4. Toda feature de "temporada" (`_season_avg`, `target_share_season_avg` etc.)
   deve ser recalculada incluindo o jogo mais recente que já ocorreu, e para
   jogadores/times sem jogos suficientes na temporada atual, aplicar fallback
   (ver seção de Shrinkage).
5. Onde há EWM (exponentially weighted moving average), o span/halflife deve
   ser parametrizado (ex. span=3 ou span=5) e aplicado de forma consistente
   entre os três modelos — hoje só existe no modelo de rushing; deve ser
   estendido aos outros dois.

Para cada feature abaixo, implementar:
- Nome da coluna sugerido
- Definição / fórmula
- Fonte de dados necessária (se não existir, sinalizar como "requer nova
  fonte de dados")
- Frequência de atualização (deve ser semanal, recalculada como rolling
  window "as of" a data de corte)

---

## 1. Features de Pace e Game Script (aplicam-se aos 3 modelos)

| Feature | Definição | Observação de atualização semanal |
|---|---|---|
| `team_plays_per_game_avg_5` | Média de plays ofensivos do time nas últimas 5 partidas | Recalcular incluindo o jogo mais recente concluído |
| `opp_plays_per_game_avg_5` | Média de plays ofensivos permitidos/gerados pela defesa adversária nas últimas 5 partidas | Idem |
| `proe_avg_5` / `proe_season_avg` | Pass Rate Over Expected: diferença entre taxa de passe real do time e taxa esperada dado down/distance/score/tempo (usar modelo de expectativa padrão, ex. nflfastR `pass_oe` se disponível) | Recalcular média móvel a cada semana |
| `neutral_script_pass_rate_avg_5` | Taxa de passe do time **apenas em situações de placar neutro** (win probability entre ~20%-80%, ou diferença de placar dentro de 1 posse) | Precisa filtrar plays por WP antes de agregar; recalcular por semana |
| `line_movement_total` | `closing_total - opening_total` da semana do jogo a ser previsto | Não é rolling — é do próprio jogo alvo, capturado antes do kickoff |
| `line_movement_spread` | `closing_spread - opening_spread` | Idem |

---

## 2. Passing Yards — features a adicionar

| Feature | Definição | Fonte / Observação |
|---|---|---|
| `def_pass_epa_allowed_avg_5` | EPA/dropback permitido pela defesa adversária, média das últimas 5 semanas | Substituir/complementar `def_pass_yds_allowed_avg_5`, que é enviesado por volume de plays |
| `def_pass_epa_allowed_opp_adjusted` | Igual acima, mas ajustado pela força das ofensas enfrentadas (SoS) — ex. resíduo de um modelo simples de EPA ~ time_ofensivo + time_defensivo | Requer cálculo de rating tipo "adjusted EPA" (regressão ridge ou similar) |
| `def_pressure_rate_generated_avg_5` | % de dropbacks do oponente em que a defesa gerou pressão nas últimas 5 semanas | Requer dados de pressure/pass-block win rate |
| `qb_injury_designation` | Categórico: Healthy / Questionable / Probable-retorno-recente | Requer feed de injury report; congelar no snapshot pré-jogo |
| `games_since_return_from_injury` | Nº de jogos desde que o QB voltou de lesão que o tirou de ≥1 jogo | Calcular a partir do histórico de active/inactive |
| `wr_corps_epa_per_target_weighted` | Soma ponderada de `target_share_esperado × epa_per_target` de cada recebedor disponível na semana (ajustando ausências) | Depende de resolver primeiro quem estará ativo — usar probable/questionable como proxy quando injury report final não estiver disponível no momento do processamento |
| `days_rest` | Dias desde o último jogo do time | Calendário |
| `is_short_week` | Binário: jogo na quinta-feira após jogo de domingo | Calendário |
| `timezone_change` | Diferença de fuso horário entre estádio da semana anterior e desta semana | Calendário + geolocalização de estádios |

**Interações a criar (colunas derivadas, não apenas features brutas):**
- `implied_team_total_x_proe` = `implied_team_total * proe_avg_5`
- `sack_rate_x_def_pressure` = `sack_rate_avg_5 * def_pressure_rate_generated_avg_5`

---

## 3. Rushing Yards — features a adicionar

| Feature | Definição | Observação |
|---|---|---|
| `starting_qb_out` | Binário: QB titular do time está inativo/fora nesta semana | Requer injury report / depth chart, congelado pré-jogo |
| `rushing_yards_ewm_3`, `carries_ewm_3` | Versões EWM (não apenas `avg_3`) das já existentes médias simples | Padronizar EWM span=3 em todo o modelo de rushing, incluindo `rybc`/`ryac` que hoje só têm `avg_3` simples |
| `def_rush_epa_opp_adjusted` | `def_rush_epa_avg_5` ajustado pela força das ofensas de corrida enfrentadas (SoS) | Regressão tipo adjusted rating |
| `def_run_stop_rate_avg_5` | % de corridas do oponente contidas em ≤2 yards, média das últimas 5 semanas | Requer dado play-by-play de yards por corrida individual |
| `committee_entropy` | Entropia de Shannon da distribuição de `carry_share` entre os RBs do time nas últimas 3-4 semanas: `-Σ p_i * log(p_i)` | Calcular por time/semana; RB1 usa esse valor do seu próprio time |
| `backup_rb_injury_status` | Binário/categórico: RB competidor direto por touches está fora/limitado | Injury report |
| `weather_temp`, `precipitation_pct` | Temperatura e probabilidade/intensidade de chuva no horário do jogo | Requer fonte de clima (se ainda não integrada) |

**Interações a criar:**
- `light_box_x_def_rush_epa` = `light_box_pct_avg_3 * def_rush_epa_avg_5`
- `implied_spread_x_rz_carry_share` = `implied_spread * rz_carry_share_ewm_3`
- `carry_share_x_backup_injury` = `carry_share_ewm_3 * backup_rb_injury_status`

---

## 4. Receiving Yards — features a adicionar

| Feature | Definição | Observação |
|---|---|---|
| `qb_epa_per_dropback_avg_5` (do time do recebedor) | EPA/dropback do QB titular do time, não do próprio recebedor | Precisa fazer join do recebedor com o QB titular da semana; se QB mudar, refletir a mudança |
| `starting_qb_out` | Igual ao usado no modelo de rushing, aplicado ao time do recebedor | Mesmo dado, reaproveitar |
| `def_pass_epa_allowed_avg_5` | Substituir/complementar `def_pass_yds_allowed_avg_5` | Igual ao item do modelo de passing |
| `slot_vs_outside_coverage_grade_allowed` | Nota de cobertura permitida pela defesa adversária separada por alinhamento do recebedor (slot vs outside) | Requer dado de alinhamento (charting), sinalizar como "requer nova fonte" se não disponível |
| `shadow_coverage_flag` | Binário: oponente historicamente designa um CB para seguir o recebedor específico | Requer dado de charting/scouting; pode começar como flag manual para poucos jogadores relevantes |
| `route_participation_rate_avg_5` | % de dropbacks do time em que o recebedor rodou uma rota | Requer dado de participação em rotas |
| `target_share_ewm_5`, `air_yards_share_ewm_5`, `wopr_ewm_5` | Versões EWM das métricas já existentes em `avg_5` | Padronizar EWM span=5 |
| `teammate_injury_redistribution_elasticity` | Coeficiente histórico de quanto o target share deste jogador sobe quando um recebedor específico do elenco (ex. WR1) está fora | Calcular por par de jogadores/time, usando histórico de jogos com/sem o WR1 ativo |
| `rz_efficiency_offense` | Eficiência da ofensa do time em conversão de red zone trips em TD | Complementa `red_zone_targets_avg_5` |

**Interações a criar:**
- `wopr_x_implied_total` = `wopr_avg_5 * implied_team_total`
- `target_share_x_redistribution` = `target_share_avg_5 * teammate_injury_redistribution_elasticity`
- `rz_targets_x_rz_efficiency` = `red_zone_targets_avg_5 * rz_efficiency_offense`

---

## 5. Features de metodologia — aplicar aos 3 modelos

### 5.1 Shrinkage bayesiano para amostra pequena

Para todo jogador com poucos jogos na temporada atual (ex. rookies, jogadores
recém-promovidos a titular, jogadores retornando de lesão longa), as médias
`_avg_3/5/10` e `_season_avg` calculadas com poucas observações são muito
ruidosas. Adicionar:

- `games_played_sample_size` — nº de jogos usados no cálculo do `_season_avg`
  do jogador nesta temporada.
- `shrunk_season_avg` — calculado como:

  ```
  shrunk_avg = (n / (n + k)) * player_season_avg + (k / (n + k)) * positional_avg
  ```

  onde `n` = `games_played_sample_size`, `k` é uma constante calibrada por
  posição (a definir via validação, ex. k=4 para RB, k=6 para WR), e
  `positional_avg` é a média da métrica entre jogadores da mesma posição na
  liga na temporada atual (ou nas últimas N temporadas).
- Aplicar esse shrinkage em pelo menos: `passing_yards`, `rushing_yards`,
  `receiving_yards`, `target_share`, `carry_share`, `wopr` — qualquer feature
  de produção usada como "season avg".

### 5.2 Variância histórica (para modelagem de distribuição, não só média)

Adicionar, para os 3 modelos:
- `{stat}_std_5` — desvio padrão da métrica alvo (`passing_yards`,
  `rushing_yards`, `receiving_yards`) nas últimas 5 semanas.
- `{stat}_std_season` — desvio padrão na temporada.
- `role_stability_score` — inverso da variação de `snap_share`/`target_share`/
  `carry_share` semana a semana (ex. 1 / (1 + coef_variação)); usar para sinalizar
  jogadores com role instável (maior incerteza de projeção).

Essas features não alimentam necessariamente o modelo de média, mas devem
estar disponíveis para um segundo modelo/cabeça que estime o desvio padrão
esperado da distribuição de yards, usado no cálculo de EV contra a linha do
mercado.

### 5.3 Padronização entre os três modelos

- Decidir um único padrão (recomendação: EWM com span parametrizável) e
  aplicá-lo de forma consistente aos três modelos, substituindo o mix atual
  de `avg_N` simples e EWM.
- Documentar, para cada feature recalculada semanalmente, qual é exatamente
  o "corte" temporal usado (ex.: "todos os jogos com `game_date < snapshot_date`
  da semana em processamento").

---

## 6. Checklist de validação anti-leakage (rodar a cada atualização semanal)

- [ ] Nenhuma feature de jogador/time usa dados do próprio jogo que está sendo previsto.
- [ ] `total_line`, `spread_line`, `implied_team_total` e `line_movement_*` usam
      o snapshot correto (definir e documentar o horário de corte, ex. "linha
      disponível 24h antes do kickoff").
- [ ] Injury status (`qb_injury_designation`, `starting_qb_out`,
      `backup_rb_injury_status`) reflete o **último report antes do kickoff**,
      não o status pós-jogo.
- [ ] Todas as `_season_avg` foram recalculadas incluindo o jogo mais recente
      já disputado, e excluindo o jogo alvo da semana atual.
- [ ] Jogadores/times novos ou com poucos jogos passam pelo shrinkage antes de
      entrar no modelo.