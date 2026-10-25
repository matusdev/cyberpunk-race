import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.nightcityrush.game',
  appName: 'Night City Rush',
  webDir: 'dist',
  backgroundColor: '#05030a',
  android: {
    backgroundColor: '#05030a',
    allowMixedContent: false,
    webContentsDebuggingEnabled: true
  },
  server: { androidScheme: 'https' }
};

export default config;
