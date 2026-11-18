export const GROUND_STYLES = ['grid', 'checker', 'wood', 'track', 'stage'];
const storageKey = 'duckking-ground-style';

export function setupGroundPreference(select, apply, {randomDefault = false} = {}) {
  let saved;
  try { saved = localStorage.getItem(storageKey); } catch { /* Storage is optional. */ }
  select.value = GROUND_STYLES.includes(saved) ? saved : randomDefault ? 'random' : 'grid';

  function applySelection() {
    const choice = select.value;
    apply(choice === 'random'
      ? GROUND_STYLES[Math.floor(Math.random() * GROUND_STYLES.length)]
      : choice);
  }

  applySelection();
  select.addEventListener('change', () => {
    try {
      if (select.value === 'random') localStorage.removeItem(storageKey);
      else if (GROUND_STYLES.includes(select.value)) localStorage.setItem(storageKey, select.value);
    } catch { /* Apply the choice for this page even when storage is blocked. */ }
    applySelection();
  });
}
