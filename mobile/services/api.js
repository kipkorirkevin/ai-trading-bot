// api.js — client for backend/src/api/server.py
// Endpoint names match server.py exactly: /status, /start, /pause,
// /stop_new_trades, /cancel_pending, /close_all, /emergency_stop, /audit

let API_URL = 'https://your-bot-url.example.com';

export const setConfig = (cfg) => {
  if (cfg.apiUrl) API_URL = cfg.apiUrl;
};

async function getJSON(path) {
  const res = await fetch(`${API_URL}${path}`);
  return res.json();
}

async function postJSON(path, body) {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

export const getStatus = () => getJSON('/status');
export const getBrokers = () => getJSON('/brokers');
export const connectBroker = (brokerId, credentials) =>
  postJSON(`/brokers/${brokerId}/connect`, { credentials });
export const startBot = (symbols, confidence) => postJSON('/start', { symbols, confidence });
export const pauseBot = () => postJSON('/pause');
export const stopNewTrades = () => postJSON('/stop_new_trades');
export const cancelPending = () => postJSON('/cancel_pending');
export const closeAll = () => postJSON('/close_all');
export const emergencyStop = () => postJSON('/emergency_stop');
export const getAudit = () => getJSON('/audit');
