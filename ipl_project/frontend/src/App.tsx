import { useState, useEffect } from 'react';
import './index.css';

const API_URL = 'http://localhost:8000/api';

function App() {
  const [metadata, setMetadata] = useState<{teams: string[], venues: string[]}>({ teams: [], venues: [] });
  const [team1, setTeam1] = useState('');
  const [team2, setTeam2] = useState('');
  const [venue, setVenue] = useState('');
  
  // Store all players globally
  const [allPlayers, setAllPlayers] = useState<{batters: any[], bowlers: any[]}>({ batters: [], bowlers: [] });

  const [t1Batters, setT1Batters] = useState<string[]>([]);
  const [t1Bowlers, setT1Bowlers] = useState<string[]>([]);
  const [t2Batters, setT2Batters] = useState<string[]>([]);
  const [t2Bowlers, setT2Bowlers] = useState<string[]>([]);
  
  // Search state for each list
  const [searchT1Bat, setSearchT1Bat] = useState('');
  const [searchT1Bowl, setSearchT1Bowl] = useState('');
  const [searchT2Bat, setSearchT2Bat] = useState('');
  const [searchT2Bowl, setSearchT2Bowl] = useState('');

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
      
    // Fetch all global players
    fetch(`${API_URL}/players`)
      .then(res => res.json())
      .then(data => {
        setAllPlayers(data);
        // Pre-select some dummy top players just so the user isn't forced to click 34 times immediately
        setT1Batters(data.batters.slice(0, 11).map((p: any) => p.id));
        setT1Bowlers(data.bowlers.slice(0, 6).map((p: any) => p.id));
        setT2Batters(data.batters.slice(11, 22).map((p: any) => p.id));
        setT2Bowlers(data.bowlers.slice(6, 12).map((p: any) => p.id));
      });
  }, []);

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

  // Helpers to filter players based on search and always show selected players at top
  const filterPlayers = (players: any[], search: string, selectedIds: string[]) => {
    let filtered = players.filter(p => p.name.toLowerCase().includes(search.toLowerCase()));
    // Sort so selected players appear at the top
    return filtered.sort((a, b) => {
      const aSel = selectedIds.includes(a.id);
      const bSel = selectedIds.includes(b.id);
      if (aSel && !bSel) return -1;
      if (!aSel && bSel) return 1;
      return 0;
    });
  };

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
              <input 
                type="text" 
                placeholder="Search batters..." 
                className="search-input"
                value={searchT1Bat}
                onChange={e => setSearchT1Bat(e.target.value)}
              />
              <div className="player-list">
                {filterPlayers(allPlayers.batters, searchT1Bat, t1Batters).map(p => (
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
              <input 
                type="text" 
                placeholder="Search bowlers..." 
                className="search-input"
                value={searchT1Bowl}
                onChange={e => setSearchT1Bowl(e.target.value)}
              />
              <div className="player-list">
                {filterPlayers(allPlayers.bowlers, searchT1Bowl, t1Bowlers).map(p => (
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
              <input 
                type="text" 
                placeholder="Search batters..." 
                className="search-input"
                value={searchT2Bat}
                onChange={e => setSearchT2Bat(e.target.value)}
              />
              <div className="player-list">
                {filterPlayers(allPlayers.batters, searchT2Bat, t2Batters).map(p => (
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
              <input 
                type="text" 
                placeholder="Search bowlers..." 
                className="search-input"
                value={searchT2Bowl}
                onChange={e => setSearchT2Bowl(e.target.value)}
              />
              <div className="player-list">
                {filterPlayers(allPlayers.bowlers, searchT2Bowl, t2Bowlers).map(p => (
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
          
          {result.sample_match && (
            <div className="scorecard-container">
              <h3 className="section-title" style={{marginTop: '3rem'}}>Sample Match Scorecard</h3>
              <p style={{color: '#94a3b8', marginBottom: '2rem'}}>
                Here is exactly how one of the simulations played out: <br/>
                <strong>{team1}:</strong> {result.sample_match.inn1_runs}/{result.sample_match.inn1_wickets} (20.0 overs) <br/>
                <strong>{team2}:</strong> {result.sample_match.inn2_runs}/{result.sample_match.inn2_wickets} ({result.sample_match.inn2_overs}.{result.sample_match.inn2_balls} overs)
              </p>
              
              <div className="grid-2">
                {/* INNINGS 1 */}
                <div className="innings-card glass-panel">
                  <h4>{team1} Innings</h4>
                  <table className="scorecard-table">
                    <thead>
                      <tr>
                        <th style={{textAlign: 'left'}}>Batter</th>
                        <th>R</th>
                        <th>B</th>
                        <th>4s</th>
                        <th>6s</th>
                        <th>SR</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.sample_match.inn1_scorecard.batting.map((b: any, i: number) => (
                        <tr key={i} className={b.out ? 'out' : 'not-out'}>
                          <td style={{textAlign: 'left'}}>{b.name} {b.out ? '' : '*'}</td>
                          <td><strong>{b.runs}</strong></td>
                          <td>{b.balls}</td>
                          <td>{b.fours}</td>
                          <td>{b.sixes}</td>
                          <td>{b.balls > 0 ? ((b.runs / b.balls) * 100).toFixed(1) : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  
                  <h5 style={{textAlign: 'left', marginTop: '1rem', color: '#a5b4fc'}}>Bowling</h5>
                  <table className="scorecard-table">
                    <thead>
                      <tr>
                        <th style={{textAlign: 'left'}}>Bowler</th>
                        <th>O</th>
                        <th>R</th>
                        <th>W</th>
                        <th>Econ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.sample_match.inn1_scorecard.bowling.map((b: any, i: number) => (
                        <tr key={i}>
                          <td style={{textAlign: 'left'}}>{b.name}</td>
                          <td>{b.overs}</td>
                          <td>{b.runs}</td>
                          <td><strong>{b.wickets}</strong></td>
                          <td>{b.balls > 0 ? ((b.runs / b.balls) * 6).toFixed(1) : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* INNINGS 2 */}
                <div className="innings-card glass-panel">
                  <h4>{team2} Innings</h4>
                  <table className="scorecard-table">
                    <thead>
                      <tr>
                        <th style={{textAlign: 'left'}}>Batter</th>
                        <th>R</th>
                        <th>B</th>
                        <th>4s</th>
                        <th>6s</th>
                        <th>SR</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.sample_match.inn2_scorecard.batting.map((b: any, i: number) => (
                        <tr key={i} className={b.out ? 'out' : 'not-out'}>
                          <td style={{textAlign: 'left'}}>{b.name} {b.out ? '' : '*'}</td>
                          <td><strong>{b.runs}</strong></td>
                          <td>{b.balls}</td>
                          <td>{b.fours}</td>
                          <td>{b.sixes}</td>
                          <td>{b.balls > 0 ? ((b.runs / b.balls) * 100).toFixed(1) : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  
                  <h5 style={{textAlign: 'left', marginTop: '1rem', color: '#a5b4fc'}}>Bowling</h5>
                  <table className="scorecard-table">
                    <thead>
                      <tr>
                        <th style={{textAlign: 'left'}}>Bowler</th>
                        <th>O</th>
                        <th>R</th>
                        <th>W</th>
                        <th>Econ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.sample_match.inn2_scorecard.bowling.map((b: any, i: number) => (
                        <tr key={i}>
                          <td style={{textAlign: 'left'}}>{b.name}</td>
                          <td>{b.overs}</td>
                          <td>{b.runs}</td>
                          <td><strong>{b.wickets}</strong></td>
                          <td>{b.balls > 0 ? ((b.runs / b.balls) * 6).toFixed(1) : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default App;
