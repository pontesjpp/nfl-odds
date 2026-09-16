'use client';

import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import Image from 'next/image';

export type PropBet = {
  id: string;
  playerName: string;
  fullPlayerName?: string;
  playerPosition: string;
  playerTeam: string;
  espnId: string;
  matchup: string;
  opponent?: string;
  metric: string;
  line: number | string;
  side?: 'over' | 'under';
  overOdds: string | number;
  underOdds: string | number;
  evPercent?: number;
  modelProb?: number;
  fairOdds?: number;
  edge?: number;
  aiSummary?: string;
  depthChartPos?: string;
  depthRole?: string;
  depthStatus?: string;
  positionTitle?: string;
  posRank?: number;
  depthString?: number;
  yearsExp?: number;
  expDesc?: string;
  jerseyNumber?: number;
  college?: string;
  depthSummary?: string;
  hasNewsAlert?: boolean;
  alertSeverity?: 'NONE' | 'INFO' | 'WARNING' | 'CRITICAL' | string;
  alertType?: string;
  alertHeadline?: string;
  newsContext?: string;
  impactAssessment?: string;
  recommendationAdjustment?: string;
  season?: number;
  week?: number;
};

import { formatStatName, getStatDescription } from '@/lib/statExplanations';

export { formatStatName, getStatDescription };


export interface PropCardProps {
  propBet: PropBet;
  selectedPick?: 'over' | 'under' | null;
  onSelectPick: (propId: string, selection: 'over' | 'under') => void;
  onAddToPortfolio?: (propBet: PropBet) => void;
  isLoading?: boolean;
}

