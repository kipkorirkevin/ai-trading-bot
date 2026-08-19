// BrokerSelect.js — Broker → Auth flow.
//
// The credential form is built ENTIRELY from what GET /brokers returns
// (each broker's auth_fields array) — nothing about Deriv/MT5/Exness/etc.
// auth requirements is hardcoded here. Add a new broker on the backend
// (brokers/registry.py) and it shows up here automatically, with the
// correct fields, with zero changes to this file. That's the point of
// the whole architecture.

import React, { useState, useEffect } from 'react';
import {
  View, Text, TextInput, Button, StyleSheet, FlatList,
  TouchableOpacity, ActivityIndicator, Alert,
} from 'react-native';
import { getBrokers, connectBroker } from '../services/api';

export default function BrokerSelect({ onConnected }) {
  const [brokers, setBrokers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [fieldValues, setFieldValues] = useState({});
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    getBrokers()
      .then((list) => { setBrokers(list); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const selectBroker = (broker) => {
    setSelected(broker);
    setFieldValues({});
  };

  const setField = (name, value) => {
    setFieldValues((prev) => ({ ...prev, [name]: value }));
  };

  const submit = async () => {
    if (!selected) return;
    const missing = selected.auth_fields.filter(
      (f) => f.required && !fieldValues[f.name]
    );
    if (missing.length > 0) {
      Alert.alert('Missing fields', missing.map((f) => f.label).join(', '));
      return;
    }
    setConnecting(true);
    try {
      const res = await connectBroker(selected.id, fieldValues);
      setConnecting(false);
      if (res.verified === false) {
        Alert.alert(
          'Broker not yet verified',
          `${selected.name} is registered but not yet tested against a real account. ` +
          `Trading is blocked for unverified brokers regardless of AI confidence.`
        );
      }
      onConnected && onConnected(selected.id, res);
    } catch (e) {
      setConnecting(false);
      Alert.alert('Connection failed', String(e));
    }
  };

  if (loading) return <ActivityIndicator size="large" style={styles.container} />;

  if (!selected) {
    return (
      <View style={styles.container}>
        <Text style={styles.title}>Select a broker</Text>
        <FlatList
          data={brokers}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <TouchableOpacity style={styles.brokerRow} onPress={() => selectBroker(item)}>
              <Text style={styles.brokerName}>{item.name}</Text>
              <Text style={item.verified ? styles.verified : styles.unverified}>
                {item.verified ? 'Ready' : 'Not yet verified'}
              </Text>
            </TouchableOpacity>
          )}
        />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{selected.name}</Text>
      {!selected.verified && (
        <Text style={styles.warning}>
          This broker's live trading/market-data API has not been implemented and tested yet.
          You can still enter credentials, but order execution will be blocked.
        </Text>
      )}
      {selected.auth_fields.map((f) => (
        <View key={f.name} style={styles.fieldGroup}>
          <Text style={styles.label}>{f.label}{f.required ? ' *' : ''}</Text>
          {f.help_text ? <Text style={styles.help}>{f.help_text}</Text> : null}
          <TextInput
            style={styles.input}
            secureTextEntry={f.type === 'password'}
            value={fieldValues[f.name] || ''}
            onChangeText={(v) => setField(f.name, v)}
            placeholder={f.options ? f.options.join(' / ') : ''}
          />
        </View>
      ))}
      <Button title={connecting ? 'Connecting...' : 'Connect'} onPress={submit} disabled={connecting} />
      <Button title="Back" onPress={() => setSelected(null)} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 20 },
  title: { fontSize: 22, fontWeight: 'bold', marginBottom: 16 },
  brokerRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#333',
  },
  brokerName: { fontSize: 16 },
  verified: { color: '#4caf50' },
  unverified: { color: '#ff9800' },
  warning: { color: '#ff9800', marginBottom: 16 },
  fieldGroup: { marginBottom: 14 },
  label: { fontWeight: 'bold', marginBottom: 4 },
  help: { fontSize: 12, color: '#888', marginBottom: 4 },
  input: { borderWidth: 1, borderColor: '#ccc', padding: 10, borderRadius: 4 },
});
