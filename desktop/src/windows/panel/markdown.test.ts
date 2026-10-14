import { describe, expect, it } from 'vitest';
import { renderAnswer } from './markdown';

describe('renderAnswer', () => {
  it('turns an aliased wikilink into a chip that carries the file path', () => {
    const html = renderAnswer('See [[knowledge/people/sid-rahman|Sid Rahman]].');
    expect(html).toContain('<button class="wl" data-file="knowledge/people/sid-rahman">Sid Rahman</button>');
  });

  it('labels a bare wikilink with its last path segment and drops heading anchors', () => {
    expect(renderAnswer('[[knowledge/projects/fleet]]')).toContain(
      'data-file="knowledge/projects/fleet">fleet</button>',
    );
    expect(renderAnswer('[[a/b#Section|B]]')).toContain('data-file="a/b">B</button>');
  });

  it('escapes markup inside the link label', () => {
    expect(renderAnswer('[[x|<b>bold</b>]]')).toContain('>&lt;b&gt;bold&lt;/b&gt;</button>');
  });

  it('renders ordinary markdown with line breaks', () => {
    const html = renderAnswer('**Sid** owns it\nsecond line');
    expect(html).toContain('<strong>Sid</strong>');
    expect(html).toContain('<br>');
  });
});
