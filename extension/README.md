# Talking Copilot — In-Page Chat Extension & Userscript

An in-page AI texting assistant that floats right inside **WhatsApp Web** and **Instagram Direct**. It reads the current contact's name and last incoming message, generates 3 energy variants (`🧊 Chill`, `🎯 Direct`, `🔥 Banter`) using your local Talking autopilot, and inserts approved replies directly into the chat input.

---

## ⚡ Option 1: Violentmonkey / Tampermonkey Userscript (Recommended — Instant Setup)

No unpacked developer mode or browser warnings required.

1. Install **Tampermonkey** or **Violentmonkey** from the Chrome Web Store / Firefox Add-ons.
2. In Tampermonkey, click **Create a new script**.
3. Copy and paste the contents of [`talking-copilot.user.js`](talking-copilot.user.js).
4. Save (`Ctrl+S`).
5. Open [web.whatsapp.com](https://web.whatsapp.com) or [instagram.com/direct](https://www.instagram.com/direct) with your local Talking server running (`python -m backend.main`).

---

## 🧩 Option 2: Chrome Unpacked Extension

1. Open Google Chrome, Brave, or Edge.
2. Navigate to `chrome://extensions`.
3. Enable **Developer mode** (toggle in the top-right corner).
4. Click **Load unpacked** in the top-left.
5. Select this `extension/` folder.
6. The Talking Copilot icon will appear in your browser toolbar.

---

## 🎮 Usage & Shortcuts

- **`Alt + D`**: Generate an instant contextual draft for the open chat.
- **`Enter`** (inside the popup): Insert the active draft directly into the messaging input box.
- **`Esc`**: Close the copilot overlay.
- **Energy chips (`🧊 Chill`, `🎯 Direct`, `🔥 Banter`)**: Click any chip to instantly swap the draft energy.
- **`⚡ Pro` toggle**: Enables strategic reasoning and subtext analysis.
- **`Insert ↵` button**: Injects the reply into the chat and logs the approval to Talking's SQLite and Chroma database so the system learns your voice.
