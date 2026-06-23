# Usage Status

A simple macOS menu bar app that shows how much **SuperGrok**, **Codex**, and **Claude** quota you have left.

No terminal needed after install — just icons in your menu bar with percentages.

![macOS 13+](https://img.shields.io/badge/macOS-13%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)

## Install (easy)

1. Download **[Usage-Status.dmg](https://github.com/yurii-lgtm/usage-status/releases/latest)** from Releases
2. Open the DMG
3. Double-click **`Install Usage Status.command`**
4. Usage icons appear in your menu bar

**First launch:** macOS may block the app because it is not notarized. Right-click **Usage Status** in Applications → **Open** → **Open** once.

## What you see

| Icon | Shows |
|------|--------|
| Grok | SuperGrok free credits remaining |
| Codex | Codex weekly quota remaining |
| Claude | Claude usage remaining |

Click any icon for details, hide services you do not need, or **Reauthenticate...** to sign in again.

## Sign in to your AI tools

Usage Status reads quota from each provider’s CLI session. Sign in once per tool:

- **Grok:** `grok login` (or Reauthenticate from the Grok menu)
- **Codex:** `codex login`
- **Claude:** `claude auth login`

If you are not signed in, the menu bar shows **—** for that provider. Click it or use **Reauthenticate...** to open the login flow.

## Menu options

Each provider menu includes:

- Current usage and reset time
- **Hide [provider]** — remove that icon from the menu bar
- **Show in Menu Bar** — checkboxes to turn services on/off (available from any visible provider menu)
- **Reauthenticate...**
- **Quit Usage Status**

Settings are saved automatically.

## Build from source (developers)

Requirements: macOS 13+, Python 3.12+, Xcode command line tools.

```bash
git clone https://github.com/yurii-lgtm/usage-status.git
cd usage-status
./package.sh
open dist/Usage-Status.dmg
```

Run tests:

```bash
python3 -m unittest discover -v
```

## Privacy

- Reads usage from local CLI sessions and provider APIs
- Stores display preferences in `~/Library/Application Support/com.bot.usage-status/`
- No telemetry, no cloud account for Usage Status itself

## License

MIT — see [LICENSE](LICENSE).