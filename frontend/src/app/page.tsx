'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import Image from 'next/image';
import { PropCard, PropBet, formatStatName } from '@/components/PropCard';

type Mode = 'schedule' | 'recommended' | 'top_picks' | 'investments' | 'calculator';
type CalcMethod = 'xgboost' | 'manual';
type MarketType = 'passing_yards' | 'rushing_yards' | 'receiving_yards';

interface PlayerOption {
  player_name: string;
  player_display_name?: string;
  position?: string;
  team?: string;
  opponent_team?: string;
}

interface FeatureStat {
  value: number | string | null;
  importance?: number;
}

interface PredictSide {
  model_prob: number;
  implied_prob: number;
  fair_odds: number;
  edge: number;
  ev: number;
  profit: number;
  kelly_percent: number;
  half_kelly_percent: number;
  recommended_stake: number;
}

interface PredictResult {
  projected_yards: number | null;
  stake: number;
  team?: string;
  opponent?: string;
  over: PredictSide;
  under: PredictSide;
}

interface PortfolioSummary {
  total_bets: number;
  settled_count: number;
  pending_count: number;
  won_count: number;
  lost_count: number;
  push_count: number;
  total_staked_units: number;
  settled_staked_units: number;
  pending_staked_units?: number;
  net_profit_units: number;
  roi_percent: number;
  win_rate_percent: number;
  hit_rate_percent?: number;
  resolved_count?: number;
  avg_odds: number;
  profit_factor: number | null;
  avg_stake_units?: number;
  stake_distribution?: {
    '0.5u': number;
    '0.75u': number;
    '1.0u': number;
    '1.25u-1.5u': number;
    '1.75u+': number;
  };
  highest_conviction_pick?: {
    player_name: string;
    market: string;
    side: string;
    line: number;
    units: number;
    ev_percent: number;
    rationale: string;
  } | null;
}

