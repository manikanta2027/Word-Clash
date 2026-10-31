import React from 'react';

import { ArrowRight, Lightbulb, Trophy, Users, Wifi } from 'lucide-react';
import './aboutus.css';

export default function AboutUs({ onBack }) {
  return (
    <section className="about-page">
      <div className="about-hero panel">
        <button className="back-link" onClick={onBack}>← Back to home</button>
        <div className="eyebrow"><span className="pulse-dot" /> THE STORY BEHIND THE GAME</div>
        <h1>More than words.<br /><span>It's a friendly clash.</span></h1>
        <p className="about-intro">
          WordClash is a real-time multiplayer word-guessing game where quick thinking,
          clever clues and friendly competition bring players together. Create a room
          with a friend or find an opponent through Quick Match.
        </p>
        <div className="about-stats">
          <div><strong>2</strong><span>PLAYERS PER MATCH</span></div>
          <div><strong>3–15</strong><span>ROUNDS TO PLAY</span></div>
          <div><strong>45s</strong><span>PER ROUND</span></div>
        </div>
      </div>

      <div className="about-section-heading">
        <div className="eyebrow">WHAT MAKES IT FUN</div>
        <h2>Built for the <span>clash.</span></h2>
      </div>

      <div className="about-feature-grid">
        <article className="about-feature panel">
          <span className="about-feature-icon"><Users size={21} /></span>
          <h3>Play together</h3>
          <p>Create a private room and invite a friend, or use Quick Match to find another player.</p>
        </article>
        <article className="about-feature panel">
          <span className="about-feature-icon"><Lightbulb size={21} /></span>
          <h3>Think through clues</h3>
          <p>Use the hints to uncover the mystery word. Every clue brings you closer to the answer.</p>
        </article>
        <article className="about-feature panel">
          <span className="about-feature-icon"><Trophy size={21} /></span>
          <h3>Race for points</h3>
          <p>Guess quickly, use hints wisely and compete for the highest score on the leaderboard.</p>
        </article>
        <article className="about-feature panel">
          <span className="about-feature-icon"><Wifi size={21} /></span>
          <h3>Real-time matches</h3>
          <p>Room updates, guesses and chat keep both players connected during the game.</p>
        </article>
      </div>

      <div className="about-bottom panel">
        <div>
          <div className="eyebrow">READY TO PLAY?</div>
          <h2>Your next word battle <span>starts here.</span></h2>
          <p>Head back to the home screen, create a room or jump into Quick Match.</p>
        </div>
        <button className="primary-btn" onClick={onBack}>Play WordClash <ArrowRight size={17} /></button>
      </div>
    </section>
  );
}
