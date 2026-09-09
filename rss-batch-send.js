const fs = require('fs');
const { execSync } = require('child_process');
const msgs = JSON.parse(fs.readFileSync('/root/.openclaw/workspace/messages.json', 'utf8'));

for (let i = 0; i < msgs.length; i++) {
  const text = msgs[i];
  // Write to temp file and use curl
  const tmpFile = `/tmp/rss-msg-${i}.txt`;
  fs.writeFileSync(tmpFile, text);
  try {
    // Try to send via daxiang skill if available
    console.log(`Sending batch ${i+1}/${msgs.length}...`);
  } catch (e) {
    console.error(`Failed to send batch ${i+1}:`, e.message);
  }
}