export default function Home() {
  const [mode, setMode] = useState<Mode>('schedule');
  const [currentWeek, setCurrentWeek] = useState<number>(2);
  const [selectedWeek, setSelectedWeek] = useState<number>(2);
  const [availableWeeks, setAvailableWeeks] = useState<number[]>(Array.from({ length: 18 }, (_, i) => i + 1));
  const [schedule, setSchedule] = useState<any[]>([]);
  const [selectedGame, setSelectedGame] = useState<any>(null);
  const [liveBets, setLiveBets] = useState<any[]>([]);
  const [topPicks, setTopPicks] = useState<any[]>([]);
  const [selections, setSelections] = useState<Record<string, 'over' | 'under' | null>>({});

  // Portfolio States
  const [portfolioTab, setPortfolioTab] = useState<'safe' | 'safe_flat' | 'high_risk' | 'all_props'>('safe_flat');
  const [portfolioSafeCount, setPortfolioSafeCount] = useState<number>(0);
  const [portfolioSafeFlatCount, setPortfolioSafeFlatCount] = useState<number>(0);
  const [portfolioHighRiskCount, setPortfolioHighRiskCount] = useState<number>(0);
  const [portfolioAllPropsCount, setPortfolioAllPropsCount] = useState<number>(0);
  const [liveSafeCount, setLiveSafeCount] = useState<number>(0);
  const [liveSafeFlatCount, setLiveSafeFlatCount] = useState<number>(0);
  const [liveHighRiskCount, setLiveHighRiskCount] = useState<number>(0);
  const [liveAllPropsCount, setLiveAllPropsCount] = useState<number>(0);
  const [portfolioSummary, setPortfolioSummary] = useState<PortfolioSummary | null>(null);
  const [equityCurve, setEquityCurve] = useState<any[]>([]);
  const [portfolioBets, setPortfolioBets] = useState<any[]>([]);
  const [loadingPortfolio, setLoadingPortfolio] = useState<boolean>(false);
  const [portfolioMessage, setPortfolioMessage] = useState<string | null>(null);
  const [portfolioFilter, setPortfolioFilter] = useState<'all' | 'pending' | 'won' | 'lost' | 'push' | 'ne_sea'>('all');
  const [portfolioWeekFilter, setPortfolioWeekFilter] = useState<string>('all');
  const [portfolioAvailableWeeks, setPortfolioAvailableWeeks] = useState<number[]>([]);
  const [portfolioGameFilter, setPortfolioGameFilter] = useState<string>('all');
  const [portfolioSearch, setPortfolioSearch] = useState<string>('');

  const getBetGameInfo = useCallback((bet: any) => {
    // 1. Direct match with schedule via game_id
    if (bet.game_id && schedule && schedule.length > 0) {
      const found = schedule.find((s: any) => s.game_id === bet.game_id);
      if (found) {
        return {
          game_id: found.game_id,
          week: found.week || bet.week,
          away_team: found.away_team,
          home_team: found.home_team,
          label: `${found.away_team} @ ${found.home_team}`,
          stadium: found.stadium,
          gameday: found.gameday,
          gametime: found.gametime,
        };
      }
    }

    // 2. Parse from game_id string (e.g. 2026_01_NE_SEA)
    if (bet.game_id && typeof bet.game_id === 'string' && bet.game_id.includes('_')) {
      const parts = bet.game_id.split('_');
      if (parts.length >= 4) {
        const w = parseInt(parts[1], 10);
        const away = parts[2];
        const home = parts[3];
        return {
          game_id: bet.game_id,
          week: isNaN(w) ? bet.week : w,
          away_team: away,
          home_team: home,
          label: `${away} @ ${home}`,
        };
      }
    }

    // 3. Match from bet.team and bet.opponent via schedule
    if (bet.team && bet.opponent && schedule && schedule.length > 0) {
      const found = schedule.find(
        (s: any) =>
          ((s.away_team === bet.team && s.home_team === bet.opponent) ||
           (s.away_team === bet.opponent && s.home_team === bet.team)) &&
          (bet.week ? Number(s.week) === Number(bet.week) : true)
      );
      if (found) {
        return {
          game_id: found.game_id || `${bet.team}_${bet.opponent}`,
          week: found.week || bet.week,
          away_team: found.away_team,
          home_team: found.home_team,
          label: `${found.away_team} @ ${found.home_team}`,
          stadium: found.stadium,
          gameday: found.gameday,
          gametime: found.gametime,
        };
      }
    }

    // 4. Fallback using team and opponent
    if (bet.team && bet.opponent) {
      return {
        game_id: bet.game_id || `${bet.team}_vs_${bet.opponent}`,
        week: bet.week,
        away_team: bet.opponent,
        home_team: bet.team,
        label: `${bet.opponent} @ ${bet.team}`,
      };
    }

    return {
      game_id: bet.game_id || 'unknown',
      week: bet.week,
      away_team: bet.team || 'NFL',
      home_team: bet.opponent || 'NFL',
      label: bet.game_id || 'Jogo NFL',
    };
  }, [schedule]);

  const portfolioGames = useMemo(() => {
    const gameMap = new Map<string, {
      game_id: string;
      week?: number;
      away_team: string;
      home_team: string;
      label: string;
      displayLabel: string;
      stadium?: string;
      gameday?: string;
      gametime?: string;
      count: number;
      wonCount: number;
      lostCount: number;
      pendingCount: number;
    }>();

    portfolioBets.forEach((b: any) => {
      const info = getBetGameInfo(b);
      const gid = info.game_id || 'unknown';
      const bWeek = b.week || info.week;
      if (!gameMap.has(gid)) {
        const weekTag = bWeek ? ` (Semana ${bWeek})` : '';
        gameMap.set(gid, {
          game_id: gid,
          week: bWeek,
          away_team: info.away_team,
          home_team: info.home_team,
          label: info.label,
          displayLabel: `${info.label}${weekTag}`,
          stadium: info.stadium,
          gameday: info.gameday,
          gametime: info.gametime,
          count: 0,
          wonCount: 0,
          lostCount: 0,
          pendingCount: 0,
        });
      }
      const g = gameMap.get(gid)!;
      g.count += 1;
      if (b.result === 'won') g.wonCount += 1;
      else if (b.result === 'lost') g.lostCount += 1;
      else if (b.result === 'pending') g.pendingCount += 1;
    });

    return Array.from(gameMap.values()).sort((a, b) => b.count - a.count);
  }, [portfolioBets, getBetGameInfo]);

  const filteredPortfolioBets = useMemo(() => {
    return portfolioBets
      .filter((b: any) => {
        if (portfolioFilter === 'pending' && b.result !== 'pending') return false;
        if (portfolioFilter === 'won' && b.result !== 'won') return false;
        if (portfolioFilter === 'lost' && b.result !== 'lost') return false;
        if (portfolioFilter === 'push' && b.result !== 'push') return false;
        if (portfolioFilter === 'ne_sea' && b.team !== 'NE' && b.team !== 'SEA' && b.opponent !== 'NE' && b.opponent !== 'SEA') return false;

        // Filtro por Semana
        if (portfolioWeekFilter !== 'all' && b.week !== undefined && b.week !== null && String(b.week) !== String(portfolioWeekFilter)) {
          return false;
        }

        // Filtro por Jogo
        if (portfolioGameFilter !== 'all') {
          const info = getBetGameInfo(b);
          if (info.game_id !== portfolioGameFilter) {
            const target = portfolioGames.find((g: any) => g.game_id === portfolioGameFilter);
            if (target) {
              const matchTeams = (b.team === target.away_team || b.team === target.home_team || b.opponent === target.away_team || b.opponent === target.home_team);
              if (!matchTeams) return false;
            } else {
              return false;
            }
          }
        }

        // Filtro de busca por texto (jogador, time ou confronto)
        if (portfolioSearch.trim()) {
          const q = portfolioSearch.toLowerCase().trim();
          const matchPlayer = (b.player_name || '').toLowerCase().includes(q);
          const matchTeam = (b.team || '').toLowerCase().includes(q);
          const matchOpp = (b.opponent || '').toLowerCase().includes(q);
          const info = getBetGameInfo(b);
          const matchGame = info.label.toLowerCase().includes(q);
          if (!matchPlayer && !matchTeam && !matchOpp && !matchGame) return false;
        }
        return true;
      })
      .sort((a: any, b: any) => (b.ev_percent ?? -999) - (a.ev_percent ?? -999));
  }, [portfolioBets, portfolioFilter, portfolioWeekFilter, portfolioGameFilter, portfolioGames, portfolioSearch, getBetGameInfo]);

  const activeSummary = useMemo<PortfolioSummary | null>(() => {
    const hasSubFilter = portfolioGameFilter !== 'all' || portfolioFilter !== 'all' || portfolioSearch.trim().length > 0;
    if (!hasSubFilter && portfolioSummary) {
      return portfolioSummary;
    }

    const bets = filteredPortfolioBets;
    const total_bets = bets.length;
    const settled = bets.filter((b: any) => b.result === 'won' || b.result === 'lost' || b.result === 'push');
    const pending = bets.filter((b: any) => b.result === 'pending');
    const won = bets.filter((b: any) => b.result === 'won');
    const lost = bets.filter((b: any) => b.result === 'lost');
    const push = bets.filter((b: any) => b.result === 'push');

    const total_staked_units = bets.reduce((acc: number, b: any) => acc + (Number(b.units) || 0), 0);
    const settled_staked_units = settled.reduce((acc: number, b: any) => acc + (Number(b.units) || 0), 0);
    const pending_staked_units = pending.reduce((acc: number, b: any) => acc + (Number(b.units) || 0), 0);
    const net_profit_units = settled.reduce((acc: number, b: any) => acc + (Number(b.profit_units) || 0), 0);

    const roi_percent = settled_staked_units > 0 ? (net_profit_units / settled_staked_units) * 100 : 0;
    const resolved_count = won.length + lost.length;
    const win_rate_percent = resolved_count > 0 ? (won.length / resolved_count) * 100 : 0;
    const hit_rate_percent = settled.length > 0 ? (won.length / settled.length) * 100 : 0;

    const avg_odds = total_staked_units > 0
      ? bets.reduce((acc: number, b: any) => acc + (Number(b.odds) || 0) * (Number(b.units) || 0), 0) / total_staked_units
      : 0;

    const gross_profit = won.reduce((acc: number, b: any) => acc + (Number(b.profit_units) || 0), 0);
    const gross_loss = Math.abs(lost.reduce((acc: number, b: any) => acc + (Number(b.profit_units) || 0), 0));
    const profit_factor = gross_loss > 0 ? gross_profit / gross_loss : (gross_profit > 0 ? gross_profit : 0);

    const stake_dist: { '0.5u': number; '0.75u': number; '1.0u': number; '1.25u-1.5u': number; '1.75u+': number } = {
      '0.5u': 0, '0.75u': 0, '1.0u': 0, '1.25u-1.5u': 0, '1.75u+': 0
    };
    bets.forEach((b: any) => {
      const u = Number(b.units) || 1.0;
      if (u <= 0.5) stake_dist['0.5u']++;
      else if (u <= 0.75) stake_dist['0.75u']++;
      else if (u <= 1.0) stake_dist['1.0u']++;
      else if (u <= 1.5) stake_dist['1.25u-1.5u']++;
      else stake_dist['1.75u+']++;
    });

    const bestFilteredPick = bets.length > 0
      ? [...bets].sort((a: any, b: any) => ((Number(b.units) || 0) * (Number(b.ev_percent) || 0)) - ((Number(a.units) || 0) * (Number(a.ev_percent) || 0)))[0]
      : null;

    return {
      total_bets,
      settled_count: settled.length,
      pending_count: pending.length,
      won_count: won.length,
      lost_count: lost.length,
      push_count: push.length,
      total_staked_units,
      settled_staked_units,
      pending_staked_units,
      net_profit_units,
      roi_percent,
      win_rate_percent,
      hit_rate_percent,
      avg_odds,
      profit_factor,
      avg_stake_units: total_bets > 0 ? total_staked_units / total_bets : 1.0,
      stake_distribution: stake_dist,
      highest_conviction_pick: bestFilteredPick ? {
        player_name: bestFilteredPick.player_name,
        market: bestFilteredPick.market,
        side: bestFilteredPick.side,
        line: bestFilteredPick.line,
        odds: bestFilteredPick.odds,
        ev_percent: bestFilteredPick.ev_percent,
        units: bestFilteredPick.units,
        rationale: bestFilteredPick.ai_rationale || bestFilteredPick.rationale || 'Aposta selecionada pelo modelo de maior convicção.'
      } : (portfolioSummary?.highest_conviction_pick || null)
    };
  }, [portfolioSummary, filteredPortfolioBets, portfolioGameFilter, portfolioFilter, portfolioSearch]);

  // Box Score Modal States
  const [boxScoreOpen, setBoxScoreOpen] = useState<boolean>(false);
  const [boxScoreData, setBoxScoreData] = useState<any>(null);
  const [loadingBoxScore, setLoadingBoxScore] = useState<boolean>(false);
  const [boxScoreTab, setBoxScoreTab] = useState<'stats' | 'bets'>('stats');

  // AI Sizing & Contextual Explanation Modal State
  const [selectedAiBet, setSelectedAiBet] = useState<any | null>(null);

  // Security / Read-Only Demonstration Mode & MFA State
  const [isReadOnly, setIsReadOnly] = useState<boolean>(true);
  const [isAdmin, setIsAdmin] = useState<boolean>(false);
  const [adminModalOpen, setAdminModalOpen] = useState<boolean>(false);
  const [adminPassword, setAdminPassword] = useState<string>('');
  const [adminTotp, setAdminTotp] = useState<string>('');
  const [adminAuthLoading, setAdminAuthLoading] = useState<boolean>(false);
  const [adminAuthError, setAdminAuthError] = useState<string | null>(null);

  const authFetch = async (url: string, options: RequestInit = {}) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('nfl_admin_token') : null;
    const headers = new Headers(options.headers || {});
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    const sep = url.includes('?') ? '&' : '?';
    const busterUrl = `${url}${sep}_t=${Date.now()}`;
    return fetch(busterUrl, {
      ...options,
      cache: 'no-store',
      headers,
    });
  };

  const handleAdminLogin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setAdminAuthLoading(true);
    setAdminAuthError(null);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          password: adminPassword,
          totp_code: adminTotp.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setAdminAuthError(data.detail || 'Falha ao autenticar.');
        return;
      }
      if (data.token) {
        localStorage.setItem('nfl_admin_token', data.token);
      }
      setIsAdmin(true);
      setIsReadOnly(false);
      setAdminModalOpen(false);
      setAdminPassword('');
      setAdminTotp('');
      setPortfolioMessage('Autenticado como Administrador com sucesso!');
      await fetchPortfolio(portfolioTab);
    } catch (err) {
      setAdminAuthError('Erro de conexão ao autenticar.');
    } finally {
      setAdminAuthLoading(false);
    }
  };

  const handleAdminLogout = async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch (err) {}
    localStorage.removeItem('nfl_admin_token');
    setIsAdmin(false);
    setIsReadOnly(true);
    setPortfolioMessage('Modo Visitante (somente leitura) ativado.');
    await fetchPortfolio(portfolioTab);
  };

  const handleOpenBoxScore = async (game?: any) => {
    const gameId = game?.game_id || '2026_01_NE_SEA';
    setLoadingBoxScore(true);
    setBoxScoreOpen(true);
    try {
      const res = await fetch(`/api/games/${gameId}/boxscore`);
      if (res.ok) {
        const data = await res.json();
        setBoxScoreData(data);
      }
    } catch (err) {
      console.error("Erro ao carregar box score:", err);
    } finally {
      setLoadingBoxScore(false);
    }
  };

  // Schedule Props View States (Zero EV filter)
  const [scheduleSearch, setScheduleSearch] = useState<string>('');
  const [scheduleMarket, setScheduleMarket] = useState<string>('all');
  const [scheduleSort, setScheduleSort] = useState<'ev_desc' | 'ev_asc' | 'player_asc' | 'line_desc'>('ev_desc');
  const [showGamesGrid, setShowGamesGrid] = useState<boolean>(true);

  // Calculator State
  const [calcMethod, setCalcMethod] = useState<CalcMethod>('xgboost');
  const [market, setMarket] = useState<MarketType>('rushing_yards');
  const [teamsList, setTeamsList] = useState<{ code: string; name: string }[]>([]);
  const [playersList, setPlayersList] = useState<PlayerOption[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState<string>('');
  const [selectedOpponent, setSelectedOpponent] = useState<string>('');
  const [features, setFeatures] = useState<Record<string, FeatureStat> | null>(null);
  const [loadingFeatures, setLoadingFeatures] = useState<boolean>(false);
  const [showAllFeatures, setShowAllFeatures] = useState<boolean>(false);

  const [line, setLine] = useState<number>(60.5);
  const [oddsOver, setOddsOver] = useState<number>(1.90);
  const [oddsUnder, setOddsUnder] = useState<number>(1.90);
  const [stake, setStake] = useState<number>(100.0);
  const [manualProbOver, setManualProbOver] = useState<number>(55.0);

  const [calcResult, setCalcResult] = useState<PredictResult | null>(null);
  const [isCalculating, setIsCalculating] = useState<boolean>(false);
  const [calcError, setCalcError] = useState<string | null>(null);

  const fetchPortfolio = async (
    tab: 'safe' | 'safe_flat' | 'high_risk' | 'all_props' = portfolioTab,
    week: string = portfolioWeekFilter
  ) => {
    try {
      const weekQuery = week && week !== 'all' ? `&week=${encodeURIComponent(week)}` : '';
      const res = await authFetch(`/api/portfolio?portfolio_type=${tab}${weekQuery}`);
      if (res.ok) {
        const data = await res.json();
        setPortfolioSummary(data.summary);
        setEquityCurve(data.equity_curve || []);
        setPortfolioBets(data.bets || []);
        if (data.available_weeks && Array.isArray(data.available_weeks)) {
          setPortfolioAvailableWeeks(data.available_weeks);
        }
        if (data.read_only !== undefined && !isAdmin) setIsReadOnly(Boolean(data.read_only));
        if (data.safe_count !== undefined) setPortfolioSafeCount(data.safe_count);
        if (data.safe_flat_count !== undefined) setPortfolioSafeFlatCount(data.safe_flat_count);
        if (data.high_risk_count !== undefined) setPortfolioHighRiskCount(data.high_risk_count);
        if (data.all_props_count !== undefined) setPortfolioAllPropsCount(data.all_props_count);
        if (data.live_safe_count !== undefined) setLiveSafeCount(data.live_safe_count);
        if (data.live_safe_flat_count !== undefined) setLiveSafeFlatCount(data.live_safe_flat_count);
        if (data.live_high_risk_count !== undefined) setLiveHighRiskCount(data.live_high_risk_count);
        if (data.live_all_props_count !== undefined) setLiveAllPropsCount(data.live_all_props_count);
      }
    } catch (err) {
      console.error("Error fetching portfolio:", err);
    }
  };

  const handleToggleReadOnly = async (targetMode: boolean) => {
    if (targetMode === false) {
      setAdminAuthError(null);
      setAdminModalOpen(true);
      return;
    }
    await handleAdminLogout();
  };

  const handleSettlePortfolio = async (gameIdParam?: string) => {
    setLoadingPortfolio(true);
    setPortfolioMessage(null);
    try {
      if (isReadOnly) {
        setPortfolioMessage('Modo somente leitura ativo. Desbloqueie o Modo Administrador para liquidar.');
        setLoadingPortfolio(false);
        return;
      }
      const url = gameIdParam
        ? `/api/portfolio/settle?game_id=${gameIdParam}`
        : `/api/portfolio/settle?portfolio_type=${portfolioTab}`;
      const res = await authFetch(url, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        setPortfolioMessage(data.detail || 'Operação bloqueada no modo somente leitura.');
        return;
      }
      setPortfolioMessage(data.message || 'Conferência de resultados concluída.');
      await fetchPortfolio(portfolioTab);
      // Se o modal de box score estiver aberto, atualiza os dados
      if (boxScoreOpen) {
        handleOpenBoxScore({ game_id: gameIdParam || boxScoreData?.game_id || '2026_01_NE_SEA' });
      }
    } catch (err) {
      setPortfolioMessage('Erro ao verificar e liquidar resultados.');
    } finally {
      setLoadingPortfolio(false);
    }
  };

  const handleImportSafePicks = async () => {
    setLoadingPortfolio(true);
    setPortfolioMessage(null);
    try {
      const res = await authFetch('/api/portfolio/import-safe-picks?replace_pending=true', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        setPortfolioMessage(data.detail || 'Operação bloqueada no modo somente leitura.');
        return;
      }
      setPortfolioMessage(`${data.imported} apostas conservadoras (+EV 2.5% a 15%) sincronizadas com sucesso.`);
      await fetchPortfolio('safe');
    } catch (err) {
      setPortfolioMessage('Erro ao sincronizar recomendações seguras.');
    } finally {
      setLoadingPortfolio(false);
    }
  };

  const handleImportSafeFlatPicks = async () => {
    setLoadingPortfolio(true);
    setPortfolioMessage(null);
    try {
      const res = await authFetch('/api/portfolio/import-safe-flat?replace_pending=true', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        setPortfolioMessage(data.detail || 'Operação bloqueada no modo somente leitura.');
        return;
      }
      setPortfolioMessage(`${data.imported} recomendações (+EV 2.5% a 15% com Flat 1.0u) sincronizadas.`);
      await fetchPortfolio('safe_flat');
    } catch (err) {
      setPortfolioMessage('Erro ao sincronizar recomendações flat 1u.');
    } finally {
      setLoadingPortfolio(false);
    }
  };

  const handleImportHighRiskPicks = async () => {
    setLoadingPortfolio(true);
    setPortfolioMessage(null);
    try {
      const res = await authFetch('/api/portfolio/import-high-risk-picks?replace_pending=true', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        setPortfolioMessage(data.detail || 'Operação bloqueada no modo somente leitura.');
        return;
      }
      setPortfolioMessage(`${data.imported} apostas de alto risco (+EV > 20%) sincronizadas.`);
      await fetchPortfolio('high_risk');
    } catch (err) {
      setPortfolioMessage('Erro ao sincronizar apostas de alto risco.');
    } finally {
      setLoadingPortfolio(false);
    }
  };

  const handleImportAllProps = async (mode: 'best_side' | 'all_rows' = 'best_side') => {
    setLoadingPortfolio(true);
    setPortfolioMessage(null);
    try {
      const res = await authFetch(`/api/portfolio/import-all-props?replace_pending=true&mode=${mode}`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        setPortfolioMessage(data.detail || 'Operação bloqueada no modo somente leitura.');
        return;
      }
      setPortfolioMessage(`${data.imported} props sincronizadas na carteira All Props (${mode === 'best_side' ? 'Lado Recomendado de Cada Prop' : 'Ambos os Lados'}).`);
      await fetchPortfolio('all_props');
    } catch (err) {
      setPortfolioMessage('Erro ao sincronizar todas as props.');
    } finally {
      setLoadingPortfolio(false);
    }
  };

  const handleSimulateSettlement = async () => {
    setLoadingPortfolio(true);
    setPortfolioMessage(null);
    try {
      const res = await authFetch(`/api/portfolio/simulate-settlement?portfolio_type=${portfolioTab}`, { method: 'POST' });
      const data = await res.json();
      setPortfolioMessage(data.message || 'Simulação de desfechos concluída.');
      await fetchPortfolio(portfolioTab);
    } catch (err) {
      setPortfolioMessage('Erro ao simular liquidação.');
    } finally {
      setLoadingPortfolio(false);
    }
  };

  const handleResetSettlement = async () => {
    setLoadingPortfolio(true);
    try {
      await authFetch(`/api/portfolio/reset-settlement?portfolio_type=${portfolioTab}`, { method: 'POST' });
      setPortfolioMessage('Apostas desta carteira foram resetadas para pendente.');
      await fetchPortfolio(portfolioTab);
    } catch (err) {
      setPortfolioMessage('Erro ao resetar apostas.');
    } finally {
      setLoadingPortfolio(false);
    }
  };

  const handleClearPortfolio = async () => {
    const portfolioLabel = portfolioTab === 'safe' 
      ? 'Carteira Dinâmica Inteligente (+EV 2.5% - 15%)' 
      : portfolioTab === 'safe_flat'
      ? 'Carteira Recomendadas Flat 1u (+EV 2.5% - 15%)'
      : portfolioTab === 'high_risk' 
      ? 'Carteira de Alto Risco (EV > 20%)' 
      : 'Carteira All Props (100% das Props)';
    if (!confirm(`Deseja realmente limpar todas as apostas da ${portfolioLabel}?`)) return;
    setLoadingPortfolio(true);
    try {
      await authFetch(`/api/portfolio/clear?portfolio_type=${portfolioTab}`, { method: 'DELETE' });
      setPortfolioMessage(`${portfolioLabel} limpa com sucesso.`);
      await fetchPortfolio(portfolioTab);
    } catch (err) {
      setPortfolioMessage('Erro ao limpar carteira.');
    } finally {
      setLoadingPortfolio(false);
    }
  };

  const handleManualSettle = async (betId: number, result: 'won' | 'lost' | 'push' | 'pending') => {
    try {
      await authFetch(`/api/portfolio/${betId}/manual-settle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ result })
      });
      await fetchPortfolio(portfolioTab);
    } catch (err) {
      console.error("Error setting manual result:", err);
    }
  };

  const handleDeleteBet = async (betId: number) => {
    if (isReadOnly) return;
    try {
      await authFetch(`/api/portfolio/${betId}`, { method: 'DELETE' });
      await fetchPortfolio(portfolioTab);
    } catch (err) {
      console.error("Error deleting bet:", err);
    }
  };

  const handleAddBetToPortfolio = async (bet: any) => {
    if (isReadOnly) return;
    try {
      const evVal = bet.evPercent !== undefined ? Number(bet.evPercent) : (bet.ev_percent !== undefined ? Number(bet.ev_percent) : null);
      const ptype = portfolioTab === 'all_props' ? 'all_props' : portfolioTab === 'safe_flat' ? 'safe_flat' : ((evVal !== null && evVal > 20.0) ? 'high_risk' : 'safe');
      const payload = {
        player_name: bet.playerName || bet.player_name,
        team: bet.playerTeam || bet.team,
        opponent: bet.opponent,
        market: bet.metric || bet.market,
        line: Number(bet.line),
        side: (bet.side || 'over').toLowerCase(),
        odds: Number(bet.overOdds || bet.odds || 1.85),
        units: 1.0,
        model_probability: bet.modelProb !== undefined ? Number(bet.modelProb) : (bet.model_prob !== undefined ? Number(bet.model_prob) : null),
        implied_probability: bet.implied_prob !== undefined ? Number(bet.implied_prob) : null,
        edge: bet.edge !== undefined ? Number(bet.edge) : null,
        ev_percent: evVal,
        portfolio_type: ptype,
        season: 2026,
        week: 1
      };
      const res = await fetch('/api/portfolio/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      const destName = ptype === 'high_risk' ? 'Carteira de Alto Risco (EV > 20%)' : ptype === 'all_props' ? 'Carteira All Props' : 'Carteira Conservadora (+EV 2.5% a 15%)';
      if (data.status === 'already_exists') {
        alert(`Esta aposta já está registrada na ${destName}.`);
      } else {
        alert(`Aposta adicionada com sucesso na ${destName}!`);
        await fetchPortfolio(portfolioTab);
      }
    } catch (err) {
      console.error("Error adding bet to portfolio:", err);
    }
  };

  const handleSelectPick = (propId: string, selection: 'over' | 'under') => {
    setSelections(prev => {
      if (prev[propId] === selection) {
        const newSelections = { ...prev };
        delete newSelections[propId];
        return newSelections;
      }
      return {
        ...prev,
        [propId]: selection,
      };
    });
  };

  // Initial data loading & auth verification
  useEffect(() => {
    // Check initial auth status
    const token = typeof window !== 'undefined' ? localStorage.getItem('nfl_admin_token') : null;
    const authHeaders: Record<string, string> = {};
    if (token) authHeaders['Authorization'] = `Bearer ${token}`;
    
    const buster = `_t=${Date.now()}`;
    fetch(`/api/auth/status?${buster}`, { headers: authHeaders, cache: 'no-store' })
      .then(res => res.json())
      .then(data => {
        const isAdm = Boolean(data.is_admin);
        setIsAdmin(isAdm);
        setIsReadOnly(!isAdm);
      })
      .catch(err => console.error("Error checking auth status:", err));

    fetchPortfolio();
    fetch(`/api/current-week?${buster}`, { cache: 'no-store' })
      .then(res => res.json())
      .then(data => {
        if (data.current_week) {
          setCurrentWeek(data.current_week);
          setSelectedWeek(data.current_week);
        }
        if (data.available_weeks && Array.isArray(data.available_weeks)) {
          setAvailableWeeks(data.available_weeks);
        }
      })
      .catch(err => console.error("Error loading current week:", err));

    fetch(`/api/schedule?${buster}`, { cache: 'no-store' })
      .then(res => res.json())
      .then(data => setSchedule(data))
      .catch(err => console.error("Error loading schedule:", err));

    fetch(`/api/live-bets?${buster}`, { cache: 'no-store' })
      .then(res => res.json())
      .then(data => setLiveBets(data))
      .catch(err => console.error("Error loading bets:", err));

    fetch(`/api/top-picks?limit=15&${buster}`, { cache: 'no-store' })
      .then(res => res.json())
      .then(data => setTopPicks(data))
      .catch(err => console.error("Error loading top picks:", err));

    fetch(`/api/teams?${buster}`, { cache: 'no-store' })
      .then(res => res.json())
      .then(data => setTeamsList(data))
      .catch(err => console.error("Error loading teams:", err));
  }, []);

  // Load players when market changes in calculator
  useEffect(() => {
    fetch(`/api/players?market=${market}`)
      .then(res => res.json())
      .then((data: any[]) => {
        if (Array.isArray(data) && data.length > 0) {
          const parsed = data.map(p => typeof p === 'string' ? { player_name: p } : p);
          setPlayersList(parsed);
          setSelectedPlayer(parsed[0].player_name);
          if (parsed[0].opponent_team) {
            setSelectedOpponent(parsed[0].opponent_team);
          }
        } else {
          setPlayersList([]);
          setSelectedPlayer('');
          setSelectedOpponent('');
        }
      })
      .catch(err => console.error("Error loading players:", err));

    // Reset default lines based on market
    if (market === 'passing_yards') setLine(245.5);
    else if (market === 'rushing_yards') setLine(60.5);
    else if (market === 'receiving_yards') setLine(52.5);
  }, [market]);

  // Load features when selected player, market or opponent changes
  useEffect(() => {
    if (selectedPlayer && calcMethod === 'xgboost') {
      setLoadingFeatures(true);
      const oppParam = selectedOpponent ? `&opponent=${encodeURIComponent(selectedOpponent)}` : '';
      fetch(`/api/players/${encodeURIComponent(selectedPlayer)}/features?market=${market}${oppParam}`)
        .then(res => {
          if (!res.ok) throw new Error("Falha ao carregar estatísticas");
          return res.json();
        })
        .then(data => {
          setFeatures(data);
          setLoadingFeatures(false);
        })
        .catch(err => {
          console.error("Error loading player features:", err);
          setFeatures(null);
          setLoadingFeatures(false);
        });
    } else {
      setFeatures(null);
    }
  }, [selectedPlayer, market, selectedOpponent, calcMethod]);

  const calculateEV = async () => {
    setIsCalculating(true);
    setCalcError(null);
    try {
      const payload: any = {
        odds_over: Number(oddsOver),
        odds_under: Number(oddsUnder),
        stake: Number(stake),
      };

      if (calcMethod === 'manual') {
        payload.manual_prob_over = Number(manualProbOver);
        payload.line = Number(line);
      } else {
        if (!selectedPlayer) {
          setCalcError("Por favor, selecione um jogador.");
          setIsCalculating(false);
          return;
        }
        payload.player_name = selectedPlayer;
        payload.line = Number(line);
        payload.market = market;
        if (selectedOpponent) {
          payload.opponent = selectedOpponent;
        }
      }

      const res = await fetch('/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Erro ao calcular EV");
      }

      const data = await res.json();
      setCalcResult(data);
    } catch (err: any) {
      setCalcError(err.message || "Erro de conexão com a API.");
      setCalcResult(null);
    } finally {
      setIsCalculating(false);
    }
  };

  // Helper to group bets for PropCard
  const groupBetsToProps = (bets: any[]): PropBet[] => {
    return bets.map(bet => {
      const game = schedule.find((g: any) => g.away_team === bet.team || g.home_team === bet.team);
      const isAway = game?.away_team === bet.team;
      const opponent = game ? (isAway ? game.home_team : game.away_team) : undefined;
      const matchupStr = game ? `${game.away_team} @ ${game.home_team}` : 'NFL Matchup';
      return {
        id: `${bet.player_name}-${bet.market}-${bet.line}-${bet.side}`,
        playerName: bet.player_name,
        fullPlayerName: bet.full_player_name || bet.player_name,
        playerPosition: bet.depth_chart_pos || bet.position || '',
        playerTeam: bet.team,
        espnId: bet.espn_id ? Math.floor(bet.espn_id).toString() : '',
        matchup: matchupStr,
        opponent: opponent,
        metric: bet.market,
        line: bet.line,
        side: bet.side?.toLowerCase(),
        overOdds: bet.odds,
        underOdds: bet.odds,
        evPercent: bet.ev_percent,
        modelProb: bet.prob_win,
        fairOdds: bet.fair_odds,
        edge: bet.edge,
        aiSummary: bet.ai_summary,
        depthChartPos: bet.depth_chart_pos,
        depthRole: bet.depth_role,
        depthStatus: bet.depth_status,
        positionTitle: bet.position_title,
        posRank: bet.pos_rank,
        depthString: bet.depth_string,
        yearsExp: bet.years_exp,
        expDesc: bet.exp_desc,
        jerseyNumber: bet.jersey_number,
        depthSummary: bet.depth_summary,
        hasNewsAlert: bet.has_news_alert,
        alertSeverity: bet.alert_severity,
        alertType: bet.alert_type,
        alertHeadline: bet.alert_headline,
        newsContext: bet.news_context,
        impactAssessment: bet.impact_assessment,
        recommendationAdjustment: bet.recommendation_adjustment,
      };
    });
  };

  // Active game props count and filter for Schedule tab (ABSOLUTELY NO EV FILTERS)
  const scheduleFilteredBets = liveBets.filter(bet => {
    // 0. Match week if present in bet data
    if (bet.week !== undefined && bet.week !== null && Number(bet.week) !== Number(selectedWeek)) {
      return false;
    }
    // 1. Match game if selected
    if (selectedGame) {
      if (bet.team !== selectedGame.away_team && bet.team !== selectedGame.home_team) {
        return false;
      }
    }
    // 2. Match market if selected
    if (scheduleMarket !== 'all' && bet.market !== scheduleMarket) {
      return false;
    }
    // 3. Match text search (player or team)
    if (scheduleSearch.trim()) {
      const q = scheduleSearch.toLowerCase().trim();
      const nameMatch = (bet.full_player_name || bet.player_name || '').toLowerCase().includes(q);
      const teamMatch = (bet.team || '').toLowerCase().includes(q);
      if (!nameMatch && !teamMatch) return false;
    }
    // NO EV FILTER: all props included (negative EV, zero EV, positive EV)
    return true;
  });

  const sortedScheduleBets = [...scheduleFilteredBets].sort((a, b) => {
    if (scheduleSort === 'ev_desc') {
      return (b.ev_percent ?? -999) - (a.ev_percent ?? -999);
    }
    if (scheduleSort === 'ev_asc') {
      return (a.ev_percent ?? -999) - (b.ev_percent ?? -999);
    }
    if (scheduleSort === 'player_asc') {
      return (a.player_name || '').localeCompare(b.player_name || '');
    }
    if (scheduleSort === 'line_desc') {
      return (b.line ?? 0) - (a.line ?? 0);
    }
    return 0;
  });

  const activeGameBets = liveBets.filter(b => {
    if (b.week !== undefined && b.week !== null && Number(b.week) !== Number(selectedWeek)) {
      return false;
    }
    if (selectedGame) {
      return b.team === selectedGame.away_team || b.team === selectedGame.home_team;
    }
    return true;
  });

  const marketCounts = {
    all: activeGameBets.length,
    rushing_yards: activeGameBets.filter(b => b.market === 'rushing_yards').length,
    receiving_yards: activeGameBets.filter(b => b.market === 'receiving_yards').length,
    passing_yards: activeGameBets.filter(b => b.market === 'passing_yards').length,
  };

  const safeCount = liveBets.filter(b => b.ev_percent >= 2.5 && b.ev_percent <= 15.0).length;

  const navTabs: { id: Mode; label: string; badge?: string }[] = [
    { id: 'schedule', label: 'Agenda & Todas as Props' },
    { id: 'recommended', label: 'Recomendações Seguras', badge: safeCount > 0 ? `${safeCount} Oportunidades` : undefined },
    { id: 'top_picks', label: 'Highest EVs (Risk)' },
    { id: 'investments', label: 'Carteira de Investimentos', badge: (portfolioSafeCount + portfolioHighRiskCount + portfolioAllPropsCount) > 0 ? `${portfolioSafeCount + portfolioHighRiskCount + portfolioAllPropsCount} Ativos` : undefined },
    { id: 'calculator', label: 'Calculadora de EV' },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-[#000000] text-white font-sans selection:bg-[#C5A880]/30 selection:text-white">
      {/* Precision Engineered Luxury Header */}
      <header className="h-16 flex items-center justify-between px-5 sm:px-8 md:px-12 fixed top-0 left-0 right-0 z-40 bg-[#000000]/90 backdrop-blur-xl border-b border-[#2B261D] shadow-2xl transition-all">
        {/* Left: Monogram Mark & Brand Title */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl overflow-hidden border border-[#D4AF37]/50 bg-[#0C0C0E] shadow-[0_0_15px_rgba(212,175,55,0.15)] flex items-center justify-center p-0.5 group shrink-0">
            <img 
              src="/images/biskate-analytics-monogram-champagne-gold.svg" 
              alt="Biskate Monogram" 
              className="w-full h-full object-contain group-hover:scale-105 transition-transform"
            />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span className="font-serif text-sm md:text-base tracking-[0.26em] font-extrabold text-[#FFFFFF]">
                BISKATE
              </span>
              <span className="text-[9px] font-mono font-bold tracking-widest text-[#D4AF37] px-1.5 py-0.2 border border-[#D4AF37]/40 rounded bg-[#D4AF37]/10">
                PRO
              </span>
            </div>
            <span className="font-mono text-[9px] tracking-[0.45em] uppercase text-[#C5A880] font-medium">
              ANALYTICS
            </span>
          </div>
        </div>

        {/* Center: Season & Week Chip */}
        <div className="hidden md:flex items-center gap-2.5 px-4 py-1.5 rounded-full bg-[#0C0C0E] border border-[#2B261D]">
          <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse"></span>
          <span className="font-mono text-xs tracking-[0.25em] uppercase text-zinc-300 font-medium">
            NFL 2026-2027
          </span>
          <span className="text-[#2B261D]">/</span>
          <span className="font-mono text-xs tracking-[0.25em] uppercase text-[#D4AF37] font-bold">
            WEEK {currentWeek}
          </span>
        </div>

        {/* Right: Engine Status Indicator & Admin MFA */}
        <div className="flex items-center gap-2.5">
          <div className="hidden sm:flex items-center gap-2 px-3 py-1 rounded-full bg-[#0C0C0E] border border-[#2B261D]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#D4AF37]"></span>
            <span className="font-mono text-[10px] tracking-wider text-[#C5A880] uppercase font-semibold">
              CALIPER ENGINE
            </span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-[#10B981]/10 border border-[#10B981]/40 text-[#10B981] font-mono text-[11px] tracking-wider font-bold shadow-[0_0_12px_rgba(16,185,129,0.2)]">
            <span className="w-2 h-2 rounded-full bg-[#10B981]"></span>
            +EV LIVE
          </div>

          {isAdmin ? (
            <div className="flex items-center gap-1.5 bg-[#D4AF37]/10 border border-[#D4AF37]/40 rounded-full pl-3 pr-1.5 py-1">
              <span className="w-2 h-2 rounded-full bg-[#D4AF37] animate-pulse"></span>
              <span className="text-[10px] font-mono font-bold tracking-wider text-[#D4AF37] uppercase mr-1">ADMIN</span>
              <button
                type="button"
                onClick={handleAdminLogout}
                className="text-[10px] font-mono text-zinc-400 hover:text-white px-2 py-0.5 rounded-full border border-zinc-700 bg-zinc-900 hover:bg-zinc-800 transition-colors"
                title="Sair do modo administrador"
              >
                Sair
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => {
                setAdminAuthError(null);
                setAdminModalOpen(true);
              }}
              className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#0C0C0E] hover:bg-[#15130F] border border-[#2B261D] hover:border-[#D4AF37]/40 text-zinc-400 hover:text-[#D4AF37] font-mono text-[10px] tracking-wider uppercase transition-all"
              title="Acesso de Administrador via MFA"
            >
              <span>🔒</span>
              <span>ADMIN</span>
            </button>
          )}
        </div>
      </header>

      <main className="flex-1 pt-28 pb-16">
        {/* Hero Header */}
        <div className="flex flex-col items-center justify-center mb-12 px-4 text-center">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 mb-4 rounded-full bg-[#0C0C0E] border border-[#D4AF37]/30 shadow-[0_0_15px_rgba(212,175,55,0.08)]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#D4AF37]"></span>
            <span className="font-mono text-[10px] tracking-[0.3em] uppercase text-[#C5A880] font-semibold">
              QUANTITATIVE VALUE BETTING ENGINE
            </span>
          </div>
          <h1 className="text-3xl sm:text-4xl md:text-6xl font-extrabold uppercase tracking-[0.16em] mb-4 text-[#FFFFFF]">
            {mode === 'investments'
              ? 'CARTEIRA DE INVESTIMENTOS'
              : mode === 'calculator' 
              ? 'CALCULADORA DE EV & KELLY' 
              : mode === 'top_picks'
                ? 'HIGHEST EVS (RISK)'
                : mode === 'recommended'
                  ? 'RECOMENDAÇÕES SEGURAS'
                  : 'AGENDA & TODAS AS PROPS'}
          </h1>
          <span className="font-mono text-xs md:text-sm tracking-[0.2em] uppercase text-[#C5A880]/80 max-w-3xl leading-relaxed">
            {mode === 'investments'
              ? 'GESTÃO DE UNIDADES FIXAS (1.0 U), CONFERÊNCIA PÓS-JOGO & AUDITORIA DE ROI'
              : mode === 'calculator' 
              ? 'SIMULADOR PREDITIVO XGBOOST & CRITÉRIO DE GESTÃO DE BANCA' 
              : mode === 'top_picks'
                ? 'MAIORES ASSIMETRIAS MATEMÁTICAS COM RISCO DE DRIFT'
                : mode === 'recommended' 
                  ? 'CURADORIA DE VALOR COM FILTRO DE SEGURANÇA (EV 2.5% - 15%)' 
                  : 'CALENDÁRIO OFICIAL & TODAS AS 138+ LINHAS BETCLIC (SEM FILTRO DE EV)'}
          </span>
        </div>

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative">
          {/* Navigation Bar */}
          <div className="flex flex-wrap gap-3 border-b border-[#2B261D] pb-5 mb-10">
            {navTabs.map((tab) => {
              const isActive = mode === tab.id;
              return (
                <button
                  key={tab.id}
                  className={`px-6 py-2.5 rounded-full font-mono text-xs tracking-widest uppercase transition-all duration-300 flex items-center gap-2.5 ${
                    isActive 
                      ? 'bg-[#FFFFFF] text-[#000000] font-bold shadow-[0_0_20px_rgba(197,168,128,0.25)] border border-[#D4AF37]' 
                      : 'bg-[#0C0C0E] text-zinc-400 border border-[#2B261D] hover:border-[#C5A880]/60 hover:text-[#FFFFFF]'
                  }`}
                  onClick={() => setMode(tab.id)}
                >
                  <span>{tab.label}</span>
                  {tab.badge && (
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-bold transition-colors ${
                      isActive ? 'bg-[#0C0C0E] text-[#D4AF37]' : 'bg-[#000000] text-[#C5A880] border border-[#2B261D]'
                    }`}>
                      {tab.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* 1. SCHEDULE TAB (ALL PROPS & MATCHUPS - ZERO EV FILTERS) */}
          {mode === 'schedule' && (
            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
              {/* Week Selector Bar */}
              <div className="flex items-center gap-1.5 overflow-x-auto pb-3 mb-6 scrollbar-none border-b border-[#2B261D]/60 -mx-2 px-2 sm:mx-0 sm:px-0">
                <span className="text-[11px] font-mono uppercase text-[#D4AF37] font-semibold tracking-wider mr-2 shrink-0 flex items-center gap-1.5">
                  <span>📅</span> Rodada:
                </span>
                {availableWeeks.map((w) => {
                  const isSel = selectedWeek === w;
                  const isCurrent = currentWeek === w;
                  return (
                    <button
                      key={w}
                      onClick={() => {
                        setSelectedWeek(w);
                        setSelectedGame(null);
                      }}
                      className={`px-3 py-1.5 rounded-xl text-xs font-mono tracking-wider transition-all whitespace-nowrap flex items-center gap-1.5 shrink-0 border ${
                        isSel
                          ? 'bg-[#D4AF37] text-black font-bold border-[#D4AF37] shadow-[0_0_12px_rgba(212,175,55,0.35)]'
                          : isCurrent
                          ? 'bg-[#15130F] text-[#D4AF37] border-[#D4AF37]/50 hover:bg-[#201C15]'
                          : 'bg-black text-zinc-400 hover:text-white border-[#2B261D] hover:border-zinc-700'
                      }`}
                    >
                      <span>Semana {w}</span>
                      {isCurrent && (
                        <span className={`text-[9px] px-1 py-0.2 rounded font-bold uppercase ${
                          isSel ? 'bg-black/20 text-black' : 'bg-emerald-500/20 text-emerald-400'
                        }`}>
                          Atual
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Top Controls & Matchups Summary */}
              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
                <div>
                  <h2 className="text-2xl font-bold uppercase tracking-wider flex items-center gap-3">
                    <span>Agenda de Jogos & Todas as Props (Semana {selectedWeek})</span>
                    {selectedWeek === currentWeek && (
                      <span className="text-[10px] font-mono px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 uppercase tracking-widest font-bold">
                        Rodada Atual
                      </span>
                    )}
                  </h2>
                  <p className="text-zinc-400 text-sm mt-1">
                    Selecione um jogo para isolar o confronto ou explore abaixo todas as apostas abertas sem filtros de EV.
                  </p>
                </div>

                <div className="flex items-center gap-3 flex-wrap">
                  <button
                    onClick={() => setShowGamesGrid(!showGamesGrid)}
                    className="border border-[#2B261D] hover:border-[#C5A880]/60 bg-[#0C0C0E] hover:bg-[#15130F] text-[#C5A880] font-mono text-xs tracking-wider py-2.5 px-4 rounded-xl transition-all flex items-center gap-2"
                  >
                    {showGamesGrid ? 'Ocultar Calendário' : 'Ver Calendário de Jogos'}
                  </button>
                  {selectedGame && (
                    <button
                      onClick={() => setSelectedGame(null)}
                      className="border border-[#2B261D] hover:bg-[#15130F] text-white font-mono text-xs tracking-wider py-2.5 px-4 rounded-xl transition-colors flex items-center gap-1.5"
                    >
                      Ver Todos os Jogos da Semana {selectedWeek}
                    </button>
                  )}
                  {isAdmin && (
                    <button 
                      className="bg-[#FFFFFF] text-[#000000] hover:bg-[#F4E8D1] border border-[#D4AF37]/50 font-bold font-mono text-xs tracking-wider py-2.5 px-5 rounded-xl transition-all shadow-[0_0_15px_rgba(212,175,55,0.2)] flex items-center gap-2"
                      onClick={async () => {
                        alert("Iniciando scraper Stealth Playwright e geração de IA... Isso pode levar ~25 segundos.");
                        try {
                          const pRes = await authFetch('/api/run-pipeline', { method: 'POST' });
                          if (!pRes.ok) {
                            const errData = await pRes.json();
                            alert(errData.detail || "Erro ao rodar pipeline.");
                            return;
                          }
                          const res = await fetch(`/api/live-bets?_t=${Date.now()}`, { cache: 'no-store' });
                          setLiveBets(await res.json());
                          alert("Odds e análises de IA atualizadas com sucesso!");
                        } catch (e) {
                          alert("Erro ao rodar scraper e IA.");
                        }
                      }}
                    >
                      ATUALIZAR ODDS & IA
                    </button>
                  )}
                </div>
              </div>

              {/* Games Grid (Expandable/Collapsible) */}
              {showGamesGrid && (
                <div className="mb-12">
                  {(() => {
                    const weekGames = schedule.filter(g => Number(g.week) === Number(selectedWeek));
                    return (
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                        {weekGames.length === 0 ? (
                          <div className="col-span-full text-center py-12">
                            <p className="font-mono text-xs tracking-widest text-[#C5A880]/60 uppercase mb-2">
                              {schedule.length === 0 ? 'Carregando agenda de jogos...' : `Nenhum confronto cadastrado para a Semana ${selectedWeek}`}
                            </p>
                            {selectedWeek !== currentWeek && (
                              <button
                                onClick={() => setSelectedWeek(currentWeek)}
                                className="mt-2 text-xs font-mono text-[#D4AF37] hover:underline"
                              >
                                Ir para a Semana {currentWeek} (Atual) →
                              </button>
                            )}
                          </div>
                        ) : (
                          weekGames.map((game, i) => {
                            const isSelected = selectedGame?.game_id === game.game_id || (selectedGame?.away_team === game.away_team && selectedGame?.home_team === game.home_team);
                            const count = liveBets.filter(b => (b.team === game.away_team || b.team === game.home_team) && (b.week === undefined || b.week === null || Number(b.week) === Number(selectedWeek))).length;

                            return (
                              <div 
                                key={game.game_id || i} 
                                className={`bg-[#0C0C0E] border p-5 rounded-2xl flex flex-col justify-between gap-4 transition-all shadow-lg ${
                                  isSelected 
                                    ? 'border-[#10B981] bg-[#10B981]/10 ring-1 ring-[#10B981]/50 shadow-[0_0_20px_rgba(16,185,129,0.2)]' 
                                    : 'border-[#2B261D] hover:border-[#C5A880]/50 hover:-translate-y-0.5'
                                }`}
                              >
                                <div className="flex justify-between items-start">
                                  <div className="flex items-center gap-3">
                                    <div className="relative w-10 h-10">
                                      <Image src={`/logos/${game.away_team}.png`} alt={game.away_team} fill className="object-contain" />
                                    </div>
                                    <span className="font-bold text-[#C5A880]/50 text-xs">@</span>
                                    <div className="relative w-10 h-10">
                                      <Image src={`/logos/${game.home_team}.png`} alt={game.home_team} fill className="object-contain" />
                                    </div>
                                    <div>
                                      <div className="flex items-center gap-1.5">
                                        <span className="font-bold text-base text-white">{game.away_team}</span>
                                        <span className="text-[#C5A880]/60 text-xs">vs</span>
                                        <span className="font-bold text-base text-white">{game.home_team}</span>
                                      </div>
                                      <div className="text-[11px] text-zinc-500 font-mono mt-0.5 truncate max-w-[150px]">
                                        {game.stadium || 'Estádio NFL'}
                                      </div>
                                    </div>
                                  </div>
                                  <div className="text-right flex-shrink-0">
                                    <div className="font-mono text-[11px] tracking-wider uppercase text-[#C5A880] font-semibold">
                                      {game.gameday}
                                    </div>
                                    <div className="text-zinc-500 text-[11px] font-mono mt-0.5">
                                      {game.gametime} ET
                                    </div>
                                    <div className={`mt-1.5 inline-flex items-center text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${
                                      count > 0 
                                        ? 'bg-[#15130F] text-[#C5A880] border-[#D4AF37]/30' 
                                        : 'bg-[#050505] text-zinc-600 border-[#2B261D]'
                                    }`}>
                                      {count > 0 ? `${count} props` : 'Sem props'}
                                    </div>
                                  </div>
                                </div>

                                {/* Placar e Status de Jogo Finalizado */}
                                {(game.status === 'finished' || (game.home_score !== null && game.away_score !== null)) && (
                                  <div className="mt-1 p-2.5 rounded-xl bg-[#10B981]/15 border border-[#10B981]/35 flex items-center justify-between shadow-[0_0_12px_rgba(16,185,129,0.15)]">
                                    <div className="flex items-center gap-2">
                                      <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse"></span>
                                      <span className="text-[11px] font-mono font-bold text-[#10B981] uppercase tracking-wider">FINALIZADO</span>
                                    </div>
                                    <div className="text-xs font-mono font-bold text-white tracking-wide">
                                      {game.away_team} <span className="text-zinc-300 font-extrabold">{game.away_score}</span> <span className="text-zinc-500 font-normal">@</span> <span className="text-zinc-300 font-extrabold">{game.home_score}</span> {game.home_team}
                                    </div>
                                  </div>
                                )}

                                <div className="flex flex-col gap-2 mt-1">
                                  <div className="flex items-center gap-2">
                                    <button 
                                      onClick={() => {
                                        if (isSelected) {
                                          setSelectedGame(null);
                                        } else {
                                          setSelectedGame(game);
                                          const el = document.getElementById('props-section');
                                          if (el) el.scrollIntoView({ behavior: 'smooth' });
                                        }
                                      }}
                                      className={`flex-1 py-2.5 rounded-xl font-mono text-xs tracking-wider uppercase transition-colors flex items-center justify-center gap-2 ${
                                        isSelected
                                          ? 'bg-[#10B981] text-black font-bold hover:bg-[#10B981]/90 shadow-[0_0_12px_rgba(16,185,129,0.3)]'
                                          : 'bg-[#15130F] hover:bg-[#201C15] text-[#C5A880] border border-[#2B261D]'
                                      }`}
                                    >
                                      {isSelected ? 'SELECIONADO (VER ABAIXO)' : `VER TODAS AS PROPS (${count})`}
                                    </button>
                                    {isSelected && (
                                      <button
                                        onClick={() => setSelectedGame(null)}
                                        className="px-3 py-2.5 bg-[#15130F] hover:bg-[#201C15] text-[#C5A880] rounded-xl font-mono text-xs border border-[#2B261D]"
                                        title="Limpar seleção e ver todos os jogos"
                                      >
                                        Limpar
                                      </button>
                                    )}
                                  </div>

                                  {/* Botão de Box Score e Estatísticas Oficiais */}
                                  {(game.status === 'finished' || (game.home_score !== null && game.away_score !== null)) && (
                                    <button
                                      onClick={() => handleOpenBoxScore(game)}
                                      className="w-full py-2 px-3 rounded-xl bg-[#D4AF37]/10 hover:bg-[#D4AF37]/20 text-[#D4AF37] border border-[#D4AF37]/35 font-mono text-[11px] uppercase tracking-wider flex items-center justify-center gap-2 transition-all shadow-[0_0_10px_rgba(212,175,55,0.1)]"
                                    >
                                      <svg className="w-4 h-4 text-[#D4AF37]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                                      </svg>
                                      <span>Ver Desempenho Real dos Jogadores & Apostas</span>
                                    </button>
                                  )}
                                </div>
                              </div>
                            );
                          })
                        )}
                      </div>
                    );
                  })()}
                </div>
              )}

              {/* Props Section (NO EV FILTER) */}
              <div id="props-section" className="pt-6 border-t border-[#2B261D]">
                {/* Props Header */}
                <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center mb-8 gap-4">
                  <div>
                    <div className="flex items-center gap-3 flex-wrap">
                      <h3 className="text-2xl font-bold uppercase tracking-wider text-white">
                        {selectedGame 
                          ? `Todas as Props: ${selectedGame.away_team} @ ${selectedGame.home_team}` 
                          : `Todas as Apostas da Semana ${selectedWeek}`}
                      </h3>
                      <span className="bg-[#10B981]/10 text-[#10B981] border border-[#10B981]/30 text-xs font-mono px-3 py-1 rounded-full uppercase tracking-wider font-semibold">
                        Sem Filtro de EV ({sortedScheduleBets.length} {sortedScheduleBets.length === 1 ? 'Aposta' : 'Apostas'})
                      </span>
                    </div>
                    <p className="text-[#C5A880]/80 text-sm mt-1.5">
                      {selectedGame 
                        ? `Todas as linhas abertas na Betclic para este jogo (Over, Under, positivas, negativas e assimetrias).`
                        : `Todas as linhas abertas na Betclic para a Semana ${selectedWeek} da NFL sem qualquer filtro de EV.`}
                    </p>
                  </div>

                  {selectedGame && (
                    <button
                      onClick={() => setSelectedGame(null)}
                      className="border border-[#2B261D] hover:bg-[#15130F] text-[#C5A880] font-mono text-xs tracking-wider py-2.5 px-5 rounded-full transition-colors flex items-center gap-2"
                    >
                      Ver Todas as Props da Semana {selectedWeek}
                    </button>
                  )}
                </div>

                {/* Filter and Search Toolbar */}
                <div className="bg-[#0C0C0E] border border-[#2B261D] p-4 rounded-2xl mb-8 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 shadow-xl">
                  {/* Search */}
                  <div className="relative flex-1 min-w-[240px]">
                    <input
                      type="text"
                      placeholder="Buscar jogador ou equipe (ex: Gibbs, DET, Mahomes)..."
                      value={scheduleSearch}
                      onChange={(e) => setScheduleSearch(e.target.value)}
                      className="w-full bg-[#000000] border border-[#2B261D] text-white text-xs font-mono rounded-xl px-4 py-2.5 focus:border-[#C5A880] focus:outline-none placeholder:text-zinc-600 transition-colors"
                    />
                    {scheduleSearch && (
                      <button
                        onClick={() => setScheduleSearch('')}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white text-xs font-mono"
                      >
                        Limpar
                      </button>
                    )}
                  </div>

                  {/* Market Tabs */}
                  <div className="flex items-center gap-2 flex-wrap">
                    {[
                      { key: 'all', label: `TODOS (${marketCounts.all})` },
                      { key: 'rushing_yards', label: `CORRIDAS (${marketCounts.rushing_yards})` },
                      { key: 'receiving_yards', label: `RECEÇÕES (${marketCounts.receiving_yards})` },
                      { key: 'passing_yards', label: `PASSES (${marketCounts.passing_yards})` },
                    ].map(tab => {
                      const isActive = scheduleMarket === tab.key;
                      return (
                        <button
                          key={tab.key}
                          onClick={() => setScheduleMarket(tab.key as any)}
                          className={`px-3 py-1.5 rounded-lg text-xs font-mono tracking-wider transition-all ${
                            isActive
                              ? 'bg-[#FFFFFF] text-[#000000] font-bold border border-[#D4AF37] shadow-[0_0_12px_rgba(212,175,55,0.2)]'
                              : 'bg-[#000000] text-zinc-400 hover:text-white border border-[#2B261D] hover:border-[#C5A880]/50'
                          }`}
                        >
                          {tab.label}
                        </button>
                      );
                    })}
                  </div>

                  {/* Sort */}
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono text-[#C5A880] uppercase tracking-wider hidden sm:inline">Ordenar:</span>
                    <select
                      value={scheduleSort}
                      onChange={(e: any) => setScheduleSort(e.target.value)}
                      className="bg-[#000000] border border-[#2B261D] text-white text-xs font-mono rounded-xl px-3 py-2 focus:border-[#C5A880] focus:outline-none cursor-pointer"
                    >
                      <option value="ev_desc">Maior EV % (Assimetria)</option>
                      <option value="ev_asc">Menor EV %</option>
                      <option value="player_asc">Jogador (A-Z)</option>
                      <option value="line_desc">Linha (Maior primeiro)</option>
                    </select>
                  </div>
                </div>

                {/* Props Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {liveBets.length === 0 ? (
                    <div className="col-span-full text-center py-20 text-zinc-500 font-mono text-sm tracking-widest">
                      Carregando dados das apostas...
                    </div>
                  ) : sortedScheduleBets.length === 0 ? (
                    <div className="col-span-full text-center py-16 bg-[#0C0C0E] border border-[#2B261D] rounded-2xl text-zinc-400 font-mono text-sm tracking-wider shadow-lg">
                      <p className="mb-4">Nenhuma aposta encontrada com os filtros selecionados.</p>
                      <button
                        onClick={() => {
                          setSelectedGame(null);
                          setScheduleSearch('');
                          setScheduleMarket('all');
                        }}
                        className="px-6 py-2.5 bg-[#15130F] hover:bg-[#201C15] text-[#C5A880] border border-[#2B261D] rounded-xl text-xs uppercase tracking-wider transition-colors font-mono"
                      >
                        Limpar Filtros e Ver Todas as Props
                      </button>
                    </div>
                  ) : (
                    groupBetsToProps(sortedScheduleBets).map(prop => (
                      <PropCard 
                        key={prop.id} 
                        propBet={prop} 
                        selectedPick={selections[prop.id]} 
                        onSelectPick={handleSelectPick} 
                        onAddToPortfolio={handleAddBetToPortfolio}
                      />
                    ))
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 2. RECOMMENDED TAB */}
          {mode === 'recommended' && (
            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
              <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center mb-10 gap-6">
                <div>
                  <h2 className="text-2xl font-bold tracking-widest text-white">
                    {selectedGame 
                      ? `Recomendações: ${selectedGame.away_team} @ ${selectedGame.home_team}` 
                      : `Recomendações Seguras (Semana ${currentWeek})`}
                  </h2>
                  <p className="text-[#C5A880]/80 text-sm mt-2 max-w-2xl leading-relaxed">
                    Filtro ajustado para apostas com Expected Value entre <strong className="text-white">+2.5% e +15.0%</strong> (Titulares e Reservas). Exclui distorções causadas por pequenas amostras ou caudas extremas de probabilidade (data drift).
                  </p>
                </div>
                
                <div className="flex flex-wrap gap-4">
                  {selectedGame && (
                    <button 
                      className="border border-[#2B261D] hover:bg-[#15130F] text-[#C5A880] font-mono text-xs tracking-widest py-3 px-6 rounded-full transition-colors"
                      onClick={() => setSelectedGame(null)}
                    >
                      ← TODOS OS JOGOS
                    </button>
                  )}
                  {isAdmin && (
                    <button 
                      className="bg-[#FFFFFF] text-[#000000] hover:bg-[#F4E8D1] border border-[#D4AF37]/50 font-bold font-mono text-xs tracking-widest py-3 px-8 rounded-full transition-all shadow-[0_0_15px_rgba(212,175,55,0.2)] flex items-center gap-2"
                      onClick={async () => {
                        alert("Iniciando scraper Stealth Playwright e geração de IA... Isso pode levar ~25 segundos.");
                        try {
                          const pRes = await authFetch('/api/run-pipeline', { method: 'POST' });
                          if (!pRes.ok) {
                            const errData = await pRes.json();
                            alert(errData.detail || "Erro ao rodar pipeline.");
                            return;
                          }
                          const res = await fetch(`/api/live-bets?_t=${Date.now()}`, { cache: 'no-store' });
                          setLiveBets(await res.json());
                          alert("Odds e análises de IA atualizadas com sucesso!");
                        } catch (e) {
                          alert("Erro ao rodar scraper e IA.");
                        }
                      }}
                    >
                      ATUALIZAR ODDS & IA
                    </button>
                  )}
                </div>
              </div>

              {/* Grid of Recommended Props */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {liveBets.length === 0 ? (
                  <div className="col-span-full text-center py-20 text-[#C5A880]/60 font-mono text-sm tracking-widest">
                    Carregando dados das apostas...
                  </div>
                ) : (
                  (() => {
                    const filtered = liveBets
                      .filter(bet => {
                        const matchGame = !selectedGame || bet.team === selectedGame.away_team || bet.team === selectedGame.home_team;
                        const matchEV = bet.ev_percent >= 2.5 && bet.ev_percent <= 15.0;
                        return matchGame && matchEV;
                      })
                      .sort((a, b) => (b.ev_percent ?? -999) - (a.ev_percent ?? -999));

                    if (filtered.length === 0) {
                      return (
                        <div className="col-span-full text-center py-20 bg-[#0C0C0E] border border-[#2B261D] rounded-2xl text-zinc-400 font-mono text-sm tracking-wider flex flex-col items-center justify-center gap-4">
                          <p>Nenhuma aposta encontrada na faixa de segurança (+2.5% a +15% EV) para este filtro.</p>
                          <button
                            onClick={() => setMode('schedule')}
                            className="px-6 py-2.5 bg-[#15130F] hover:bg-[#201C15] text-[#C5A880] border border-[#2B261D] rounded-xl text-xs uppercase tracking-wider transition-colors font-mono"
                          >
                            Ver Todas as Props deste Jogo na Agenda (Sem Filtro de EV)
                          </button>
                        </div>
                      );
                    }

                    return groupBetsToProps(filtered).map(prop => (
                      <PropCard 
                        key={prop.id} 
                        propBet={prop} 
                        selectedPick={selections[prop.id]} 
                        onSelectPick={handleSelectPick} 
                        onAddToPortfolio={handleAddBetToPortfolio}
                      />
                    ));
                  })()
                )}
              </div>
            </div>
          )}

          {/* 3. HIGHEST EVS (RISK) TAB */}
          {mode === 'top_picks' && (
            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-10 gap-6">
                <div>
                  <h2 className="text-2xl font-bold tracking-widest flex items-center gap-3 text-white">
                    Highest EVs (Risk)
                    <span className="text-xs font-mono font-bold text-[#D4AF37] bg-[#D4AF37]/10 border border-[#D4AF37]/40 px-3 py-1 rounded-full">
                      ALTO RETORNO & RISCO
                    </span>
                  </h2>
                  <p className="text-[#C5A880]/80 text-sm mt-2 max-w-3xl leading-relaxed">
                    Apostas identificadas pelo modelo com maior valor esperado teórico (&gt;12%). 
                    <strong className="text-zinc-200"> Atenção:</strong> Picks com EV muito elevado podem indicar oportunidades desreguladas pela casa de apostas, mas também carregam maior risco decorrente de mudanças no depth chart, lesões recentes ou incerteza em amostras pequenas. Gestão de banca recomendada: Meio-Kelly ou menos.
                  </p>
                </div>

                <button 
                  className="bg-[#0C0C0E] hover:bg-[#15130F] text-[#C5A880] hover:text-white border border-[#2B261D] hover:border-[#D4AF37]/40 font-mono text-xs tracking-widest py-3 px-6 rounded-full transition-all flex items-center gap-2 shrink-0"
                  onClick={async () => {
                    try {
                      const res = await fetch(`/api/top-picks?limit=15&_t=${Date.now()}`, { cache: 'no-store' });
                      setTopPicks(await res.json());
                      alert("Top picks com maior EV atualizados!");
                    } catch (e) {
                      alert("Erro ao buscar top picks.");
                    }
                  }}
                >
                  ATUALIZAR
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {!Array.isArray(topPicks) || topPicks.length === 0 ? (
                  <div className="col-span-full text-center py-20 text-[#C5A880]/60 font-mono text-sm tracking-widest">
                    Nenhuma aposta de alto EV encontrada.
                  </div>
                ) : (
                  groupBetsToProps([...topPicks].sort((a, b) => (b.ev_percent ?? -999) - (a.ev_percent ?? -999))).map(prop => (
                    <PropCard 
                      key={prop.id} 
                      propBet={prop} 
                      selectedPick={selections[prop.id]} 
                      onSelectPick={handleSelectPick} 
                      onAddToPortfolio={handleAddBetToPortfolio}
                    />
                  ))
                )}
              </div>
            </div>
          )}

          {/* 4. REFACTORED CALCULATOR TAB */}
          {mode === 'calculator' && (
            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
              {/* Method Switcher */}
              <div className="flex justify-center mb-10">
                <div className="inline-flex bg-[#0C0C0E] p-1.5 rounded-2xl border border-[#2B261D]">
                  <button
                    onClick={() => setCalcMethod('xgboost')}
                    className={`px-6 py-2.5 rounded-xl font-mono text-xs tracking-widest uppercase transition-all ${
                      calcMethod === 'xgboost'
                        ? 'bg-[#FFFFFF] text-[#000000] font-bold shadow-[0_0_12px_rgba(212,175,55,0.2)] border border-[#D4AF37]'
                        : 'text-zinc-400 hover:text-white'
                    }`}
                  >
                    Modelo Preditivo XGBoost (IA)
                  </button>
                  <button
                    onClick={() => setCalcMethod('manual')}
                    className={`px-6 py-2.5 rounded-xl font-mono text-xs tracking-widest uppercase transition-all ${
                      calcMethod === 'manual'
                        ? 'bg-[#FFFFFF] text-[#000000] font-bold shadow-[0_0_12px_rgba(212,175,55,0.2)] border border-[#D4AF37]'
                        : 'text-zinc-400 hover:text-white'
                    }`}
                  >
                    Calculadora de Probabilidade & Kelly
                  </button>
                </div>
              </div>

              {/* Input Section */}
              <div className="bg-[#0C0C0E] border border-[#2B261D] rounded-3xl p-6 sm:p-10 mb-12 shadow-2xl">
                {calcMethod === 'xgboost' ? (
                  <div>
                    {/* Market Selector */}
                    <div className="mb-8">
                      <label className="block font-mono text-[11px] tracking-widest uppercase text-[#C5A880] mb-3">
                        Selecione o Mercado de Prop
                      </label>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        {[
                          { id: 'passing_yards', label: 'Passing Yards (QBs)' },
                          { id: 'rushing_yards', label: 'Rushing Yards (RBs/QBs)' },
                          { id: 'receiving_yards', label: 'Receiving Yards (WRs/TEs)' },
                        ].map(m => (
                          <button
                            key={m.id}
                            type="button"
                            onClick={() => setMarket(m.id as MarketType)}
                            className={`p-3.5 rounded-xl font-mono text-xs tracking-wider font-semibold border transition-all text-center ${
                              market === m.id
                                ? 'bg-[#15130F] border-[#D4AF37] text-white shadow-lg'
                                : 'bg-[#000000] border-[#2B261D] text-[#C5A880]/80 hover:border-[#C5A880]/40 hover:text-white'
                            }`}
                          >
                            {m.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                      {/* Left: Player and Opponent Selection */}
                      <div>
                        <div className="space-y-4">
                          <div>
                            <label className="block font-mono text-[11px] tracking-widest uppercase text-zinc-400 mb-2">
                              Jogador Ativo ({playersList.length} disponíveis)
                            </label>
                            <select
                              className="w-full bg-zinc-900 border border-zinc-800 text-white p-3.5 outline-none focus:border-zinc-500 transition-colors rounded-xl font-medium"
                              value={selectedPlayer}
                              onChange={e => {
                                const newName = e.target.value;
                                setSelectedPlayer(newName);
                                const found = playersList.find(p => p.player_name === newName);
                                if (found?.opponent_team) {
                                  setSelectedOpponent(found.opponent_team);
                                }
                              }}
                            >
                              {playersList.map(p => {
                                const name = p.player_display_name || p.player_name;
                                const teamPos = p.team ? `(${p.team} • ${p.position || 'NFL'})` : '';
                                return (
                                  <option key={p.player_name} value={p.player_name}>
                                    {name} {teamPos}
                                  </option>
                                );
                              })}
                            </select>
                          </div>

                          {/* Opponent Selection */}
                          <div>
                            <div className="flex justify-between items-center mb-2">
                              <label className="block font-mono text-[11px] tracking-widest uppercase text-zinc-400">
                                Defesa Adversária (Matchup)
                              </label>
                              {(() => {
                                const curPlayer = playersList.find(p => p.player_name === selectedPlayer);
                                if (curPlayer?.opponent_team && selectedOpponent !== curPlayer.opponent_team) {
                                  return (
                                    <button
                                      type="button"
                                      onClick={() => setSelectedOpponent(curPlayer.opponent_team!)}
                                      className="text-[10px] font-mono text-emerald-400 hover:text-emerald-300 underline"
                                    >
                                      Restaurar Oficial ({curPlayer.opponent_team})
                                    </button>
                                  );
                                }
                                return null;
                              })()}
                            </div>
                            <select
                              className="w-full bg-zinc-900 border border-zinc-800 text-white p-3.5 outline-none focus:border-zinc-500 transition-colors rounded-xl font-medium"
                              value={selectedOpponent}
                              onChange={e => setSelectedOpponent(e.target.value)}
                            >
                              {teamsList.map(t => {
                                const curPlayer = playersList.find(p => p.player_name === selectedPlayer);
                                const isScheduled = curPlayer?.opponent_team === t.code;
                                return (
                                  <option key={t.code} value={t.code}>
                                    {t.code} — {t.name} {isScheduled ? `(Oficial Semana ${currentWeek})` : ''}
                                  </option>
                                );
                              })}
                            </select>

                            {(() => {
                              const curPlayer = playersList.find(p => p.player_name === selectedPlayer);
                              if (!curPlayer) return null;
                              const isOfficial = curPlayer.opponent_team === selectedOpponent;
                              return (
                                <div className="mt-2.5">
                                  {isOfficial ? (
                                    <span className="text-[10px] font-mono font-semibold text-emerald-400 bg-emerald-950/60 border border-emerald-500/30 px-2.5 py-1 rounded-md inline-flex items-center gap-1.5">
                                      Confronto Oficial da Semana {currentWeek} ({curPlayer.team} vs {selectedOpponent})
                                    </span>
                                  ) : (
                                    <span className="text-[10px] font-mono font-semibold text-amber-400 bg-amber-950/60 border border-amber-500/30 px-2.5 py-1 rounded-md inline-flex items-center gap-1.5">
                                      Simulação Customizada vs Defesa de {selectedOpponent}
                                    </span>
                                  )}
                                </div>
                              );
                            })()}
                          </div>
                        </div>

                        {/* Recent Features Cards */}
                        <div className="mt-6 bg-zinc-900/60 border border-zinc-800/80 rounded-2xl p-5">
                          <div className="flex justify-between items-center mb-4">
                            <span className="font-mono text-[11px] tracking-widest uppercase text-zinc-400">
                              Métricas do Modelo XGBoost
                            </span>
                            {features && Object.keys(features).length > 6 && (
                              <button
                                type="button"
                                onClick={() => setShowAllFeatures(!showAllFeatures)}
                                className="text-zinc-400 hover:text-white font-mono text-[10px] uppercase underline"
                              >
                                {showAllFeatures ? 'Ver menos' : `Ver todas (${Object.keys(features).length})`}
                              </button>
                            )}
                          </div>

                          {loadingFeatures ? (
                            <div className="text-zinc-500 font-mono text-xs py-6 text-center animate-pulse">
                              Carregando features do jogador...
                            </div>
                          ) : !features || Object.keys(features).length === 0 ? (
                            <div className="text-zinc-500 font-mono text-xs py-6 text-center">
                              Selecione um jogador para carregar seu histórico.
                            </div>
                          ) : (
                            <div className="space-y-2.5">
                              {Object.entries(features)
                                .slice(0, showAllFeatures ? 30 : 6)
                                .map(([key, stat]) => {
                                  const rawVal = stat.value;
                                  let formattedVal = '-';
                                  if (typeof rawVal === 'number') {
                                    formattedVal = rawVal % 1 === 0 ? rawVal.toString() : rawVal.toFixed(1);
                                    if (key.includes('pct') || key.includes('share') || key.includes('rate')) {
                                      if (rawVal <= 1.0) formattedVal = `${(rawVal * 100).toFixed(1)}%`;
                                    }
                                  } else if (rawVal !== null && rawVal !== undefined) {
                                    formattedVal = String(rawVal);
                                  }

                                  const imp = stat.importance ? (stat.importance * 100).toFixed(1) : null;

                                  return (
                                    <div 
                                      key={key} 
                                      className="flex items-center justify-between p-2.5 bg-zinc-950/80 rounded-lg border border-zinc-900 text-xs"
                                    >
                                      <div className="flex flex-col">
                                        <span className="font-medium text-zinc-200">
                                          {formatStatName(key)}
                                        </span>
                                        {imp && (
                                          <span className="font-mono text-[9px] text-zinc-500">
                                            Peso no Modelo: {imp}%
                                          </span>
                                        )}
                                      </div>
                                      <span className="font-mono font-bold text-white bg-zinc-900 px-2.5 py-1 rounded">
                                        {formattedVal}
                                      </span>
                                    </div>
                                  );
                                })}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Right: Lines, Odds, and Stake */}
                      <div className="flex flex-col justify-between">
                        <div className="space-y-5">
                          <div>
                            <label className="block font-mono text-[11px] tracking-widest uppercase text-zinc-400 mb-2">
                              Linha de Jardas da Casa (Over / Under)
                            </label>
                            <input 
                              type="number" 
                              step="0.5" 
                              className="w-full bg-zinc-900 border border-zinc-800 text-white p-3.5 outline-none focus:border-zinc-500 transition-colors rounded-xl font-mono text-lg font-bold"
                              value={line} 
                              onChange={e => setLine(parseFloat(e.target.value) || 0)} 
                            />
                          </div>

                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <label className="block font-mono text-[11px] tracking-widest uppercase text-zinc-400 mb-2">
                                Odd Decimal OVER
                              </label>
                              <input 
                                type="number" 
                                step="0.01" 
                                className="w-full bg-zinc-900 border border-zinc-800 text-white p-3.5 outline-none focus:border-zinc-500 transition-colors rounded-xl font-mono font-semibold"
                                value={oddsOver} 
                                onChange={e => setOddsOver(parseFloat(e.target.value) || 0)} 
                              />
                            </div>
                            <div>
                              <label className="block font-mono text-[11px] tracking-widest uppercase text-zinc-400 mb-2">
                                Odd Decimal UNDER
                              </label>
                              <input 
                                type="number" 
                                step="0.01" 
                                className="w-full bg-zinc-900 border border-zinc-800 text-white p-3.5 outline-none focus:border-zinc-500 transition-colors rounded-xl font-mono font-semibold"
                                value={oddsUnder} 
                                onChange={e => setOddsUnder(parseFloat(e.target.value) || 0)} 
                              />
                            </div>
                          </div>

                          <div>
                            <label className="block font-mono text-[11px] tracking-widest uppercase text-zinc-400 mb-2">
                              Valor da Banca / Stake Base
                            </label>
                            <input 
                              type="number" 
                              step="10" 
                              className="w-full bg-zinc-900 border border-zinc-800 text-white p-3.5 outline-none focus:border-zinc-500 transition-colors rounded-xl font-mono font-semibold"
                              value={stake} 
                              onChange={e => setStake(parseFloat(e.target.value) || 100)} 
                            />
                            <p className="text-[11px] text-zinc-500 mt-1">
                              Usado para projetar o lucro esperado e o dimensionamento Meio-Kelly.
                            </p>
                          </div>
                        </div>

                        <div className="mt-8">
                          <button 
                            onClick={calculateEV}
                            disabled={isCalculating || !selectedPlayer}
                            className={`w-full py-4 rounded-xl font-bold uppercase tracking-widest font-mono text-sm transition-all flex items-center justify-center gap-3 ${
                              isCalculating || !selectedPlayer
                                ? 'bg-zinc-800 text-zinc-500 cursor-not-allowed'
                                : 'bg-white text-black hover:bg-zinc-200 shadow-xl shadow-white/10'
                            }`}
                          >
                            {isCalculating ? (
                              <span>Calculando projeção...</span>
                            ) : (
                              <span>CALCULAR PROJEÇÃO E EXPECTED VALUE</span>
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  /* Manual Mode */
                  <div className="max-w-2xl mx-auto">
                    <div className="mb-6 text-center">
                      <h3 className="text-xl font-bold uppercase tracking-wider mb-2">
                        Calculadora Manual de Probabilidade e Valor Esperado
                      </h3>
                      <p className="text-sm text-zinc-400">
                        Informe sua probabilidade estimada para a aposta e as cotações da casa para obter o EV%, a Odd Justa e a recomendação de Kelly.
                      </p>
                    </div>

                    <div className="space-y-5">
                      <div>
                        <label className="block font-mono text-[11px] tracking-widest uppercase text-zinc-400 mb-2">
                          Sua Probabilidade Estimada para o OVER (%)
                        </label>
                        <div className="relative">
                          <input 
                            type="number" 
                            step="0.5" 
                            min="1" 
                            max="99" 
                            className="w-full bg-zinc-900 border border-zinc-800 text-white p-3.5 outline-none focus:border-zinc-500 transition-colors rounded-xl font-mono text-lg font-bold"
                            value={manualProbOver} 
                            onChange={e => setManualProbOver(parseFloat(e.target.value) || 0)} 
                          />
                          <span className="absolute right-4 top-3.5 font-mono text-zinc-500 font-bold">%</span>
                        </div>
                        <p className="text-[11px] text-zinc-500 mt-1">
                          Probabilidade implícita do UNDER: <strong>{(100 - manualProbOver).toFixed(1)}%</strong>
                        </p>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block font-mono text-[11px] tracking-widest uppercase text-zinc-400 mb-2">
                            Odd Decimal OVER
                          </label>
                          <input 
                            type="number" 
                            step="0.01" 
                            className="w-full bg-zinc-900 border border-zinc-800 text-white p-3.5 outline-none focus:border-zinc-500 transition-colors rounded-xl font-mono font-semibold"
                            value={oddsOver} 
                            onChange={e => setOddsOver(parseFloat(e.target.value) || 0)} 
                          />
                        </div>
                        <div>
                          <label className="block font-mono text-[11px] tracking-widest uppercase text-zinc-400 mb-2">
                            Odd Decimal UNDER
                          </label>
                          <input 
                            type="number" 
                            step="0.01" 
                            className="w-full bg-zinc-900 border border-zinc-800 text-white p-3.5 outline-none focus:border-zinc-500 transition-colors rounded-xl font-mono font-semibold"
                            value={oddsUnder} 
                            onChange={e => setOddsUnder(parseFloat(e.target.value) || 0)} 
                          />
                        </div>
                      </div>

                      <div>
                        <label className="block font-mono text-[11px] tracking-widest uppercase text-zinc-400 mb-2">
                          Valor da Banca / Stake Base
                        </label>
                        <input 
                          type="number" 
                          step="10" 
                          className="w-full bg-zinc-900 border border-zinc-800 text-white p-3.5 outline-none focus:border-zinc-500 transition-colors rounded-xl font-mono font-semibold"
                          value={stake} 
                          onChange={e => setStake(parseFloat(e.target.value) || 100)} 
                        />
                      </div>

                      <div className="pt-4">
                        <button 
                          onClick={calculateEV}
                          disabled={isCalculating}
                          className="w-full py-4 bg-white text-black font-bold uppercase tracking-widest font-mono text-sm rounded-xl hover:bg-zinc-200 transition-colors shadow-lg"
                        >
                          {isCalculating ? 'Calculando...' : 'CALCULAR EV & CRITÉRIO DE KELLY'}
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {calcError && (
                  <div className="mt-6 p-4 bg-rose-950/60 border border-rose-800/80 rounded-xl text-rose-300 font-mono text-xs text-center">
                    {calcError}
                  </div>
                )}
              </div>

              {/* Calculation Results */}
              {calcResult && (
                <div className="animate-in fade-in duration-500 space-y-8">
                  {/* Projected Yards Banner (if XGBoost mode) */}
                  {calcResult.projected_yards !== null && (
                    <div className="bg-gradient-to-r from-zinc-900 via-zinc-850 to-zinc-900 border border-zinc-800 p-6 rounded-2xl flex flex-col md:flex-row items-center justify-between gap-4 shadow-xl">
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-xl bg-white/10 flex items-center justify-center font-mono text-xs font-bold text-emerald-400 border border-white/10">
                          PROJ
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs tracking-widest uppercase text-zinc-400">
                              Projeção Mediana do Modelo XGBoost
                            </span>
                            {calcResult.opponent && (
                              <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                                {calcResult.team ? `${calcResult.team} vs ${calcResult.opponent}` : `vs ${calcResult.opponent}`}
                              </span>
                            )}
                          </div>
                          <div className="text-3xl font-black text-white mt-0.5">
                            {calcResult.projected_yards} jardas
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-6">
                        <div className="text-right">
                          <div className="font-mono text-xs tracking-widest uppercase text-zinc-400">
                            Linha da Casa
                          </div>
                          <div className="text-2xl font-bold text-zinc-300">
                            {line} jardas
                          </div>
                        </div>

                        <div className={`px-4 py-2 rounded-xl font-mono text-xs font-bold uppercase border ${
                          calcResult.projected_yards > line
                            ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/40'
                            : 'bg-indigo-950/80 text-indigo-300 border-indigo-500/40'
                        }`}>
                          {calcResult.projected_yards > line
                            ? `Tendência OVER (+${(calcResult.projected_yards - line).toFixed(1)} yds)`
                            : `Tendência UNDER (${(calcResult.projected_yards - line).toFixed(1)} yds)`}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Dual Result Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    {/* OVER CARD */}
                    <div className={`border rounded-3xl p-8 flex flex-col shadow-2xl transition-all ${
                      calcResult.over.ev > 0 
                        ? 'bg-gradient-to-b from-[#10B981]/15 to-[#0C0C0E] border-[#10B981]/50 shadow-[0_0_25px_rgba(16,185,129,0.15)]' 
                        : 'bg-[#0C0C0E] border-[#2B261D]'
                    }`}>
                      <div className="flex justify-between items-start mb-6">
                        <div>
                          <span className="font-mono text-xs tracking-widest uppercase text-zinc-400">MERCADO</span>
                          <h3 className="text-2xl font-black tracking-wide text-white mt-1">
                            OVER {line}
                          </h3>
                        </div>
                        <span className={`font-mono text-xs font-bold px-3 py-1.5 rounded-full border ${
                          calcResult.over.ev > 0 
                            ? 'bg-emerald-900/60 text-emerald-300 border-emerald-500/50' 
                            : 'bg-rose-950/60 text-rose-300 border-rose-800/50'
                        }`}>
                          {calcResult.over.ev > 0 ? '+EV APOSTA' : '-EV DESFAVORÁVEL'}
                        </span>
                      </div>

                      {/* Main EV Metric */}
                      <div className="p-5 bg-zinc-900/80 border border-zinc-800/80 rounded-2xl mb-6">
                        <div className="flex justify-between items-baseline">
                          <span className="font-mono text-xs tracking-widest text-zinc-400 uppercase">
                            VALOR ESPERADO (EV)
                          </span>
                          <span className={`text-4xl font-black ${
                            calcResult.over.ev > 0 ? 'text-emerald-400' : 'text-rose-400'
                          }`}>
                            {calcResult.over.ev > 0 ? '+' : ''}{calcResult.over.ev.toFixed(2)}%
                          </span>
                        </div>
                        <div className="flex justify-between text-xs mt-2 text-zinc-400 font-mono">
                          <span>Retorno p/ aposta de {stake.toFixed(0)}:</span>
                          <span className={`font-bold ${calcResult.over.profit > 0 ? 'text-emerald-300' : 'text-rose-400'}`}>
                            {calcResult.over.profit > 0 ? '+' : ''}{calcResult.over.profit.toFixed(2)}
                          </span>
                        </div>
                      </div>

                      {/* Probabilities & Edge */}
                      <div className="space-y-3 font-mono text-xs divide-y divide-zinc-900">
                        <div className="flex justify-between py-2">
                          <span className="text-zinc-500">PROBABILIDADE REAL (MODELO)</span>
                          <span className="font-bold text-white">{(calcResult.over.model_prob * 100).toFixed(1)}%</span>
                        </div>
                        <div className="flex justify-between py-2">
                          <span className="text-zinc-500">PROBABILIDADE IMPLÍCITA DA CASA</span>
                          <span className="font-bold text-zinc-300">{(calcResult.over.implied_prob * 100).toFixed(1)}%</span>
                        </div>
                        <div className="flex justify-between py-2">
                          <span className="text-zinc-500">EDGE SOBRE A CASA</span>
                          <span className={`font-bold ${calcResult.over.edge > 0 ? 'text-emerald-400' : 'text-zinc-400'}`}>
                            {calcResult.over.edge > 0 ? '+' : ''}{calcResult.over.edge.toFixed(2)}%
                          </span>
                        </div>
                        <div className="flex justify-between py-2">
                          <span className="text-zinc-500">ODD JUSTA (FAIR ODDS)</span>
                          <span className="font-bold text-white">{calcResult.over.fair_odds.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between py-2">
                          <span className="text-zinc-500">ODD DA CASA DE APOSTAS</span>
                          <span className="font-bold text-white">{oddsOver.toFixed(2)}</span>
                        </div>
                      </div>

                      {/* Kelly Management */}
                      <div className="mt-6 pt-5 border-t border-zinc-800">
                        <div className="font-mono text-[11px] tracking-widest uppercase text-zinc-400 mb-3">
                          GESTÃO DE BANCA (CRITÉRIO DE KELLY)
                        </div>
                        <div className="grid grid-cols-2 gap-3 font-mono text-xs">
                          <div className="bg-zinc-900/60 p-3 rounded-xl border border-zinc-800/80">
                            <span className="text-zinc-500 block text-[10px]">FULL KELLY</span>
                            <span className="text-base font-bold text-white">
                              {calcResult.over.kelly_percent.toFixed(1)}%
                            </span>
                          </div>
                          <div className="bg-zinc-900/60 p-3 rounded-xl border border-zinc-800/80">
                            <span className="text-zinc-500 block text-[10px]">MEIO-KELLY (RECOMENDADO)</span>
                            <span className="text-base font-bold text-emerald-400">
                              {calcResult.over.half_kelly_percent.toFixed(1)}%
                              <span className="text-xs text-zinc-400 ml-1 font-normal">
                                ({calcResult.over.recommended_stake.toFixed(2)})
                              </span>
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* UNDER CARD */}
                    <div className={`border rounded-3xl p-8 flex flex-col shadow-2xl transition-all ${
                      calcResult.under.ev > 0 
                        ? 'bg-gradient-to-b from-[#10B981]/15 to-[#0C0C0E] border-[#10B981]/50 shadow-[0_0_25px_rgba(16,185,129,0.15)]' 
                        : 'bg-[#0C0C0E] border-[#2B261D]'
                    }`}>
                      <div className="flex justify-between items-start mb-6">
                        <div>
                          <span className="font-mono text-xs tracking-widest uppercase text-zinc-400">MERCADO</span>
                          <h3 className="text-2xl font-black tracking-wide text-white mt-1">
                            UNDER {line}
                          </h3>
                        </div>
                        <span className={`font-mono text-xs font-bold px-3 py-1.5 rounded-full border ${
                          calcResult.under.ev > 0 
                            ? 'bg-emerald-900/60 text-emerald-300 border-emerald-500/50' 
                            : 'bg-rose-950/60 text-rose-300 border-rose-800/50'
                        }`}>
                          {calcResult.under.ev > 0 ? '+EV APOSTA' : '-EV DESFAVORÁVEL'}
                        </span>
                      </div>

                      {/* Main EV Metric */}
                      <div className="p-5 bg-zinc-900/80 border border-zinc-800/80 rounded-2xl mb-6">
                        <div className="flex justify-between items-baseline">
                          <span className="font-mono text-xs tracking-widest text-zinc-400 uppercase">
                            VALOR ESPERADO (EV)
                          </span>
                          <span className={`text-4xl font-black ${
                            calcResult.under.ev > 0 ? 'text-emerald-400' : 'text-rose-400'
                          }`}>
                            {calcResult.under.ev > 0 ? '+' : ''}{calcResult.under.ev.toFixed(2)}%
                          </span>
                        </div>
                        <div className="flex justify-between text-xs mt-2 text-zinc-400 font-mono">
                          <span>Retorno p/ aposta de {stake.toFixed(0)}:</span>
                          <span className={`font-bold ${calcResult.under.profit > 0 ? 'text-emerald-300' : 'text-rose-400'}`}>
                            {calcResult.under.profit > 0 ? '+' : ''}{calcResult.under.profit.toFixed(2)}
                          </span>
                        </div>
                      </div>

                      {/* Probabilities & Edge */}
                      <div className="space-y-3 font-mono text-xs divide-y divide-zinc-900">
                        <div className="flex justify-between py-2">
                          <span className="text-zinc-500">PROBABILIDADE REAL (MODELO)</span>
                          <span className="font-bold text-white">{(calcResult.under.model_prob * 100).toFixed(1)}%</span>
                        </div>
                        <div className="flex justify-between py-2">
                          <span className="text-zinc-500">PROBABILIDADE IMPLÍCITA DA CASA</span>
                          <span className="font-bold text-zinc-300">{(calcResult.under.implied_prob * 100).toFixed(1)}%</span>
                        </div>
                        <div className="flex justify-between py-2">
                          <span className="text-zinc-500">EDGE SOBRE A CASA</span>
                          <span className={`font-bold ${calcResult.under.edge > 0 ? 'text-emerald-400' : 'text-zinc-400'}`}>
                            {calcResult.under.edge > 0 ? '+' : ''}{calcResult.under.edge.toFixed(2)}%
                          </span>
                        </div>
                        <div className="flex justify-between py-2">
                          <span className="text-zinc-500">ODD JUSTA (FAIR ODDS)</span>
                          <span className="font-bold text-white">{calcResult.under.fair_odds.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between py-2">
                          <span className="text-zinc-500">ODD DA CASA DE APOSTAS</span>
                          <span className="font-bold text-white">{oddsUnder.toFixed(2)}</span>
                        </div>
                      </div>

                      {/* Kelly Management */}
                      <div className="mt-6 pt-5 border-t border-zinc-800">
                        <div className="font-mono text-[11px] tracking-widest uppercase text-zinc-400 mb-3">
                          GESTÃO DE BANCA (CRITÉRIO DE KELLY)
                        </div>
                        <div className="grid grid-cols-2 gap-3 font-mono text-xs">
                          <div className="bg-zinc-900/60 p-3 rounded-xl border border-zinc-800/80">
                            <span className="text-zinc-500 block text-[10px]">FULL KELLY</span>
                            <span className="text-base font-bold text-white">
                              {calcResult.under.kelly_percent.toFixed(1)}%
                            </span>
                          </div>
                          <div className="bg-zinc-900/60 p-3 rounded-xl border border-zinc-800/80">
                            <span className="text-zinc-500 block text-[10px]">MEIO-KELLY (RECOMENDADO)</span>
                            <span className="text-base font-bold text-emerald-400">
                              {calcResult.under.half_kelly_percent.toFixed(1)}%
                              <span className="text-xs text-zinc-400 ml-1 font-normal">
                                ({calcResult.under.recommended_stake.toFixed(2)})
                              </span>
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 5. INVESTMENTS / PORTFOLIO TAB */}
          {mode === 'investments' && (
            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 space-y-5 sm:space-y-8">
              {/* Notification Banner */}
              {portfolioMessage && (
                <div className="p-3.5 sm:p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 font-mono text-xs flex justify-between items-center shadow-lg">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0"></span>
                    <span>{portfolioMessage}</span>
                  </div>
                  <button onClick={() => setPortfolioMessage(null)} className="text-zinc-500 hover:text-white text-sm font-bold px-2">✕</button>
                </div>
              )}

              {/* Smart Sync Alert if live market odds drifted/changed */}
              {((portfolioTab === 'safe' && liveSafeCount > 0 && portfolioSafeCount !== liveSafeCount) ||
                (portfolioTab === 'safe_flat' && liveSafeFlatCount > 0 && portfolioSafeFlatCount !== liveSafeFlatCount) ||
                (portfolioTab === 'high_risk' && liveHighRiskCount > 0 && portfolioHighRiskCount !== liveHighRiskCount) ||
                (portfolioTab === 'all_props' && liveAllPropsCount > 0 && portfolioAllPropsCount !== liveAllPropsCount)) && (
                <div className="p-3.5 sm:p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-300 font-mono text-xs flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 shadow-lg">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping shrink-0"></span>
                    <span className="text-[11px] sm:text-xs">
                      {portfolioTab === 'safe'
                        ? `Atualização de mercado: Existem ${liveSafeCount} recomendações disponíveis ao vivo vs ${portfolioSafeCount} salvas na carteira dinâmica.`
                        : portfolioTab === 'safe_flat'
                        ? `Atualização de mercado: Existem ${liveSafeFlatCount} recomendações disponíveis ao vivo vs ${portfolioSafeFlatCount} salvas na carteira flat 1u.`
                        : portfolioTab === 'high_risk'
                        ? `Atualização de mercado: Existem ${liveHighRiskCount} apostas de alto risco disponíveis ao vivo vs ${portfolioHighRiskCount} salvas na carteira.`
                        : `Atualização de mercado: Existem ${liveAllPropsCount} props com +EV disponíveis ao vivo vs ${portfolioAllPropsCount} salvas na carteira.`}
                    </span>
                  </div>
                  <button
                    onClick={portfolioTab === 'safe' ? handleImportSafePicks : portfolioTab === 'safe_flat' ? handleImportSafeFlatPicks : portfolioTab === 'high_risk' ? handleImportHighRiskPicks : () => handleImportAllProps('best_side')}
                    disabled={loadingPortfolio || isReadOnly}
                    className={`w-full sm:w-auto px-4 py-2 rounded-lg bg-amber-500 text-black font-bold font-mono text-xs uppercase tracking-wider transition-colors shadow-sm shrink-0 text-center ${
                      isReadOnly ? 'opacity-40 cursor-not-allowed' : 'hover:bg-amber-400'
                    }`}
                    title={isReadOnly ? "Ação bloqueada no modo demonstração (somente leitura)" : ""}
                  >
                    Sincronizar Carteira ({portfolioTab === 'safe' ? liveSafeCount : portfolioTab === 'safe_flat' ? liveSafeFlatCount : portfolioTab === 'high_risk' ? liveHighRiskCount : liveAllPropsCount} Ativos)
                  </button>
                </div>
              )}

              {/* Portfolio Switcher Sub-Tabs */}
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 sm:gap-4 p-1.5 sm:p-2 bg-[#0C0C0E] border border-[#2B261D] rounded-2xl shadow-xl">
                <div className="grid grid-cols-2 lg:flex items-center gap-1 sm:gap-2 p-1 bg-[#15130F] rounded-xl border border-[#2B261D] w-full sm:w-auto">
                  {/* Tab 1: Recomendadas Dinâmica Inteligente */}
                  <button
                    onClick={() => {
                      setPortfolioTab('safe');
                      fetchPortfolio('safe');
                    }}
                    className={`flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-2 px-2 py-2 sm:px-4 sm:py-3 rounded-lg font-mono text-[11px] sm:text-xs uppercase tracking-wider transition-all duration-200 text-center ${
                      portfolioTab === 'safe'
                        ? 'bg-[#10B981] text-black font-bold shadow-[0_0_15px_rgba(16,185,129,0.3)]'
                        : 'text-zinc-400 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    <span className="text-sm">🧠</span>
                    <span className="truncate">
                      <span className="sm:hidden">Dinâmica</span>
                      <span className="hidden sm:inline">Recomendadas (Dinâmica)</span>
                    </span>
                    <span className={`px-1.5 sm:px-2 py-0.5 rounded-full text-[9px] sm:text-[10px] font-bold ${
                      portfolioTab === 'safe' ? 'bg-black/20 text-black' : 'bg-zinc-800 text-zinc-300'
                    }`}>
                      <span className="hidden sm:inline">+EV 2.5%-15% • </span>{portfolioSafeCount}
                    </span>
                  </button>

                  {/* Tab 2: Recomendadas Flat 1u (Sem alocação inteligente) */}
                  <button
                    onClick={() => {
                      setPortfolioTab('safe_flat');
                      fetchPortfolio('safe_flat');
                    }}
                    className={`flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-2 px-2 py-2 sm:px-4 sm:py-3 rounded-lg font-mono text-[11px] sm:text-xs uppercase tracking-wider transition-all duration-200 text-center ${
                      portfolioTab === 'safe_flat'
                        ? 'bg-[#00E5FF] text-black font-bold shadow-[0_0_15px_rgba(0,229,255,0.3)]'
                        : 'text-zinc-400 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    <span className="text-sm">📏</span>
                    <span className="truncate">
                      <span className="sm:hidden">Flat 1u</span>
                      <span className="hidden sm:inline">Recomendadas (Flat 1u)</span>
                    </span>
                    <span className={`px-1.5 sm:px-2 py-0.5 rounded-full text-[9px] sm:text-[10px] font-bold ${
                      portfolioTab === 'safe_flat' ? 'bg-black/20 text-black' : 'bg-zinc-800 text-cyan-300'
                    }`}>
                      <span className="hidden sm:inline">Flat 1.0u • </span>{portfolioSafeFlatCount}
                    </span>
                  </button>

                  {/* Tab 3: Carteira de Alto Risco */}
                  <button
                    onClick={() => {
                      setPortfolioTab('high_risk');
                      fetchPortfolio('high_risk');
                    }}
                    className={`flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-2 px-2 py-2 sm:px-4 sm:py-3 rounded-lg font-mono text-[11px] sm:text-xs uppercase tracking-wider transition-all duration-200 text-center ${
                      portfolioTab === 'high_risk'
                        ? 'bg-amber-500 text-black font-bold shadow-[0_0_15px_rgba(245,158,11,0.3)]'
                        : 'text-zinc-400 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    <span className="text-sm">⚡</span>
                    <span className="truncate">
                      <span className="sm:hidden">Alto Risco</span>
                      <span className="hidden sm:inline">Carteira de Alto Risco</span>
                    </span>
                    <span className={`px-1.5 sm:px-2 py-0.5 rounded-full text-[9px] sm:text-[10px] font-bold ${
                      portfolioTab === 'high_risk' ? 'bg-black/20 text-black' : 'bg-zinc-800 text-amber-400'
                    }`}>
                      <span className="hidden sm:inline">EV &gt; 20% • </span>{portfolioHighRiskCount}
                    </span>
                  </button>

                  {/* Tab 4: All Props */}
                  <button
                    onClick={() => {
                      setPortfolioTab('all_props');
                      fetchPortfolio('all_props');
                    }}
                    className={`flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-2 px-2 py-2 sm:px-4 sm:py-3 rounded-lg font-mono text-[11px] sm:text-xs uppercase tracking-wider transition-all duration-200 text-center ${
                      portfolioTab === 'all_props'
                        ? 'bg-sky-500 text-black font-bold shadow-[0_0_15px_rgba(14,165,233,0.3)]'
                        : 'text-zinc-400 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    <span className="text-sm">🌐</span>
                    <span className="truncate">All Props</span>
                    <span className={`px-1.5 sm:px-2 py-0.5 rounded-full text-[9px] sm:text-[10px] font-bold ${
                      portfolioTab === 'all_props' ? 'bg-black/20 text-black' : 'bg-zinc-800 text-sky-400'
                    }`}>
                      <span className="hidden sm:inline">Todas as Props • </span>{portfolioAllPropsCount}
                    </span>
                  </button>
                </div>

                <div className="text-right px-4 hidden md:block">
                  <span className="text-[11px] font-mono text-zinc-400 block">
                    {portfolioTab === 'safe' 
                      ? 'Alocação quantitativa dinâmica ponderada por IA (Over/Under) e companheiros (+EV 2.5% a 15%)'
                      : portfolioTab === 'safe_flat'
                      ? 'Recomendações com stake fixa uniforme de 1.0 unidade em todas as entradas (+EV 2.5% a 15%)'
                      : portfolioTab === 'high_risk'
                      ? 'Props com desregulagem matemática severa (EV > 20%), alta volatilidade'
                      : 'Universo completo de props do mercado (todas as 227 props avaliadas)'}
                  </span>
                </div>
              </div>

              {/* Top Financial Report: 6 KPI Cards & Dynamic Distribution */}
              {(() => {
                const summary = activeSummary || portfolioSummary;
                return (
                  <>
                    <div>
                      <div className="flex justify-between items-center mb-3 sm:mb-4">
                        <h2 className="text-[11px] sm:text-xs font-mono font-bold uppercase tracking-[0.15em] sm:tracking-[0.2em] text-zinc-400 truncate">
                          {portfolioTab === 'safe' 
                            ? 'Relatório Financeiro • Carteira Conservadora Dinâmica (+EV 2.5% a 15%)' 
                            : portfolioTab === 'safe_flat'
                            ? 'Relatório Financeiro • Recomendações Flat 1.0u (+EV 2.5% a 15%)'
                            : portfolioTab === 'high_risk'
                            ? 'Relatório Financeiro • Carteira de Alto Risco (Apenas EV > 20%)'
                            : 'Relatório Financeiro • Carteira All Props (100% das Props)'}
                        </h2>
                        <span className="text-[10px] sm:text-[11px] font-mono text-zinc-500 whitespace-nowrap ml-2">
                          {portfolioWeekFilter === 'all' ? 'Todas as Semanas • NFL' : `Semana ${portfolioWeekFilter} • NFL`}
                        </span>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 sm:gap-4">
                        {/* Card 1: Capital Alocado (Ativo / Em Aberto) */}
                        <div className="bg-[#0C0C0E] border border-[#2B261D] hover:border-[#C5A880]/40 transition-colors p-3 sm:p-5 rounded-xl sm:rounded-2xl flex flex-col justify-between shadow-lg">
                          <div className="flex justify-between items-start mb-1">
                            <span className="text-[#C5A880]/80 text-[9px] sm:text-[10px] font-mono uppercase tracking-wider block">
                              Capital Alocado
                            </span>
                            <span className="text-[8px] sm:text-[9px] font-mono px-1 sm:px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400/90 border border-amber-500/20">
                              RISCO
                            </span>
                          </div>
                          <span className="text-xl sm:text-2xl lg:text-3xl font-bold font-mono text-white tracking-tight">
                            {summary 
                              ? `${(summary.pending_staked_units !== undefined ? summary.pending_staked_units : summary.total_staked_units).toFixed(2)} u` 
                              : '0.00 u'}
                          </span>
                          <span 
                            className="text-zinc-500 text-[10px] sm:text-[11px] font-mono mt-1 sm:mt-2 block truncate cursor-help"
                            title={summary ? `Total histórico aportado: ${summary.total_staked_units.toFixed(2)} u em ${summary.total_bets} apostas (${summary.settled_staked_units.toFixed(2)} u já faturadas)` : ''}
                          >
                            {summary 
                              ? `${summary.pending_count} ativas (${summary.avg_stake_units ? `méd ${summary.avg_stake_units.toFixed(2)}u` : '1.0 u'})` 
                              : 'Nenhuma aposta'}
                          </span>
                        </div>

                        {/* Card 2: Liquidation Status */}
                        <div 
                          className="bg-[#0C0C0E] border border-[#2B261D] hover:border-[#C5A880]/40 transition-colors p-3 sm:p-5 rounded-xl sm:rounded-2xl flex flex-col justify-between shadow-lg"
                          title={summary ? `Detalhamento: ${summary.won_count}W (Greens) / ${summary.lost_count}L (Reds) / ${summary.push_count}P (Pushes/Anuladas)` : ''}
                        >
                          <span className="text-[#C5A880]/80 text-[9px] sm:text-[10px] font-mono uppercase tracking-wider block mb-1">
                            Liquidação
                          </span>
                          <span className="text-xl sm:text-2xl lg:text-3xl font-bold font-mono text-white tracking-tight">
                            {summary ? `${summary.settled_count}/${summary.total_bets}` : '0/0'}
                          </span>
                          <span className="text-[#D4AF37] text-[10px] sm:text-[11px] font-mono mt-1 sm:mt-2 block truncate">
                            {summary ? `${summary.settled_staked_units.toFixed(2)} u (${summary.pending_count} pend)` : '0 pendentes'}
                          </span>
                        </div>

                        {/* Card 3: Net Profit */}
                        <div className="bg-[#0C0C0E] border border-[#2B261D] hover:border-[#C5A880]/40 transition-colors p-3 sm:p-5 rounded-xl sm:rounded-2xl flex flex-col justify-between shadow-lg">
                          <span className="text-[#C5A880]/80 text-[9px] sm:text-[10px] font-mono uppercase tracking-wider block mb-1">
                            Resultado Líquido
                          </span>
                          <span className={`text-xl sm:text-2xl lg:text-3xl font-bold font-mono tracking-tight ${
                            (summary?.net_profit_units ?? 0) >= 0 ? 'text-[#10B981]' : 'text-rose-400'
                          }`}>
                            {summary 
                              ? `${summary.net_profit_units >= 0 ? '+' : ''}${summary.net_profit_units.toFixed(2)} u`
                              : '0.00 u'}
                          </span>
                          <span className={`text-[10px] sm:text-[11px] font-mono mt-1 sm:mt-2 block truncate ${
                            (summary?.roi_percent ?? 0) >= 0 ? 'text-[#10B981]' : 'text-rose-500'
                          }`}>
                            ROI: {summary ? `${summary.roi_percent >= 0 ? '+' : ''}${summary.roi_percent.toFixed(1)}%` : '0.0%'}
                          </span>
                        </div>

                        {/* Card 4: Win Rate */}
                        <div 
                          className="bg-[#0C0C0E] border border-[#2B261D] hover:border-[#C5A880]/40 transition-colors p-3 sm:p-5 rounded-xl sm:rounded-2xl flex flex-col justify-between shadow-lg"
                          title={summary ? `${summary.won_count} vitórias, ${summary.lost_count} derrotas, ${summary.push_count} pushes/anuladas. Total liquidado: ${summary.settled_count}. Decisive Win Rate: ${summary.win_rate_percent.toFixed(1)}%. Overall Hit Rate: ${(summary.hit_rate_percent ?? ((summary.won_count / (summary.settled_count || 1)) * 100)).toFixed(1)}%.` : ''}
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-[#C5A880]/80 text-[9px] sm:text-[10px] font-mono uppercase tracking-wider block mb-1">
                              Taxa de Acerto
                            </span>
                            {summary && summary.push_count > 0 && (
                              <span 
                                className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                title="Hit rate global sobre todas as liquidadas (inclui empates/pushes)"
                              >
                                {(summary.hit_rate_percent ?? ((summary.won_count / (summary.settled_count || 1)) * 100)).toFixed(1)}% tot
                              </span>
                            )}
                          </div>
                          <span className="text-xl sm:text-2xl lg:text-3xl font-bold font-mono text-white tracking-tight">
                            {summary ? `${summary.win_rate_percent.toFixed(1)}%` : '0.0%'}
                          </span>
                          <span className="text-[#C5A880]/60 text-[10px] sm:text-[11px] font-mono mt-1 sm:mt-2 block truncate">
                            {summary 
                              ? `${summary.won_count}W - ${summary.lost_count}L${summary.push_count > 0 ? ` - ${summary.push_count}P` : ''} (${summary.settled_count} liq)` 
                              : '0W - 0L'}
                          </span>
                        </div>

                        {/* Card 5: Average Odds */}
                        <div className="bg-[#0C0C0E] border border-[#2B261D] hover:border-[#C5A880]/40 transition-colors p-3 sm:p-5 rounded-xl sm:rounded-2xl flex flex-col justify-between shadow-lg">
                          <span className="text-[#C5A880]/80 text-[9px] sm:text-[10px] font-mono uppercase tracking-wider block mb-1">
                            Odd Média
                          </span>
                          <span className="text-xl sm:text-2xl lg:text-3xl font-bold font-mono text-white tracking-tight">
                            {summary && summary.avg_odds > 0 ? summary.avg_odds.toFixed(2) : '1.82'}
                          </span>
                          <span className="text-zinc-500 text-[10px] sm:text-[11px] font-mono mt-1 sm:mt-2 block truncate">
                            BE: {summary && summary.avg_odds > 0 ? `${(100 / summary.avg_odds).toFixed(1)}%` : '54.9%'}
                          </span>
                        </div>

                        {/* Card 6: Profit Factor */}
                        <div className="bg-[#0C0C0E] border border-[#2B261D] hover:border-[#C5A880]/40 transition-colors p-3 sm:p-5 rounded-xl sm:rounded-2xl flex flex-col justify-between shadow-lg">
                          <span className="text-[#C5A880]/80 text-[9px] sm:text-[10px] font-mono uppercase tracking-wider block mb-1">
                            Profit Factor
                          </span>
                          <span className="text-xl sm:text-2xl lg:text-3xl font-bold font-mono text-white tracking-tight">
                            {summary && summary.profit_factor !== null && summary.profit_factor !== undefined
                              ? summary.profit_factor.toFixed(2)
                              : 'N/A'}
                          </span>
                          <span className="text-zinc-500 text-[10px] sm:text-[11px] font-mono mt-1 sm:mt-2 block">
                            Ganho / Perda
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Dynamic Sizing & AI Conviction Panel */}
                    {summary?.stake_distribution && (
                      <div className="bg-[#0C0C0E] border border-[#2B261D] rounded-2xl p-3.5 sm:p-5 shadow-xl grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-5">
                        {/* Col 1: Sizing Distribution */}
                        <div className="lg:col-span-2">
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 sm:gap-2 mb-2">
                            <div className="flex items-center gap-2">
                              <span className="text-[#C5A880] text-sm">⚖️</span>
                              <h3 className="text-[11px] sm:text-xs font-mono font-bold uppercase tracking-wider text-white">
                                Distribuição de Unidades Dinâmicas (Apostas Ativas)
                              </h3>
                            </div>
                            <span className="text-[10px] sm:text-[11px] font-mono text-zinc-400">
                              Stake Médio: <strong className="text-[#D4AF37]">{summary.avg_stake_units?.toFixed(2) ?? '1.00'} u</strong>
                            </span>
                          </div>
                          <p className="text-[10px] sm:text-[11px] font-sans text-zinc-400 mb-3 leading-relaxed">
                            Alocação inteligente calibrada por EV (+2.5% a 15%), desconto de cauda estatística e multiplicador heurístico/IA considerando lesões (Over vs Under) e correlações de elenco.
                          </p>
                          <div className="grid grid-cols-5 gap-1 sm:gap-2 font-mono text-center">
                            <div className="bg-zinc-900/80 border border-zinc-800 rounded-lg sm:rounded-xl p-1.5 sm:p-2.5">
                              <div className="text-[8px] sm:text-[10px] text-zinc-500 uppercase tracking-wider truncate">0.50 u</div>
                              <div className="text-sm sm:text-lg font-bold text-zinc-300 mt-0.5">{summary.stake_distribution['0.5u'] || 0}</div>
                              <div className="text-[8px] sm:text-[9px] text-zinc-500 mt-0.5 truncate">Cauda</div>
                            </div>
                            <div className="bg-zinc-900/80 border border-zinc-800 rounded-lg sm:rounded-xl p-1.5 sm:p-2.5">
                              <div className="text-[8px] sm:text-[10px] text-zinc-400 uppercase tracking-wider truncate">0.75 u</div>
                              <div className="text-sm sm:text-lg font-bold text-zinc-200 mt-0.5">{summary.stake_distribution['0.75u'] || 0}</div>
                              <div className="text-[8px] sm:text-[9px] text-zinc-500 mt-0.5 truncate">2.5-5%</div>
                            </div>
                            <div className="bg-zinc-900/80 border border-[#2B261D] rounded-lg sm:rounded-xl p-1.5 sm:p-2.5">
                              <div className="text-[8px] sm:text-[10px] text-[#C5A880]/80 uppercase tracking-wider truncate">1.00 u</div>
                              <div className="text-sm sm:text-lg font-bold text-white mt-0.5">{summary.stake_distribution['1.0u'] || 0}</div>
                              <div className="text-[8px] sm:text-[9px] text-zinc-500 mt-0.5 truncate">5-10%</div>
                            </div>
                            <div className="bg-[#C5A880]/10 border border-[#C5A880]/30 rounded-lg sm:rounded-xl p-1.5 sm:p-2.5">
                              <div className="text-[8px] sm:text-[10px] text-[#D4AF37] uppercase tracking-wider truncate">1.25-1.5u</div>
                              <div className="text-sm sm:text-lg font-bold text-[#D4AF37] mt-0.5">{summary.stake_distribution['1.25u-1.5u'] || 0}</div>
                              <div className="text-[8px] sm:text-[9px] text-[#C5A880]/70 mt-0.5 truncate">Alta Convicção</div>
                            </div>
                            <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg sm:rounded-xl p-1.5 sm:p-2.5">
                              <div className="text-[8px] sm:text-[10px] text-emerald-400 uppercase tracking-wider truncate">1.75 u+</div>
                              <div className="text-sm sm:text-lg font-bold text-emerald-300 mt-0.5">{summary.stake_distribution['1.75u+'] || 0}</div>
                              <div className="text-[8px] sm:text-[9px] text-emerald-500/70 mt-0.5 truncate">Edge Máx</div>
                            </div>
                          </div>
                        </div>

                        {/* Col 2: Highest Conviction Bet */}
                        <div 
                          onClick={() => {
                            if (summary.highest_conviction_pick) {
                              const match = portfolioBets.find(b => 
                                b.player_name === summary.highest_conviction_pick?.player_name && 
                                b.market === summary.highest_conviction_pick?.market
                              );
                              if (match) setSelectedAiBet(match);
                            }
                          }}
                          className={`bg-zinc-900/50 border border-zinc-800 rounded-xl p-3.5 sm:p-4 flex flex-col justify-between transition-all ${
                            summary.highest_conviction_pick ? 'cursor-pointer hover:border-[#C5A880]/60 hover:bg-zinc-900/80 group' : ''
                          }`}
                          title={summary.highest_conviction_pick ? "Clique para abrir a justificativa completa da IA" : ""}
                        >
                          <div>
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-[9px] sm:text-[10px] font-mono uppercase tracking-wider text-[#C5A880] flex items-center gap-1.5">
                                <span className="inline-block w-2 h-2 rounded-full bg-[#D4AF37] animate-pulse"></span>
                                Maior Convicção do Modelo
                              </span>
                              {summary.highest_conviction_pick && (
                                <span className="px-2 py-0.5 rounded-full bg-[#C5A880]/20 text-[#D4AF37] border border-[#C5A880]/40 text-[9px] sm:text-[10px] font-mono font-bold">
                                  {summary.highest_conviction_pick.units.toFixed(2)} u
                                </span>
                              )}
                            </div>
                            {summary.highest_conviction_pick ? (
                              <>
                                <div className="text-sm font-bold text-white font-sans mt-1 group-hover:text-[#D4AF37] transition-colors flex items-center justify-between">
                                  <span>{summary.highest_conviction_pick.player_name}</span>
                                  <span className="text-[10px] sm:text-[11px] font-mono text-[#C5A880]/70 group-hover:text-[#D4AF37] transition-colors">🧠 Análise ↗</span>
                                </div>
                                <div className="text-[11px] sm:text-xs font-mono text-zinc-300 mt-1.5 flex items-center gap-1.5 sm:gap-2 flex-wrap">
                                  <span className={`px-1.5 py-0.5 rounded text-[9px] sm:text-[10px] font-bold ${
                                    summary.highest_conviction_pick.side.toLowerCase() === 'over'
                                      ? 'bg-sky-500/15 text-sky-300 border border-sky-500/30'
                                      : 'bg-purple-500/15 text-purple-300 border border-purple-500/30'
                                  }`}>
                                    {summary.highest_conviction_pick.side.toUpperCase()} {summary.highest_conviction_pick.line}
                                  </span>
                                  <span className="text-zinc-400">
                                    {summary.highest_conviction_pick.market === 'rushing_yards' ? 'Jardas Terrestres' :
                                     summary.highest_conviction_pick.market === 'receiving_yards' ? 'Jardas Recepção' :
                                     summary.highest_conviction_pick.market === 'passing_yards' ? 'Jardas Passe' : summary.highest_conviction_pick.market}
                                  </span>
                                  <span className="text-emerald-400 font-bold">
                                    +{summary.highest_conviction_pick.ev_percent.toFixed(1)}% EV
                                  </span>
                                </div>
                                <p className="text-[10px] sm:text-[11px] font-sans text-zinc-400 mt-2 line-clamp-2 italic">
                                  &ldquo;{summary.highest_conviction_pick.rationale}&rdquo;
                                </p>
                              </>
                            ) : (
                              <div className="text-xs text-zinc-500 font-mono mt-4">
                                Nenhuma aposta com stake calculada.
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                );
              })()}

              {/* Equity Curve SVG Chart */}
              {(() => {
                const curve = equityCurve && equityCurve.length > 0 ? equityCurve : [{ bet_index: 0, cum_units: 0.0 }];
                const values = curve.map(c => Number(c.cum_units || 0));
                const minVal = Math.min(0, ...values);
                const maxVal = Math.max(0, ...values);
                const range = (maxVal - minVal) === 0 ? 2 : (maxVal - minVal);
                const padding = range * 0.15;
                const chartMin = minVal - padding;
                const chartMax = maxVal + padding;
                const chartRange = chartMax - chartMin;

                const width = 800;
                const height = 180;
                const padX = 40;
                const padY = 20;
                const innerW = width - padX * 2;
                const innerH = height - padY * 2;

                const getY = (val: number) => padY + innerH - ((val - chartMin) / chartRange) * innerH;
                const getX = (idx: number) => padX + (curve.length <= 1 ? 0.5 : (idx / (curve.length - 1))) * innerW;
                const zeroY = getY(0);

                const points = curve.map((c, idx) => `${getX(idx)},${getY(Number(c.cum_units || 0))}`).join(' ');
                const lastIdx = curve.length - 1;
                const areaPoints = `${getX(0)},${zeroY} ${points} ${getX(lastIdx)},${zeroY}`;
                const lastVal = Number(curve[lastIdx].cum_units || 0);
                const isPositive = lastVal >= 0;

                return (
                  <div className="w-full bg-[#0C0C0E] border border-[#2B261D] rounded-2xl p-4 sm:p-6 shadow-2xl">
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 mb-4">
                      <div>
                        <h3 className="font-mono text-xs uppercase tracking-widest text-[#FFFFFF] font-bold">
                          Evolução Patrimonial da Carteira (Unidades Acumuladas)
                        </h3>
                        <p className="text-[#C5A880]/70 text-[10px] sm:text-[11px] font-mono mt-0.5">
                          Trajetória líquida de ganhos e perdas a cada aposta liquidada
                        </p>
                      </div>
                      <div className="flex items-center gap-2 sm:gap-3">
                        <span className="text-xs font-mono text-zinc-400">Saldo Atual:</span>
                        <span className={`font-mono text-sm sm:text-base font-bold px-2.5 sm:px-3 py-1 rounded-lg border ${
                          isPositive 
                            ? 'bg-[#10B981]/10 text-[#10B981] border-[#10B981]/40 shadow-[0_0_12px_rgba(16,185,129,0.2)]' 
                            : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                        }`}>
                          {isPositive ? '+' : ''}{lastVal.toFixed(2)} u
                        </span>
                      </div>
                    </div>

                    <div className="relative w-full h-36 sm:h-44">
                      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full overflow-visible" preserveAspectRatio="none">
                        <defs>
                          <linearGradient id="equityGradGreen" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#10B981" stopOpacity="0.30" />
                            <stop offset="100%" stopColor="#10B981" stopOpacity="0.0" />
                          </linearGradient>
                          <linearGradient id="equityGradRed" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.30" />
                            <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.0" />
                          </linearGradient>
                        </defs>

                        {/* Zero break-even reference line */}
                        <line
                          x1={padX}
                          y1={zeroY}
                          x2={width - padX}
                          y2={zeroY}
                          stroke="#52525b"
                          strokeWidth="1.5"
                          strokeDasharray="4 4"
                        />
                        <text x={padX + 6} y={zeroY - 6} fill="#71717a" fontSize="10" fontFamily="monospace">
                          0.0 u (Ponto de Equilíbrio)
                        </text>

                        {curve.length > 1 && (
                          <>
                            {/* Area under curve */}
                            <polygon
                              points={areaPoints}
                              fill={isPositive ? "url(#equityGradGreen)" : "url(#equityGradRed)"}
                            />

                            {/* Line */}
                            <polyline
                              fill="none"
                              stroke={isPositive ? "#10B981" : "#f43f5e"}
                              strokeWidth="2.5"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              points={points}
                            />

                            {/* Data points */}
                            {curve.map((c, idx) => (
                              <circle
                                key={idx}
                                cx={getX(idx)}
                                cy={getY(Number(c.cum_units || 0))}
                                r={idx === lastIdx ? 5 : 3}
                                fill={idx === 0 ? "#71717a" : (c.step_units >= 0 ? "#10B981" : "#f43f5e")}
                                stroke="#18181b"
                                strokeWidth="2"
                              >
                                <title>{`${c.player || 'Início'}: ${c.step_units >= 0 ? '+' : ''}${c.step_units} u | Total: ${c.cum_units >= 0 ? '+' : ''}${c.cum_units} u`}</title>
                              </circle>
                            ))}
                          </>
                        )}
                      </svg>
                    </div>
                  </div>
                );
              })()}

              {/* Action and Control Bar */}
              <div className="bg-[#0C0C0E] border border-[#2B261D] p-3.5 sm:p-5 rounded-2xl flex flex-col gap-3 sm:gap-4 shadow-xl">
                {isReadOnly ? (
                  <div className="w-full flex flex-col sm:flex-row items-start sm:items-center justify-between p-3 sm:p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 font-mono text-xs gap-3">
                    <div className="flex items-center gap-2">
                      <span className="text-base shrink-0">🔒</span>
                      <div>
                        <span className="font-bold uppercase tracking-wider">Modo Visitante (Somente Leitura)</span>
                        <span className="text-zinc-400 text-[11px] block sm:inline sm:ml-2">
                          Botões de liquidação travados para demonstração segura.
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
                      <button
                        type="button"
                        onClick={() => handleToggleReadOnly(false)}
                        className="w-full sm:w-auto px-3.5 py-1.5 rounded-lg bg-amber-400 hover:bg-amber-300 text-black font-mono font-bold text-xs uppercase tracking-wider transition-all shadow-md flex items-center justify-center gap-1.5"
                        title="Desbloquear modo administrador para liquidar resultados e editar carteira"
                      >
                        <span>🔓 Desbloquear Modo Admin</span>
                      </button>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 uppercase font-bold tracking-wider shrink-0 hidden sm:inline-block">
                        Visitante
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="w-full flex flex-col sm:flex-row items-start sm:items-center justify-between p-3 rounded-xl bg-emerald-950/20 border border-emerald-500/30 text-emerald-400 font-mono text-xs gap-2">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0" />
                      <span className="font-bold uppercase tracking-wider">Modo Administrador Ativo</span>
                      <span className="text-zinc-400 text-[11px] hidden sm:inline">
                        — Controle total liberado.
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleToggleReadOnly(true)}
                      className="w-full sm:w-auto px-2.5 py-1 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 border border-zinc-700 text-[11px] font-mono transition-colors text-center"
                      title="Ativar modo visitante (somente leitura) para demonstrações seguras"
                    >
                      <span>🔒 Ativar Modo Visitante</span>
                    </button>
                  </div>
                )}

                <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-2.5 sm:gap-3">
                  {/* Primary Operational Group */}
                  <div className="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-2.5">
                    <button
                      onClick={() => handleSettlePortfolio()}
                      disabled={loadingPortfolio || isReadOnly}
                      className={`w-full sm:w-auto px-4 sm:px-5 py-2.5 rounded-xl bg-[#10B981] text-black font-mono font-bold text-xs uppercase tracking-wider shadow-[0_0_15px_rgba(16,185,129,0.25)] flex items-center justify-center gap-2 transition-all ${
                        isReadOnly ? 'opacity-40 cursor-not-allowed' : 'hover:bg-[#10B981]/90 hover:shadow-[0_0_20px_rgba(16,185,129,0.35)]'
                      }`}
                      title={isReadOnly ? "Ação bloqueada no modo somente leitura. Clique em 'Desbloquear Modo Admin' acima." : "Verificar e liquidar resultados com as estatísticas oficiais da NFL"}
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span>{loadingPortfolio ? 'Verificando...' : 'Verificar e Liquidar Resultados'}</span>
                    </button>

                    {portfolioTab === 'safe' ? (
                      <button
                        onClick={handleImportSafePicks}
                        disabled={loadingPortfolio || isReadOnly}
                        className={`w-full sm:w-auto px-4 py-2.5 rounded-xl bg-[#15130F] text-white font-mono text-xs uppercase tracking-wider border border-[#2B261D] transition-all flex items-center justify-center gap-2 shadow-[0_0_12px_rgba(16,185,129,0.12)] ${
                          isReadOnly ? 'opacity-40 cursor-not-allowed' : 'hover:bg-[#201C15] hover:border-[#10B981]/50'
                        }`}
                        title={isReadOnly ? "Ação bloqueada no modo somente leitura" : "Sincronizar recomendações seguras com sizing dinâmico"}
                      >
                        <svg className="w-4 h-4 text-[#10B981]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                        </svg>
                        <span>Sincronizar Dinâmica (+EV 2.5% a 15%)</span>
                      </button>
                    ) : portfolioTab === 'safe_flat' ? (
                      <button
                        onClick={handleImportSafeFlatPicks}
                        disabled={loadingPortfolio || isReadOnly}
                        className={`w-full sm:w-auto px-4 py-2.5 rounded-xl bg-[#15130F] text-cyan-300 font-mono text-xs uppercase tracking-wider border border-cyan-900/40 transition-all flex items-center justify-center gap-2 shadow-[0_0_12px_rgba(0,229,255,0.15)] ${
                          isReadOnly ? 'opacity-40 cursor-not-allowed' : 'hover:bg-[#201C15] hover:border-cyan-400/50'
                        }`}
                        title={isReadOnly ? "Ação bloqueada no modo somente leitura" : "Sincronizar recomendações com stake fixa de 1.0 unidade"}
                      >
                        <svg className="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                        </svg>
                        <span>Sincronizar Flat 1.0u (+EV 2.5% a 15%)</span>
                      </button>
                    ) : portfolioTab === 'high_risk' ? (
                      <button
                        onClick={handleImportHighRiskPicks}
                        disabled={loadingPortfolio || isReadOnly}
                        className={`w-full sm:w-auto px-4 py-2.5 rounded-xl bg-[#15130F] text-amber-300 font-mono text-xs uppercase tracking-wider border border-amber-900/40 transition-all flex items-center justify-center gap-2 shadow-[0_0_12px_rgba(245,158,11,0.15)] ${
                          isReadOnly ? 'opacity-40 cursor-not-allowed' : 'hover:bg-[#201C15] hover:border-amber-500/50'
                        }`}
                        title={isReadOnly ? "Ação bloqueada no modo somente leitura" : "Sincronizar apostas de alto risco"}
                      >
                        <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                        <span>Sincronizar Apostas (EV &gt; 20%)</span>
                      </button>
                    ) : (
                      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 w-full sm:w-auto">
                        <button
                          onClick={() => handleImportAllProps('best_side')}
                          disabled={loadingPortfolio || isReadOnly}
                          className={`w-full sm:w-auto px-4 py-2.5 rounded-xl bg-[#15130F] text-sky-300 font-mono text-xs uppercase tracking-wider border border-sky-900/40 transition-all flex items-center justify-center gap-2 shadow-[0_0_12px_rgba(14,165,233,0.15)] ${
                            isReadOnly ? 'opacity-40 cursor-not-allowed' : 'hover:bg-[#201C15] hover:border-sky-500/50'
                          }`}
                          title={isReadOnly ? "Ação bloqueada no modo somente leitura" : "Sincronizar todas as props"}
                        >
                          <svg className="w-4 h-4 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064" />
                          </svg>
                          <span>Sincronizar Props (+EV) ({liveAllPropsCount || 155})</span>
                        </button>
                        <button
                          onClick={() => handleImportAllProps('all_rows')}
                          disabled={loadingPortfolio || isReadOnly}
                          className={`w-full sm:w-auto px-3 py-2.5 rounded-xl bg-black text-zinc-400 font-mono text-[11px] uppercase tracking-wider border border-zinc-800 transition-all text-center ${
                            isReadOnly ? 'opacity-40 cursor-not-allowed' : 'hover:bg-zinc-900 hover:text-white'
                          }`}
                          title={isReadOnly ? "Ação bloqueada no modo somente leitura" : "Importa todas as linhas brutas com valor esperado positivo"}
                        >
                          Linhas Brutas
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Secondary Analysis & Management Group */}
                  <div className="grid grid-cols-3 sm:flex items-center gap-1.5 sm:gap-2 w-full sm:w-auto">
                    <button
                      onClick={handleSimulateSettlement}
                      disabled={loadingPortfolio || isReadOnly}
                      className={`px-2 sm:px-3.5 py-2 sm:py-2.5 rounded-xl bg-black/60 text-[#D4AF37] font-mono text-[11px] sm:text-xs uppercase tracking-wider border border-[#D4AF37]/30 transition-all flex items-center justify-center gap-1 text-center ${
                        isReadOnly ? 'opacity-40 cursor-not-allowed' : 'hover:bg-[#15130F] hover:border-[#D4AF37]/60'
                      }`}
                      title={isReadOnly ? "Ação bloqueada no modo somente leitura" : "Simula a conferência das apostas pendentes"}
                    >
                      <span>🎲 Simular</span>
                    </button>

                    <button
                      onClick={handleResetSettlement}
                      disabled={loadingPortfolio || isReadOnly}
                      className={`px-2 sm:px-3 py-2 sm:py-2.5 rounded-xl bg-[#000000] text-[#C5A880]/80 hover:text-white font-mono text-[11px] sm:text-xs uppercase tracking-wider border border-[#2B261D] hover:border-zinc-700 transition-all text-center flex items-center justify-center ${
                        isReadOnly ? 'opacity-40 cursor-not-allowed' : 'hover:bg-[#15130F]'
                      }`}
                      title={isReadOnly ? "Ação bloqueada no modo somente leitura" : "Retorna todas as apostas para o status Pendente"}
                    >
                      Resetar
                    </button>

                    <button
                      onClick={handleClearPortfolio}
                      disabled={loadingPortfolio || isReadOnly}
                      className={`px-2 sm:px-3 py-2 sm:py-2.5 rounded-xl bg-[#000000] text-rose-400/80 hover:text-rose-300 font-mono text-[11px] sm:text-xs uppercase tracking-wider border border-rose-900/30 hover:border-rose-900/60 transition-all text-center flex items-center justify-center ${
                        isReadOnly ? 'opacity-40 cursor-not-allowed' : 'hover:bg-rose-950/30'
                      }`}
                      title={isReadOnly ? "Ação bloqueada no modo somente leitura" : "Limpar carteira"}
                    >
                      Limpar
                    </button>
                  </div>
                </div>
              </div>

              {/* Ledger / Table of Bets in Portfolio */}
              <div className="bg-[#0C0C0E] border border-[#2B261D] rounded-2xl overflow-hidden shadow-2xl">
                {/* Table Header & Search/Game Filters */}
                <div className="p-3.5 sm:p-5 border-b border-[#2B261D] flex flex-col gap-3 sm:gap-4">
                  <div className="flex flex-col lg:flex-row justify-between items-stretch lg:items-center gap-3 sm:gap-4">
                    {/* Status Filter Tabs */}
                    <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                      <button
                        onClick={() => setPortfolioFilter('all')}
                        className={`px-2.5 sm:px-3.5 py-1.5 rounded-lg text-[11px] sm:text-xs font-mono tracking-wider transition-all text-center ${
                          portfolioFilter === 'all'
                            ? 'bg-[#FFFFFF] text-[#000000] font-bold border border-[#D4AF37]'
                            : 'bg-[#000000] text-[#C5A880]/80 hover:text-white border border-[#2B261D]'
                        }`}
                      >
                        TODAS ({portfolioSummary?.total_bets || 0})
                      </button>
                      <button
                        onClick={() => setPortfolioFilter('pending')}
                        className={`px-2.5 sm:px-3.5 py-1.5 rounded-lg text-[11px] sm:text-xs font-mono tracking-wider transition-all text-center ${
                          portfolioFilter === 'pending'
                            ? 'bg-[#D4AF37] text-black font-bold border border-[#D4AF37]'
                            : 'bg-[#000000] text-[#C5A880]/80 hover:text-white border border-[#2B261D]'
                        }`}
                      >
                        PENDENTES ({portfolioSummary?.pending_count || 0})
                      </button>
                      <button
                        onClick={() => setPortfolioFilter('won')}
                        className={`px-2.5 sm:px-3.5 py-1.5 rounded-lg text-[11px] sm:text-xs font-mono tracking-wider transition-all text-center ${
                          portfolioFilter === 'won'
                            ? 'bg-[#10B981] text-black font-bold border border-[#10B981]'
                            : 'bg-[#000000] text-[#C5A880]/80 hover:text-white border border-[#2B261D]'
                        }`}
                      >
                        GREENS ({portfolioSummary?.won_count || 0})
                      </button>
                      <button
                        onClick={() => setPortfolioFilter('lost')}
                        className={`px-2.5 sm:px-3.5 py-1.5 rounded-lg text-[11px] sm:text-xs font-mono tracking-wider transition-all text-center ${
                          portfolioFilter === 'lost'
                            ? 'bg-rose-500 text-white font-bold'
                            : 'bg-[#000000] text-[#C5A880]/80 hover:text-white border border-[#2B261D]'
                        }`}
                      >
                        REDS ({portfolioSummary?.lost_count || 0})
                      </button>
                      <button
                        onClick={() => setPortfolioFilter('push')}
                        className={`px-2.5 sm:px-3.5 py-1.5 rounded-lg text-[11px] sm:text-xs font-mono tracking-wider transition-all text-center ${
                          portfolioFilter === 'push'
                            ? 'bg-amber-500 text-black font-bold border border-amber-500'
                            : 'bg-[#000000] text-[#C5A880]/80 hover:text-white border border-[#2B261D]'
                        }`}
                      >
                        PUSHES ({portfolioSummary?.push_count || 0})
                      </button>
                    </div>

                    {/* Week, Game Filter & Search Input */}
                    <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 sm:gap-3">
                      {/* Week Select Dropdown */}
                      {portfolioAvailableWeeks.length > 0 && (
                        <div className="flex items-center gap-2 flex-1 sm:flex-initial">
                          <label className="text-[11px] font-mono text-[#D4AF37] uppercase tracking-wider hidden sm:inline whitespace-nowrap flex items-center gap-1">
                            <span>📅</span> Semana:
                          </label>
                          <div className="relative w-full sm:w-auto">
                            <select
                              value={portfolioWeekFilter}
                              onChange={(e) => {
                                const val = e.target.value;
                                setPortfolioWeekFilter(val);
                                setPortfolioGameFilter('all');
                                fetchPortfolio(portfolioTab, val);
                              }}
                              className={`w-full sm:w-auto bg-[#000000] border text-xs font-mono rounded-xl pl-3 pr-8 py-2 focus:outline-none transition-all cursor-pointer ${
                                portfolioWeekFilter !== 'all'
                                  ? 'border-[#D4AF37] text-[#D4AF37] font-bold shadow-[0_0_12px_rgba(212,175,55,0.25)]'
                                  : 'border-[#2B261D] text-white hover:border-[#C5A880]/60'
                              }`}
                            >
                              <option value="all">📅 Todas as Semanas</option>
                              {portfolioAvailableWeeks.map((w) => (
                                <option key={w} value={String(w)}>
                                  Semana {w}
                                </option>
                              ))}
                            </select>
                          </div>
                        </div>
                      )}

                      {/* Game Select Dropdown */}
                      <div className="flex items-center gap-2 flex-1 sm:flex-initial">
                        <label className="text-[11px] font-mono text-[#C5A880] uppercase tracking-wider hidden sm:inline whitespace-nowrap flex items-center gap-1">
                          <span>🏈</span> Jogo:
                        </label>
                        <div className="relative w-full sm:w-auto">
                          <select
                            value={portfolioGameFilter}
                            onChange={(e) => setPortfolioGameFilter(e.target.value)}
                            className={`w-full sm:w-auto bg-[#000000] border text-xs font-mono rounded-xl pl-3 pr-8 py-2 focus:outline-none transition-all cursor-pointer ${
                              portfolioGameFilter !== 'all'
                                ? 'border-[#10B981] text-[#10B981] font-bold shadow-[0_0_12px_rgba(16,185,129,0.25)]'
                                : 'border-[#2B261D] text-white hover:border-[#C5A880]/60'
                            }`}
                          >
                            <option value="all">🏈 Todos os Jogos ({portfolioBets.length})</option>
                            {portfolioGames.map((g) => (
                              <option key={g.game_id} value={g.game_id}>
                                {g.displayLabel || g.label} ({g.count})
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>

                      {/* Search Input */}
                      <div className="relative min-w-0 sm:min-w-[200px] flex-1 sm:flex-initial">
                        <input
                          type="text"
                          placeholder="Buscar jogador, time ou jogo..."
                          value={portfolioSearch}
                          onChange={(e) => setPortfolioSearch(e.target.value)}
                          className="w-full bg-[#000000] border border-[#2B261D] text-white text-xs font-mono rounded-xl px-3 sm:px-4 py-2 focus:border-[#C5A880] focus:outline-none placeholder:text-zinc-600 transition-colors"
                        />
                        {portfolioSearch && (
                          <button
                            onClick={() => setPortfolioSearch('')}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white text-xs font-mono"
                          >
                            ✕
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Quick Week Filter Pills */}
                  {portfolioAvailableWeeks.length > 1 && (
                    <div className="pt-2 sm:pt-2.5 border-t border-[#2B261D]/60 flex items-center gap-1.5 sm:gap-2 overflow-x-auto pb-1.5 scrollbar-none -mx-3.5 px-3.5 sm:mx-0 sm:px-0">
                      <span className="text-[10px] font-mono uppercase text-[#D4AF37]/80 tracking-wider whitespace-nowrap flex items-center gap-1 shrink-0 mr-1">
                        <span>📅</span> Semanas:
                      </span>
                      <button
                        onClick={() => {
                          setPortfolioWeekFilter('all');
                          setPortfolioGameFilter('all');
                          fetchPortfolio(portfolioTab, 'all');
                        }}
                        className={`px-2.5 sm:px-3 py-1.5 rounded-xl text-[11px] sm:text-xs font-mono tracking-wider transition-all whitespace-nowrap shrink-0 shadow-sm ${
                          portfolioWeekFilter === 'all'
                            ? 'bg-[#D4AF37] text-black font-bold border border-[#D4AF37]'
                            : 'bg-black text-zinc-400 hover:text-white border border-[#2B261D] hover:border-zinc-700'
                        }`}
                      >
                        Todas as Semanas
                      </button>
                      {portfolioAvailableWeeks.map((w) => {
                        const isSelected = portfolioWeekFilter === String(w);
                        return (
                          <button
                            key={w}
                            onClick={() => {
                              const val = isSelected ? 'all' : String(w);
                              setPortfolioWeekFilter(val);
                              setPortfolioGameFilter('all');
                              fetchPortfolio(portfolioTab, val);
                            }}
                            className={`px-2.5 sm:px-3 py-1.5 rounded-xl text-[11px] sm:text-xs font-mono tracking-wider transition-all whitespace-nowrap flex items-center gap-1.5 sm:gap-2 border shadow-sm shrink-0 ${
                              isSelected
                                ? 'bg-[#D4AF37] text-black font-bold border-[#D4AF37] shadow-[0_0_12px_rgba(212,175,55,0.35)]'
                                : 'bg-[#15130F] hover:bg-[#201C15] text-zinc-300 hover:text-white border-[#2B261D] hover:border-[#C5A880]/50'
                            }`}
                          >
                            Semana {w}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* Quick Game Filter Pills - Horizontal swipeable row on mobile */}
                  {portfolioGames.length > 0 && (
                    <div className="pt-2 sm:pt-2.5 border-t border-[#2B261D]/60 flex items-center gap-1.5 sm:gap-2 overflow-x-auto pb-1.5 scrollbar-none -mx-3.5 px-3.5 sm:mx-0 sm:px-0">
                      <span className="text-[10px] font-mono uppercase text-[#C5A880]/80 tracking-wider whitespace-nowrap flex items-center gap-1 shrink-0 mr-1">
                        <span>🏈</span> Jogos:
                      </span>
                      <button
                        onClick={() => setPortfolioGameFilter('all')}
                        className={`px-2.5 sm:px-3 py-1.5 rounded-xl text-[11px] sm:text-xs font-mono tracking-wider transition-all whitespace-nowrap shrink-0 shadow-sm ${
                          portfolioGameFilter === 'all'
                            ? 'bg-[#FFFFFF] text-black font-bold border border-[#D4AF37]'
                            : 'bg-black text-zinc-400 hover:text-white border border-[#2B261D] hover:border-zinc-700'
                        }`}
                      >
                        Todos ({portfolioBets.length})
                      </button>
                      {portfolioGames.map((g) => {
                        const isSelected = portfolioGameFilter === g.game_id;
                        return (
                          <button
                            key={g.game_id}
                            onClick={() => setPortfolioGameFilter(isSelected ? 'all' : g.game_id)}
                            className={`px-2.5 sm:px-3 py-1.5 rounded-xl text-[11px] sm:text-xs font-mono tracking-wider transition-all whitespace-nowrap flex items-center gap-1.5 sm:gap-2 border shadow-sm shrink-0 ${
                              isSelected
                                ? 'bg-[#10B981] text-black font-bold border-[#10B981] shadow-[0_0_12px_rgba(16,185,129,0.35)]'
                                : 'bg-[#15130F] hover:bg-[#201C15] text-zinc-300 hover:text-white border-[#2B261D] hover:border-[#C5A880]/50'
                            }`}
                            title={`Filtrar apostas de ${g.away_team} @ ${g.home_team}`}
                          >
                            <div className="flex items-center gap-1">
                              <img src={`/logos/${g.away_team}.png`} alt={g.away_team} className="w-3.5 h-3.5 sm:w-4 sm:h-4 object-contain shrink-0" />
                              <span className="font-bold">{g.away_team}</span>
                            </div>
                            <span className={isSelected ? 'text-black/60 font-bold text-[10px]' : 'text-[#C5A880]/80 text-[10px]'}>@</span>
                            <div className="flex items-center gap-1">
                              <img src={`/logos/${g.home_team}.png`} alt={g.home_team} className="w-3.5 h-3.5 sm:w-4 sm:h-4 object-contain shrink-0" />
                              <span className="font-bold">{g.home_team}</span>
                            </div>
                            <span className={`text-[9px] sm:text-[10px] px-1 sm:px-1.5 py-0.5 rounded-md font-bold ml-0.5 ${
                              isSelected ? 'bg-black/25 text-black' : 'bg-zinc-800 text-zinc-400'
                            }`}>
                              {g.count}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* Active Filters Summary Bar */}
                  {(portfolioWeekFilter !== 'all' || portfolioGameFilter !== 'all' || portfolioFilter !== 'all' || portfolioSearch.trim().length > 0) && (
                    <div className="pt-2 sm:pt-2.5 border-t border-[#2B261D]/60 flex flex-wrap items-center justify-between gap-2 text-xs font-mono">
                      <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                        <span className="text-[10px] uppercase tracking-wider text-zinc-500 mr-1">Filtros:</span>
                        
                        {portfolioWeekFilter !== 'all' && (
                          <button
                            onClick={() => {
                              setPortfolioWeekFilter('all');
                              setPortfolioGameFilter('all');
                              fetchPortfolio(portfolioTab, 'all');
                            }}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#D4AF37]/15 border border-[#D4AF37]/40 text-[#D4AF37] text-[11px] font-bold hover:bg-[#D4AF37]/25 transition-colors"
                            title="Remover filtro de semana"
                          >
                            <span>📅 Semana {portfolioWeekFilter}</span>
                            <span className="text-xs">✕</span>
                          </button>
                        )}

                        {portfolioGameFilter !== 'all' && (() => {
                          const activeGame = portfolioGames.find(g => g.game_id === portfolioGameFilter);
                          return (
                            <button
                              onClick={() => setPortfolioGameFilter('all')}
                              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 text-[11px] font-bold hover:bg-emerald-500/25 transition-colors"
                              title="Remover filtro de jogo"
                            >
                              <span>🏈 {activeGame ? `${activeGame.away_team} @ ${activeGame.home_team}` : 'Jogo'}</span>
                              <span className="text-xs">✕</span>
                            </button>
                          );
                        })()}

                        {portfolioFilter !== 'all' && (
                          <button
                            onClick={() => setPortfolioFilter('all')}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 text-[11px] hover:bg-zinc-700 transition-colors"
                            title="Remover filtro de status"
                          >
                            <span>
                              {portfolioFilter === 'pending' ? '⏳ Pendentes' :
                               portfolioFilter === 'won' ? '✅ Greens' :
                               portfolioFilter === 'lost' ? '❌ Reds' : '🔄 Pushes'}
                            </span>
                            <span className="text-xs">✕</span>
                          </button>
                        )}

                        {portfolioSearch.trim().length > 0 && (
                          <button
                            onClick={() => setPortfolioSearch('')}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 text-[11px] hover:bg-zinc-700 transition-colors"
                            title="Limpar busca textual"
                          >
                            <span>🔍 &ldquo;{portfolioSearch}&rdquo;</span>
                            <span className="text-xs">✕</span>
                          </button>
                        )}
                      </div>

                      <button
                        onClick={() => {
                          setPortfolioWeekFilter('all');
                          setPortfolioGameFilter('all');
                          setPortfolioFilter('all');
                          setPortfolioSearch('');
                          fetchPortfolio(portfolioTab, 'all');
                        }}
                        className="text-[11px] text-zinc-400 hover:text-white underline underline-offset-2 transition-colors ml-auto"
                      >
                        Limpar Todos os Filtros
                      </button>
                    </div>
                  )}

                  {/* Active Game Filter Notification Banner */}
                  {portfolioGameFilter !== 'all' && (() => {
                    const activeGame = portfolioGames.find(g => g.game_id === portfolioGameFilter);
                    if (!activeGame) return null;
                    return (
                      <div className="p-3 sm:px-4 rounded-xl bg-gradient-to-r from-[#1A160F] via-[#15130F] to-[#0C0C0E] border border-[#D4AF37]/40 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs font-mono shadow-md animate-in fade-in duration-150">
                        <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
                          <div className="flex items-center gap-2 bg-black/80 px-2.5 sm:px-3 py-1.5 rounded-lg border border-[#D4AF37]/50">
                            <div className="flex items-center gap-1.5">
                              <img src={`/logos/${activeGame.away_team}.png`} alt={activeGame.away_team} className="w-4 h-4 object-contain shrink-0" />
                              <span className="font-bold text-white text-xs">{activeGame.away_team}</span>
                            </div>
                            <span className="text-[#C5A880] text-[10px]">@</span>
                            <div className="flex items-center gap-1.5">
                              <img src={`/logos/${activeGame.home_team}.png`} alt={activeGame.home_team} className="w-4 h-4 object-contain shrink-0" />
                              <span className="font-bold text-white text-xs">{activeGame.home_team}</span>
                            </div>
                          </div>
                          <div className="text-zinc-300 text-xs">
                            Exibindo <span className="font-bold text-[#D4AF37]">{activeGame.count} apostas</span>
                            {(activeGame.wonCount > 0 || activeGame.lostCount > 0 || activeGame.pendingCount > 0) && (
                              <span className="text-zinc-400 ml-1.5">
                                (<span className="text-emerald-400 font-bold">{activeGame.wonCount}W</span> • <span className="text-rose-400 font-bold">{activeGame.lostCount}L</span>{activeGame.pendingCount > 0 ? ` • ${activeGame.pendingCount}P` : ''})
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
                          <button
                            onClick={() => handleOpenBoxScore(activeGame)}
                            className="flex-1 sm:flex-initial px-3 py-1 rounded-lg bg-[#D4AF37]/15 hover:bg-[#D4AF37]/25 text-[#D4AF37] border border-[#D4AF37]/50 text-xs font-mono font-bold transition-all flex items-center justify-center gap-1.5 shadow-sm"
                            title="Ver estatísticas completas e box score deste jogo"
                          >
                            <svg className="w-3.5 h-3.5 text-[#D4AF37]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                            </svg>
                            <span>Box Score</span>
                          </button>
                          <button
                            onClick={() => setPortfolioGameFilter('all')}
                            className="px-2.5 py-1 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-300 hover:text-white border border-zinc-700 text-xs font-mono transition-colors flex items-center justify-center gap-1"
                            title="Limpar filtro de jogo e mostrar todas as apostas"
                          >
                            <span>✕ Limpar</span>
                          </button>
                        </div>
                      </div>
                    );
                  })()}
                </div>
                {/* Desktop Table */}
                <div className="hidden md:block overflow-x-auto">
                  <table className="w-full text-left font-sans text-xs">
                    <thead className="bg-[#15130F] text-[#C5A880] uppercase font-mono text-[10px] tracking-wider border-b border-[#2B261D]">
                      <tr>
                        <th className="py-3.5 px-4 font-semibold whitespace-nowrap">Ativo (Jogador)</th>
                        <th className="py-3.5 px-4 font-semibold whitespace-nowrap">Jogo</th>
                        <th className="py-3.5 px-4 font-semibold whitespace-nowrap">Mercado</th>
                        <th className="py-3.5 px-4 font-semibold whitespace-nowrap">Linha & Lado</th>
                        <th className="py-3.5 px-4 font-semibold whitespace-nowrap">Odd</th>
                        <th className="py-3.5 px-4 font-semibold whitespace-nowrap">Aporte</th>
                        <th className="py-3.5 px-4 font-semibold whitespace-nowrap">EV Teórico</th>
                        <th className="py-3.5 px-4 font-semibold whitespace-nowrap">Resultado Real</th>
                        <th className="py-3.5 px-4 font-semibold whitespace-nowrap">Retorno (PnL)</th>
                        <th className="py-3.5 px-4 font-semibold whitespace-nowrap">Status</th>
                        <th className="py-3.5 px-4 font-semibold whitespace-nowrap text-right">Ações</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-850">
                      {filteredPortfolioBets.length === 0 ? (
                        <tr>
                          <td colSpan={11} className="py-16 text-center text-zinc-500 font-mono text-xs uppercase tracking-wider">
                            {portfolioBets.length === 0 
                              ? (portfolioTab === 'safe'
                                  ? 'A carteira conservadora dinâmica está vazia. Clique em "Sincronizar Dinâmica" para importar apostas (+EV 2.5% a 15%).'
                                  : portfolioTab === 'safe_flat'
                                  ? 'A carteira flat 1.0u está vazia. Clique em "Sincronizar Flat 1.0u" para importar recomendações (+EV 2.5% a 15%).'
                                  : portfolioTab === 'high_risk'
                                  ? 'A carteira de alto risco está vazia. Clique em "Sincronizar Apostas" para importar apostas (EV > 20%).'
                                  : 'A carteira All Props está vazia. Clique em "Sincronizar Props" para importar todas as props com valor esperado positivo (+EV > 0).')
                              : 'Nenhuma aposta encontrada para este filtro.'}
                          </td>
                        </tr>
                      ) : (
                        filteredPortfolioBets.map((bet: any) => {
                          const isWon = bet.result === 'won';
                          const isLost = bet.result === 'lost';
                          const isPending = bet.result === 'pending';
                          const isPush = bet.result === 'push';
                          const gameInfo = getBetGameInfo(bet);

                          const marketLabel = 
                            bet.market === 'rushing_yards' ? 'Jardas Terrestres' :
                            bet.market === 'receiving_yards' ? 'Jardas de Recepção' :
                            bet.market === 'passing_yards' ? 'Jardas de Passe' : bet.market;

                          return (
                            <tr key={bet.id} className="hover:bg-zinc-900/40 transition-colors font-mono">
                              {/* Ativo */}
                              <td className="py-3.5 px-4 font-sans font-semibold text-white">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <button
                                    type="button"
                                    onClick={() => setSelectedAiBet(bet)}
                                    className="text-white hover:text-[#D4AF37] font-sans font-semibold flex items-center gap-1.5 group text-left transition-colors cursor-pointer"
                                    title="Clique para ver o racional de unidades e análise da IA"
                                  >
                                    <span className="group-hover:underline underline-offset-4">{bet.player_name}</span>
                                    <span className="text-[10px] text-[#C5A880]/60 group-hover:text-[#D4AF37] transition-colors">🧠</span>
                                  </button>
                                  {bet.team && (
                                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                                      {bet.team}
                                    </span>
                                  )}
                                  {bet.week && (
                                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#1F1B14] text-[#D4AF37] border border-[#D4AF37]/30" title={`Semana ${bet.week}`}>
                                      W{bet.week}
                                    </span>
                                  )}
                                  {bet.portfolio_type === 'high_risk' ? (
                                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
                                      ⚡ ALTO RISCO
                                    </span>
                                  ) : bet.portfolio_type === 'all_props' ? (
                                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30">
                                      🌐 ALL PROPS
                                    </span>
                                  ) : (
                                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                                      🛡️ CONSERVADORA
                                    </span>
                                  )}
                                </div>
                              </td>

                              {/* Jogo */}
                              <td className="py-3.5 px-4 whitespace-nowrap">
                                <button
                                  type="button"
                                  onClick={() => setPortfolioGameFilter(portfolioGameFilter === gameInfo.game_id ? 'all' : gameInfo.game_id)}
                                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-mono transition-all whitespace-nowrap shadow-sm ${
                                    portfolioGameFilter === gameInfo.game_id
                                      ? 'bg-[#10B981]/20 border-[#10B981] text-[#10B981] font-bold shadow-[0_0_10px_rgba(16,185,129,0.2)]'
                                      : 'bg-zinc-900/80 hover:bg-[#15130F] border-zinc-800 hover:border-[#D4AF37]/50 text-zinc-300 hover:text-[#D4AF37]'
                                  }`}
                                  title={`Filtrar apenas apostas de ${gameInfo.away_team} @ ${gameInfo.home_team}`}
                                >
                                  <div className="flex items-center gap-1">
                                    <img src={`/logos/${gameInfo.away_team}.png`} alt={gameInfo.away_team} className="w-4 h-4 object-contain shrink-0" />
                                    <span className="font-semibold text-white">{gameInfo.away_team}</span>
                                  </div>
                                  <span className="text-[#C5A880]/70 text-[10px]">@</span>
                                  <div className="flex items-center gap-1">
                                    <img src={`/logos/${gameInfo.home_team}.png`} alt={gameInfo.home_team} className="w-4 h-4 object-contain shrink-0" />
                                    <span className="font-semibold text-white">{gameInfo.home_team}</span>
                                  </div>
                                </button>
                              </td>

                              {/* Mercado */}
                              <td className="py-3.5 px-4 text-zinc-300 whitespace-nowrap">
                                {marketLabel}
                              </td>

                              {/* Linha & Lado */}
                              <td className="py-3.5 px-4 whitespace-nowrap">
                                <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-mono font-bold whitespace-nowrap shadow-sm ${
                                  bet.side === 'over' 
                                    ? 'bg-sky-500/15 text-sky-300 border border-sky-500/30' 
                                    : 'bg-purple-500/15 text-purple-300 border border-purple-500/30'
                                }`}>
                                  <span className="text-[10px] font-black tracking-wider uppercase">
                                    {bet.side === 'over' ? '▲ OVER' : '▼ UNDER'}
                                  </span>
                                  <span className="text-white font-bold ml-0.5">{bet.line}</span>
                                </span>
                              </td>

                              {/* Odd */}
                              <td className="py-3.5 px-4 font-bold text-white">
                                {bet.odds.toFixed(2)}
                              </td>

                              {/* Aporte */}
                              <td className="py-3.5 px-4 text-zinc-300">
                                <div 
                                  onClick={() => setSelectedAiBet(bet)}
                                  className="flex flex-col items-start gap-1 cursor-pointer group"
                                  title="Clique para ver o racional de unidades da IA"
                                >
                                  <span className={`px-2 py-0.5 rounded text-[11px] font-mono font-bold transition-all group-hover:scale-105 ${
                                    bet.units >= 1.25
                                      ? 'bg-[#C5A880]/20 text-[#D4AF37] border border-[#C5A880]/40 shadow-sm'
                                      : bet.units >= 1.0
                                      ? 'bg-zinc-800 text-zinc-200 border border-zinc-700'
                                      : 'bg-zinc-900 text-zinc-400 border border-zinc-800'
                                  }`}>
                                    {bet.units.toFixed(2)} u
                                  </span>
                                  {bet.base_units !== undefined && bet.ai_multiplier !== undefined && (
                                    <span className="text-[10px] font-mono text-zinc-500 whitespace-nowrap group-hover:text-zinc-400 transition-colors">
                                      Base {bet.base_units.toFixed(2)}u × {bet.ai_multiplier.toFixed(2)}x
                                    </span>
                                  )}
                                  {bet.ai_sizing_rationale && (
                                    <span 
                                      className="text-[9px] font-mono text-[#C5A880]/80 truncate max-w-[130px] group-hover:text-[#D4AF37] transition-colors" 
                                      title={bet.ai_sizing_rationale}
                                    >
                                      🧠 {bet.ai_sizing_rationale}
                                    </span>
                                  )}
                                </div>
                              </td>

                              {/* EV Teórico */}
                              <td className="py-3.5 px-4 text-zinc-300">
                                {bet.ev_percent ? `${bet.ev_percent >= 0 ? '+' : ''}${bet.ev_percent.toFixed(1)}%` : '-'}
                              </td>

                              {/* Resultado Real */}
                              <td className="py-3.5 px-4">
                                {bet.actual_value !== null && bet.actual_value !== undefined ? (
                                  <span className="font-bold text-white">
                                    {bet.actual_value.toFixed(1)} yds
                                  </span>
                                ) : (
                                  <span className="text-zinc-500 text-[11px]">
                                    Aguardando jogo
                                  </span>
                                )}
                              </td>

                              {/* Retorno */}
                              <td className="py-3.5 px-4 font-bold">
                                {isWon && <span className="text-emerald-400">+{bet.profit_units.toFixed(2)} u</span>}
                                {isLost && <span className="text-rose-400">{bet.profit_units.toFixed(2)} u</span>}
                                {isPush && <span className="text-zinc-400">0.00 u</span>}
                                {isPending && <span className="text-amber-400/80 text-[11px]">Pendente</span>}
                              </td>

                              {/* Status Badge */}
                              <td className="py-3.5 px-4">
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  {isWon && (
                                    <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 tracking-wider">
                                      GREEN
                                    </span>
                                  )}
                                  {isLost && (
                                    <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 tracking-wider">
                                      RED
                                    </span>
                                  )}
                                  {isPush && (
                                    <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-sky-500/20 text-sky-300 border border-sky-500/40 tracking-wider">
                                      PUSH
                                    </span>
                                  )}
                                  {isPending && (
                                    <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-300 border border-amber-500/30 tracking-wider">
                                      PENDENTE
                                    </span>
                                  )}
                                  {bet.is_locked && (
                                    <span
                                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/40 tracking-wider"
                                      title="Aposta Bloqueada: Partida iniciada ou encerrada com súmula oficial. Não pode ser modificada nem excluída."
                                    >
                                      🔒 LOCKED
                                    </span>
                                  )}
                                </div>
                              </td>

                              {/* Ações */}
                              <td className="py-3.5 px-4 text-right">
                                {bet.is_locked ? (
                                  <div className="inline-flex items-center gap-1 text-[11px] font-mono text-zinc-500" title="Aposta bloqueada contra exclusão e edição manual (resultado oficial)">
                                    <span>🔒</span>
                                    <span className="text-[10px] text-zinc-500 font-semibold uppercase">BLOQUEADA</span>
                                  </div>
                                ) : isReadOnly ? (
                                  <div className="inline-flex items-center gap-1 text-[11px] font-mono text-zinc-500" title="Edição manual desabilitada no modo demonstração pública">
                                    <span>🔒</span>
                                    <span className="text-[10px] text-zinc-500 font-semibold uppercase">LEITURA</span>
                                  </div>
                                ) : (
                                  <div className="inline-flex items-center gap-1.5">
                                    <button
                                      onClick={() => handleManualSettle(bet.id, 'won')}
                                      title="Marcar Green manualmente"
                                      className="px-2 py-1 rounded bg-zinc-800 hover:bg-emerald-900/60 text-zinc-400 hover:text-emerald-300 text-[10px] font-bold transition-colors border border-zinc-700/60"
                                    >
                                      W
                                    </button>
                                    <button
                                      onClick={() => handleManualSettle(bet.id, 'lost')}
                                      title="Marcar Red manualmente"
                                      className="px-2 py-1 rounded bg-zinc-800 hover:bg-rose-900/60 text-zinc-400 hover:text-rose-300 text-[10px] font-bold transition-colors border border-zinc-700/60"
                                    >
                                      L
                                    </button>
                                    <button
                                      onClick={() => handleManualSettle(bet.id, 'pending')}
                                      title="Resetar para Pendente"
                                      className="px-2 py-1 rounded bg-zinc-800 hover:bg-amber-900/60 text-zinc-400 hover:text-amber-300 text-[10px] font-bold transition-colors border border-zinc-700/60"
                                    >
                                      P
                                    </button>
                                    <button
                                      onClick={() => handleDeleteBet(bet.id)}
                                      title="Remover da carteira"
                                      className="px-2 py-1 rounded bg-zinc-800 hover:bg-rose-950 text-zinc-500 hover:text-rose-400 text-[10px] font-bold transition-colors border border-zinc-700/60 ml-1"
                                    >
                                      ✕
                                    </button>
                                  </div>
                                )}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>

                {/* Mobile View: Dedicated responsive cards */}
                <div className="md:hidden divide-y divide-[#2B261D] flex flex-col">
                  {filteredPortfolioBets.length === 0 ? (
                    <div className="py-12 px-4 text-center text-zinc-500 font-mono text-xs uppercase tracking-wider">
                      {portfolioBets.length === 0 
                        ? (portfolioTab === 'safe'
                            ? 'A carteira conservadora dinâmica está vazia. Clique em "Sincronizar Dinâmica" para importar apostas.'
                            : portfolioTab === 'safe_flat'
                            ? 'A carteira flat 1.0u está vazia. Clique em "Sincronizar Flat 1.0u" para importar recomendações.'
                            : portfolioTab === 'high_risk'
                            ? 'A carteira de alto risco está vazia. Clique em "Sincronizar Apostas" para importar apostas.'
                            : 'A carteira All Props está vazia. Clique em "Sincronizar Props" para importar todas as props.')
                        : 'Nenhuma aposta encontrada para este filtro.'}
                    </div>
                  ) : (
                    filteredPortfolioBets.map((bet: any) => {
                      const isWon = bet.result === 'won';
                      const isLost = bet.result === 'lost';
                      const isPending = bet.result === 'pending';
                      const isPush = bet.result === 'push';
                      const gameInfo = getBetGameInfo(bet);

                      const marketLabel = 
                        bet.market === 'rushing_yards' ? 'Jardas Terrestres' :
                        bet.market === 'receiving_yards' ? 'Jardas de Recepção' :
                        bet.market === 'passing_yards' ? 'Jardas de Passe' : bet.market;

                      return (
                        <div key={bet.id} className="p-3.5 bg-[#0C0C0E] hover:bg-[#15130F]/60 transition-colors flex flex-col gap-2.5 font-mono">
                          {/* Row 1: Player Name, Team, Tag & Status */}
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex items-center gap-1.5 flex-wrap flex-1 min-w-0">
                              <button
                                type="button"
                                onClick={() => setSelectedAiBet(bet)}
                                className="text-white hover:text-[#D4AF37] font-sans font-bold text-sm flex items-center gap-1 text-left transition-colors truncate"
                                title="Clique para ver o racional de unidades e análise da IA"
                              >
                                <span className="truncate">{bet.player_name}</span>
                                <span className="text-[11px] text-[#C5A880]/70">🧠</span>
                              </button>
                              {bet.team && (
                                <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                                  {bet.team}
                                </span>
                              )}
                              {bet.week && (
                                <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#1F1B14] text-[#D4AF37] border border-[#D4AF37]/30" title={`Semana ${bet.week}`}>
                                  W{bet.week}
                                </span>
                              )}
                              {bet.portfolio_type === 'high_risk' ? (
                                <span className="text-[8px] font-mono px-1 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
                                  ⚡ ALTO RISCO
                                </span>
                              ) : bet.portfolio_type === 'all_props' ? (
                                <span className="text-[8px] font-mono px-1 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30">
                                  🌐 ALL PROPS
                                </span>
                              ) : (
                                <span className="text-[8px] font-mono px-1 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                                  🛡️ SAFE
                                </span>
                              )}
                            </div>

                            <div className="flex items-center gap-1 shrink-0">
                              {isWon && (
                                <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                                  GREEN
                                </span>
                              )}
                              {isLost && (
                                <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">
                                  RED
                                </span>
                              )}
                              {isPush && (
                                <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-sky-500/20 text-sky-300 border border-sky-500/40">
                                  PUSH
                                </span>
                              )}
                              {isPending && (
                                <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-amber-500/10 text-amber-300 border border-amber-500/30">
                                  PENDENTE
                                </span>
                              )}
                              {bet.is_locked && (
                                <span className="px-1.5 py-0.5 rounded-full text-[8px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/40" title="Aposta Bloqueada (Jogo finalizado)">
                                  🔒
                                </span>
                              )}
                            </div>
                          </div>

                          {/* Row 2: Matchup & Market */}
                          <div className="flex items-center justify-between gap-2 text-[11px] text-zinc-400">
                            <button
                              type="button"
                              onClick={() => setPortfolioGameFilter(portfolioGameFilter === gameInfo.game_id ? 'all' : gameInfo.game_id)}
                              className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-zinc-900/80 border border-zinc-800 text-[10px] text-zinc-300 hover:text-white"
                            >
                              <img src={`/logos/${gameInfo.away_team}.png`} alt={gameInfo.away_team} className="w-3.5 h-3.5 object-contain" />
                              <span className="font-semibold">{gameInfo.away_team}</span>
                              <span className="text-[#C5A880]/60">@</span>
                              <img src={`/logos/${gameInfo.home_team}.png`} alt={gameInfo.home_team} className="w-3.5 h-3.5 object-contain" />
                              <span className="font-semibold">{gameInfo.home_team}</span>
                            </button>
                            <span className="text-zinc-400 truncate text-[11px]">{marketLabel}</span>
                          </div>

                          {/* Row 3: 4 Key Metrics Grid */}
                          <div className="grid grid-cols-4 gap-1.5 p-2 bg-black/60 rounded-xl border border-[#2B261D] text-center">
                            {/* Linha / Lado */}
                            <div className="flex flex-col items-center justify-center">
                              <span className="text-[9px] text-zinc-500 uppercase tracking-wider">Linha</span>
                              <span className={`text-[11px] font-bold mt-0.5 flex items-center gap-0.5 ${
                                bet.side === 'over' ? 'text-sky-300' : 'text-purple-300'
                              }`}>
                                <span>{bet.side === 'over' ? '▲' : '▼'}</span>
                                <span>{bet.line}</span>
                              </span>
                            </div>

                            {/* Odd */}
                            <div className="flex flex-col items-center justify-center">
                              <span className="text-[9px] text-zinc-500 uppercase tracking-wider">Odd</span>
                              <span className="text-xs font-bold text-white mt-0.5">{bet.odds.toFixed(2)}</span>
                            </div>

                            {/* Aporte */}
                            <button
                              type="button"
                              onClick={() => setSelectedAiBet(bet)}
                              className="flex flex-col items-center justify-center hover:opacity-80 transition-opacity"
                              title="Clique para ver o racional de unidades"
                            >
                              <span className="text-[9px] text-zinc-500 uppercase tracking-wider flex items-center gap-0.5">
                                Aporte <span className="text-[8px]">🧠</span>
                              </span>
                              <span className={`text-xs font-bold mt-0.5 ${
                                bet.units >= 1.25 ? 'text-[#D4AF37]' : 'text-zinc-200'
                              }`}>
                                {bet.units.toFixed(2)} u
                              </span>
                            </button>

                            {/* EV */}
                            <div className="flex flex-col items-center justify-center">
                              <span className="text-[9px] text-zinc-500 uppercase tracking-wider">Edge EV</span>
                              <span className={`text-xs font-bold mt-0.5 ${
                                (bet.ev_percent ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                              }`}>
                                {bet.ev_percent ? `${bet.ev_percent >= 0 ? '+' : ''}${bet.ev_percent.toFixed(1)}%` : '-'}
                              </span>
                            </div>
                          </div>

                          {/* Row 4: Settlement Result & Actions */}
                          <div className="flex items-center justify-between pt-1 border-t border-[#2B261D]/50 text-xs">
                            <div className="flex items-center gap-3">
                              {/* Real Result */}
                              <div className="text-[11px]">
                                <span className="text-zinc-500 text-[10px] uppercase mr-1">Real:</span>
                                {bet.actual_value !== null && bet.actual_value !== undefined ? (
                                  <span className="font-bold text-white">{bet.actual_value.toFixed(1)} yds</span>
                                ) : (
                                  <span className="text-zinc-500 text-[10px]">Aguardando</span>
                                )}
                              </div>

                              {/* PnL Retorno */}
                              <div className="text-[11px]">
                                <span className="text-zinc-500 text-[10px] uppercase mr-1">PnL:</span>
                                {isWon && <span className="text-emerald-400 font-bold">+{bet.profit_units.toFixed(2)} u</span>}
                                {isLost && <span className="text-rose-400 font-bold">{bet.profit_units.toFixed(2)} u</span>}
                                {isPush && <span className="text-zinc-400 font-bold">0.00 u</span>}
                                {isPending && <span className="text-amber-400/80 text-[10px]">Pendente</span>}
                              </div>
                            </div>

                            {/* Actions */}
                            <div>
                              {bet.is_locked ? (
                                <span className="text-[9px] text-zinc-500 uppercase font-semibold px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800">
                                  🔒 Locked
                                </span>
                              ) : isReadOnly ? (
                                <span className="text-[9px] text-zinc-500 uppercase font-semibold px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800">
                                  🔒 Leitura
                                </span>
                              ) : (
                                <div className="flex items-center gap-1">
                                  <button
                                    onClick={() => handleManualSettle(bet.id, 'won')}
                                    title="Marcar Green manualmente"
                                    className="px-2 py-1 rounded bg-zinc-900 hover:bg-emerald-950 text-emerald-400 border border-zinc-800 hover:border-emerald-500/50 text-[10px] font-bold"
                                  >
                                    W
                                  </button>
                                  <button
                                    onClick={() => handleManualSettle(bet.id, 'lost')}
                                    title="Marcar Red manualmente"
                                    className="px-2 py-1 rounded bg-zinc-900 hover:bg-rose-950 text-rose-400 border border-zinc-800 hover:border-rose-500/50 text-[10px] font-bold"
                                  >
                                    L
                                  </button>
                                  <button
                                    onClick={() => handleManualSettle(bet.id, 'pending')}
                                    title="Resetar para Pendente"
                                    className="px-2 py-1 rounded bg-zinc-900 hover:bg-amber-950 text-amber-400 border border-zinc-800 hover:border-amber-500/50 text-[10px] font-bold"
                                  >
                                    P
                                  </button>
                                  <button
                                    onClick={() => handleDeleteBet(bet.id)}
                                    title="Remover da carteira"
                                    className="px-2 py-1 rounded bg-zinc-900 hover:bg-rose-950 text-zinc-500 hover:text-rose-400 border border-zinc-800 text-[10px] font-bold ml-0.5"
                                  >
                                    ✕
                                  </button>
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Row 5: AI Thesis preview snippet if exists */}
                          {bet.ai_sizing_rationale && (
                            <div
                              onClick={() => setSelectedAiBet(bet)}
                              className="text-[10px] text-[#C5A880]/80 italic bg-[#15130F] px-2.5 py-1.5 rounded-lg border border-[#2B261D] cursor-pointer flex items-center justify-between gap-1.5 hover:border-[#C5A880]/50 transition-colors"
                            >
                              <span className="truncate">🧠 {bet.ai_sizing_rationale}</span>
                              <span className="text-[#D4AF37] font-sans font-bold text-[9px] uppercase tracking-wider shrink-0">Ver Análise ↗</span>
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Box Score & Player Results Modal */}
      {boxScoreOpen && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-3 md:p-6 bg-black/85 backdrop-blur-md">
          <div className="bg-[#0C0C0E] border border-[#D4AF37]/50 rounded-2xl w-full max-w-5xl max-h-[92vh] flex flex-col shadow-[0_0_50px_rgba(212,175,55,0.25)] overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="p-5 border-b border-[#2B261D] bg-[#15130F] flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <div className="relative w-10 h-10">
                    <Image src={`/logos/${boxScoreData?.away_team || 'NE'}.png`} alt={boxScoreData?.away_team || 'NE'} fill className="object-contain" />
                  </div>
                  <div className="text-right">
                    <span className="font-bold text-white text-lg">{boxScoreData?.away_team || 'NE'}</span>
                    <div className="text-2xl font-extrabold font-mono text-zinc-200">{boxScoreData?.away_score ?? 10}</div>
                  </div>
                </div>

                <div className="text-center px-2">
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 uppercase tracking-widest">
                    FINALIZADO
                  </span>
                  <div className="text-xs font-mono text-zinc-500 mt-1">@</div>
                </div>

                <div className="flex items-center gap-2">
                  <div className="text-left">
                    <span className="font-bold text-white text-lg">{boxScoreData?.home_team || 'SEA'}</span>
                    <div className="text-2xl font-extrabold font-mono text-[#D4AF37]">{boxScoreData?.home_score ?? 13}</div>
                  </div>
                  <div className="relative w-10 h-10">
                    <Image src={`/logos/${boxScoreData?.home_team || 'SEA'}.png`} alt={boxScoreData?.home_team || 'SEA'} fill className="object-contain" />
                  </div>
                </div>

                <div className="hidden sm:block pl-4 border-l border-zinc-800">
                  <div className="text-xs font-bold text-white uppercase tracking-wider">NFL 2026 • Semana {boxScoreData?.week || currentWeek}</div>
                  <div className="text-[11px] font-mono text-zinc-400">{boxScoreData?.stadium || 'Lumen Field'} • {boxScoreData?.gameday || '09/09/2026'}</div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={() => handleSettlePortfolio(boxScoreData?.game_id)}
                  disabled={loadingPortfolio}
                  className="px-4 py-2.5 rounded-xl bg-[#10B981] hover:bg-[#10B981]/90 text-black font-mono font-bold text-xs uppercase tracking-wider shadow-[0_0_12px_rgba(16,185,129,0.3)] flex items-center gap-1.5 transition-all disabled:opacity-50"
                  title="Conferir e liquidar todas as apostas deste jogo no portfólio"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>{loadingPortfolio ? 'Liquidando...' : 'Liquidar Apostas'}</span>
                </button>

                <button
                  onClick={() => setBoxScoreOpen(false)}
                  className="w-9 h-9 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-white flex items-center justify-center font-mono text-base border border-zinc-700 transition-colors"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Sub-Header Tabs */}
            <div className="px-3.5 sm:px-5 py-2.5 sm:py-3 border-b border-[#2B261D] bg-[#0C0C0E] flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5 sm:gap-4">
              <div className="grid grid-cols-2 sm:flex items-center gap-2">
                <button
                  onClick={() => setBoxScoreTab('stats')}
                  className={`px-3 sm:px-4 py-2 rounded-xl text-xs font-mono tracking-wider transition-all flex items-center justify-center gap-1.5 sm:gap-2 text-center ${
                    boxScoreTab === 'stats'
                      ? 'bg-[#D4AF37] text-black font-bold shadow-[0_0_12px_rgba(212,175,55,0.3)]'
                      : 'bg-zinc-900 text-zinc-400 hover:text-white border border-zinc-800'
                  }`}
                >
                  <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  <span>
                    <span className="hidden sm:inline">Estatísticas Oficiais (Box Score)</span>
                    <span className="sm:hidden">Box Score</span>
                  </span>
                </button>

                <button
                  onClick={() => setBoxScoreTab('bets')}
                  className={`px-3 sm:px-4 py-2 rounded-xl text-xs font-mono tracking-wider transition-all flex items-center justify-center gap-1.5 sm:gap-2 text-center ${
                    boxScoreTab === 'bets'
                      ? 'bg-[#10B981] text-black font-bold shadow-[0_0_12px_rgba(16,185,129,0.3)]'
                      : 'bg-zinc-900 text-zinc-400 hover:text-white border border-zinc-800'
                  }`}
                >
                  <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>
                    <span className="hidden sm:inline">Apostas deste Jogo</span>
                    <span className="sm:hidden">Apostas</span> ({boxScoreData?.bets?.length || 0})
                  </span>
                </button>
              </div>

              <div className="text-[10px] sm:text-xs font-mono text-zinc-500 hidden sm:block">
                Oficial NFLReadPy • Semana {boxScoreData?.week || currentWeek} / 2026
              </div>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-5 space-y-6">
              {loadingBoxScore ? (
                <div className="py-20 text-center text-zinc-400 font-mono text-xs uppercase tracking-wider flex flex-col items-center justify-center gap-3">
                  <div className="w-6 h-6 border-2 border-[#D4AF37] border-t-transparent rounded-full animate-spin"></div>
                  <span>Carregando estatísticas oficiais e apostas da partida...</span>
                </div>
              ) : boxScoreTab === 'stats' ? (
                <div className="space-y-8">
                  {/* Away Team: Patriots */}
                  <div className="bg-[#15130F] border border-[#2B261D] rounded-xl p-4 overflow-hidden shadow-lg">
                    <div className="flex items-center gap-3 mb-4 pb-3 border-b border-zinc-800">
                      <div className="relative w-7 h-7">
                        <Image src={`/logos/${boxScoreData?.away_team || 'NE'}.png`} alt="NE" fill className="object-contain" />
                      </div>
                      <h3 className="text-sm font-bold text-white font-sans uppercase tracking-wider">
                        {boxScoreData?.away_team === 'NE' ? 'New England Patriots' : boxScoreData?.away_team} — Estatísticas do Jogo
                      </h3>
                    </div>

                    <div className="overflow-x-auto">
                      <table className="w-full text-left font-mono text-xs">
                        <thead className="text-[10px] text-[#C5A880] uppercase tracking-wider bg-black/40 border-b border-zinc-800">
                          <tr>
                            <th className="py-2.5 px-3">Jogador</th>
                            <th className="py-2.5 px-3">Pos</th>
                            <th className="py-2.5 px-3">Passe (C/A)</th>
                            <th className="py-2.5 px-3">Jds Passe</th>
                            <th className="py-2.5 px-3">TD/INT</th>
                            <th className="py-2.5 px-3">Carregadas</th>
                            <th className="py-2.5 px-3">Jds Corridas</th>
                            <th className="py-2.5 px-3">Recepções</th>
                            <th className="py-2.5 px-3">Jds Recebidas</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-850 text-zinc-300">
                          {boxScoreData?.away_players?.map((p: any) => (
                            <tr key={p.player_id || p.player_name} className="hover:bg-zinc-800/40">
                              <td className="py-2.5 px-3 font-semibold text-white font-sans">
                                {p.player_display_name || p.player_name}
                              </td>
                              <td className="py-2.5 px-3 text-zinc-400">{p.position}</td>
                              <td className="py-2.5 px-3">{p.attempts > 0 ? `${p.completions}/${p.attempts}` : '-'}</td>
                              <td className="py-2.5 px-3 font-bold text-white">{p.passing_yards > 0 ? `${p.passing_yards} yds` : '-'}</td>
                              <td className="py-2.5 px-3">{p.attempts > 0 ? `${p.passing_tds}/${p.passing_interceptions}` : '-'}</td>
                              <td className="py-2.5 px-3">{p.carries > 0 ? p.carries : '-'}</td>
                              <td className="py-2.5 px-3 font-bold text-emerald-400">{p.rushing_yards > 0 ? `${p.rushing_yards} yds` : '-'}</td>
                              <td className="py-2.5 px-3">{p.receptions > 0 ? `${p.receptions} rec` : '-'}</td>
                              <td className="py-2.5 px-3 font-bold text-sky-400">{p.receiving_yards > 0 ? `${p.receiving_yards} yds` : '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Home Team: Seahawks */}
                  <div className="bg-[#15130F] border border-[#2B261D] rounded-xl p-4 overflow-hidden shadow-lg">
                    <div className="flex items-center gap-3 mb-4 pb-3 border-b border-zinc-800">
                      <div className="relative w-7 h-7">
                        <Image src={`/logos/${boxScoreData?.home_team || 'SEA'}.png`} alt="SEA" fill className="object-contain" />
                      </div>
                      <h3 className="text-sm font-bold text-white font-sans uppercase tracking-wider">
                        {boxScoreData?.home_team === 'SEA' ? 'Seattle Seahawks' : boxScoreData?.home_team} — Estatísticas do Jogo
                      </h3>
                    </div>

                    <div className="overflow-x-auto">
                      <table className="w-full text-left font-mono text-xs">
                        <thead className="text-[10px] text-[#C5A880] uppercase tracking-wider bg-black/40 border-b border-zinc-800">
                          <tr>
                            <th className="py-2.5 px-3">Jogador</th>
                            <th className="py-2.5 px-3">Pos</th>
                            <th className="py-2.5 px-3">Passe (C/A)</th>
                            <th className="py-2.5 px-3">Jds Passe</th>
                            <th className="py-2.5 px-3">TD/INT</th>
                            <th className="py-2.5 px-3">Carregadas</th>
                            <th className="py-2.5 px-3">Jds Corridas</th>
                            <th className="py-2.5 px-3">Recepções</th>
                            <th className="py-2.5 px-3">Jds Recebidas</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-850 text-zinc-300">
                          {boxScoreData?.home_players?.map((p: any) => (
                            <tr key={p.player_id || p.player_name} className="hover:bg-zinc-800/40">
                              <td className="py-2.5 px-3 font-semibold text-white font-sans">
                                {p.player_display_name || p.player_name}
                              </td>
                              <td className="py-2.5 px-3 text-zinc-400">{p.position}</td>
                              <td className="py-2.5 px-3">{p.attempts > 0 ? `${p.completions}/${p.attempts}` : '-'}</td>
                              <td className="py-2.5 px-3 font-bold text-white">{p.passing_yards > 0 ? `${p.passing_yards} yds` : '-'}</td>
                              <td className="py-2.5 px-3">{p.attempts > 0 ? `${p.passing_tds}/${p.passing_interceptions}` : '-'}</td>
                              <td className="py-2.5 px-3">{p.carries > 0 ? p.carries : '-'}</td>
                              <td className="py-2.5 px-3 font-bold text-emerald-400">{p.rushing_yards > 0 ? `${p.rushing_yards} yds` : '-'}</td>
                              <td className="py-2.5 px-3">{p.receptions > 0 ? `${p.receptions} rec` : '-'}</td>
                              <td className="py-2.5 px-3 font-bold text-sky-400">{p.receiving_yards > 0 ? `${p.receiving_yards} yds` : '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              ) : (
                /* Tab 2: Bets for this game */
                <div className="space-y-4">
                  <div className="flex items-center justify-between gap-3 bg-[#15130F] p-4 rounded-xl border border-zinc-800">
                    <div>
                      <h4 className="font-bold text-white text-sm">Apostas dos Jogadores de Patriots x Seahawks</h4>
                      <p className="text-zinc-400 text-xs font-mono mt-0.5">
                        Resultado apurado com as estatísticas oficiais do jogo de abertura da NFL 2026.
                      </p>
                    </div>
                    <button
                      onClick={() => handleSettlePortfolio(boxScoreData?.game_id)}
                      disabled={loadingPortfolio}
                      className="px-4 py-2 rounded-xl bg-[#10B981] hover:bg-[#10B981]/90 text-black font-mono font-bold text-xs uppercase tracking-wider flex items-center gap-1.5 transition-all shadow-md"
                    >
                      <span>{loadingPortfolio ? 'Atualizando...' : 'Verificar & Liquidar Tudo'}</span>
                    </button>
                  </div>

                  <div className="bg-[#15130F] border border-[#2B261D] rounded-xl overflow-hidden shadow-lg">
                    <div className="overflow-x-auto">
                      <table className="w-full text-left font-mono text-xs">
                        <thead className="text-[10px] text-[#C5A880] uppercase tracking-wider bg-black/40 border-b border-zinc-800">
                          <tr>
                            <th className="py-3 px-3.5">Jogador</th>
                            <th className="py-3 px-3.5">Time</th>
                            <th className="py-3 px-3.5">Mercado</th>
                            <th className="py-3 px-3.5">Linha & Lado</th>
                            <th className="py-3 px-3.5">Odd</th>
                            <th className="py-3 px-3.5">Resultado Real</th>
                            <th className="py-3 px-3.5">Status</th>
                            <th className="py-3 px-3.5">Retorno (PnL)</th>
                            <th className="py-3 px-3.5">Carteira</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-850">
                          {boxScoreData?.bets && boxScoreData.bets.length > 0 ? (
                            boxScoreData.bets.map((b: any) => {
                              const isWon = b.result === 'won';
                              const isLost = b.result === 'lost';
                              const isPush = b.result === 'push';
                              const isPending = b.result === 'pending';

                              const marketLabel = 
                                b.market === 'rushing_yards' ? 'Jardas Terrestres' :
                                b.market === 'receiving_yards' ? 'Jardas Recepção' :
                                b.market === 'passing_yards' ? 'Jardas de Passe' : b.market;

                              return (
                                <tr key={b.id} className="hover:bg-zinc-800/40 transition-colors">
                                  <td className="py-3 px-3.5 font-semibold text-white font-sans">{b.player_name}</td>
                                  <td className="py-3 px-3.5">
                                    <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 text-[10px]">
                                      {b.team}
                                    </span>
                                  </td>
                                  <td className="py-3 px-3.5 text-zinc-300 whitespace-nowrap">{marketLabel}</td>
                                  <td className="py-3 px-3.5 whitespace-nowrap">
                                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[11px] font-mono font-bold whitespace-nowrap shadow-sm ${
                                      b.side === 'over' 
                                        ? 'bg-sky-500/15 text-sky-300 border border-sky-500/30' 
                                        : 'bg-purple-500/15 text-purple-300 border border-purple-500/30'
                                    }`}>
                                      <span className="text-[9px] font-black uppercase">{b.side === 'over' ? '▲ OVER' : '▼ UNDER'}</span>
                                      <span className="text-white font-bold ml-0.5">{b.line}</span>
                                    </span>
                                  </td>
                                  <td className="py-3 px-3.5 font-bold text-white">{Number(b.odds).toFixed(2)}</td>
                                  <td className="py-3 px-3.5">
                                    {b.actual_value !== null && b.actual_value !== undefined ? (
                                      <span className="font-bold text-white">{Number(b.actual_value).toFixed(1)} yds</span>
                                    ) : (
                                      <span className="text-zinc-500 text-[11px]">Pendente</span>
                                    )}
                                  </td>
                                  <td className="py-3 px-3.5">
                                    {isWon && (
                                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                                        GREEN ✅
                                      </span>
                                    )}
                                    {isLost && (
                                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">
                                        RED ❌
                                      </span>
                                    )}
                                    {isPush && (
                                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-zinc-500/20 text-zinc-300 border border-zinc-500/40">
                                        PUSH ⚪
                                      </span>
                                    )}
                                    {isPending && (
                                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                                        PENDENTE ⏳
                                      </span>
                                    )}
                                  </td>
                                  <td className="py-3 px-3.5 font-bold">
                                    {isWon && <span className="text-emerald-400">+{Number(b.profit_units).toFixed(2)} u</span>}
                                    {isLost && <span className="text-rose-400">{Number(b.profit_units).toFixed(2)} u</span>}
                                    {isPush && <span className="text-zinc-400">0.00 u</span>}
                                    {isPending && <span className="text-zinc-500">-</span>}
                                  </td>
                                  <td className="py-3 px-3.5">
                                    <span className="text-[10px] text-zinc-400 uppercase">
                                      {b.portfolio_type === 'high_risk' ? 'Alto Risco' : b.portfolio_type === 'all_props' ? 'All Props' : 'Segura'}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })
                          ) : (
                            <tr>
                              <td colSpan={9} className="py-8 text-center text-zinc-500 font-mono text-xs">
                                Nenhuma aposta deste jogo encontrada nas carteiras.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-[#2B261D] bg-[#15130F] flex items-center justify-between">
              <div className="text-[11px] font-mono text-zinc-500">
                Dados oficiais apurados da súmula da NFL • Temporada 2026 Semana {boxScoreData?.week || currentWeek}
              </div>
              <button
                onClick={() => setBoxScoreOpen(false)}
                className="px-5 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-white font-mono text-xs uppercase tracking-wider transition-colors"
              >
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AI Unit Sizing & Contextual Explanation Modal */}
      {selectedAiBet && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-3 md:p-6 bg-black/85 backdrop-blur-md">
          <div className="bg-[#0C0C0E] border border-[#D4AF37]/50 rounded-2xl w-full max-w-2xl max-h-[92vh] flex flex-col shadow-[0_0_50px_rgba(212,175,55,0.25)] overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="p-5 border-b border-[#2B261D] bg-[#15130F] flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-[#C5A880]/15 border border-[#C5A880]/30 flex items-center justify-center text-xl shadow-inner">
                  🧠
                </div>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-lg font-bold text-white font-sans">
                      {selectedAiBet.player_name}
                    </h3>
                    {selectedAiBet.team && (
                      <span className="text-xs font-mono px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700 font-bold">
                        {selectedAiBet.team}
                      </span>
                    )}
                    {selectedAiBet.opponent && (
                      <span className="text-xs font-mono text-zinc-500">
                        vs {selectedAiBet.opponent}
                      </span>
                    )}
                    {selectedAiBet.portfolio_type === 'high_risk' ? (
                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
                        ⚡ ALTO RISCO
                      </span>
                    ) : (
                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                        🛡️ CARTEIRA CONSERVADORA
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-1 flex-wrap">
                    <span className="text-xs font-mono text-zinc-400">
                      {selectedAiBet.market === 'rushing_yards' ? 'Jardas Terrestres' :
                       selectedAiBet.market === 'receiving_yards' ? 'Jardas de Recepção' :
                       selectedAiBet.market === 'passing_yards' ? 'Jardas de Passe' : selectedAiBet.market}
                    </span>
                    <span className="text-zinc-600">•</span>
                    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-lg text-[11px] font-mono font-bold whitespace-nowrap ${
                      selectedAiBet.side?.toLowerCase() === 'over' 
                        ? 'bg-sky-500/15 text-sky-300 border border-sky-500/30' 
                        : 'bg-purple-500/15 text-purple-300 border border-purple-500/30'
                    }`}>
                      <span className="text-[9px] font-black uppercase">
                        {selectedAiBet.side?.toLowerCase() === 'over' ? '▲ OVER' : '▼ UNDER'}
                      </span>
                      <span className="text-white font-bold ml-0.5">{selectedAiBet.line}</span>
                    </span>
                    <span className="text-zinc-600">•</span>
                    <span className="text-xs font-mono text-white font-bold">
                      Odd {selectedAiBet.odds?.toFixed(2)}
                    </span>
                    {selectedAiBet.ev_percent !== undefined && selectedAiBet.ev_percent !== null && (
                      <>
                        <span className="text-zinc-600">•</span>
                        <span className="text-xs font-mono text-emerald-400 font-bold">
                          +{selectedAiBet.ev_percent?.toFixed(1)}% EV
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              <button
                onClick={() => setSelectedAiBet(null)}
                className="w-9 h-9 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-white flex items-center justify-center font-mono text-base border border-zinc-700 transition-colors"
              >
                ✕
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-5 text-sm">
              {/* Unit Sizing Decomposition Card */}
              <div className="bg-[#15130F] border border-[#2B261D] rounded-xl p-5 shadow-lg">
                <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                  <span className="text-[#C5A880] text-xs font-mono uppercase tracking-widest font-bold flex items-center gap-1.5">
                    <span>⚖️</span> Alocação Dinâmica de Unidades
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-zinc-400">Aporte Recomendado:</span>
                    <span className={`px-3 py-1 rounded-lg font-mono font-extrabold text-sm border ${
                      (selectedAiBet.units || 1.0) >= 1.25
                        ? 'bg-[#C5A880]/20 text-[#D4AF37] border-[#C5A880]/50 shadow-[0_0_12px_rgba(212,175,55,0.2)]'
                        : (selectedAiBet.units || 1.0) >= 1.0
                        ? 'bg-zinc-800 text-white border-zinc-700'
                        : 'bg-zinc-900 text-zinc-300 border-zinc-800'
                    }`}>
                      {(selectedAiBet.units || 1.0).toFixed(2)} u
                    </span>
                  </div>
                </div>

                {/* Grid of formula components */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono mb-4 text-center">
                  <div className="bg-zinc-900/80 border border-zinc-800 rounded-lg p-2.5">
                    <span className="text-[10px] text-zinc-500 uppercase block">Unidade Base (U_base)</span>
                    <span className="text-base font-bold text-white mt-1 block">
                      {(selectedAiBet.base_units || 1.0).toFixed(2)} u
                    </span>
                    <span className="text-[9px] text-zinc-500 mt-0.5 block">Faixa EV {selectedAiBet.ev_percent >= 10 ? '10-15%' : selectedAiBet.ev_percent >= 5 ? '5-10%' : '2.5-5%'}</span>
                  </div>

                  <div className="bg-zinc-900/80 border border-zinc-800 rounded-lg p-2.5">
                    <span className="text-[10px] text-zinc-500 uppercase block">Multiplicador IA (M_IA)</span>
                    <span className={`text-base font-bold mt-1 block ${
                      (selectedAiBet.ai_multiplier || 1.0) > 1.0 ? 'text-emerald-400' :
                      (selectedAiBet.ai_multiplier || 1.0) < 1.0 ? 'text-rose-400' : 'text-zinc-200'
                    }`}>
                      {(selectedAiBet.ai_multiplier || 1.0).toFixed(2)}x
                    </span>
                    <span className="text-[9px] text-zinc-500 mt-0.5 block">
                      {(selectedAiBet.ai_multiplier || 1.0) > 1.0 ? 'Boost Convicção' : (selectedAiBet.ai_multiplier || 1.0) < 1.0 ? 'Cautela / Risco' : 'Neutro'}
                    </span>
                  </div>

                  <div className="bg-zinc-900/80 border border-zinc-800 rounded-lg p-2.5">
                    <span className="text-[10px] text-zinc-500 uppercase block">Lado Favorecido</span>
                    <span className={`text-base font-bold mt-1 block uppercase ${
                      (selectedAiBet.side_favorability || selectedAiBet.side)?.toLowerCase() === 'under' ? 'text-purple-300' :
                      (selectedAiBet.side_favorability || selectedAiBet.side)?.toLowerCase() === 'over' ? 'text-sky-300' : 'text-zinc-400'
                    }`}>
                      {selectedAiBet.side_favorability || selectedAiBet.side || '-'}
                    </span>
                    <span className="text-[9px] text-zinc-500 mt-0.5 block">Lesões & Snaps</span>
                  </div>

                  <div className="bg-zinc-900/80 border border-zinc-800 rounded-lg p-2.5">
                    <span className="text-[10px] text-zinc-500 uppercase block">Discretização</span>
                    <span className="text-base font-bold text-[#D4AF37] mt-1 block">
                      Passo 0.25u
                    </span>
                    <span className="text-[9px] text-zinc-500 mt-0.5 block">[0.50u, 2.50u]</span>
                  </div>
                </div>

                {/* Sizing Rationale Quote Box */}
                <div className="bg-[#0C0C0E] border border-[#2B261D] rounded-xl p-3.5 flex items-start gap-3">
                  <span className="text-lg">💡</span>
                  <div>
                    <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-[#C5A880] block mb-0.5">
                      Por Que Esta Quantidade de Unidades?
                    </span>
                    <p className="text-xs font-sans text-zinc-200 leading-relaxed">
                      {selectedAiBet.ai_sizing_rationale || 'Alocação padrão baseada no modelo quantitativo (sem desvios contextuais na semana).'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Complete AI Thesis / Scout Section */}
              {selectedAiBet.ai_summary ? (
                <div className="bg-[#15130F] border border-[#2B261D] rounded-xl p-5 shadow-lg space-y-3">
                  <div className="flex items-center gap-2 pb-2 border-b border-[#2B261D]">
                    <span className="text-sm">📋</span>
                    <h4 className="text-xs font-mono font-bold uppercase tracking-wider text-white">
                      Tese & Análise Contextual da IA
                    </h4>
                  </div>
                  
                  <div className="space-y-2.5 font-sans text-xs leading-relaxed text-zinc-300">
                    {selectedAiBet.ai_summary.split('\n').filter((l: string) => l.trim().length > 0).map((line: string, idx: number) => {
                      const clean = line.replace(/^\*\s*/, '').trim();
                      return (
                        <div key={idx} className="flex items-start gap-2 bg-zinc-900/40 p-3 rounded-lg border border-zinc-800/80">
                          <span className="text-[#C5A880] text-sm mt-0.5">•</span>
                          <div className="flex-1" dangerouslySetInnerHTML={{
                            __html: clean.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white font-mono">$1</strong>')
                          }} />
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : selectedAiBet.notes ? (
                <div className="bg-[#15130F] border border-[#2B261D] rounded-xl p-4">
                  <span className="text-xs font-mono text-zinc-400 block mb-1">Observações da Aposta:</span>
                  <p className="text-xs text-zinc-200 font-mono">{selectedAiBet.notes}</p>
                </div>
              ) : null}

              {/* Mathematical Edge Box */}
              <div className="bg-zinc-900/40 border border-zinc-800 rounded-xl p-4 flex items-center justify-around font-mono text-center flex-wrap gap-3">
                <div>
                  <span className="text-[10px] text-zinc-500 uppercase block">Prob. Modelo</span>
                  <span className="text-sm font-bold text-white">
                    {selectedAiBet.model_probability ? `${(selectedAiBet.model_probability * 100).toFixed(1)}%` : '-'}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-zinc-500 uppercase block">Prob. Implícita</span>
                  <span className="text-sm font-bold text-zinc-300">
                    {selectedAiBet.implied_probability ? `${(selectedAiBet.implied_probability * 100).toFixed(1)}%` : '-'}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-zinc-500 uppercase block">Edge Estimado</span>
                  <span className="text-sm font-bold text-[#D4AF37]">
                    {selectedAiBet.edge ? `${selectedAiBet.edge >= 0 ? '+' : ''}${(selectedAiBet.edge * 100).toFixed(1)}%` : '-'}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-zinc-500 uppercase block">Valor Esperado (+EV)</span>
                  <span className="text-sm font-bold text-emerald-400">
                    {selectedAiBet.ev_percent ? `+${selectedAiBet.ev_percent.toFixed(1)}%` : '-'}
                  </span>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-[#2B261D] bg-[#15130F] flex items-center justify-between">
              <div className="text-[11px] font-mono text-zinc-500">
                Calibrado pelo Caliper Quant Engine & Google DeepMind AI
              </div>
              <button
                onClick={() => setSelectedAiBet(null)}
                className="px-5 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-white font-mono text-xs uppercase tracking-wider transition-colors"
              >
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Admin MFA Authentication Modal */}
      {adminModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-in fade-in duration-200">
          <div className="bg-[#0C0C0E] border border-[#D4AF37]/50 rounded-2xl w-full max-w-md overflow-hidden shadow-[0_0_50px_rgba(212,175,55,0.15)]">
            <div className="p-6 border-b border-[#2B261D] bg-[#15130F] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-[#D4AF37]/10 border border-[#D4AF37]/40 flex items-center justify-center text-lg">
                  🔐
                </div>
                <div>
                  <h3 className="font-serif text-base font-bold text-white tracking-wide">
                    Acesso de Administrador
                  </h3>
                  <span className="font-mono text-[10px] text-[#C5A880] tracking-wider uppercase">
                    Autenticação MFA (TOTP)
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setAdminModalOpen(false)}
                className="w-7 h-7 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-white flex items-center justify-center transition-colors"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleAdminLogin} className="p-6 space-y-4">
              <p className="text-xs text-zinc-400 leading-relaxed font-sans">
                Para atualizar odds em tempo real, executar scraping ou liquidar resultados, confirme suas credenciais de administrador.
              </p>

              {adminAuthError && (
                <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-500/50 text-rose-300 text-xs font-mono flex items-start gap-2">
                  <span>⚠️</span>
                  <span>{adminAuthError}</span>
                </div>
              )}

              <div className="space-y-1.5">
                <label className="text-[11px] font-mono text-zinc-300 uppercase tracking-wider block">
                  Senha de Administrador
                </label>
                <input
                  type="password"
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                  placeholder="Digite sua senha..."
                  required
                  autoFocus
                  className="w-full bg-[#15130F] border border-[#2B261D] focus:border-[#D4AF37] rounded-xl px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:outline-none transition-colors font-mono"
                />
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-mono text-zinc-300 uppercase tracking-wider block">
                    Código de 6 Dígitos (Google Authenticator / Authy)
                  </label>
                  <span className="text-[10px] font-mono text-[#D4AF37]">MFA / TOTP</span>
                </div>
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  value={adminTotp}
                  onChange={(e) => setAdminTotp(e.target.value.replace(/\D/g, ''))}
                  placeholder="000 000"
                  className="w-full bg-[#15130F] border border-[#2B261D] focus:border-[#D4AF37] rounded-xl px-4 py-2.5 text-center text-xl tracking-[0.35em] text-[#D4AF37] font-mono placeholder-zinc-700 focus:outline-none transition-colors"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setAdminModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-xs font-mono text-zinc-400 hover:text-white hover:bg-zinc-900 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={adminAuthLoading || !adminPassword}
                  className="px-5 py-2.5 rounded-xl bg-[#D4AF37] hover:bg-[#F4E8D1] text-black font-mono font-bold text-xs uppercase tracking-wider transition-all disabled:opacity-50 shadow-[0_0_20px_rgba(212,175,55,0.25)] flex items-center gap-2"
                >
                  {adminAuthLoading ? 'Validando...' : 'Desbloquear Acesso'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Precision Engineered Luxury Footer */}
      <footer className="bg-[#000000] py-14 px-6 text-center border-t border-[#2B261D] mt-auto relative z-10">
        <div className="max-w-4xl mx-auto flex flex-col items-center">
          <div className="w-56 h-28 mb-5 flex items-center justify-center">
            <img 
              src="/images/biskate-analytics-lockup-stacked-champagne-gold.svg" 
              alt="Biskate Analytics" 
              className="w-full h-full object-contain opacity-90 hover:opacity-100 transition-opacity" 
            />
          </div>
          <div className="font-mono text-xs tracking-[0.35em] uppercase text-[#C5A880] font-semibold mb-2">
            PRESTIGE QUANTITATIVE VALUE BETTING ENGINE
          </div>
          <div className="font-mono text-[11px] text-zinc-500 tracking-wider">
            © 2026–2027 BISKATE ANALYTICS • CALIPER QUANTITATIVE PROPRIETARY MODEL • ALL RIGHTS RESERVED
          </div>
          <p className="text-[10px] font-mono text-zinc-600 max-w-xl mx-auto mt-4 leading-relaxed">
            Modelos preditivos probabilísticos calibrados com XGBoost, FTN Chartering & Next Gen Stats. Apostas envolvem risco financeiro. Aposte com responsabilidade.
          </p>
        </div>
      </footer>
    </div>
  );
}
