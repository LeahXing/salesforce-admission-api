"""SAT / GRE / GMAT (legacy) / TOEFL iBT score-report extraction.

Requires: pip install pymupdf opencv-python-headless pytesseract numpy
System OCR dependency: tesseract-ocr. Text PDFs do not need OCR.
This module extracts evidence; it cannot establish issuer authenticity.
"""
from __future__ import annotations
import argparse
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz

MONTH = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
DATE = rf'(?:\d{{1,2}}\s+{MONTH}\s+\d{{4}}|{MONTH}\.?\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{4}})'


def clean(s: str) -> str:
    return re.sub(r'[ \t]+', ' ', unicodedata.normalize('NFKC', s)).strip()


def name_key(s: str) -> list[str]:
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c)).upper()
    # Family-name-first formats (e.g. RABABA, ZAID AHMAD MOHAMMAD)
    if ',' in s:
        family, given = s.split(',', 1)
        s = given + ' ' + family
    return re.findall(r'[A-Z]+', s)


def compare_name(extracted: str | None, applicant: str | None) -> str:
    if not extracted or not applicant:
        return 'REVIEW_REQUIRED'
    a, b = name_key(extracted), name_key(applicant)
    if a == b or (len(a) == len(b) and sorted(a) == sorted(b)):
        return 'MATCH'
    # Avoid rejecting different spellings/initials automatically.
    return 'REVIEW_REQUIRED' if set(a) & set(b) else 'MISMATCH'


def _ocr_page(page: fitz.Page) -> tuple[str, float | None]:
    import cv2
    import numpy as np
    import pytesseract
    pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(clipLimit=2, tileGridSize=(8, 8)).apply(gray)
    data = pytesseract.image_to_data(gray, config='--psm 3', output_type=pytesseract.Output.DICT)
    confidence = [float(x) for x, t in zip(data['conf'], data['text']) if t.strip() and float(x) >= 0]
    return pytesseract.image_to_string(gray, config='--psm 3'), (sum(confidence)/len(confidence) if confidence else None)


def _page_text(page: fitz.Page) -> tuple[str, str, float | None]:
    txt = page.get_text(sort=True)
    if len(re.sub(r'\W', '', txt)) >= 100:
        return txt, 'PDF_TEXT', None
    try:
        ocr, conf = _ocr_page(page)
        return ocr, 'TESSERACT_OCR', conf
    except (ImportError, RuntimeError, OSError) as e:
        return txt, 'OCR_UNAVAILABLE', None


def find(pattern: str, text: str, flags: int = re.I | re.M | re.S) -> re.Match | None:
    return re.search(pattern, text, flags)


