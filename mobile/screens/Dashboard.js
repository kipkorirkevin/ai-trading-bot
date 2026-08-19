import React, { useState, useEffect } from 'react';
import { View, Text, Button, StyleSheet, ActivityIndicator } from 'react-native';
import { getStatus } from '../services/api';

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = () => {
    getStatus()
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, []);

  if (loading || !data) return <ActivityIndicator size="large" style={styles.container} />;

  return (
    <View style={styles.container}>
      <Text style={styles.title}>🤖 AI Hybrid Bot</Text>
      <Text style={styles.status}>Status: {data.bot_status}</Text>
      <Text>Balance: ${data.account?.balance?.toFixed(2)}</Text>
      <Text>Open positions: {data.account?.open_positions}</Text>
      <Text>Pending orders: {data.account?.pending_orders}</Text>
      <Text style={styles.section}>AI</Text>
      <Text>Last cycle: {data.ai?.decision}</Text>
      <Button title="Refresh" onPress={refresh} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 20, justifyContent: 'center' },
  title: { fontSize: 24, fontWeight: 'bold', marginBottom: 20 },
  status: { fontSize: 16, marginBottom: 10 },
  section: { marginTop: 20, fontWeight: 'bold' },
});
