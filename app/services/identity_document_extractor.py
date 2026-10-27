"""Conservative passport name verification for the Admissions API.

Dependencies: pip install pymupdf pytesseract opencv-python numpy
System dependency: tesseract-ocr (English language pack).
Only the applicant's name is verified; no authenticity or expiration checks.
"""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
import cv2
import fitz
import numpy as np
import pytesseract
from pytesseract import Output

@dataclass
class NameCandidate:
    name: str
    source: str
    confidence: float


def normalize_name(value: str) -> str:
    value = unicodedata.normalize('NFKD', value or '')
    value = ''.join(c for c in value if not unicodedata.combining(c))
    value = value.upper().replace('’', "'")
    value = re.sub(r"[^A-Z\s'-]", ' ', value)
    value = re.sub(r"[-']", ' ', value)
    return ' '.join(value.split())


def name_tokens(value: str) -> tuple[str, ...]:
    return tuple(sorted(normalize_name(value).split()))


def compare_names(extracted: str, expected: str) -> str:
    """Exact normalized token multiset match; no risky fuzzy auto-pass."""
    a, b = name_tokens(extracted), name_tokens(expected)
    if not a or not b:
        return 'UNCERTAIN'
    if a == b:
        return 'MATCH'
    # One-letter initials, missing parts, OCR typos, transliterations are not definitive mismatches.
    if any(len(t) == 1 for t in a + b):
        return 'UNCERTAIN'
    if set(a).issubset(set(b)) or set(b).issubset(set(a)):
        return 'UNCERTAIN'
    return 'MISMATCH'


def mrz_candidates(text: str) -> list[NameCandidate]:
    """Parse ICAO TD3 passport name line P<CCC...<<... (also tolerates OCR spaces)."""
    found = []
    for raw in text.upper().splitlines():
        line = re.sub(r'\s+', '', raw)
        # First MRZ line must begin P< plus three-letter issuing country.
        if not re.match(r'^P<[A-Z]{3}', line):
            continue
        body = line[5:]
        if '<<' not in body:
            continue
        surname, given = body.split('<<', 1)
        surname = surname.replace('<', ' ').strip()
        given = given.rstrip('<').replace('<', ' ').strip()
        name = normalize_name(f'{given} {surname}')
        if surname and given and len(name) >= 5:
            found.append(NameCandidate(name, 'MRZ', 0.98 if len(line) == 44 else 0.78))
    return found


def visual_name_candidates(text: str, confidence: float) -> list[NameCandidate]:
    lines = [re.sub(r'\s+', ' ', x).strip() for x in text.splitlines()]
    found = []
    # Only accept text adjacent to explicit passport-name labels.
    for i, line in enumerate(lines):
        label = re.search(r'\b(SURNAME|FAMILY NAME|GIVEN NAMES?|FIRST NAME|FULL NAME)\b', line, re.I)
        if not label:
            continue
        field = label.group(1).upper()
        # A value may follow the label or be on the next line.
        after = re.sub(r'^.*?\b(?:SURNAME|FAMILY NAME|GIVEN NAMES?|FIRST NAME|FULL NAME)\b', '', line, flags=re.I)
        after = re.sub(r'^[\s:/-]+', '', after)
        value = after if re.fullmatch(r'[A-Za-z][A-Za-z .\'-]{2,65}', after) else ''
        if not value and i + 1 < len(lines):
            nxt = lines[i+1]
            if re.fullmatch(r'[A-Za-z][A-Za-z .\'-]{2,65}', nxt) and not re.search(r'\b(?:NATIONALITY|DATE|PASSPORT|PLACE|SEX|COUNTRY|ISSUE|EXPIRY)\b', nxt, re.I):
                value = nxt
        if value:
            found.append((field, normalize_name(value)))
    output = []
    surnames = [v for k,v in found if k in ('SURNAME','FAMILY NAME')]
    given = [v for k,v in found if k in ('GIVEN NAME','GIVEN NAMES','FIRST NAME')]
    for s in surnames:
        for g in given:
            output.append(NameCandidate(f'{g} {s}', 'VISUAL_FIELDS', confidence))
    for k,v in found:
        if k == 'FULL NAME':
            output.append(NameCandidate(v, 'VISUAL_FULL_NAME', confidence))
    return output


