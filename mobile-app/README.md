# App Shell

This branch contains a first-pass Capacitor Android shell for Moments Library.

Current approach:

- Keep the Flask site and server deployment as the source of truth.
- Wrap the live site `https://app.zhzhehua.com` in a Capacitor Android app.
- Use this shell as the base for later native enhancements like camera, geolocation, and share.

Useful commands:

```bash
npm install
npm run cap:add:android
npm run cap:sync
npm run cap:open:android
```

Notes:

- This first version is optimized for personal install on Android from Windows.
- iOS packaging should be added later from a Mac.
