"""Presentation cleanup for generated notes; chart provenance stays in metadata."""
from copy import deepcopy
import re

MARKERS = re.compile(r'\ue200(?:cite|filecite)\ue202[^\ue201]*\ue201|【[^】]*†source[^】]*】')
LINKS = re.compile(r'\[([^\]\n]+)\]\(https?://[^\s]+\)')
URLS = re.compile(r'https?://[^\s<>"\])}]+')
SOURCE_HEADING = re.compile(r'^\s*(?:\d+[.)]\s*)?(?:sources?|references?|bibliography|citations?)\s*:?\s*$', re.I)
ATTRIBUTION = re.compile(
    r'^(?:see\b|consult\b|retrieved from\b|available (?:at|from)\b|'
    r'(?:the |this )?(?:adopted |reference )?(?:value|constant|data|method|formula|relationship) '
    r'(?:is|are|was|were) (?:recorded in|listed in|documented in|published by|available at|taken from)\b)', re.I)


def citations_requested(question):
    text = (question or '').lower().replace('’', "'")
    if re.search(r"\b(?:no|without|omit|remove|skip|don't|do not)\b[^.!?\n]{0,35}\b(?:cite|citations?|sources?|references?)\b|citation-free", text):
        return False
    return bool(re.search(r'\b(?:cite|citations?|bibliography)\b|\b(?:include|show|list|provide|give)\s+(?:the\s+)?(?:sources|references|source (?:links|urls))\b', text))


def clean_text(text):
    lines = []
    for line in text.splitlines():
        has_reference = bool(URLS.search(line) or MARKERS.search(line))
        if has_reference and re.match(r'^\s*(?:sources?|references?|citations?|bibliography)\s*:', line, re.I):
            continue
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', line)
        kept = []
        for sentence in sentences:
            # Remove a source-only sentence, but retain values and mathematical work.
            if URLS.search(sentence) and ATTRIBUTION.match(sentence.strip()):
                outside_links = URLS.sub('', LINKS.sub('', sentence))
                if not re.search(r'\d|=', outside_links):
                    continue
            sentence = MARKERS.sub('', sentence)
            sentence = LINKS.sub(lambda match: '' if re.fullmatch(r'\d+(?:,\s*\d+)*', match[1]) else match[1], sentence)
            def remove_url(match):
                value = match.group()
                return value[len(value.rstrip('.,;:!?')):]
            sentence = URLS.sub(remove_url, sentence)
            sentence = re.sub(r'\(\s*\)|\[\s*\]', '', sentence) if has_reference else sentence
            sentence = re.sub(r'[ \t]+([.,;:!?])', r'\1', sentence).strip()
            if sentence:
                kept.append(sentence)
        if kept:
            lines.append(' '.join(kept))
    return '\n'.join(lines).strip()


def without_citations(answer):
    result = deepcopy(answer)
    sections = []
    for section in result['sections']:
        if SOURCE_HEADING.fullmatch(section['heading']) and all(block['kind'] == 'text' for block in section['blocks']):
            continue
        section['heading'] = clean_text(section['heading'])
        blocks = []
        for block in section['blocks']:
            if block['kind'] == 'equation':
                block['content'] = MARKERS.sub('', block['content']).strip()
            else:
                block['content'] = clean_text(block['content'])
            if block['kind'] == 'chart':
                chart = block['chart']
                for key in ('title', 'x_label', 'y_label', 'notes'):
                    chart[key] = clean_text(chart[key])
                for item in chart['series'] + chart['annotations']:
                    item['label'] = clean_text(item['label'])
            if block['content'] or block['kind'] == 'chart':
                blocks.append(block)
        section['blocks'] = blocks
        if blocks:
            sections.append(section)
    result['sections'] = sections
    return result
