import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.zhzhehua.moments",
  appName: "Moments Library",
  webDir: "mobile-app/web",
  server: {
    url: "https://app.zhzhehua.com",
    cleartext: false,
    allowNavigation: ["app.zhzhehua.com", "*.zhzhehua.com"],
  },
};

export default config;
