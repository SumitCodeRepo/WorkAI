# 04 — Publishing the App to App Store + Google Play

This guide uses **Expo Application Services (EAS Build)** — the official Expo
cloud build service. It compiles native iOS (.ipa) and Android (.aab) binaries
in the cloud without needing a Mac for iOS builds.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Expo account | Free — create at https://expo.dev |
| Apple Developer account | $99/year — required for iOS distribution |
| Google Play Developer account | $25 one-time — required for Android |
| EAS CLI | Installed globally (step 1) |
| Production backend URL | HTTPS endpoint (see hosting guides) |

---

## Step 1 — Before You Build: Update App Config

### 1a. Rename the app (currently named "mobile")

Open `mobile/app.json` and fill in real values:

```json
{
  "expo": {
    "name": "WorkAI",
    "slug": "workai-chatbot",
    "version": "1.0.0",
    "orientation": "portrait",
    "icon": "./assets/icon.png",
    "userInterfaceStyle": "light",
    "splash": {
      "image": "./assets/splash-icon.png",
      "resizeMode": "contain",
      "backgroundColor": "#1E3A8A"
    },
    "ios": {
      "supportsTablet": true,
      "bundleIdentifier": "com.yourcompany.workai",
      "buildNumber": "1"
    },
    "android": {
      "package": "com.yourcompany.workai",
      "versionCode": 1,
      "adaptiveIcon": {
        "foregroundImage": "./assets/adaptive-icon.png",
        "backgroundColor": "#1E3A8A"
      }
    },
    "extra": {
      "eas": {
        "projectId": "YOUR_EAS_PROJECT_ID"
      }
    }
  }
}
```

**Key fields:**
- `ios.bundleIdentifier` — unique reverse-DNS identifier (com.company.appname). Must match what you register in App Store Connect.
- `android.package` — same reverse-DNS format. Must match Google Play.
- `version` / `buildNumber` / `versionCode` — increment these on every release.

### 1b. Set the production API URL

In `mobile/services/api.ts`:
```typescript
export const BASE_URL = 'https://api.yourdomain.com';
```

### 1c. Create app icons

