
import React from 'react';
import AboutUs from './Aboutus';
import {
  useCallback,
  useEffect,
  useRef,
  useState
} from 'react';

import {
  ArrowRight,
  Check,
  CircleHelp,
  Copy,
  Crown,
  Lightbulb,
  LogIn,
  MessageCircle,
  Play,
  Send,
  Shield,
  Sparkles,
  Trophy,
  Users,
  Volume2,
  VolumeX,
  Wifi,
  X
} from 'lucide-react';

const API =
  import.meta.env.VITE_WS_URL ||
  `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.hostname}:8000/ws`;

const savedId = () => {
  let id = sessionStorage.getItem('wc_player_id');

  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem('wc_player_id', id);
  }

  return id;
};

export default function App() {
  const [screen, setScreen] = useState('home');
const [name, setName] = useState(
  () => sessionStorage.getItem('wc_player_name') || ''
);

const [roomCode, setRoomCode] = useState(
  () => sessionStorage.getItem('wc_room_code') || ''
);
  const [state, setState] = useState(null);
  const [playerId] = useState(savedId);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState('');
  const [guess, setGuess] = useState('');
  const [feedback, setFeedback] = useState(null);
  const [chatText, setChatText] = useState('');
  const [muted, setMuted] = useState(false);
  const [seconds, setSeconds] = useState(45);
  const [copied, setCopied] = useState(false);
  const [matchmakingStatus, setMatchmakingStatus] = useState('');
  const matchedRef = useRef(false);

  const ws = useRef(null);
  const chatEnd = useRef(null);
  const audio = useRef(null);
  const stateRef = useRef(null);

  // Browser back navigation
  const screenRef = useRef(screen);
  const lastHistoryScreen = useRef(screen);
  useEffect(() => {
  sessionStorage.setItem('wc_player_name', name);
}, [name]);
  useEffect(() => {
    screenRef.current = screen;
  }, [screen]);

  useEffect(() => {
    const makeEntry = (target) =>
      `${window.location.pathname}${window.location.search}#${target}`;

    if (!window.history.state?.wordClash) {
      window.history.pushState(
        { wordClash: true, screen: 'home' },
        '',
        makeEntry('home')
      );
    }

    const handlePopState = (event) => {
      // Do not allow browser Back to reopen an earlier round/screen
      // while a round is active or its result is being shown.
      const currentGameStatus = stateRef.current?.status;
      if (currentGameStatus === 'round' || currentGameStatus === 'round_result') {
        const currentScreen = screenRef.current;
        window.history.pushState(
          { wordClash: true, screen: currentScreen },
          '',
          makeEntry(currentScreen)
        );
        return;
      }

      if (event.state?.wordClash) {
        const destination = event.state.screen || 'home';
        const previous = screenRef.current;

        if (destination === 'home' && previous !== 'home') {
          ws.current?.close();
          setConnected(false);
          setState(null);
        }

        screenRef.current = destination;
        lastHistoryScreen.current = destination;
        setScreen(destination);
      } else {
        window.history.pushState(
          { wordClash: true, screen: screenRef.current },
          '',
          makeEntry(screenRef.current)
        );
      }
    };

    window.addEventListener('popstate', handlePopState);

    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  useEffect(() => {
    if (lastHistoryScreen.current === screen) return;

    lastHistoryScreen.current = screen;

    window.history.pushState(
      { wordClash: true, screen },
      '',
      `${window.location.pathname}${window.location.search}#${screen}`
    );
  }, [screen]);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  // Sound effects
  const sound = useCallback((type) => {
    if (muted) return;

    try {
      const Ctx =
        window.AudioContext || window.webkitAudioContext;

      if (!audio.current) {
        audio.current = new Ctx();
      }

      const c = audio.current;
      const osc = c.createOscillator();
      const gain = c.createGain();

      osc.connect(gain);
      gain.connect(c.destination);

      const notes =
        type === 'win'
          ? [523, 659, 784]
          : type === 'bad'
          ? [180]
          : type === 'tick'
          ? [440]
          : [660, 880];

      const t = c.currentTime;

      notes.forEach((n, i) => {
        osc.frequency.setValueAtTime(n, t + i * 0.11);
      });

      gain.gain.setValueAtTime(0.08, t);
      gain.gain.exponentialRampToValueAtTime(
        0.001,
        t + notes.length * 0.12
      );

      osc.start(t);
      osc.stop(t + notes.length * 0.12);
    } catch {}
  }, [muted]);

  // WebSocket sender
  const send = useCallback((event, data = {}) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(
        JSON.stringify({ event, data })
      );
    }
  }, []);

  // Connect to multiplayer server
  const connect = useCallback((action, code = '') => {
    matchedRef.current = false;
    setError('');

    const socket = new WebSocket(API);
    ws.current = socket;

    socket.onopen = () => {
      socket.send(
        JSON.stringify({
          event: action,
          data: {
            name: name.trim() || 'Player',
            player_id: playerId,
            room_code: code
          }
        })
      );
    };

    socket.onmessage = (e) => {
      const msg = JSON.parse(e.data);

      if (msg.event === 'welcome') {
  matchedRef.current = true;
  setConnected(true);
  setMatchmakingStatus('');

  const code = msg.data.room_code;

  setRoomCode(code);
  sessionStorage.setItem('wc_room_code', code);
  sessionStorage.setItem('wc_player_name', name.trim() || 'Player');

  setScreen('lobby');
}

      else if (msg.event === 'matchmaking') {
        if (msg.data.status === 'cancelled') {
          matchedRef.current = false;
          setMatchmakingStatus('');
          setScreen('home');
        } else if (!matchedRef.current) {
          setMatchmakingStatus(msg.data.message || 'Looking for another player...');
          setScreen('matchmaking');
        }
      }

      else if (msg.event === 'state') {
        setState(msg.data);

        if (msg.data.status === 'round') {
          setScreen('game');
        }

        if (msg.data.status === 'round_result') {
          setScreen('roundResult');
        }

        if (msg.data.status === 'finished') {
          setScreen('results');
          sound('win');
        }
      }

      else if (msg.event === 'error') {
        setError(msg.data.message);
        setMatchmakingStatus('');
        setScreen('home');
      }

      else if (msg.event === 'guess_result') {
        setFeedback(msg.data);

        if (msg.data.correct) {
          sound('good');
        } else {
          sound('bad');
        }
      }

      else if (msg.event === 'chat_message') {
        setState(prev =>
          prev
            ? {
                ...prev,
                chat: [
                  ...(prev.chat || []),
                  msg.data
                ].slice(-30)
              }
            : prev
        );
      }

      else if (msg.event === 'player_guessed') {
        setFeedback({
          message: `${msg.data.player_name} found the word!`,
          correct: true,
          points: 0
        });
      }
    };

    socket.onclose = () => setConnected(false);

    socket.onerror = () => {
      setError(
        'Could not connect to the game server. Start the backend and try again.'
      );
    };
  }, [name, playerId, sound]);

  // Automatic reconnection after browser refresh
const reconnectAttempted = useRef(false);

useEffect(() => {
  if (reconnectAttempted.current) return;

  const savedRoomCode = sessionStorage.getItem('wc_room_code');

  if (!savedRoomCode) return;

  reconnectAttempted.current = true;

  connect('reconnect', savedRoomCode);
}, [connect]);

  useEffect(() => {
    return () => ws.current?.close();
  }, []);

  // Countdown
  useEffect(() => {
    if (
      !state?.round_ends_at ||
      state.status !== 'round'
    ) {
      return;
    }

    const tick = () => {
      const n = Math.max(
        0,
        Math.ceil(state.round_ends_at - Date.now() / 1000)
      );

      setSeconds(n);

      if (n > 0 && n <= 5) {
        sound('tick');
      }
    };

    tick();

    const id = setInterval(tick, 1000);

    return () => clearInterval(id);
  }, [state?.round_ends_at, state?.status, sound]);

  useEffect(() => {
    chatEnd.current?.scrollIntoView({
      behavior: 'smooth'
    });
  }, [state?.chat?.length]);

  const create = () => {
    if (!name.trim()) {
      setError('Enter your name first.');
      return;
    }

    connect('create_room');
  };

  const join = () => {
    if (!name.trim()) {
      setError('Enter your name first.');
      return;
    }

    if (roomCode.trim().length !== 6) {
      setError('Enter a valid 6-character room code.');
      return;
    }

    connect(
      'join_room',
      roomCode.trim().toUpperCase()
    );
  };

  const quickMatch = () => {
    if (!name.trim()) {
      setError('Enter your name first.');
      return;
    }

    setError('');
    setMatchmakingStatus('Looking for another player...');
    setScreen('matchmaking');
    connect('quick_match');
  };

  const cancelMatchmaking = () => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({
        event: 'cancel_matchmaking',
        data: {}
      }));
    }
    ws.current?.close();
    ws.current = null;
    setConnected(false);
    setMatchmakingStatus('');
    setScreen('home');
  };

  const me = state?.players?.find(
    p => p.id === playerId
  );

  const isHost = state?.host_id === playerId;

  const sorted = state?.players || [];

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(roomCode);
      setCopied(true);

      setTimeout(() => setCopied(false), 1500);
    } catch {
      setError('Clipboard unavailable. Copy the code manually.');
    }
  };

  const submit = () => {
    if (!guess.trim()) return;

    send('submit_guess', { guess });
    setGuess('');
  };

  const sendChat = (e) => {
    e.preventDefault();

    if (chatText.trim()) {
      send('chat', { message: chatText });
      setChatText('');
    }
  };

  const disconnect = () => {
    ws.current?.close();
    setConnected(false);
    setState(null);
    setScreen('home');
  };

  return (
    <div className="app-shell">

      <div className="ambient ambient-a" />
      <div className="ambient ambient-b" />

      {/* HEADER */}

      <header className="topbar">
        

        {/* <button
         className="about-nav-btn"
         onClick={() => setScreen('about')}
         >
         About Us
        </button> */}
        <button
          className="brand"
          onClick={() =>
            screen === 'home' ? null : disconnect()
          }
        >
          <img
           src="/favicon_1.png"
           alt="WordClash logo"
           className="brand-logo"
          />

          <span>
            WORD<span className="brand-accent">CLASH</span>
          </span>
        </button>

        <div className="top-actions">
         <button
          className="about-nav-btn"
          onClick={() => setScreen('about')}
           >
          About Us
          </button>
          <span className={`connection ${connected ? 'online' : ''}`}>
            <i />
            {connected ? 'LIVE' : 'OFFLINE'}
          </span>

          <button
            className="icon-btn"
            title={muted ? 'Unmute' : 'Mute'}
            onClick={() => setMuted(!muted)}
          >
            {muted ? <VolumeX size={18} /> : <Volume2 size={18} />}
          </button>

          <button
            className="icon-btn"
            title="How to play"
            onClick={() => setScreen('rules')}
          >
            <CircleHelp size={18} />
          </button>

        </div>
      </header>

      <main className="main-content">
        
        {screen === 'about' && (
        <AboutUs onBack={() => setScreen('home')} />
         )}
        {/* HOME */}

        {screen === 'home' && (
          <section className="hero">

            <div className="hero-copy">

              <div className="eyebrow">
                <span className="pulse-dot" />
                REAL-TIME WORD BATTLE
              </div>

              <h1>
                Think fast.
                <br />
                <span>Clash harder.</span>
              </h1>

              <p className="hero-sub">
                A little word knowledge. A little speed.
                A lot of friendly competition.
                Invite your people and find out who rules the room.
              </p>

              <div className="name-field">
                <label htmlFor="player-name">
                  YOUR PLAYER NAME
                </label>

                <input
                  id="player-name"
                  value={name}
                  maxLength={18}
                  onChange={e => setName(e.target.value)}
                  placeholder="Enter your name"
                  onKeyDown={e =>
                    e.key === 'Enter' && create()
                  }
                />
              </div>

              <div className="home-actions">

                <button
                  className="primary-btn"
                  onClick={create}
                >
                  <Users size={18} />
                  Create a room
                  <ArrowRight size={17} />
                </button>

                <div className="join-box">

                  <input
                    aria-label="Room code"
                    value={roomCode}
                    maxLength={6}
                    onChange={e =>
                      setRoomCode(e.target.value.toUpperCase())
                    }
                    placeholder="ROOM CODE"
                  />

                  <button
                    className="secondary-btn"
                    onClick={join}
                  >
                    <LogIn size={17} />
                    Join
                  </button>

                </div>
              </div>

              <button
                className="secondary-btn quick-match-btn"
                onClick={quickMatch}
              >
                <Wifi size={18} />
                Quick Match
                <span>Find a random opponent</span>
              </button>

              {error && (
                <div className="error-msg">
                  <X size={15} />
                  {error}
                </div>
              )}

              <div className="hero-meta">
                <span><Users size={15} /> 2 players</span>
                <span><Wifi size={15} /> Live multiplayer</span>
                <span><Trophy size={15} /> 3–15 rounds</span>
              </div>

            </div>

            <div className="hero-art">

              <div className="orbit orbit-one" />
              <div className="orbit orbit-two" />

              <div className="floating-chip chip-top">
                +100 <span>PTS</span>
              </div>

              <div className="word-card">

                <div className="card-top">
                  <span className="live-tag">
                    <i /> LIVE ROUND
                  </span>
                  <span className="card-round">01 / 05</span>
                </div>

                <div className="word-category">
                  NATURE · MYSTERY WORD
                </div>

                <div className="mystery-word">
                  <b>_</b><b>_</b><b>_</b>
                  <b>_</b><b>_</b><b>_</b>
                </div>

                <div className="fake-hint">
                  <Lightbulb size={16} />
                  I can erupt after years of silence.
                </div>

                <div className="fake-input">
                  Type your guess...
                  <span>↵</span>
                </div>

                <div className="card-bottom">
                  <span>
                    <span className="mini-avatar">A</span>
                    <span className="mini-avatar violet">J</span>
                    <span className="mini-avatar pink">M</span>
                    <small>3 players guessing</small>
                  </span>

                  <span className="timer-pill">00:32</span>
                </div>

              </div>

              <div className="floating-chip chip-bottom">
                <Trophy size={15} />
                TOP CLASHER
              </div>

              <div className="sparkle s1">✦</div>
              <div className="sparkle s2">✧</div>
              <div className="sparkle s3">✦</div>

            </div>
          </section>
        )}

        {/* RULES */}

        {screen === 'rules' && (
          <section className="panel rules-panel">

            <button
              className="back-link"
              onClick={() => setScreen('home')}
            >
              ← Back
            </button>

            <div className="eyebrow">THE PLAYBOOK</div>

            <h2>
              How to <span>Clash.</span>
            </h2>

            <div className="rules-grid">

              {[
                ['01', 'Create or join', 'Start a room and share its six-character code.'],
                ['02', 'Read the clues', 'One mystery word. Four clues revealed over time.'],
                ['03', 'Guess before time', 'Type your answer. First correct guess gets the biggest reward.'],
                ['04', 'Win the room', 'Play the host-selected number of rounds. Highest total score takes the crown.']
              ].map(x => (
                <div className="rule-card" key={x[0]}>
                  <b>{x[0]}</b>
                  <h3>{x[1]}</h3>
                  <p>{x[2]}</p>
                </div>
              ))}

            </div>

            <p className="rule-note">
              <Shield size={17} />
              Scoring is validated by the game server.
              No account or download needed.
            </p>

          </section>
        )}

        {/* LOBBY */}

        {screen === 'matchmaking' && (
          <section className="panel lobby-panel matchmaking-panel">
            <div className="eyebrow"><span className="pulse-dot" /> QUICK MATCH</div>
            <h2>Finding your <span>opponent.</span></h2>
            <p>{matchmakingStatus || 'Looking for another player...'}</p>
            <div className="eyebrow">SEARCHING FOR AN AVAILABLE PLAYER...</div>
            <p className="host-note">
              Keep this window open. We will start a match as soon as another player joins.
            </p>
            <button className="secondary-btn" onClick={cancelMatchmaking}>
              <X size={17} />
              Cancel search
            </button>
          </section>
        )}

        {screen === 'lobby' && state && (
          <section className="panel lobby-panel">

            <div className="panel-heading">

              <div>
                <div className="eyebrow">THE HANGOUT</div>
                <h2>Room <span>lobby.</span></h2>
                <p>Waiting for your crew to join the clash.</p>
              </div>

              <div className="room-code-box">
                <small>ROOM CODE</small>
                <strong>{roomCode}</strong>

                <button onClick={copyCode}>
                  <Copy size={14} />
                  {copied ? 'Copied' : 'Copy code'}
                </button>
              </div>

            </div>

            <div className="lobby-content">

              {/* PLAYER LIST */}

              <div className="players-section">

                <div className="section-title">
                  <span>
                    PLAYERS <b>{sorted.length}/2</b>
                  </span>

                  <span className="live-text">
                    <i /> LIVE
                  </span>
                </div>

                <div className="player-list">

                  {sorted.map((p, i) => (
                    <div className="player-row" key={p.id}>

                      <div className={`avatar avatar-${i % 5}`}>
                        {p.name.slice(0, 1).toUpperCase()}
                      </div>

                      <div className="player-info">
                        <strong>
                          {p.name}
                          {p.id === playerId && <em>YOU</em>}
                        </strong>

                        <small>
                          {p.is_host
                            ? 'Room host'
                            : p.connected
                            ? 'Ready to clash'
                            : 'Reconnecting...'}
                        </small>
                      </div>

                      {p.is_host && (
                        <Crown className="crown" size={18} />
                      )}

                      <span
                        className={`status-dot ${p.connected ? '' : 'away'}`}
                      />

                    </div>
                  ))}

                  {Array.from({
                    length: Math.max(0, 2 - sorted.length)
                  }).map((_, i) => (
                    <div className="player-row empty" key={i}>
                      <div className="avatar empty-avatar">+</div>

                      <div className="player-info">
                        <strong>Waiting for player...</strong>
                        <small>Share the room code</small>
                      </div>
                    </div>
                  ))}

                </div>

                <div className="lobby-tip">
                  <Sparkles size={16} />
                  You need at least 2 players to start.
                  Up to 6 can join.
                </div>

              </div>

              {/* HOST GAME SETTINGS */}

              <div className="lobby-side">

                <div className="mode-card">

                  <span className="mode-icon">
                    <Lightbulb size={21} />
                  </span>

                  <h3>Mixed word mode</h3>

                  <p>
                    Expect words from nature, tech, science,
                    food, places and more.
                  </p>

                  <label
                    htmlFor="round-count"
                    style={{
                      display: 'block',
                      marginTop: '18px',
                      marginBottom: '8px',
                      color: '#a99acb',
                      fontSize: '11px',
                      fontWeight: 700,
                      letterSpacing: '1.4px'
                    }}
                  >
                    SELECT NUMBER OF ROUNDS
                  </label>

                  <select
                    id="round-count"
                    value={state.total_rounds ?? 5}
                    disabled={!isHost}
                    onChange={e =>
                      send('set_rounds', {
                        rounds: Number(e.target.value)
                      })
                    }
                    style={{
                      width: '100%',
                      padding: '12px 14px',
                      marginBottom: '16px',
                      border: '1px solid #493b68',
                      borderRadius: '10px',
                      background: '#171426',
                      color: '#ffffff',
                      fontSize: '15px',
                      fontWeight: 600,
                      cursor: isHost ? 'pointer' : 'not-allowed',
                      opacity: isHost ? 1 : 0.7,
                      outline: 'none'
                    }}
                  >
                    <option value={3}>3 Rounds</option>
                    <option value={5}>5 Rounds</option>
                    <option value={10}>10 Rounds</option>
                    <option value={15}>15 Rounds</option>
                  </select>

                  {!isHost && (
                    <p className="host-note">
                      Only the room host can change the number of rounds.
                    </p>
                  )}

                  <div className="mode-stats">

                    <span>
                      {state.total_rounds ?? 5}
                      <small>ROUNDS</small>
                    </span>

                    <span>
                      45s
                      <small>PER ROUND</small>
                    </span>

                    <span>
                      4
                      <small>CLUES</small>
                    </span>

                  </div>

                </div>

                <button
                  className="primary-btn full-btn"
                  disabled={
                    !isHost ||
                    sorted.filter(p => p.connected).length < 2
                  }
                  onClick={() => send('start_game')}
                >
                  <Play size={17} />
                  {isHost ? 'Start the clash' : 'Waiting for host'}
                  <ArrowRight size={17} />
                </button>

                {!isHost && (
                  <p className="host-note">
                    The host will start when everyone is ready.
                  </p>
                )}

              </div>
            </div>
          </section>
        )}

        {/* GAME SCREEN */}

        {screen === 'game' && state && (
          <section className="game-layout">

            <div className="game-main panel">

              <div className="game-heading">

                <div>
                  <div className="eyebrow">
                    WORD CLASH · ROUND {state.round_number} OF {state.total_rounds}
                    {' · '}{state.difficulty || 'Easy'} · {state.question_points ?? 100} MARKS
                  </div>

                  <h2>
                    Crack the <span>word.</span>
                  </h2>
                </div>

                <div className={`countdown ${seconds <= 10 ? 'urgent' : ''}`}>
                  <span>
                    {String(Math.floor(seconds / 60)).padStart(2, '0')}:
                    {String(seconds % 60).padStart(2, '0')}
                  </span>
                  <small>TIME LEFT</small>
                </div>

              </div>

              <div className="progress-track">
                <div
                  style={{
                    width: `${(state.round_number / state.total_rounds) * 100}%`
                  }}
                />
              </div>

              <div className="challenge-card">

                <div className="challenge-top">
                  <span className="category-pill">
                    {state.category || 'MYSTERY'}
                  </span>

                  <span className="hint-count">
                    CLUE {state.revealed_hints} / 4
                    {' · '}{state.extra_hints_used || 0} EXTRA USED
                  </span>
                </div>

                <div className="masked-word">
                  {Array.from((state.masked_word || '').replace(/\s+/g, '')).map((c, i) => (
                    <span key={i}>{c}</span>
                  ))}
                </div>

                <div className="hints-list">
                  {state.hints?.map((hint, i) => (
                    <div className="hint-line" key={i}>
                      <span>{i + 1}</span>
                      <p>{hint}</p>
                    </div>
                  ))}
                </div>

                <div className="challenge-actions">
                  <button
                    className="hint-btn"
                    disabled={state.revealed_hints >= 4}
                    onClick={() => send('reveal_hint')}
                  >
                    <Lightbulb size={17} />
                    Reveal next clue
                  </button>

                  <span>
                    First 2 clues are free for everyone. Extra clues are private and reduce your score.
                  </span>
                </div>

              </div>

              <form
                className="guess-form"
                onSubmit={e => {
                  e.preventDefault();
                  submit();
                }}
              >
                <input
                  type="text"
                  value={guess}
                  onChange={e => {
                    setGuess(e.target.value);
                    setFeedback(null);
                  }}
                  onPaste={e => e.preventDefault()}
                  onDrop={e => e.preventDefault()}
                  onContextMenu={e => e.preventDefault()}
                  onKeyDown={e => {
                    if ((e.ctrlKey || e.metaKey) && ['v', 'x'].includes(e.key.toLowerCase())) {
                      e.preventDefault();
                    }
                  }}
                  placeholder="Type your answer..."
                  maxLength={40}
                  autoComplete="off"
                  autoCorrect="off"
                  spellCheck={false}
                />

                <button className="primary-btn" type="submit">
                  <Send size={17} />
                  Guess
                </button>
              </form>

              {feedback && (
                <div className={`feedback ${feedback.correct ? 'good' : 'bad'}`}>
                  {feedback.correct
                    ? <Check size={16} />
                    : <X size={16} />}
                  {feedback.message}
                </div>
              )}

              <div className="game-footer">
                <span>
                  <Users size={15} />
                  {sorted.length} players in this round
                </span>

                <span>
                  <Shield size={15} />
                  One score per player each round
                </span>
              </div>

            </div>

            <aside className="side-column">

              <div className="panel leaderboard-panel">

                <div className="side-title">
                  <h3>
                    <Trophy size={17} />
                    Leaderboard
                  </h3>
                  <span>LIVE</span>
                </div>

                {sorted.map((p, i) => (
                  <div className="score-row" key={p.id}>
                    <b className={`rank rank-${i + 1}`}>{i + 1}</b>

                    <span className={`tiny-avatar avatar-${i % 5}`}>
                      {p.name[0].toUpperCase()}
                    </span>

                    <span className="score-name">
                      {p.name}
                      {p.id === playerId ? ' (you)' : ''}
                    </span>

                    <strong>{p.score}</strong>
                  </div>
                ))}

              </div>

              <ChatPanel
                chat={state.chat || []}
                chatText={chatText}
                setChatText={setChatText}
                sendChat={sendChat}
                chatEnd={chatEnd}
              />

            </aside>
          </section>
        )}

        {/* ROUND RESULTS */}

        {screen === 'roundResult' && state && (
          <section className="panel result-panel">

            <div className="result-icon">
              <Check size={30} />
            </div>

            <div className="eyebrow">
              ROUND {state.round_number} COMPLETE
            </div>

            <h2>
              The word was <span>{state.round_results?.word}</span>
            </h2>

            <p className="result-category">
              {state.round_results?.category}
            </p>

            <p className="result-category">
              Difficulty: {state.round_results?.difficulty || state.difficulty || 'Easy'}
              {' · '}Question value: {state.round_results?.question_points ?? state.question_points ?? 100} marks
            </p>

            <div className="result-scores">
              {(state.round_results?.scores || sorted).map((p, i) => (
                <div className="result-score-row" key={p.id}>
                  <b>{i + 1}</b>
                  <span>{p.name}</span>
                  <strong>{p.score} pts</strong>
                </div>
              ))}
            </div>

            <p className="host-note">
              {state.round_number >= state.total_rounds
                ? 'Final results will appear automatically in 2 seconds...'
                : 'Next question starts automatically in 2 seconds...'}
            </p>

          </section>
        )}

        {/* FINAL RESULTS */}

        {screen === 'results' && state && (
          <section className="panel result-panel final-panel">

            <div className="winner-crown">
              <Trophy size={34} />
            </div>

            <div className="eyebrow">
              THE CLASH IS OVER
            </div>

            <h2>
              {state.winner
                ? <>We have a <span>winner.</span></>
                : <><span>It's a draw!</span></>}
            </h2>

            {state.winner ? (
            <div className="winner-card">
              <div className="winner-avatar">
                <Crown size={25} />
              </div>

              <small>WORD CLASH CHAMPION</small>

              <h3>{state.winner?.name || 'Champion'}</h3>

              <strong>
                {state.winner?.score || 0}
                <small> POINTS</small>
              </strong>
            </div>
            ) : (
              <p className="result-category">
                No winner this time. The match ended in a tie.
              </p>
            )}

            <div className="result-scores">
              {sorted.map((p, i) => (
                <div className="result-score-row" key={p.id}>
                  <b>{i + 1}</b>
                  <span>{p.name}</span>
                  <strong>{p.score} pts</strong>
                </div>
              ))}
            </div>

            <button
              className="text-btn"
              onClick={disconnect}
            >
              Leave room
            </button>

          </section>
        )}

      </main>

      <footer className="footer">
        <span>© 2026 WORD CLASH</span>
        <span>
          BUILT FOR FRIENDLY RIVALRIES
          <span className="footer-star"> ✦</span>
        </span>
      </footer>

    </div>
  );
}

// CHAT COMPONENT

function ChatPanel({
  chat,
  chatText,
  setChatText,
  sendChat,
  chatEnd
}) {
  return (
    <div className="panel chat-panel">

      <div className="side-title">
        <h3>
          <MessageCircle size={17} />
          Room chat
        </h3>

        <span>{chat.length} MSG</span>
      </div>

      <div className="chat-messages">

        {chat.length === 0 ? (
          <div className="chat-empty">
            <MessageCircle size={22} />
            <span>Break the ice. Say hello!</span>
          </div>
        ) : (
          chat.map(m => (
            <div className="chat-message" key={m.id}>
              <b>{m.name}</b>
              <p>{m.message}</p>
            </div>
          ))
        )}

        <div ref={chatEnd} />

      </div>

      <form className="chat-form" onSubmit={sendChat}>
        <input
          value={chatText}
          onChange={e => setChatText(e.target.value)}
          placeholder="Message the room..."
          maxLength={180}
        />

        <button aria-label="Send message">
          <Send size={16} />
        </button>
      </form>

    </div>
  );
}
