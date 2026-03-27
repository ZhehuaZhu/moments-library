# App Shell

This branch contains a first-pass Capacitor iOS shell for Moments Library.

Current approach:

- Keep the Flask site and server deployment as the source of truth.
- Wrap the live site `https://app.zhzhehua.com` in a Capacitor iPhone app shell.
- Use this shell as the base for later native enhancements like camera, geolocation, and share.

Useful commands on a Mac:

```bash
npm install
npm run cap:sync:ios
npm run cap:open:ios
```

Notes:

- This branch is now prepared for an iOS-first shell.
- The `ios/` project has already been generated in this branch.
- Actual iPhone building and installation should be done on macOS with Xcode.