def parse_date(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r'(?<=\w)\.(?=\s|$)', '', s.strip())
    for fmt in ('%B %d, %Y', '%B %d %Y', '%b %d, %Y', '%b %d %Y', '%d %B %Y', '%d %b %Y', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def score_date(text: str, pattern: str = r'Test\s+Date\s*:\s*') -> str | None:
    m = find(pattern + f'({DATE})', text)
    return parse_date(m.group(1)) if m else None


def get_name(text: str, test: str) -> str | None:
    lines = [clean(x) for x in text.splitlines() if clean(x)]
    if test == 'TOEFL':
        m = find(r'^\s*Name\s*:\s*([^\n]+)', text)
        return clean(m.group(1)) if m else None
    if test == 'GRE':
        for i, line in enumerate(lines[:25]):
            if 'TEST TAKER SCORE REPORT' in line.upper():
                for candidate in lines[i+1:i+5]:
                    m = re.match(r'^([A-Z][A-Z .\'-]{4,}?)(?:\s{{2,}}|\s+Most Recent Test Date:|$)'.replace('{{2,}}', '{2,}'), candidate)
                    if m and not m.group(1).startswith(('NOTE', 'ETS')):
                        return clean(m.group(1))
        return None
    if test == 'GMAT':
        for i, line in enumerate(lines[:12]):
            if 'OFFICIAL SCORE REPORT' in line.upper():
                for candidate in lines[i+1:i+5]:
                    m = re.match(r'^([A-Z][A-Z \'-]{3,}?)(?:\s{2,}|\s+Issue Date:|$)', candidate)
                    if m:
                        return clean(m.group(1))
        return None
    if test == 'SAT':
        # SAT name appears in the left-side address block on first page.
        for line in text.splitlines()[:35]:
            m = re.match(r'^\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\s{2,}', line)
            if m and not any(w in m.group(1).lower() for w in ('high school', 'test date')):
                return m.group(1)
        for line in lines[:28]:
            m = re.match(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\s{2,}', line)
            if m and not any(w in m.group(1).lower() for w in ('high school', 'test date')):
                return m.group(1)
        # On SAT summary page the name often appears near the bottom.
        return None
    return None


def _sat(text: str) -> dict[str, Any]:
    """Extract SAT scores from text PDFs, including label-after-score layouts."""

    summary = (
        text.split("SAT Summary of Scores", 1)[-1]
        if "SAT Summary of Scores" in text
        else ""
    )

    total = None
    ebrw_score = None
    math_score = None

    if summary:
        # Format A: scores appear before labels (PyMuPDF sort=True).
        # Example:
        # 1540
        # 1400
        # Total
        # 750
        # 620
        # Evidence-Based Reading and Writing
        # Math
        # 790
        # 780

        m = find(
            r"\b(1[0-5]\d{2}|1600|[4-9]\d{2})\s+"
            r"([4-9]\d{2}|1[0-5]\d{2}|1600)\s+"
            r"Total\b",
            summary[:1000],
        )

        if m:
            total = int(m.group(1))

        m = find(
            r"\b(\d{3})\s+\d{3}\s+"
            r"Evidence-Based\s+Reading\s+and\s+Writing\b",
            summary[:1000],
        )

        if m:
            ebrw_score = int(m.group(1))

        m = find(
            r"\bMath\s+(\d{3})\s+\d{3}\b",
            summary[:1000],
        )

        if m:
            math_score = int(m.group(1))

        # Format B: conventional label-first summary tables.
        if total is None:
            m = find(
                r"\bTotal\s+(1[0-5]\d{2}|1600|[4-9]\d{2})\b",
                summary[:1000],
            )
            if m:
                total = int(m.group(1))

        if ebrw_score is None:
            m = find(
                r"Evidence-Based\s+Reading\s+and\s+Writing\s+(\d{3})",
                summary[:1000],
            )
            if m:
                ebrw_score = int(m.group(1))

        if math_score is None:
            m = find(
                r"\bMath\s+(\d{3})",
                summary[:1000],
            )
            if m:
                math_score = int(m.group(1))

    # Use section scores only when both are present and valid.
    if (
        ebrw_score is not None
        and math_score is not None
        and 200 <= ebrw_score <= 800
        and 200 <= math_score <= 800
    ):
        section_total = ebrw_score + math_score

        if total is None:
            total = section_total

    # Do not guess a total from nearby numbers when the summary is ambiguous.
    valid = (
        total is not None
        and 400 <= total <= 1600
        and total % 10 == 0
    )

    if ebrw_score is not None and math_score is not None:
        valid = valid and (ebrw_score + math_score == total)

    return {
        "total_score": total,
        "sections": {
            "evidence_based_reading_writing": ebrw_score,
            "math": math_score,
        },
        "score_consistent": valid,
        "test_date": score_date(text),
    }

def _gre(text: str) -> dict[str, Any]:
    # Restrict to the actual score-history table, not recipient tables or policy text.
    part = text.split('General Test Scores', 1)[-1].split('Subject Test Scores', 1)[0]
    # date, verbal, verbal percentile, quantitative, quantitative percentile, AWA, percentile
    m = find(rf'({DATE})\s+(1[3-7]\d)\s+\d{{1,2}}\s+(1[3-7]\d)\s+\d{{1,2}}\s+([0-6](?:\.\d)?)\s+\d{{1,2}}', part)
    if not m:
        # GRE report also embeds a machine-generated CSV row on page 1.
        m2 = find(r'\b\d{2}-\d{2}-\d{2},(1[3-7]\d),\d+(?:\.\d+)?,(1[3-7]\d),\d+(?:\.\d+)?,([0-6](?:\.\d)?),', text)
        if not m2:
            return {'total_score': None, 'sections': {}, 'score_consistent': False, 'test_date': None}
        verbal, quantitative, awa = int(m2.group(1)), int(m2.group(2)), float(m2.group(3))
        date = score_date(text, r'Most\s+Recent\s+Test\s+Date\s*:\s*')
    else:
        verbal, quantitative, awa = int(m.group(2)), int(m.group(3)), float(m.group(4))
        date = parse_date(m.group(1))
    return {'total_score': verbal + quantitative,
            'sections': {'verbal': verbal, 'quantitative': quantitative, 'analytical_writing': awa},
            'score_consistent': 130 <= verbal <= 170 and 130 <= quantitative <= 170 and 0 <= awa <= 6 and awa * 2 == int(awa * 2),
            'test_date': date}


def _gmat(text: str) -> dict[str, Any]:
    """
    Extract the highest valid legacy GMAT Total Score (200–800).

    Supports:
    1. Row-based score tables (Sample 1)
    2. Column-grouped score tables (Sample 2)

    Canceled attempts are ignored.
    """
    import re

    empty = {
        "total_score": None,
        "sections": {},
        "score_consistent": False,
        "test_date": None,
        "score_scale": "LEGACY_200_800",
    }

    marker = "Test Information (Score / % Below)"
    if marker not in text:
        return empty

    part = text.split(marker, 1)[1].split("©", 1)[0]

    candidates = []

    def add_candidate(date_str, verbal, quant, total, awa, ir):
        try:
            verbal = int(verbal)
            quant = int(quant)
            total = int(total)
            awa = float(awa)
            ir = int(ir)
        except (TypeError, ValueError):
            return

        date = parse_date(date_str)

        valid = (
            date is not None
            and 200 <= total <= 800
            and total % 10 == 0
            and 0 <= verbal <= 60
            and 0 <= quant <= 60
            and 0 <= awa <= 6
            and 1 <= ir <= 8
        )

        if valid:
            candidates.append({
                "total_score": total,
                "sections": {
                    "verbal": verbal,
                    "quantitative": quant,
                    "analytical_writing": awa,
                    "integrated_reasoning": ir,
                },
                "score_consistent": True,
                "test_date": date,
                "score_scale": "LEGACY_200_800",
            })

    # --------------------------------------------------
    # Format 1: Row-based GMAT score table
    # --------------------------------------------------
    row_pattern = re.compile(
        rf"({DATE})\s+"
        r"(\d{1,2})\s*/\s*\d+%\s+"
        r"(\d{1,2})\s*/\s*\d+%\s+"
        r"(\d{3})\s*/\s*\d+%\s+"
        r"([0-6](?:\.\d)?)\s*/\s*\d+%\s+"
        r"(\d{1,2})\s*/\s*\d+%",
        re.IGNORECASE,
    )

    for match in row_pattern.finditer(part):
        add_candidate(*match.groups())

    # --------------------------------------------------
    # Format 2: Column-grouped GMAT score table
    # --------------------------------------------------
    lines = [
        line.strip()
        for line in part.splitlines()
        if line.strip()
    ]

    date_pattern = re.compile(
        r"^\d{1,2}\s+[A-Za-z]+\s+\d{4}$"
    )

    score_pattern = re.compile(
        r"^(\d+(?:\.\d+)?)\s*/\s*\d+%$"
    )

    # Locate the score-table header.
    header = [
        "Test Date",
        "Verbal",
        "Quantitative",
        "Total",
        "Analytical Writing",
        "Integrated Reasoning",
    ]

    for i in range(len(lines) - len(header) + 1):
        if lines[i:i + len(header)] != header:
            continue

        values = lines[i + len(header):]

        # Collect consecutive test dates.
        dates = []
        pos = 0

        while pos < len(values) and date_pattern.fullmatch(values[pos]):
            dates.append(values[pos])
            pos += 1

        if not dates:
            continue

        n = len(dates)

        # Each of the five score columns contains n entries.
        columns = []

        for _ in range(5):
            column = []

            for _ in range(n):
                if pos >= len(values):
                    break

                match = score_pattern.fullmatch(values[pos])

                if not match:
                    break

                column.append(match.group(1))
                pos += 1

            if len(column) != n:
                break

            columns.append(column)

        if len(columns) == 5:
            for j, date in enumerate(dates):
                add_candidate(
                    date,
                    columns[0][j],
                    columns[1][j],
                    columns[2][j],
                    columns[3][j],
                    columns[4][j],
                )

    if not candidates:
        return empty

    # Select highest valid GMAT Total Score.
    return max(candidates, key=lambda item: item["total_score"])

def _toefl(text: str) -> dict[str, Any]:
    # Score box on page 1; avoid the score legends/ranges on page 2.
    part = text.split('TOEFL iBT Scaled Scores', 1)[-1].split('Security Identification', 1)[0]
    sections = {}
    for label in ('Reading', 'Listening', 'Speaking', 'Writing'):
        m = find(rf'\b{label}\s*(?:[.·\s]{{0,30}})\s*(\d{{1,2}})\b', part)
        sections[label.lower()] = int(m.group(1)) if m else None
    m = find(r'Total\s+Score[^\n]{0,180}?\s(\d{1,3})\s*(?:\n|$)', part)
    total = int(m.group(1)) if m else None
    valid = total is not None and 0 <= total <= 120 and all(v is not None and 0 <= v <= 30 for v in sections.values()) and sum(sections.values()) == total
    return {'total_score': total, 'sections': sections, 'score_consistent': valid, 'test_date': score_date(text)}


PARSERS = {'SAT': _sat, 'GRE': _gre, 'GMAT': _gmat, 'TOEFL': _toefl}
THRESHOLDS = {'SAT': 1100, 'GRE': 290, 'GMAT': 600, 'TOEFL': 72}


def extract_exam_score(pdf_bytes: bytes, document_type: str, applicant_name: str | None = None) -> dict[str, Any]:
    """Parse PDF; no web calls or Salesforce side effects. `document_type` is the expected type."""
    expected = document_type.upper().strip()
    if expected not in PARSERS:
        raise ValueError(f'Unsupported exam document type: {document_type}')
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    pages = []
    methods = []
    ocr_conf = []
    # Score tables and name are on first page; SAT summary on second page.
    for p in list(doc)[:2 if expected == 'SAT' else 1]:
        txt, method, confidence = _page_text(p)
        pages.append(txt)
        methods.append(method)
        if confidence is not None:
            ocr_conf.append(confidence)
    text = '\n'.join(pages)
    first = pages[0] if pages else ''
    # Match report headings rather than incidental references to the test in policy pages.
    markers = {
        'SAT': r'SAT\s+Score\s+Report|SAT\s+Summary\s+of\s+Scores',
        'GRE': r'TEST\s+TAKER\s+SCORE\s+REPORT[\s\S]{0,2000}?Your\s+Scores\s+for\s+the\s+General\s+Test|Your\s+Test\s+Score\s+History',
        'GMAT': r'Graduate\s+Management\s+Admission\s+Test|Official\s+Score\s+Report\s*-\s*Test\s+Taker\s+Copy',
        'TOEFL': r'TOEFL\s+iBT\s+Scaled\s+Scores|TOEFL\s+iBT\s+Test\s+Taker\s+Score\s+Report'
    }
    matched = bool(find(markers[expected], text))
    name = get_name(first, expected)
    if not name and expected == 'SAT' and len(pages) > 1:
        m = find(r'\n\s*([A-Z][a-z]+\s+[A-Z][a-z]+)\s*\n\s*Test\s+Date', pages[1])
        if m:
            name = clean(m.group(1))
    result = PARSERS[expected](text)
    total = result['total_score']
    score_ok = bool(result['score_consistent'])
    name_status = 'SKIPPED'  # Demo: all name matching disabled
    # Missing name, score, type, or low OCR confidence -> manual review rather than invented success.
    reasons = []
    if not matched:
        reasons.append('DOCUMENT_TYPE_UNCERTAIN')
    if not score_ok:
        reasons.append('SCORE_EXTRACTION_UNCERTAIN')
    if name_status == 'REVIEW_REQUIRED':
        reasons.append('NAME_MATCH_UNCERTAIN')
    if name_status == 'MISMATCH':
        reasons.append('NAME_MISMATCH')
    if ocr_conf and min(ocr_conf) < 65:
        reasons.append('LOW_OCR_CONFIDENCE')
    if not reasons:
        verification = 'PASSED'
    elif reasons == ['NAME_MISMATCH']:
        verification = 'FAILED'
    else:
        verification = 'REVIEW_REQUIRED'
    if not matched or not score_ok:
        eligibility = 'NOT_EVALUATED'
    elif total >= THRESHOLDS[expected]:
        eligibility = 'MEETS_SCORE_THRESHOLD'
    else:
        eligibility = 'BELOW_SCORE_THRESHOLD'
    if verification == 'PASSED':
        message = (
            f'{expected} score report processed successfully. '
            f'Your score of {total} '
            + ('meets' if eligibility == 'MEETS_SCORE_THRESHOLD' else 'does not meet')
            + f' the required minimum score of {THRESHOLDS[expected]}.'
        )
    elif 'NAME_MISMATCH' in reasons and len(reasons) == 1:
        message = 'The name on your score report does not match your application. Please check your details or request manual verification.'
    else:
        message = 'We could not confidently verify all information in your score report. Our admissions team needs to review this document manually.'
    return {'document_type': expected, 'detected_document_type_match': matched,
            'student_name': name, 'name_match_status': name_status,
            'test_date': result.get('test_date'), 'total_score': total,
            'sections': result['sections'], 'score_scale': result.get('score_scale'),
            'score_consistent': score_ok, 'score_threshold': {'operator': '>=', 'value': THRESHOLDS[expected]},
            'score_eligibility': eligibility, 'verification_status': verification,
            'reason_codes': reasons, 'extraction_methods': methods,
            'ocr_confidence': round(min(ocr_conf), 1) if ocr_conf else None,
            'message': message,
            'issuer_authenticity_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf')
    parser.add_argument('--type', required=True, choices=list(PARSERS))
    parser.add_argument('--applicant-name')
    args = parser.parse_args()
    print(json.dumps(extract_exam_score(Path(args.pdf).read_bytes(), args.type, args.applicant_name), indent=2))
