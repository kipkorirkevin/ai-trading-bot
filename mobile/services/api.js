// api.js — client for backend/src/api/server.py
// Endpoint names match server.py exactly: /status, /start, /pause,
// /stop_new_trades, /cancel_pending, /close_all, /emergency_stop, /audit

// Default assumes the backend (uvicorn) is running on the SAME Android
// device via Termux, with Expo Go also on that device — Android shares
// one network stack across apps, so 127.0.0.1 reaches Termux's server
// directly. If you run the backend on a different machine, change this
// (or use Settings screen's URL field once connected) to that machine's
// LAN IP, e.g. 'http://192.168.1.23:8000'.
let API_URL = 'http://127.0.0.1:8000';

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
