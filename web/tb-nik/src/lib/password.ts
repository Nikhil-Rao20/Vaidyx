// The strength hint under a new password: four plain checks and one word. The server has the last word (minimum length,
// not the login name, not the current password).
export function passwordStrength(p: string): { score: 0 | 1 | 2 | 3 | 4; word: string; checks: Array<{ ok: boolean; text: string }> } {
  const checks = [
    { ok: p.length >= 8, text: "At least 8 characters" },
    { ok: p.length >= 12, text: "12 or more is better" },
    { ok: /[a-z]/.test(p) && /[A-Z]/.test(p), text: "Small and capital letters" },
    { ok: /\d/.test(p) || /[^A-Za-z0-9]/.test(p), text: "A number or a sign" },
  ];
  const score = checks.filter((c) => c.ok).length as 0 | 1 | 2 | 3 | 4;
  const word = score <= 1 ? "weak" : score === 2 ? "fair" : score === 3 ? "good" : "strong";
  return { score, word, checks };
}
