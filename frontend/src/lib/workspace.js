import { createContext, useContext } from 'react';

export const WorkspaceContext = createContext(null);
export const useWS = () => useContext(WorkspaceContext);

export function speak(text, onUnsupported) {
  if (!('speechSynthesis' in window)) { onUnsupported?.('Text-to-speech is not supported in this browser.'); return; }
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 0.96;
  window.speechSynthesis.speak(u);
}
