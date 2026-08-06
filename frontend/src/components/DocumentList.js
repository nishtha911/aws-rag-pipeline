import React, { useState, useEffect } from 'react';
import { listDocuments, deleteDocument, generateEmbeddings } from '../services/api';
import './DocumentList.css';

function DocumentList({ refreshTrigger }) {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchDocuments();
  }, [refreshTrigger]);

  const fetchDocuments = async () => {
    setLoading(true);
    try {
      const result = await listDocuments();
      setDocuments(result.documents || []);
      setError(null);
    } catch (err) {
      setError('Failed to load documents');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this document?')) return;
    try {
      await deleteDocument(id);
      await fetchDocuments();
    } catch (err) {
      alert('Delete failed: ' + err.message);
    }
  };

  const handleEmbed = async (id) => {
    try {
      await generateEmbeddings(id);
      await fetchDocuments();
    } catch (err) {
      alert('Embedding generation failed: ' + err.message);
    }
  };

  const getStatusBadge = (status) => {
    const colors = {
      'uploaded': 'gray',
      'processed': 'blue',
      'embedded': 'green',
      'pending': 'orange'
    };
    return <span className={`badge ${colors[status] || 'gray'}`}>{status}</span>;
  };

  if (loading) return <div className="loading">Loading documents...</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div className="document-list">
      <h3>📄 Documents ({documents.length})</h3>
      {documents.length === 0 ? (
        <p className="empty-state">No documents uploaded yet</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Filename</th>
              <th>Date</th>
              <th>Chunks</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <tr key={doc.id}>
                <td className="filename">{doc.filename}</td>
                <td>{new Date(doc.upload_date).toLocaleDateString()}</td>
                <td>{doc.total_chunks || 0}</td>
                <td>{getStatusBadge(doc.status)}</td>
                <td className="actions">
                  <button 
                    className="btn-embed" 
                    onClick={() => handleEmbed(doc.id)}
                    disabled={doc.status === 'embedded'}
                  >
                    🔮 Embed
                  </button>
                  <button 
                    className="btn-delete" 
                    onClick={() => handleDelete(doc.id)}
                  >
                    🗑️
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default DocumentList;