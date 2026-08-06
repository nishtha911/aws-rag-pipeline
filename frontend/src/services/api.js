import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL;
const API_KEY = process.env.REACT_APP_API_KEY;

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'x-api-key': API_KEY,
    'Content-Type': 'application/json',
  },
});

export const uploadDocument = async (file, filename) => {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await api.post(
    `/upload?filename=${filename}`,
    file,
    {
      headers: {
        'Content-Type': 'application/pdf',
      },
    }
  );
  return response.data;
};

export const listDocuments = async (limit = 50, offset = 0) => {
  const response = await api.get(`/documents?limit=${limit}&offset=${offset}`);
  return response.data;
};

export const getDocument = async (documentId) => {
  const response = await api.get(`/document/${documentId}`);
  return response.data;
};

export const deleteDocument = async (documentId) => {
  const response = await api.delete(`/document/${documentId}`);
  return response.data;
};

export const generateEmbeddings = async (documentId) => {
  const response = await api.post(`/document/${documentId}/embed`);
  return response.data;
};

export const semanticSearch = async (query, limit = 5) => {
  const response = await api.get(`/search?q=${encodeURIComponent(query)}&limit=${limit}`);
  return response.data;
};

export const askQuestion = async (question, limit = 3) => {
  const response = await api.get(`/chat?q=${encodeURIComponent(question)}&limit=${limit}`);
  return response.data;
};

export default api;