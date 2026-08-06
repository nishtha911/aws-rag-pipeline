import React, { useState } from 'react';
import { askQuestion } from '../services/api';
import './Chat.css';

function Chat() {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleAsk = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const data = await askQuestion(question);
      setAnswer(data);
    } catch (err) {
      setError('Question failed: ' + err.message);
      setAnswer(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-container">
      <form onSubmit={handleAsk}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="💬 Ask a question about your documents..."
          disabled={loading}
        />
        <button type="submit" disabled={loading || !question.trim()}>
          {loading ? 'Thinking...' : 'Ask'}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      {answer && (
        <div className="answer-container">
          <div className="answer">
            <h4>🧠 Answer:</h4>
            <p>{answer.answer}</p>
          </div>

          {answer.sources && answer.sources.length > 0 && (
            <div className="sources">
              <h4>📚 Sources ({answer.sources.length}):</h4>
              {answer.sources.map((source, index) => (
                <div key={index} className="source-item">
                  <span className="filename">📄 {source.filename}</span>
                  <span className="chunk">Chunk {source.chunk + 1}</span>
                  <div className="preview">{source.text_preview}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default Chat;