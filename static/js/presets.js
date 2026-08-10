const presetsModule = {
  getInject()        { return { prefix: '', suffix: '' }; },
  getSelectedPreset(){ return null; },
  getCharacterName() { return ''; },
  removePersistentChat() {},
  getAllPresets()     { return {}; },
  PROMPT_TEMPLATES: [],
};

export default presetsModule;
export const PROMPT_TEMPLATES = [];
export function removePersistentChat() {}
export function getAllPresets() { return {}; }
