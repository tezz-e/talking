document.addEventListener('DOMContentLoaded', async () => {
  const badge = document.getElementById('statusBadge');

  try {
    const res = await fetch('http://localhost:8000/api/stats', { signal: AbortSignal.timeout(2000) });
    if (res.ok) {
      badge.textContent = 'Online';
      badge.className = 'badge online';
    } else {
      throw new Error();
    }
  } catch {
    badge.textContent = 'Offline';
    badge.className = 'badge offline';
  }
});