export function PropCard({ propBet, selectedPick = null, onSelectPick, onAddToPortfolio, isLoading = false }: PropCardProps) {
  const [imgError, setImgError] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [stats, setStats] = useState<Record<string, any> | null>(null);
  const [loadingStats, setLoadingStats] = useState(false);

  if (isLoading) {
    return (
      <div className="backdrop-blur-md bg-zinc-900/80 border border-zinc-800 rounded-xl overflow-hidden flex flex-col shadow-lg animate-pulse min-h-[220px]">
        <div className="p-4 flex gap-4 border-b border-zinc-800/50">
          <div className="w-16 h-16 bg-zinc-800 rounded-full flex-shrink-0"></div>
          <div className="flex flex-col justify-center flex-1 space-y-2">
            <div className="h-5 bg-zinc-800 rounded w-3/4"></div>
            <div className="h-3 bg-zinc-800 rounded w-1/2"></div>
            <div className="h-4 bg-zinc-800 rounded w-1/4 mt-1"></div>
          </div>
        </div>
        <div className="p-4 flex-1 flex flex-col items-center justify-center space-y-3">
          <div className="h-3 bg-zinc-800 rounded w-1/3"></div>
          <div className="h-8 bg-zinc-800 rounded w-1/4"></div>
        </div>
        <div className="h-14 bg-zinc-800 border-t border-zinc-800">
          <div className="bg-zinc-900/80 w-full h-full"></div>
        </div>
      </div>
    );
  }

  const {
    id,
    playerName,
    fullPlayerName,
    playerPosition,
    playerTeam,
    espnId,
    matchup,
    opponent,
    metric,
    line,
    side = 'over',
    overOdds,
    evPercent,
    modelProb,
    fairOdds,
    edge,
    aiSummary,
    depthChartPos,
    depthRole,
    depthStatus,
    positionTitle,
    posRank,
    depthString,
    yearsExp,
    expDesc,
    jerseyNumber,
    college,
    depthSummary,
    hasNewsAlert,
    alertSeverity,
    alertType,
    alertHeadline,
    newsContext,
    impactAssessment,
    recommendationAdjustment,
    season,
    week
  } = propBet;

  const imageUrl = imgError || !espnId
    ? '/fallback-avatar.png'
    : `https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/${espnId}.png&w=350&h=254`;

  const getButtonClasses = (type: 'over' | 'under') => {
    const isSelected = selectedPick === type;
    const base = "relative flex flex-col items-center justify-center p-3 transition-all duration-200 border-t-2 outline-none group cursor-pointer w-full";
    
    if (isSelected) {
      return `${base} bg-emerald-500/10 border-emerald-500 text-emerald-400 scale-[1.02] shadow-lg shadow-emerald-500/10 z-10`;
    }
    
    return `${base} bg-zinc-900/80 border-transparent text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200`;
  };

  const handleExpand = () => {
    if (!isExpanded && !stats) {
      setLoadingStats(true);
      const oppParam = opponent ? `&opponent=${encodeURIComponent(opponent)}` : '';
      const sideParam = side ? `&side=${encodeURIComponent(side)}` : '';
      const seasonParam = season ? `&season=${season}` : '';
      const weekParam = week ? `&week=${week}` : '';
      fetch(`/api/players/${encodeURIComponent(playerName)}/features?market=${metric}&espn_id=${espnId}${oppParam}${sideParam}${seasonParam}${weekParam}`)
        .then(res => res.json())
        .then(data => {
          setStats(data);
          setLoadingStats(false);
        })
        .catch(err => {
          console.error("Error fetching stats:", err);
          setLoadingStats(false);
        });
    }
    if (!isExpanded && aiSummary) {
      setActiveTab('ai');
    }
    setIsExpanded(!isExpanded);
  };

  const [selectedStat, setSelectedStat] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'player' | 'opponent' | 'ai'>(aiSummary ? 'ai' : 'player');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (aiSummary) {
      setActiveTab('ai');
    }
  }, [aiSummary]);


  return (
    <>
      <div className="backdrop-blur-md bg-[#0C0C0E] border border-[#2B261D] rounded-2xl overflow-hidden hover:-translate-y-1 hover:border-[#C5A880]/60 transition-all duration-300 flex flex-col shadow-xl shadow-black/60">
        <div className="flex flex-col">
          <div 
            className="p-4 flex gap-4 border-b border-[#2B261D]/70 cursor-pointer hover:bg-zinc-900/30 transition-colors"
            onClick={handleExpand}
          >
            <div className="w-16 h-16 bg-zinc-900 rounded-full overflow-hidden flex-shrink-0 relative border border-[#2B261D]">
              {imageUrl !== '/fallback-avatar.png' ? (
                <Image
                  src={imageUrl}
                  alt={playerName}
                  fill
                  className="object-cover object-top"
                  onError={() => setImgError(true)}
                  sizes="64px"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-zinc-500">
                  {playerName.charAt(0)}
                </div>
              )}
            </div>
            <div className="flex flex-col justify-center flex-1">
              <div className="flex items-center gap-2">
                <h3 className="text-white font-semibold text-lg leading-tight truncate" title={fullPlayerName || playerName}>
                  {fullPlayerName || playerName}
                </h3>
                {jerseyNumber !== undefined && jerseyNumber !== null && (
                  <span className="text-[11px] font-mono font-bold text-[#C5A880] bg-[#16151A] px-1.5 py-0.5 rounded border border-[#2B261D] flex-shrink-0">
                    #{jerseyNumber}
                  </span>
                )}
              </div>
              <div className="text-zinc-400 text-sm font-medium flex items-center gap-1.5 mt-1 flex-wrap">
                {depthChartPos ? (
                  <span 
                    className={`font-mono text-xs font-bold px-2 py-0.5 rounded border ${
                      depthRole === 'Titular' || posRank === 1
                        ? 'bg-[#C5A880]/15 text-[#F4E8D1] border-[#C5A880]/40' 
                        : 'bg-zinc-800/60 text-zinc-300 border-zinc-700/60'
                    }`}
                    title={`${depthSummary || depthRole || ''}`}
                  >
                    {depthChartPos}
                  </span>
                ) : (
                  <span className="font-bold text-zinc-300">{playerPosition || 'POS'}</span>
                )}
                {depthRole && (
                  <span className="text-[11px] font-medium text-zinc-400 hidden sm:inline">
                    {depthRole}
                  </span>
                )}
                <span className="text-zinc-600">&bull;</span>
                <span className="flex items-center gap-1 text-zinc-300">
                  {playerTeam || 'TEAM'}
                  {playerTeam && (
                    <Image src={`/logos/${playerTeam}.png`} alt={playerTeam} width={16} height={16} className="object-contain" />
                  )}
                  {opponent && <span className="text-zinc-600 mx-0.5 text-[10px]">vs</span>}
                  {opponent && (
                    <Image src={`/logos/${opponent}.png`} alt={opponent} width={12} height={12} className="object-contain opacity-70 grayscale hover:grayscale-0 transition-all" title={`Adversário: ${opponent}`} />
                  )}
                </span>
              </div>
              <div className="text-zinc-400 text-xs mt-1 bg-[#16151A] border border-[#2B261D]/80 inline-flex px-2 py-0.5 rounded-md w-fit font-mono tracking-wide">
                {matchup}
              </div>
            </div>
          </div>
          
          <div 
            className="p-5 flex-1 flex flex-col items-center justify-center min-h-[100px] cursor-pointer"
            onClick={handleExpand}
          >
            <p className="text-zinc-400 text-xs uppercase tracking-widest font-semibold mb-1 text-center">
              {metric}
            </p>
            <p className="text-4xl font-bold text-white tracking-tight">
              {side === 'over' ? 'OVER' : 'UNDER'} {line}
            </p>
            {typeof evPercent === 'number' && (
              <div className={`mt-3 px-3 py-1 rounded-full text-xs font-bold tracking-widest uppercase font-mono border ${evPercent > 0 ? 'bg-[#10B981]/15 text-[#10B981] border-[#10B981]/30' : 'bg-rose-500/15 text-rose-400 border-rose-500/30'}`}>
                EV: {evPercent > 0 ? '+' : ''}{evPercent.toFixed(2)}%
              </div>
            )}
            {aiSummary && (
              <div className="mt-2 flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-[#C5A880]/10 border border-[#C5A880]/30 text-[10px] font-mono text-[#C5A880]">
                <span className="w-1.5 h-1.5 rounded-full bg-[#D4AF37] animate-pulse"></span>
                <span>Análise IA Disponível</span>
              </div>
            )}
            {hasNewsAlert && alertHeadline && (
              <div 
                className={`mt-2 flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold border transition-all max-w-[95%] truncate ${
                  alertSeverity === 'CRITICAL'
                    ? 'bg-rose-950/60 border-rose-500/70 text-rose-300 shadow-md shadow-rose-950/50 animate-pulse'
                    : alertSeverity === 'WARNING'
                    ? 'bg-amber-950/60 border-amber-500/70 text-amber-300 shadow-md shadow-amber-950/50'
                    : 'bg-sky-950/60 border-sky-500/70 text-sky-300'
                }`}
                title={alertHeadline}
              >
                <span>{alertSeverity === 'CRITICAL' ? '🚨' : alertSeverity === 'WARNING' ? '⚠️' : 'ℹ️'}</span>
                <span className="truncate">
                  {alertType === 'TIMESHARE_TARGETS' ? 'Timeshare / Targets' : alertType === 'INJURY' ? 'Alerta Médico' : 'Notícia da Semana'}
                </span>
              </div>
            )}
            <div className="mt-3 text-zinc-400 hover:text-[#C5A880] text-[10px] uppercase font-mono tracking-widest flex items-center gap-1 transition-colors">
              <span>{aiSummary ? 'Ver Análise & Stats' : 'Ver Estatísticas'}</span>
              <svg className="w-3 h-3 text-[#C5A880]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
            </div>
          </div>
        </div>

        <div className="bg-[#121216] border-t border-[#2B261D] mt-auto flex divide-x divide-[#2B261D]">
          <button
            onClick={() => onSelectPick(id, 'over')}
            className={`${getButtonClasses('over')} flex-1`}
            aria-pressed={selectedPick === 'over'}
          >
            <span className="text-[10px] uppercase font-bold tracking-widest mb-0.5 opacity-80 group-hover:opacity-100">
              Apostar no {side === 'over' ? 'Over' : 'Under'}
            </span>
            <span className="font-semibold text-sm">{overOdds}</span>
          </button>
          {onAddToPortfolio && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onAddToPortfolio(propBet);
              }}
              title="Registrar 1.0 unidade na Carteira de Investimentos"
              className="px-3.5 py-3 bg-[#16151A] hover:bg-[#10B981]/20 text-zinc-300 hover:text-[#10B981] text-[10px] font-mono font-bold tracking-wider uppercase transition-colors flex items-center justify-center gap-1.5 flex-shrink-0 border-l border-[#2B261D]"
            >
              <svg className="w-3.5 h-3.5 text-[#10B981]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
              </svg>
              <span>1.0 u</span>
            </button>
          )}
        </div>
      </div>

      {isExpanded && mounted && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm" onClick={handleExpand}>
          <div 
            className="bg-[#0C0C0E] border border-[#2B261D] rounded-3xl w-full max-w-4xl max-h-[90vh] overflow-y-auto shadow-2xl shadow-black flex flex-col"
            onClick={e => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-[#0C0C0E]/95 backdrop-blur-md border-b border-[#2B261D] p-5 flex justify-between items-center z-10">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 bg-zinc-900 rounded-full overflow-hidden flex-shrink-0 relative border border-[#2B261D]">
                  {imageUrl !== '/fallback-avatar.png' ? (
                    <Image src={imageUrl} alt={playerName} fill className="object-cover object-top" sizes="48px" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-zinc-500">{playerName.charAt(0)}</div>
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-xl font-bold text-white">{fullPlayerName || playerName}</h2>
                    {jerseyNumber !== undefined && jerseyNumber !== null && (
                      <span className="text-xs font-mono font-bold text-[#C5A880] bg-[#16151A] px-2 py-0.5 rounded border border-[#2B261D]">
                        #{jerseyNumber}
                      </span>
                    )}
                  </div>
                  <p className="text-zinc-400 text-sm">{metric} &bull; {side === 'over' ? 'OVER' : 'UNDER'} {line}</p>
                </div>
              </div>
              <button 
                onClick={handleExpand}
                className="w-10 h-10 bg-[#16151A] hover:bg-zinc-800 border border-[#2B261D] rounded-full flex items-center justify-center text-zinc-400 hover:text-white transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="p-6">
              {depthChartPos && (
                <div className="mb-6 flex flex-wrap items-center justify-between gap-3 bg-black/60 border border-[#2B261D] rounded-xl px-4 py-3">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <span className="text-xs font-mono font-bold uppercase tracking-wider text-[#C5A880] flex items-center gap-1.5">
                      Depth Chart Oficial:
                    </span>
                    <span className="text-xs font-semibold text-[#F4E8D1] bg-[#16151A] px-2 py-0.5 rounded border border-[#2B261D]">
                      {depthChartPos} {positionTitle ? `• ${positionTitle}` : ''}
                    </span>
                    {depthRole && (
                      <span className={`text-[11px] font-bold px-2 py-0.5 rounded border ${depthRole.includes('Titular') ? 'bg-[#C5A880]/15 text-[#F4E8D1] border-[#C5A880]/30' : 'bg-zinc-800/80 text-zinc-300 border-zinc-700/60'}`}>
                        {depthRole} {posRank ? `(#${posRank} na posição)` : ''}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-zinc-400 font-mono">
                    {expDesc && <span>{expDesc}</span>}
                    {college && <span>&bull; {college}</span>}
                  </div>
                </div>
              )}
              <div className="mb-8 grid grid-cols-1 sm:grid-cols-3 gap-6 bg-black/40 p-6 rounded-2xl border border-[#2B261D]">
                 <div className="flex flex-col items-center">
                   <span className="text-zinc-500 uppercase tracking-widest text-xs mb-2">Model Prob</span>
                   <span className="text-3xl font-bold text-white">{modelProb ? (modelProb * 100).toFixed(1) + '%' : 'N/A'}</span>
                 </div>
                 <div className="flex flex-col items-center">
                   <span className="text-zinc-500 uppercase tracking-widest text-xs mb-2">Fair Odds</span>
                   <span className="text-3xl font-bold text-white">{fairOdds ? fairOdds.toFixed(2) : 'N/A'}</span>
                 </div>
                 <div className="flex flex-col items-center">
                   <span className="text-zinc-500 uppercase tracking-widest text-xs mb-2">Edge</span>
                   <span className="text-3xl font-bold text-[#10B981]">{edge ? (edge * 100).toFixed(1) + '%' : 'N/A'}</span>
                 </div>
              </div>
              
              <div className="flex gap-6 border-b border-[#2B261D] mb-4">
                {aiSummary && (
                  <button 
                    onClick={() => setActiveTab('ai')} 
                    className={`pb-2 text-[10px] font-bold tracking-widest uppercase transition-colors flex items-center gap-1.5 ${activeTab === 'ai' ? 'text-[#C5A880] border-b-2 border-[#D4AF37]' : 'text-zinc-500 hover:text-zinc-300'}`}
                  >
                    <span>Análise IA (Gemini)</span>
                  </button>
                )}
                <button 
                  onClick={() => setActiveTab('player')} 
                  className={`pb-2 text-[10px] font-bold tracking-widest uppercase transition-colors ${activeTab === 'player' ? 'text-[#D4AF37] border-b-2 border-[#D4AF37]' : 'text-zinc-500 hover:text-zinc-300'}`}
                >
                  Estatísticas do Jogador
                </button>
                <button 
                  onClick={() => setActiveTab('opponent')} 
                  className={`pb-2 text-[10px] font-bold tracking-widest uppercase transition-colors flex items-center gap-2 ${activeTab === 'opponent' ? 'text-zinc-300 border-b-2 border-zinc-300' : 'text-zinc-500 hover:text-zinc-300'}`}
                >
                  Estatísticas do Adversário {opponent && `(${opponent})`}
                </button>
              </div>
              {activeTab === 'ai' ? (
                <div className="bg-[#08080A] border border-[#C5A880]/30 rounded-2xl p-6 shadow-2xl relative">
                  <div className="flex items-center justify-between mb-5 pb-3 border-b border-[#2B261D]">
                    <div className="flex items-center gap-2.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-[#D4AF37] animate-pulse"></span>
                      <span className="text-xs font-mono font-bold tracking-wider text-[#C5A880] uppercase">
                        Gemini 2.5 Flash • Resumo de Valor
                      </span>
                    </div>
                    <span className="text-[10px] font-mono font-semibold text-[#10B981] bg-[#10B981]/15 px-2.5 py-1 rounded-md border border-[#10B981]/30">
                      RECOMMENDED PICK
                    </span>
                  </div>
                  {/* News Scout Alert Banner */}
                  {hasNewsAlert && alertHeadline && (
                    <div className={`mb-5 p-4 rounded-xl border flex flex-col gap-2.5 ${
                      alertSeverity === 'CRITICAL'
                        ? 'bg-rose-950/30 border-rose-500/40 text-rose-200'
                        : alertSeverity === 'WARNING'
                        ? 'bg-amber-950/30 border-amber-500/40 text-amber-200'
                        : 'bg-sky-950/30 border-sky-500/40 text-sky-200'
                    }`}>
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-2">
                          <span className="text-base">
                            {alertSeverity === 'CRITICAL' ? '🚨' : alertSeverity === 'WARNING' ? '⚠️' : 'ℹ️'}
                          </span>
                          <span className="font-mono text-xs font-bold uppercase tracking-wider">
                            Boletim Semanal • {alertType === 'TIMESHARE_TARGETS' ? 'Timeshare / Divisão de Toques' : alertType === 'INJURY' ? 'Status Médico / Lesão' : 'Notícia do Jogador'}
                          </span>
                        </div>
                        {recommendationAdjustment && (
                          <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border uppercase ${
                            recommendationAdjustment === 'AVOID'
                              ? 'bg-rose-500/20 border-rose-500/40 text-rose-300'
                              : recommendationAdjustment === 'CAUTION'
                              ? 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                              : 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300'
                          }`}>
                            Ajuste: {recommendationAdjustment}
                          </span>
                        )}
                      </div>
                      <p className="font-semibold text-sm text-white leading-snug">
                        {alertHeadline}
                      </p>
                      {impactAssessment && (
                        <p className="text-xs text-zinc-300 leading-relaxed font-sans bg-black/40 p-2.5 rounded-lg border border-white/5">
                          <strong className="text-white font-mono">Impacto no Prop:</strong> {impactAssessment}
                        </p>
                      )}
                      {newsContext && newsContext !== alertHeadline && (
                        <p className="text-[11px] text-zinc-400 leading-relaxed italic line-clamp-3">
                          &ldquo;{newsContext}&rdquo;
                        </p>
                      )}
                    </div>
                  )}
                  {aiSummary ? (
                    <div className="space-y-3.5 text-sm text-zinc-200 leading-relaxed font-sans">
                      {aiSummary.split('\n').filter((line: string) => line.trim().length > 0).map((line: string, idx: number) => {
                        const cleanLine = line.replace(/^[\*\-]\s*/, '');
                        const parts = cleanLine.split(':');
                        if (parts.length > 1 && cleanLine.includes('**')) {
                          const title = parts[0].replace(/\*\*/g, '').trim();
                          const body = parts.slice(1).join(':').trim();
                          const isRisk = title.toLowerCase().includes('risco') || title.toLowerCase().includes('contraponto');
                          return (
                            <div key={idx} className={`flex gap-3 items-start p-4 rounded-xl border transition-colors ${
                              isRisk 
                                ? 'bg-amber-950/15 border-amber-500/30 hover:border-amber-500/50' 
                                : 'bg-zinc-900/90 border-zinc-800 hover:border-zinc-700/80'
                            }`}>
                              <div className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 shadow-sm ${
                                isRisk ? 'bg-amber-400 shadow-amber-500/50' : 'bg-emerald-400 shadow-emerald-500/50'
                              }`} />
                              <div className="flex-1">
                                <span className={`font-bold tracking-wide ${isRisk ? 'text-amber-300' : 'text-white'}`}>{title}: </span>
                                <span 
                                  className="text-zinc-300"
                                  dangerouslySetInnerHTML={{
                                    __html: body.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white font-mono">$1</strong>')
                                  }}
                                />
                              </div>
                            </div>
                          );
                        }
                        return (
                          <p 
                            key={idx} 
                            className="text-zinc-300 bg-zinc-900/50 p-3 rounded-lg border border-zinc-800/50"
                            dangerouslySetInnerHTML={{
                              __html: cleanLine.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white font-mono">$1</strong>')
                            }}
                          />
                        );
                      })}
                    </div>
                  ) : (
                    <div className="text-center py-10 text-zinc-500 font-mono text-xs">
                      Análise gerada automaticamente pelo pipeline para apostas recomendadas com EV positivo seguro.
                    </div>
                  )}
                </div>
              ) : loadingStats ? (
                <div className="animate-pulse grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
                  {[...Array(8)].map((_, i) => (
                    <div key={i} className="h-16 bg-zinc-800 rounded"></div>
                  ))}
                </div>
              ) : stats ? (
                activeTab === 'opponent' ? (
                  <div className="space-y-6">
                    {/* Opponent Profile Hero Banner */}
                    {stats._opponent_profile && (
                      <div className="bg-[#0A0A0D] border border-[#2B261D] rounded-2xl p-5 shadow-xl">
                        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-[#2B261D]">
                          <div className="flex items-center gap-3">
                            <div className="w-12 h-12 bg-zinc-900 rounded-xl flex items-center justify-center p-2 border border-[#2B261D] flex-shrink-0">
                              <Image 
                                src={`/logos/${stats._opponent_profile.team}.png`} 
                                alt={stats._opponent_profile.team} 
                                width={36} 
                                height={36} 
                                className="object-contain" 
                              />
                            </div>
                            <div>
                              <div className="flex items-center gap-2 flex-wrap">
                                <h3 className="text-white font-bold text-lg leading-tight">
                                  {stats._opponent_profile.team_name}
                                </h3>
                                <span className="text-xs font-mono text-zinc-400 bg-zinc-800/80 px-2 py-0.5 rounded border border-zinc-700">
                                  {stats._opponent_profile.team}
                                </span>
                              </div>
                              <p className="text-[11px] font-mono text-zinc-400 mt-0.5">
                                {stats._opponent_profile.season_source}
                              </p>
                            </div>
                          </div>

                          <div className="flex flex-col sm:items-end">
                            <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-1">
                              Rank Geral Defensivo
                            </span>
                            <div className={`px-3 py-1 rounded-full text-xs font-mono font-bold border flex items-center gap-1.5 ${
                              stats._opponent_profile.overall_rank <= 10 
                                ? 'bg-rose-950/40 text-rose-300 border-rose-800/50' 
                                : stats._opponent_profile.overall_rank <= 22 
                                ? 'bg-zinc-800 text-zinc-300 border-zinc-700' 
                                : 'bg-emerald-950/40 text-emerald-300 border-emerald-800/50'
                            }`}>
                              <span>#{stats._opponent_profile.overall_rank} na NFL</span>
                              <span>•</span>
                              <span>{stats._opponent_profile.overall_tier_label}</span>
                            </div>
                          </div>
                        </div>

                        {/* Matchup Insight Banner */}
                        {stats._opponent_profile.insight && (
                          <div className={`mt-4 p-3.5 rounded-xl border text-xs font-mono flex items-start gap-2.5 ${
                            stats._opponent_profile.insight_type === 'favorable'
                              ? 'bg-emerald-950/25 border-emerald-500/40 text-emerald-300'
                              : stats._opponent_profile.insight_type === 'unfavorable'
                              ? 'bg-rose-950/25 border-rose-500/40 text-rose-300'
                              : 'bg-zinc-900 border-zinc-800 text-zinc-300'
                          }`}>
                            <span className="font-bold uppercase tracking-wider flex-shrink-0">
                              Insight do Confronto:
                            </span>
                            <span className="leading-relaxed">
                              {stats._opponent_profile.insight}
                            </span>
                          </div>
                        )}

                        {/* 4 Quick Pillars */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
                          <div className="bg-zinc-900/60 p-3 rounded-xl border border-zinc-800">
                            <span className="text-zinc-500 text-[10px] font-mono uppercase tracking-wider block">Contra o Passe</span>
                            <span className="text-base font-bold font-mono text-white mt-1 block">
                              #{stats._opponent_profile.summary.pass_rank || 'N/A'} na NFL
                            </span>
                            <span className="text-zinc-400 text-[11px] font-mono mt-0.5 block">
                              {stats._opponent_profile.summary.pass_yds ? `${stats._opponent_profile.summary.pass_yds} yds/j` : '-'}
                            </span>
                          </div>

                          <div className="bg-zinc-900/60 p-3 rounded-xl border border-zinc-800">
                            <span className="text-zinc-500 text-[10px] font-mono uppercase tracking-wider block">Contra a Corrida</span>
                            <span className="text-base font-bold font-mono text-white mt-1 block">
                              #{stats._opponent_profile.summary.rush_rank || 'N/A'} na NFL
                            </span>
                            <span className="text-zinc-400 text-[11px] font-mono mt-0.5 block">
                              {stats._opponent_profile.summary.rush_yds ? `${stats._opponent_profile.summary.rush_yds} yds/j` : '-'}
                            </span>
                          </div>

                          <div className="bg-zinc-900/60 p-3 rounded-xl border border-zinc-800">
                            <span className="text-zinc-500 text-[10px] font-mono uppercase tracking-wider block">Pressão no QB (Quarterback)</span>
                            <span className="text-base font-bold font-mono text-white mt-1 block">
                              #{stats._opponent_profile.summary.pressure_rank || 'N/A'} na NFL
                            </span>
                            <span className="text-zinc-400 text-[11px] font-mono mt-0.5 block">
                              {stats._opponent_profile.summary.pressure_rank <= 10 ? 'Pressão Alta (Elite)' : stats._opponent_profile.summary.pressure_rank >= 23 ? 'Pressão Baixa (Vulnerável)' : 'Pressão Média'}
                            </span>
                          </div>

                          <div className="bg-zinc-900/60 p-3 rounded-xl border border-zinc-800">
                            <span className="text-zinc-500 text-[10px] font-mono uppercase tracking-wider block">Eficiência: EPA (Pontos Esperados)</span>
                            <span className="text-base font-bold font-mono text-white mt-1 block">
                              Passe #{stats._opponent_profile.summary.pass_epa_rank || 'N/A'}
                            </span>
                            <span className="text-zinc-400 text-[11px] font-mono mt-0.5 block">
                              Corrida #{stats._opponent_profile.summary.rush_epa_rank || 'N/A'}
                            </span>
                          </div>
                        </div>

                        {/* Explainer Tip Banner */}
                        <div className="flex items-center justify-between text-[11px] font-mono text-zinc-400 bg-zinc-900/50 px-3.5 py-2.5 rounded-xl border border-zinc-800/80 mt-3">
                          <span>Clique em qualquer cartão abaixo para ver a explicação detalhada de siglas (como EPA, Taxa de Pressão, Run Stop) e interpretação.</span>
                          <span className="text-[#C5A880] font-semibold flex-shrink-0 ml-2">Explicador Ativo</span>
                        </div>
                      </div>
                    )}

                    {/* Detailed Defensive Metrics Grid */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                      {Object.entries(stats)
                        .filter(([key]) => key.startsWith('def_') && !key.startsWith('_'))
                        .map(([key, data]) => {
                          const val = data?.value;
                          const rank = data?.rank;
                          const leagueAvg = data?.league_avg;
                          const diffPct = data?.pct_diff_league;
                          const isSelected = selectedStat === key;

                          return (
                            <div
                              key={key}
                              onClick={() => setSelectedStat(isSelected ? null : key)}
                              className={`bg-zinc-900/80 border p-4 rounded-xl transition-all cursor-pointer relative flex flex-col justify-between ${
                                isSelected 
                                  ? 'border-rose-500/80 bg-rose-950/20 ring-1 ring-rose-500/40' 
                                  : 'border-zinc-800 hover:border-zinc-700'
                              }`}
                            >
                              <div>
                                <div className="flex justify-between items-start gap-2 mb-2">
                                  <span className="text-zinc-300 text-[11px] uppercase tracking-wider font-semibold leading-snug">
                                    {formatStatName(key)}
                                  </span>
                                  {rank && (
                                    <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border whitespace-nowrap ${
                                      rank <= 10 
                                        ? 'bg-rose-950/40 text-rose-300 border-rose-800/40' 
                                        : rank <= 22 
                                        ? 'bg-zinc-800 text-zinc-300 border-zinc-700' 
                                        : 'bg-emerald-950/40 text-emerald-300 border-emerald-800/40'
                                    }`}>
                                      #{rank} de 32
                                    </span>
                                  )}
                                </div>

                                <div className="flex items-baseline gap-2 mt-1">
                                  <span className="text-2xl font-bold font-mono text-white">
                                    {val !== null && val !== undefined ? Number(val).toFixed(2) : 'N/A'}
                                  </span>
                                  {data?.unit && (
                                    <span className="text-xs font-mono text-zinc-500">{data.unit}</span>
                                  )}
                                </div>

                                {/* League Avg & Comparison */}
                                {leagueAvg !== undefined && leagueAvg !== null && (
                                  <div className="mt-2 text-[11px] font-mono flex items-center justify-between text-zinc-400 border-t border-zinc-800/70 pt-2">
                                    <span>Média NFL: {leagueAvg}</span>
                                    {diffPct !== undefined && diffPct !== null && (
                                      <span className={`font-bold ${diffPct >= 0 ? 'text-amber-400' : 'text-zinc-400'}`}>
                                        {diffPct >= 0 ? '+' : ''}{diffPct}%
                                      </span>
                                    )}
                                  </div>
                                )}

                                {/* Rank Position Gauge (1 to 32) */}
                                {rank && (
                                  <div className="w-full bg-zinc-800 h-1.5 rounded-full overflow-hidden mt-3">
                                    <div 
                                      className={`h-full rounded-full transition-all ${
                                        rank <= 10 ? 'bg-rose-500' : rank <= 22 ? 'bg-zinc-500' : 'bg-emerald-500'
                                      }`}
                                      style={{ width: `${Math.max(6, (rank / 32) * 100)}%` }}
                                      title={`Posição ${rank} de 32 na NFL`}
                                    />
                                  </div>
                                )}
                              </div>

                              {isSelected ? (
                                <div className="mt-3 pt-3 border-t border-rose-900/50 text-[11px] text-zinc-200 leading-relaxed font-sans bg-black/40 -mx-4 -mb-4 p-3 rounded-b-xl">
                                  <div className="text-rose-300 font-bold mb-1 font-mono text-[10px] uppercase tracking-wider">
                                    O que significa esta métrica:
                                  </div>
                                  <p>{getStatDescription(key)}</p>
                                </div>
                              ) : (
                                <div className="mt-2.5 pt-1.5 text-[10px] text-zinc-500 font-mono flex items-center justify-between">
                                  <span>[?] Clique para ver significado da sigla</span>
                                </div>
                              )}
                            </div>
                          );
                        })}
                    </div>
                  </div>
                ) : (
                  /* Player Offensive Stats Grid */
                  <div className="space-y-3">
                    <div className="flex items-center justify-between text-[11px] font-mono text-zinc-400 bg-zinc-900/50 px-3.5 py-2.5 rounded-xl border border-zinc-800/80">
                      <span>Clique em qualquer cartão para ver a explicação detalhada de siglas (EPA, CPOE, aDOT, WOPR, RYBC, RYAC, YAC, PROE, etc.).</span>
                      <span className="text-[#C5A880] font-semibold flex-shrink-0 ml-2">Explicador Ativo</span>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                      {Object.entries(stats)
                        .filter(([key]) => !key.startsWith('def_') && !key.startsWith('_'))
                        .map(([key, data]) => {
                        const val = data?.value;
                        const imp = data?.importance;
                        const isSelected = selectedStat === key;
                        return (
                          <div 
                            key={key} 
                            onClick={() => setSelectedStat(isSelected ? null : key)}
                            className={`flex flex-col justify-between bg-zinc-900/60 p-3.5 rounded-xl border hover:bg-zinc-800/60 transition-colors relative cursor-pointer ${
                              isSelected 
                                ? 'border-amber-500/70 bg-zinc-900/90 ring-1 ring-amber-500/40 shadow-lg' 
                                : 'border-zinc-800/80'
                            }`}
                          >
                            <div>
                              <span className="text-zinc-300 text-[11px] uppercase tracking-wider mb-2 leading-tight pr-8 font-medium block">
                                {formatStatName(key)}
                              </span>
                              <span className="text-white font-bold text-lg font-mono">
                                {val !== null && val !== undefined ? Number(val).toFixed(2) : 'N/A'}
                              </span>
                              {imp !== undefined && imp > 0 && (
                                <div className="absolute top-2.5 right-2.5 flex flex-col items-end">
                                  <span className="text-[9px] font-mono font-bold text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20" title="Influência global no modelo">
                                    {(imp * 100).toFixed(1)}%
                                  </span>
                                </div>
                              )}
                            </div>
                            
                            {isSelected ? (
                              <div className="mt-3 pt-2.5 border-t border-amber-500/30 text-[11px] text-zinc-200 leading-relaxed font-sans bg-black/40 -mx-3.5 -mb-3.5 p-3 rounded-b-xl">
                                <div className="text-amber-400 font-bold mb-1 font-mono text-[10px] uppercase tracking-wider">
                                  Significado da Sigla e Métrica:
                                </div>
                                <p>{getStatDescription(key)}</p>
                              </div>
                            ) : (
                              <div className="mt-2 text-[9px] text-zinc-500 font-mono">
                                [?] Ver significado
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )
              ) : (
                <div className="text-rose-400 p-6 bg-rose-500/10 rounded border border-rose-500/20 text-center">
                  Estatísticas indisponíveis ou não encontradas.
                </div>
              )}
            </div>
            
            <div className="p-4 border-t border-zinc-800 bg-zinc-900 flex justify-end">
               <button 
                 onClick={handleExpand}
                 className="px-6 py-2 bg-zinc-100 hover:bg-white text-zinc-900 font-bold tracking-widest uppercase text-xs rounded-full transition-colors"
               >
                 Fechar Detalhes
               </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
