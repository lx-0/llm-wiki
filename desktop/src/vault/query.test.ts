import { describe, it, expect } from 'vitest';
import { parseQueryAnswer } from './query';

const PAYLOAD = JSON.stringify(
  { question: 'What is X?', answer: 'The answer is 42.', input_tokens: 10, output_tokens: 5 },
  null,
  2,
);

describe('parseQueryAnswer', () => {
  it('extracts the answer from the `wiki query --json` payload', () => {
    expect(parseQueryAnswer(PAYLOAD)).toBe('The answer is 42.');
  });

  it('skips the dispatcher banner printed before the payload', () => {
    expect(parseQueryAnswer(`wiki query\n\n${PAYLOAD}\n`)).toBe('The answer is 42.');
  });

  it('returns "" when the payload has no string answer', () => {
    expect(parseQueryAnswer('{"question": "q"}')).toBe('');
  });

  it('throws on output without JSON (runWiki turns that into data=null)', () => {
    expect(() => parseQueryAnswer('wiki query\nsome prose answer')).toThrow();
  });
});
