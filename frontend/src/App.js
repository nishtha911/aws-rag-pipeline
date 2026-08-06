import React, { useState } from 'react';
import Upload from './components/Upload';
import DocumentList from './components/DocumentList';
import Search from './components/Search';
import Chat from './components/Chat';
import './App.css';

function App() {
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [activeTab, setActiveTab] = useState('upload');

  const handleUploadSuccess = () => {
    setRefreshTrigger(prev => prev + 1);
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>📄 AWS RAG Document Intelligence</h1>
        <p>Upload, search, and ask questions about your documents</p>
      </header>

      <div className="tabs">
        <button 
          className={activeTab === 'upload' ? 'active' : ''}
          onClick={() => setActiveTab('upload')}
        >
          📤 Upload
        </button>
        <button 
          className={activeTab === 'documents' ? 'active' : ''}
          onClick={() => setActiveTab('documents')}
        >
          📋 Documents
        </button>
        <button 
          className={activeTab === 'search' ? 'active' : ''}
          onClick={() => setActiveTab('search')}
        >
          🔍 Search
        </button>
        <button 
          className={activeTab === 'chat' ? 'active' : ''}
          onClick={() => setActiveTab('chat')}
        >
          💬 Chat
        </button>
      </div>

      <div className="tab-content">
        {activeTab === 'upload' && (
          <Upload onUploadSuccess={handleUploadSuccess} />
        )}
        {activeTab === 'documents' && (
          <DocumentList refreshTrigger={refreshTrigger} />
        )}
        {activeTab === 'search' && <Search />}
        {activeTab === 'chat' && <Chat />}
      </div>

      <footer>
        <p>AWS Free Tier | RAG Pipeline | Powered by Bedrock</p>
      </footer>
    </div>
  );
}

export default App;