Replace the placeholder assets in `mobile/assets/`:
- `icon.png` — 1024×1024 PNG, no transparency (App Store)
- `adaptive-icon.png` — 1024×1024 PNG with transparent background (Android)
- `splash-icon.png` — 1242×2436 PNG (or use Expo's splash tool)

Free tool: https://appicon.co — generates all sizes from one image.

---

## Step 2 — Install EAS CLI

```bash
npm install -g eas-cli

# Log in to your Expo account
eas login
```

---

## Step 3 — Configure EAS Build

```bash
cd mobile

# Initialize EAS (creates eas.json, links to Expo project)
eas build:configure
```

This creates `mobile/eas.json`. Update it:

```json
{
  "cli": {
    "version": ">= 12.0.0"
  },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal"
    },
    "preview": {
      "distribution": "internal",
      "android": { "buildType": "apk" }
    },
    "production": {
      "autoIncrement": true
    }
  },
  "submit": {
    "production": {}
  }
}
```

**Build profiles:**
| Profile | Use case |
|---|---|
| `development` | Dev client for testing with Expo dev tools |
| `preview` | APK for internal testing without app stores |
| `production` | Final binary for App Store / Google Play submission |

---

## Step 4 — Android Build + Submission

### 4a. Build the Android binary

```bash
cd mobile
eas build --platform android --profile production
```

EAS prompts you to create or use existing credentials.
- **Keystore:** EAS can generate and manage it for you (recommended).
- Build takes ~5–15 minutes in the cloud.
- When done, you get a download link for the `.aab` file (Android App Bundle).

### 4b. Set up Google Play

1. Go to https://play.google.com/console
2. Create an app → fill in details (name, description, screenshots, icon)
3. Go to **Release → Production** (or Internal Testing first)
4. Upload the `.aab` file EAS generated
5. Fill in the Content Rating questionnaire
6. Set a price (Free)
7. Submit for review (typically 1–3 days)

### 4c. Submit directly from EAS (optional)

```bash
# Configure Google Play credentials
eas submit --platform android --profile production

# EAS prompts for your Google Play service account JSON key
# Follow: https://docs.expo.dev/submit/android/
```

---

## Step 5 — iOS Build + Submission

### 5a. Prerequisites

- Active Apple Developer Program membership ($99/year)
- Your app registered in **App Store Connect** (https://appstoreconnect.apple.com)

### 5b. Create an App Store Connect record

1. Log in to https://appstoreconnect.apple.com
2. My Apps → **+** → New App
3. Fill in: Platform (iOS), Name, Primary Language, Bundle ID (must match `app.json`), SKU
4. Save — the record is created but the app isn't live yet

### 5c. Build the iOS binary

```bash
cd mobile
eas build --platform ios --profile production
```

EAS prompts for your Apple Developer credentials:
- **Distribution certificate** — EAS can create one for you
- **Provisioning profile** — EAS generates an App Store profile
- Build takes ~15–30 minutes

### 5d. Submit to App Store

```bash
eas submit --platform ios --profile production
# EAS uploads the .ipa directly to App Store Connect
```

Or submit manually:
1. Download the `.ipa` from the EAS build page
2. Use **Transporter** (Mac app from App Store) to upload it
3. In App Store Connect → TestFlight (for beta) or go straight to App Review
4. Fill in App Review information, screenshots (6.5" + 5.5" iPhone required), keywords
5. Submit for review (typically 1–3 days, sometimes 24h)

---

## Step 6 — Internal Testing Before Release

### Android — Internal Testing track
1. In Google Play Console → Testing → Internal Testing → Create new release
2. Upload your `.aab`
3. Add testers by email
4. Share the opt-in URL with testers

### iOS — TestFlight
```bash
# After EAS uploads to App Store Connect:
# 1. Go to App Store Connect → TestFlight
# 2. Wait for build processing (~15 min)
# 3. Add internal testers (by Apple ID)
# 4. Or create an External Group and add an email list
```

---

## Step 7 — Preview Build (for quick internal testing, no stores)

This creates a `.apk` (Android) you can share directly — no Google Play review needed.

```bash
# Build a shareable APK
eas build --platform android --profile preview

# EAS gives you a URL to download and share the APK directly
```

For iOS internal distribution without App Store:
```bash
eas build --platform ios --profile preview
# Creates an .ipa for registered test devices only
# Add UDIDs via: eas device:create
```

---

## Step 8 — Releasing Updates (OTA Updates)

Expo supports **over-the-air (OTA) updates** for JS/asset changes — no app store
review required. This only works for changes that don't touch native code.

```bash
# Push an update to all users instantly
eas update --branch production --message "Fix chat streaming bug"
```

**When you DO need a new store submission:**
- Adding a new native dependency (e.g., expo-camera, expo-notifications)
- Changing app.json settings (bundle ID, permissions, splash screen)
- Major version bumps

---

## Release Checklist

### Before every production build:
- [ ] `BASE_URL` in `api.ts` points to the production HTTPS backend
- [ ] `version` incremented in `app.json`
- [ ] `buildNumber` (iOS) / `versionCode` (Android) incremented in `app.json`
- [ ] `npx tsc --noEmit` → 0 errors
- [ ] Tested on a physical device (not just emulator)
- [ ] All 5 department chat flows tested (HR, IT, Finance, Legal, Admin)
- [ ] Admin upload + delete tested
- [ ] Clarification flow tested (send an ambiguous message)

### App Store assets required:
- [ ] App icon 1024×1024 (no transparency)
- [ ] Screenshots for iPhone 6.5" (1284×2778) and 5.5" (1242×2208)
- [ ] (Optional) iPad screenshots if `supportsTablet: true`
- [ ] App description (up to 4000 characters)
- [ ] Keywords (up to 100 characters)
- [ ] Privacy policy URL (required if the app collects any user data)
- [ ] Support URL

### Google Play assets required:
- [ ] Feature graphic 1024×500
- [ ] Screenshots (minimum 2, maximum 8 per device type)
- [ ] Short description (80 characters)
- [ ] Full description (4000 characters)
- [ ] Privacy policy URL

---

## Versioning Strategy

| Change type | What to bump |
|---|---|
| Bug fix (JS only) | OTA update — no bump needed |
| Feature (JS only) | OTA update + bump `version` in app.json |
| New native dependency | Full rebuild — bump all version numbers |
| Breaking backend change | Full rebuild |

Android `versionCode` must be a strictly increasing integer.
iOS `buildNumber` must be a strictly increasing string (usually "1", "2", "3"...).
