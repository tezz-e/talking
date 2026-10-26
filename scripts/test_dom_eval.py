from pathlib import Path
import re
from playwright.sync_api import sync_playwright

code = Path('backend/instagram_watcher.py').read_text(encoding='utf-8')
# Find evaluate string
start_token = 'messages = await page.evaluate(r"""'
if start_token not in code:
    start_token = 'messages = await page.evaluate("""'

start = code.find(start_token) + len(start_token)
end = code.find('""", limit)', start)
js_scraper = code[start:end]
print(f"Extracted JS scraper: length={len(js_scraper)}")

mock_ig_html = """
<!DOCTYPE html>
<html>
<head><title>Instagram Direct Web</title></head>
<body style="margin:0; display:flex;">
  <!-- Left Inbox Sidebar (0 to 320px) - Avatars must be IGNORED -->
  <div style="width:320px; height:900px; border-right:1px solid #ccc; padding:10px;">
    <h3>Direct Messages</h3>
    <div style="display:flex; align-items:center; gap:8px; margin-bottom:12px;">
      <img src="avatar1.jpg" alt="supermant_678's profile picture" style="width:50px; height:50px; border-radius:50%;" />
      <span>supermant_678</span>
    </div>
    <div style="display:flex; align-items:center; gap:8px;">
      <img src="avatar2.jpg" alt="sofiasaurx's profile picture" style="width:50px; height:50px; border-radius:50%;" />
      <span>sofiasaurx</span>
    </div>
  </div>

  <!-- Main Conversation Container (x > 320px) -->
  <div role="main" style="flex:1; height:900px; display:flex; flex-direction:column; padding:20px;">
    <header style="height:60px; border-bottom:1px solid #eee;">
      <h2>Conversation with Alex</h2>
    </header>

    <div style="flex:1; display:flex; flex-direction:column; gap:12px; padding-top:20px;">
      <!-- Incoming text -->
      <div role="row" style="align-self: flex-start; display: flex;">
        <div dir="auto" style="background:#eee; padding:8px 12px; border-radius:12px;">Hi, you there?</div>
      </div>

      <!-- Outgoing text -->
      <div role="row" style="align-self: flex-end; display: flex;">
        <div dir="auto" style="background:#0095f6; color:#fff; padding:8px 12px; border-radius:12px;">Yeah what's up!</div>
      </div>

      <!-- Incoming Reel -->
      <div role="row" style="align-self: flex-start; display: flex; flex-direction: column;">
        <div style="position:relative; width:220px; height:280px; display:block;">
          <img src="https://instagram.fbcdn.net/v/reel_thumb.jpg?efg=eyJlZmciOiJDTElQUyJ9" width="220" height="280" alt="Reel by @creator: Crazy trick" style="width:220px; height:280px; display:block;" />
          <a href="https://www.instagram.com/reel/C8TestReel123/" style="display:inline-block; margin-top:4px;">Watch on Instagram</a>
        </div>
      </div>

      <!-- Incoming emoji -->
      <div role="row" style="align-self: flex-start; display: flex;">
        <div dir="auto" style="font-size:24px;">😂🔥</div>
      </div>
    </div>

    <footer style="height:60px;">
      <div role="textbox" contenteditable="true" aria-label="Message..."></div>
    </footer>
  </div>
</body>
</html>
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.set_content(mock_ig_html)
    
    # Run scraper
    res = page.evaluate(js_scraper, 10)
    print("\nResult count:", len(res))
    for r in res:
        safe_c = str(r.get("content", "")).encode('ascii', 'replace').decode('ascii')
        print(" ->", r.get("role"), "| is_media:", r.get("is_media"), "| is_reel:", r.get("is_reel"), "|", safe_c)
    browser.close()
