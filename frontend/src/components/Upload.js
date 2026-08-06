import React, { useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { uploadDocument } from '../services/api';
import './Upload.css';

function Upload({ onUploadSuccess }) {
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState(null);

  const onDrop = async (acceptedFiles) => {
    const file = acceptedFiles[0];
    if (!file) return;

    if (!file.name.endsWith('.pdf')) {
      setMessage({ type: 'error', text: 'Please upload a PDF file' });
      return;
    }

    setUploading(true);
    setMessage(null);

    try {
      const result = await uploadDocument(file, file.name);
      setMessage({ 
        type: 'success', 
        text: `✅ ${result.file} uploaded successfully! Document ID: ${result.document_id}`
      });
      if (onUploadSuccess) onUploadSuccess();
    } catch (error) {
      setMessage({ 
        type: 'error', 
        text: `❌ Upload failed: ${error.response?.data?.error || error.message}`
      });
    } finally {
      setUploading(false);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1,
  });

  return (
    <div className="upload-container">
      <div 
        {...getRootProps()} 
        className={`dropzone ${isDragActive ? 'active' : ''} ${uploading ? 'uploading' : ''}`}
      >
        <input {...getInputProps()} />
        {uploading ? (
          <div className="uploading-status">
            <div className="spinner"></div>
            <p>Uploading...</p>
          </div>
        ) : isDragActive ? (
          <p>📄 Drop your PDF here...</p>
        ) : (
          <div>
            <p>📤 Drag & drop a PDF here, or click to select</p>
            <small>Only PDF files are supported</small>
          </div>
        )}
      </div>

      {message && (
        <div className={`message ${message.type}`}>
          {message.text}
        </div>
      )}
    </div>
  );
}

export default Upload;