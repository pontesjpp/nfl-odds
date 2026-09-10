# Post-Deploy Validation Roadmap

**Status do Sistema:** Deploy Inicial Realizado (Rodada Atual)
**Data Alvo para Validação:** Em 3 rodadas de operação (~3 semanas de dados reais consolidados)
**Objetivo:** Transição do pipeline de engenharia de features (comprovado) para um sistema financeiro calibrado e liberado para escala de capital.

---

## 1. Quality Gate Obrigatório: EV Backtest

Atualmente, o modelo de predição (RMSE) e a engenharia de features estão operacionais e livres de vazamento (*leakage* não-linear comprovadamente limpo no XGBoost). No entanto, RMSE baixo não implica EV positivo nas caudas. O deploy atual operará em fase de observação até que o backtest probabilístico cruze com a realidade do mercado.

**Ação a ser executada em 3 semanas:**
Executar o script `ev_backtest.py` contra a base de `data/betclic_parsed_odds.parquet` (que terá acumulado histórico suficiente) e as predições de fato ocorridas.

### Métricas de Aprovação (GO/NO-GO):
1. **ROI Geral:** O ROI (`roi_pct`) deve ser maior que zero de forma consistente.
2. **Monotonicidade de Win-Rate:** O `win_rate` empírico deve subir monotonicamente conforme os Bins de EV previsto aumentam (ex: o bin de `>10%` precisa acertar mais que o bin de `2-5%`).
3. **Calibração de Cauda (O teste mais crítico):** Avaliar a tabela gerada por `calibration_by_tail_bin()`. O `calibration_gap` (win_rate real menos probabilidade implícita do modelo) não deve ser fortemente negativo nos bins da cauda (`>1.0σ` e `>1.5σ`). Um gap negativo indica que o modelo está muito confiante em eventos extremos e "queimará" EV nesses cenários.

---

## 2. Decisões Matemáticas sob Observação (Regressão de Quantis)

O modelo `PlayerPropModel` gera regressões de quantis independentes. Para que o backtest e a produção gerem uma curva de probabilidade contínua (CDF) a partir dos quantis (`q05, q10, q25, q50, q75, q90, q95`), foram adotadas duas premissas matemáticas que devem ser revistas caso a etapa 1 reprove:

### A. Quantile Crossing
- **Problema:** Árvores independentes podem cruzar os quantis (ex: `q90` prever valor menor que `q75`).
- **Solução Atual:** A função `prob_over()` executa um `np.sort(quantiles)` (rearranjo de quantis por linha) para forçar monotonicidade antes de montar a CDF. 

### B. Extrapolação Além dos Limites Treinados (Heavy Tails)
- **Problema:** Linhas de mercado muito acima do `q95` ou abaixo do `q05` precisariam de extrapolação. O uso puro de `np.interp` criaria um muro constante (0 ou 1 absoluto).
- **Solução Atual:** O código estende a cauda de forma **linear** usando uma rampa heurística (`q[-1] * 1.5 + 10`) mapeada para a probabilidade `1.0`.
- **Validação Futura:** O futebol americano possui caudas grossas (*heavy-tailed distributions*), especialmente na cauda direita de `rushing_yards` e `receiving_yards`. Se o modelo inflar erroneamente o EV nas caudas durante o backtest, esta rampa linear será abandonada e substituída por um fit de **Generalized Pareto Distribution (GPD)** nas margens do array de quantis.

---

## 3. Monitoramento de Features
- **Ação Paralela:** Após o deploy atual, acompanhar a incidência do erro `ValueError: CRITICAL: Feature X is 100% NULL`. O sistema de proteção de *stubs* está ativo e abortará treinamentos se tentarem alimentar lixo silenciosamente.
- **Drift:** Futuramente, implementar Teste Kolmogorov-Smirnov comparando as features contínuas semana após semana.