def ocr_image(img: np.ndarray) -> tuple[str,float]:
    data = pytesseract.image_to_data(img, config='--psm 6', output_type=Output.DICT)
    words, scores = [], []
    for word, conf in zip(data['text'], data['conf']):
        try: c = float(conf)
        except (TypeError,ValueError): continue
        if word.strip() and c >= 0:
            words.append(word)
            scores.append(c)
    text = pytesseract.image_to_string(img, config='--psm 6')
    return text, (sum(scores)/len(scores)/100 if scores else 0.0)


def get_pages(pdf_bytes: bytes, max_pages: int = 3):
    with fitz.open(stream=pdf_bytes, filetype='pdf') as doc:
        for page in list(doc)[:max_pages]:
            pix = page.get_pixmap(matrix=fitz.Matrix(2.5,2.5), alpha=False)
            img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height,pix.width,pix.n)
            if pix.n == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
            yield page.get_text('text'), img


def verify_passport_name(pdf_bytes: bytes, applicant_name: str) -> dict:
    if not applicant_name or not normalize_name(applicant_name):
        raise ValueError('Salesforce applicant name is required')
    candidates: list[NameCandidate] = []
    text_seen = False
    try:
        pages = list(get_pages(pdf_bytes))
    except Exception:
        return dict(verification_status='REVIEW_REQUIRED', reason_code='UNREADABLE_DOCUMENT',
                    message='We could not read your identity document. Please upload a clearer copy or request manual verification.',
                    action_required='MANUAL_REVIEW')
    for embedded, img in pages:
        if embedded.strip():
            text_seen = True
            candidates += mrz_candidates(embedded)
            candidates += visual_name_candidates(embedded, 0.90)
        # OCR original plus 180-degree rotation for sideways/upside-down scans.
        for rotation in (0, 180):
            frame = cv2.rotate(img, cv2.ROTATE_180) if rotation else img
            text, confidence = ocr_image(frame)
            text_seen |= bool(text.strip())
            candidates += mrz_candidates(text)
            candidates += visual_name_candidates(text, confidence)
            # MRZ: OCR on the lower half of passport photo pages with single-line mode
            for strip in (frame[int(frame.shape[0]*0.84):],):
                gray = cv2.cvtColor(strip, cv2.COLOR_RGB2GRAY)
                mrz_text = pytesseract.image_to_string(gray, config='--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<\n')
                candidates += mrz_candidates(mrz_text)
    # Avoid trusting one garbled candidate: require reliable source and corroboration.
    good = [c for c in candidates if c.confidence >= 0.80 and len(name_tokens(c.name)) >= 2]
    matches = [c for c in good if compare_names(c.name, applicant_name) == 'MATCH']
    distinct = {name_tokens(c.name) for c in good}
    has_mrz = any(c.source == 'MRZ' and c.confidence >= .90 for c in good)
    has_visual = any(c.source.startswith('VISUAL') for c in good)
    if matches and len(distinct) == 1 and (has_mrz or len(matches) >= 2):
        return dict(verification_status='PASSED', reason_code='NAME_MATCH',
                    message='The name on your passport matches the name on your application.',
                    action_required='NONE', name_match=True)
    # Never auto-fail based solely on OCR mismatch; the mismatch may be OCR error.
    if good and len(distinct) == 1 and has_mrz and has_visual and not matches:
        return dict(verification_status='REVIEW_REQUIRED', reason_code='NAME_MISMATCH_REVIEW',
                    message='The passport name could not be matched to your application. Our team will review it manually.',
                    action_required='MANUAL_REVIEW', name_match=None)
    return dict(verification_status='REVIEW_REQUIRED',
                reason_code='LOW_CONFIDENCE_NAME_EXTRACTION' if text_seen else 'UNREADABLE_DOCUMENT',
                message='We could not confidently verify the name on your passport. Please upload a clearer copy or request manual verification.',
                action_required='MANUAL_REVIEW', name_match=None)

if __name__ == '__main__':
    import argparse, json
    p = argparse.ArgumentParser()
    p.add_argument('pdf')
    p.add_argument('--applicant-name', required=True)
    a = p.parse_args()
    print(json.dumps(verify_passport_name(Path(a.pdf).read_bytes(), a.applicant_name), indent=2))
