import React, { useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import BrokerSelect from './screens/BrokerSelect';
import Dashboard from './screens/Dashboard';
import Settings from './screens/Settings';
import AuditLog from './screens/AuditLog';
import Trading from './screens/Trading';

const Tab = createBottomTabNavigator();

export default function App() {
  const [connectedBroker, setConnectedBroker] = useState(null);

  // Broker → Auth happens once, before the rest of the app is usable —
  // matches the required flow: Broker Selection -> Account Authentication
  // -> Backend -> everything else.
  if (!connectedBroker) {
    return <BrokerSelect onConnected={(brokerId) => setConnectedBroker(brokerId)} />;
  }

  return (
    <NavigationContainer>
      <Tab.Navigator>
        <Tab.Screen name="Dashboard" component={Dashboard} />
        <Tab.Screen name="Trading" component={Trading} />
        <Tab.Screen name="Audit" component={AuditLog} />
        <Tab.Screen name="Settings" component={Settings} />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
