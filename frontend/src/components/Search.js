import React, { useState } from 'react';
import { semanticSearch } from '../services/api';
import './Search.css';

function Search() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const data = await semanticSearch(query);
      setResults(data.results || []);
    } catch (err) {
      setError('Search failed: ' + err.message);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="search-container">
      <form onSubmit={handleSearch}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="🔍 Search your documents..."
          disabled={loading}
        />
        <button type="submit" disabled={loading || !query.trim()}>
          {loading ? 'Searching...' : 'Search'}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      {results.length > 0 && (
        <div className="results">
          <h4>Found {results.length} results:</h4>
          {results.map((result, index) => (
            <div key={index} className="result-item">
              <div className="result-header">
                <span className="filename">📄 {result.filename}</span>
                <span className="score">Score: {result.similarity_score?.toFixed(4)}</span>
              </div>
              <div className="result-text">{result.text}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Search;