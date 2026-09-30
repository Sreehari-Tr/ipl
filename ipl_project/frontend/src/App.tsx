import { useState, useEffect } from 'react';
import './index.css';

const API_URL = 'http://localhost:8000/api';

function App() {
  const [metadata, setMetadata] = useState<{teams: string[], venues: string[]}>({ teams: [], venues: [] });
  const [team1, setTeam1] = useState('');
  const [team2, setTeam2] = useState('');
  const [venue, setVenue] = useState('');
  
  const [team1Players, setTeam1Players] = useState<{batters: any[], bowlers: any[]}>({ batters: [], bowlers: [] });
  const [team2Players, setTeam2Players] = useState<{batters: any[], bowlers: any[]}>({ batters: [], bowlers: [] });

  const [t1Batters, setT1Batters] = useState<string[]>([]);
  const [t1Bowlers, setT1Bowlers] = useState<string[]>([]);
  const [t2Batters, setT2Batters] = useState<string[]>([]);
  const [t2Bowlers, setT2Bowlers] = useState<string[]>([]);

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    fetch(`${API_URL}/metadata`)
      .then(res => res.json())
      .then(data => {
        setMetadata(data);
        if (data.teams.length > 1) {
          setTeam1(data.teams[0]);
          setTeam2(data.teams[1]);
        }
        if (data.venues.length > 0) setVenue(data.venues[0]);
      });
  }, []);

  useEffect(() => {
    if (team1) {
      fetch(`${API_URL}/players/${team1}`)
        .then(res => res.json())
        .then(data => {
          setTeam1Players(data);
          setT1Batters(data.batters.slice(0, 11).map((p: any) => p.id));
          setT1Bowlers(data.bowlers.slice(0, 6).map((p: any) => p.id));
        });
    }
  }, [team1]);

  useEffect(() => {
    if (team2) {
      fetch(`${API_URL}/players/${team2}`)
        .then(res => res.json())
        .then(data => {
          setTeam2Players(data);
          setT2Batters(data.batters.slice(0, 11).map((p: any) => p.id));
          setT2Bowlers(data.bowlers.slice(0, 6).map((p: any) => p.id));
        });
    }
  }, [team2]);

  const togglePlayer = (id: string, list: string[], setList: (l: string[]) => void, max: number) => {
    if (list.includes(id)) {
      setList(list.filter(x => x !== id));
    } else if (list.length < max) {
      setList([...list, id]);
    }
  };

  const handleSimulate = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          team1, team2, venue,
          team1_batters: t1Batters,
          team1_bowlers: t1Bowlers,
          team2_batters: t2Batters,
          team2_bowlers: t2Bowlers,
          n_sims: 500
        })
      });
      const data = await res.json();
      setResult(data);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  const isReady = t1Batters.length === 11 && t1Bowlers.length >= 5 && t2Batters.length === 11 && t2Bowlers.length >= 5;

  return (
    <div className="glass-panel">
      <h1>IPL Match Simulator</h1>
      
      <div className="grid-2">
        <div>
          <label>Match Venue</label>
          <select value={venue} onChange={e => setVenue(e.target.value)}>
            {metadata.venues.map(v => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>
      </div>

      <div className="grid-2">
        {/* TEAM 1 */}
        <div className="glass-panel">
          <label>Team 1 (Batting First)</label>
          <select value={team1} onChange={e => setTeam1(e.target.value)}>
            {metadata.teams.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          
          <div className="grid-2" style={{ marginTop: '1rem' }}>
            <div>
              <label>Batters ({t1Batters.length}/11)</label>
              <div className="player-list">
                {team1Players.batters.map(p => (
                  <div key={p.id} 
                       className={`player-item ${t1Batters.includes(p.id) ? 'selected' : ''}`}
                       onClick={() => togglePlayer(p.id, t1Batters, setT1Batters, 11)}>
                    <span className="player-name">{p.name}</span>
                    <span className="player-role">BAT</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <label>Bowlers ({t1Bowlers.length}/6)</label>
              <div className="player-list">
                {team1Players.bowlers.map(p => (
                  <div key={p.id} 
                       className={`player-item ${t1Bowlers.includes(p.id) ? 'selected' : ''}`}
                       onClick={() => togglePlayer(p.id, t1Bowlers, setT1Bowlers, 6)}>
                    <span className="player-name">{p.name}</span>
                    <span className="player-role">BOWL</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* TEAM 2 */}
        <div className="glass-panel">
          <label>Team 2 (Chasing)</label>
          <select value={team2} onChange={e => setTeam2(e.target.value)}>
            {metadata.teams.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          
          <div className="grid-2" style={{ marginTop: '1rem' }}>
            <div>
              <label>Batters ({t2Batters.length}/11)</label>
              <div className="player-list">
                {team2Players.batters.map(p => (
                  <div key={p.id} 
                       className={`player-item ${t2Batters.includes(p.id) ? 'selected' : ''}`}
                       onClick={() => togglePlayer(p.id, t2Batters, setT2Batters, 11)}>
                    <span className="player-name">{p.name}</span>
                    <span className="player-role">BAT</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <label>Bowlers ({t2Bowlers.length}/6)</label>
              <div className="player-list">
                {team2Players.bowlers.map(p => (
                  <div key={p.id} 
                       className={`player-item ${t2Bowlers.includes(p.id) ? 'selected' : ''}`}
                       onClick={() => togglePlayer(p.id, t2Bowlers, setT2Bowlers, 6)}>
                    <span className="player-name">{p.name}</span>
                    <span className="player-role">BOWL</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      <button onClick={handleSimulate} disabled={!isReady || loading}>
        {loading ? 'Simulating 500 Matches...' : 'Run Simulation'}
      </button>

      {loading && <div style={{ textAlign: 'center' }}><div className="loading-spinner"></div></div>}

      {result && (
        <div className="results-panel glass-panel">
          <h2 className="section-title">Simulation Results</h2>
          <p style={{ color: '#94a3b8' }}>Average {team1} 1st Innings Score: <strong>{result.avg_t1_score}</strong></p>
          
          <div className="prob-grid">
            <div className={`prob-card ${result.team1_win_prob > result.team2_win_prob ? 'winner' : ''}`}>
              <div className="prob-label">{team1} Win</div>
              <div className="prob-value">{result.team1_win_prob}%</div>
            </div>
            <div className={`prob-card ${result.team2_win_prob > result.team1_win_prob ? 'winner' : ''}`}>
              <div className="prob-label">{team2} Win</div>
              <div className="prob-value">{result.team2_win_prob}%</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
