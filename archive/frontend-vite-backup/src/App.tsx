import { useState, useEffect } from 'react'

interface PlayerFeatures {
  [key: string]: number | null
}

function App() {
  const [mode, setMode] = useState<'calculator' | 'live_bets' | 'schedule' | 'top_picks'>('schedule')
  const [players, setPlayers] = useState<string[]>([])
  const [selectedPlayer, setSelectedPlayer] = useState<string>('')
  const [features, setFeatures] = useState<PlayerFeatures | null>(null)
  
  const [topPicks, setTopPicks] = useState<any[]>([])
  
  const [line, setLine] = useState<number>(60.5)
  const [oddsOver, setOddsOver] = useState<number>(1.90)
  const [oddsUnder, setOddsUnder] = useState<number>(1.90)
  
  const [result, setResult] = useState<any>(null)
  const [liveBets, setLiveBets] = useState<any[]>([])
  const [schedule, setSchedule] = useState<any[]>([])
  const [selectedGame, setSelectedGame] = useState<any>(null)

  useEffect(() => {
    fetch('http://localhost:8000/api/players')
      .then(res => res.json())
      .then(data => {
        setPlayers(data)
        if (data.length > 0) setSelectedPlayer(data[0])
      })
      .catch(err => console.error("API error:", err))
      
    fetch('http://localhost:8000/api/live-bets')
      .then(res => res.json())
      .then(data => setLiveBets(data))
      .catch(err => console.error(err))

    fetch('http://localhost:8000/api/schedule')
      .then(res => res.json())
      .then(data => setSchedule(data))
      .catch(err => console.error(err))

    fetch('http://localhost:8000/api/top-picks?limit=15')
      .then(res => res.json())
      .then(data => setTopPicks(data))
      .catch(err => console.error(err))
  }, [])

  useEffect(() => {
    if (selectedPlayer) {
      fetch(`http://localhost:8000/api/players/${selectedPlayer}/features`)
        .then(res => res.json())
        .then(data => setFeatures(data))
        .catch(err => console.error(err))
    }
  }, [selectedPlayer])

  const calculateEV = () => {
    fetch('http://localhost:8000/api/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        player_name: selectedPlayer,
        line,
        odds_over: oddsOver,
        odds_under: oddsUnder
      })
    })
    .then(res => res.json())
    .then(data => setResult(data))
    .catch(err => console.error(err))
  }

  return (
    <>
      <div style={{
        height: '56px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 40px',
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 10
      }}>
        <span className="caption-uppercase">MENU</span>
        <span style={{
          fontFamily: 'var(--font-display)',
          fontSize: '14px',
          letterSpacing: '6px'
        }}>BUGATTI</span>
        <span className="caption-uppercase">STORE</span>
      </div>

      <div style={{
        margin: '0',
        height: '400px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column'
      }}>
        <h1 style={{ paddingTop: '56px', textAlign: 'center' }}>
          {mode === 'calculator' ? 'VALUE BETTING' : 'LIVE BETCLIC ODDS'}
        </h1>
        <span className="caption-uppercase">
          {mode === 'calculator' ? 'SIMULADOR DE ODDS DE NFL' : 'MARKET EDGE DETECTION'}
        </span>
      </div>

      <div className="container" style={{ marginTop: '-40px', position: 'relative', zIndex: 5 }}>
        <div className="flex" style={{ gap: '24px', borderBottom: '1px solid var(--hairline)', paddingBottom: '16px', marginBottom: '40px' }}>
          <button 
            style={{ backgroundColor: mode === 'schedule' ? '#ffffff' : 'transparent', color: mode === 'schedule' ? '#000000' : '#ffffff' }}
            onClick={() => setMode('schedule')}
          >
            Agenda
          </button>
          <button 
            style={{ backgroundColor: mode === 'top_picks' ? '#ffffff' : 'transparent', color: mode === 'top_picks' ? '#000000' : '#ffffff' }}
            onClick={() => setMode('top_picks')}
          >
            Top Picks ⭐
          </button>
          <button 
            style={{ backgroundColor: mode === 'live_bets' ? '#ffffff' : 'transparent', color: mode === 'live_bets' ? '#000000' : '#ffffff' }}
            onClick={() => setMode('live_bets')}
          >
            Live Betclic Lines
          </button>
          <button 
            style={{ backgroundColor: mode === 'calculator' ? '#ffffff' : 'transparent', color: mode === 'calculator' ? '#000000' : '#ffffff' }}
            onClick={() => setMode('calculator')}
          >
            Live Calculator
          </button>
        </div>

        {mode === 'schedule' && (
          <div>
            <p className="title-md mb-8">
              Agenda de Jogos (Week 1 - 2026)
            </p>
            <div className="grid-2">
              {schedule.length === 0 ? (
                 <p className="caption-uppercase">Carregando agenda...</p>
              ) : (
                schedule.map((game, i) => (
                  <div key={i} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div className="flex" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                       <div className="flex" style={{ alignItems: 'center', gap: '16px' }}>
                         <img src={`/logos/${game.away_team}.png`} alt={game.away_team} style={{ width: '40px', height: '40px', objectFit: 'contain' }} />
                         <span style={{ fontWeight: 'bold' }}>@</span>
                         <img src={`/logos/${game.home_team}.png`} alt={game.home_team} style={{ width: '40px', height: '40px', objectFit: 'contain' }} />
                       </div>
                       <div style={{ textAlign: 'right' }}>
                         <div className="caption-uppercase" style={{ fontSize: '10px' }}>{game.gameday} • {game.gametime} ET</div>
                         <div style={{ color: 'var(--muted)', fontSize: '12px' }}>{game.stadium}</div>
                       </div>
                    </div>
                    <button 
                      onClick={() => {
                        setSelectedGame(game);
                        setMode('live_bets');
                      }}
                      style={{ width: '100%', padding: '12px', marginTop: '8px' }}
                    >
                      VER ODDS
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {mode === 'calculator' && (
          <div>
            <p className="title-md mb-8">
              Selecione o jogador para carregar seu histórico recente e calcular EV para linhas personalizadas.
            </p>

            <div className="grid-2">
              <div>
                <h3>1. SELECIONE O JOGADOR</h3>
                <div className="mb-4">
                  <label>Jogador</label>
                  <select value={selectedPlayer} onChange={e => setSelectedPlayer(e.target.value)}>
                    {players.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
                {features && (
                  <div className="card">
                    <div className="caption-uppercase mb-4">ESTATÍSTICAS RECENTES (FEATURES)</div>
                    <pre style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--muted)', whiteSpace: 'pre-wrap' }}>
                      {JSON.stringify(features, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              <div>
                <h3>2. LINHA DA CASA DE APOSTA</h3>
                <div className="mb-4">
                  <label>Rushing Yards Line</label>
                  <input type="number" step="0.5" value={line} onChange={e => setLine(parseFloat(e.target.value))} />
                </div>
                <div className="mb-4">
                  <label>Odds OVER</label>
                  <input type="number" step="0.01" value={oddsOver} onChange={e => setOddsOver(parseFloat(e.target.value))} />
                </div>
                <div className="mb-4">
                  <label>Odds UNDER</label>
                  <input type="number" step="0.01" value={oddsUnder} onChange={e => setOddsUnder(parseFloat(e.target.value))} />
                </div>

                <div style={{ marginTop: '32px' }}>
                  <button onClick={calculateEV}>Calcular EV!</button>
                </div>
              </div>
            </div>

            {result && (
              <>
                <hr />
                <h3>3. ANÁLISE DE VALOR</h3>
                <div className="grid-2 mt-8">
                  <div className="card">
                    <h3 style={{ color: result.over.ev > 0 ? '#ffffff' : 'var(--muted)' }}>OVER {line}</h3>
                    <div className="flex" style={{ justifyContent: 'space-between', borderBottom: '1px solid var(--hairline)', padding: '16px 0' }}>
                      <span className="caption-uppercase">MODEL PROBABILITY</span>
                      <span className="metric-value">{(result.over.model_prob * 100).toFixed(1)}%</span>
                    </div>
                    <div className="flex" style={{ justifyContent: 'space-between', borderBottom: '1px solid var(--hairline)', padding: '16px 0' }}>
                      <span className="caption-uppercase">FAIR ODDS</span>
                      <span className="metric-value">{result.over.fair_odds.toFixed(2)}</span>
                    </div>
                    <div className="flex" style={{ justifyContent: 'space-between', paddingTop: '16px' }}>
                      <span className="caption-uppercase" style={{ color: result.over.ev > 0 ? '#5fa657' : 'inherit' }}>EXPECTED VALUE</span>
                      <span className="metric-value" style={{ color: result.over.ev > 0 ? '#5fa657' : 'inherit' }}>
                        {result.over.ev > 0 ? '+' : ''}{result.over.ev.toFixed(2)}%
                      </span>
                    </div>
                  </div>

                  <div className="card">
                    <h3 style={{ color: result.under.ev > 0 ? '#ffffff' : 'var(--muted)' }}>UNDER {line}</h3>
                    <div className="flex" style={{ justifyContent: 'space-between', borderBottom: '1px solid var(--hairline)', padding: '16px 0' }}>
                      <span className="caption-uppercase">MODEL PROBABILITY</span>
                      <span className="metric-value">{(result.under.model_prob * 100).toFixed(1)}%</span>
                    </div>
                    <div className="flex" style={{ justifyContent: 'space-between', borderBottom: '1px solid var(--hairline)', padding: '16px 0' }}>
                      <span className="caption-uppercase">FAIR ODDS</span>
                      <span className="metric-value">{result.under.fair_odds.toFixed(2)}</span>
                    </div>
                    <div className="flex" style={{ justifyContent: 'space-between', paddingTop: '16px' }}>
                      <span className="caption-uppercase" style={{ color: result.under.ev > 0 ? '#5fa657' : 'inherit' }}>EXPECTED VALUE</span>
                      <span className="metric-value" style={{ color: result.under.ev > 0 ? '#5fa657' : 'inherit' }}>
                        {result.under.ev > 0 ? '+' : ''}{result.under.ev.toFixed(2)}%
                      </span>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {mode === 'top_picks' && (
          <div>
             <div className="flex" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
               <p className="title-md" style={{ margin: 0 }}>
                 Top Picks: Maiores Valores Esperados (EV)
               </p>
               <button 
                 onClick={async () => {
                   try {
                     const res = await fetch('http://localhost:8000/api/top-picks?limit=15');
                     setTopPicks(await res.json());
                     alert("Top picks atualizados!");
                   } catch (e) {
                     alert("Erro ao buscar top picks.");
                   }
                 }}
               >
                 🔄 ATUALIZAR
               </button>
             </div>
             
             <div className="card" style={{ overflowX: 'auto' }}>
               <table>
                 <thead>
                   <tr>
                     <th>Player</th>
                     <th>Team</th>
                     <th>Market</th>
                     <th>Side</th>
                     <th>Line</th>
                     <th>Betclic Odds</th>
                     <th>Model Prob</th>
                     <th>Fair Odds</th>
                     <th>EV %</th>
                   </tr>
                 </thead>
                 <tbody>
                   {!Array.isArray(topPicks) || topPicks.length === 0 ? (
                     <tr>
                       <td colSpan={9} style={{ textAlign: 'center', padding: '32px' }} className="caption-uppercase">
                         {!Array.isArray(topPicks) ? 'Erro ao carregar dados do backend (Verifique se a API reiniciou)' : 'Nenhuma aposta de valor (+EV) encontrada. Rode o scraper.'}
                       </td>
                     </tr>
                   ) : (
                     topPicks.map((bet, i) => (
                       <tr key={i} style={{ color: bet.ev_percent > 0 ? '#5fa657' : 'inherit' }}>
                         <td style={{ fontWeight: 'bold' }}>{bet.player_name}</td>
                         <td>{bet.team}</td>
                         <td>{bet.market}</td>
                         <td style={{textTransform: 'uppercase'}}>{bet.side}</td>
                         <td>{bet.line}</td>
                         <td style={{ fontWeight: 'bold' }}>{bet.odds}</td>
                         <td>{(bet.model_prob * 100).toFixed(1)}%</td>
                         <td>{bet.fair_odds?.toFixed(2)}</td>
                         <td style={{ fontWeight: 'bold' }}>
                           +{bet.ev_percent?.toFixed(2)}%
                         </td>
                       </tr>
                     ))
                   )}
                 </tbody>
               </table>
             </div>
          </div>
        )}

        {mode === 'live_bets' && (
          <div>
             <div className="flex" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
               <p className="title-md" style={{ margin: 0 }}>
                 {selectedGame 
                    ? `Odds para: ${selectedGame.away_team} @ ${selectedGame.home_team}` 
                    : `Abaixo estão as linhas reais extraídas da Betclic comparadas com a projeção do modelo XGBoost em tempo real.`}
               </p>
               <div style={{ display: 'flex', gap: '16px' }}>
                 {selectedGame && (
                   <button 
                     onClick={() => {
                       setSelectedGame(null);
                       setMode('schedule');
                     }}
                     style={{ backgroundColor: 'transparent', border: '1px solid var(--muted)' }}
                   >
                     ← Voltar à Agenda
                   </button>
                 )}
                 <button 
                   onClick={async () => {
                     alert("Iniciando scraper Stealth Playwright... Isso pode demorar uns 20 segundos.");
                     try {
                       await fetch('http://localhost:8000/api/run-pipeline', { method: 'POST' });
                       const res = await fetch('http://localhost:8000/api/live-bets');
                       setLiveBets(await res.json());
                       alert("Sucesso! Odds atualizadas.");
                     } catch (e) {
                       alert("Erro ao rodar scraper.");
                     }
                   }}
                 >
                   🔄 RUN SCRAPER
                 </button>
               </div>
             </div>
             
             <div className="card" style={{ overflowX: 'auto' }}>
               <table>
                 <thead>
                   <tr>
                     <th>Player</th>
                     <th>Team</th>
                     <th>Market</th>
                     <th>Side</th>
                     <th>Line</th>
                     <th>Betclic Odds</th>
                     <th>Model Prob</th>
                     <th>Fair Odds</th>
                     <th>EV %</th>
                   </tr>
                 </thead>
                 <tbody>
                   {liveBets.length === 0 ? (
                     <tr>
                       <td colSpan={9} style={{ textAlign: 'center', padding: '32px' }} className="caption-uppercase">Carregando dados via API... (Execute pipeline.py --live)</td>
                     </tr>
                   ) : (
                     liveBets
                       .filter(bet => !selectedGame || bet.team === selectedGame.away_team || bet.team === selectedGame.home_team)
                       .map((bet, i) => (
                       <tr key={i} style={{ color: bet.ev_percent > 0 ? '#5fa657' : 'inherit' }}>
                         <td>{bet.player_name}</td>
                         <td>{bet.team}</td>
                         <td>{bet.market}</td>
                         <td style={{textTransform: 'uppercase'}}>{bet.side}</td>
                         <td>{bet.line}</td>
                         <td>{bet.odds}</td>
                         <td>{(bet.model_prob * 100).toFixed(1)}%</td>
                         <td>{bet.fair_odds?.toFixed(2)}</td>
                         <td style={{ fontWeight: bet.ev_percent > 0 ? 'bold' : 'normal' }}>
                           {bet.ev_percent > 0 ? '+' : ''}{bet.ev_percent?.toFixed(2)}%
                         </td>
                       </tr>
                     ))
                   )}
                   {liveBets.filter(bet => !selectedGame || bet.team === selectedGame.away_team || bet.team === selectedGame.home_team).length === 0 && liveBets.length > 0 && (
                     <tr>
                       <td colSpan={9} style={{ textAlign: 'center', padding: '32px' }} className="caption-uppercase">
                         Nenhuma odd extraída para as equipas {selectedGame.away_team} ou {selectedGame.home_team}. Rode o scraper.
                       </td>
                     </tr>
                   )}
                 </tbody>
               </table>
             </div>
          </div>
        )}
      </div>

      <footer style={{ backgroundColor: 'var(--canvas)', padding: '64px 40px', marginTop: '120px', textAlign: 'center', borderTop: '1px solid var(--hairline)' }}>
         <div style={{ fontFamily: 'var(--font-display)', fontSize: '14px', letterSpacing: '6px', marginBottom: '16px' }}>BUGATTI</div>
         <div style={{ fontFamily: 'var(--font-body)', fontSize: '14px', color: 'var(--muted)' }}>© 2026 Bugatti Automobiles. NFL Player Prop Analytics.</div>
      </footer>
    </>
  )
}

export default App

