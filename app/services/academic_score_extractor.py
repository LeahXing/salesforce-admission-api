"""Academic record extraction (prototype). Requires pymupdf, opencv-python, pytesseract.
No admissions decisions are made here. Never infer GPA from percentage.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional
import fitz
import pymupdf

SUPPORTED = {'CLASS_12_MARKSHEET', 'UNDERGRADUATE_TRANSCRIPT'}
NUM = r'(\d+(?:\.\d+)?)'


def pdf_text(pdf_bytes: bytes, *, ocr: bool = True, max_pages: int = 25) -> tuple[str, list[str]]:
    import cv2
    import numpy as np
    import pytesseract
    pages, methods = [], []
    with fitz.open(stream=pdf_bytes, filetype='pdf') as doc:
        for page in list(doc)[:max_pages]:
            text = page.get_text('text', sort=True)
            if ocr and len(re.sub(r'\W', '', text)) < 100:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                gray = cv2.convertScaleAbs(gray, alpha=1.25, beta=4)
                text = pytesseract.image_to_string(gray, config='--psm 3')
                methods.append('OCR_TESSERACT')
            else:
                methods.append('PDF_TEXT')
            pages.append(text)
    return '\n'.join(pages), methods


def number(pattern: str, text: str, flags=re.I | re.S) -> Optional[float]:
    m = re.search(pattern, text, flags)
    return float(m.group(1)) if m else None


def extract_undergraduate(text: str) -> dict:
    result = {'overall_gpa': None, 'gpa_scale': None, 'percentage': None,
              'cumulative_credit_hours': None, 'cumulative_grade_points': None,
              'extraction_method': None, 'academic_level': 'UNKNOWN',
              'has_courses_in_progress': bool(re.search(r'COURSES?\s+IN\s+PROGRESS|IN\s+PROGRESS', text, re.I)),
              'degree_completed': None, 'warnings': []}
    # Level must be established from the record, not from the upload label.
    if re.search(r'TRANSCRIPT\s+TOTALS\s*\(GRADUATE\)|STUDENT\s+TYPE\s*:\s*GRADUATE', text, re.I):
        result['academic_level'] = 'GRADUATE'
    elif re.search(r'UNDERGRADUATE|BACHELOR|B\.\s*(?:SC|TECH|ENG)|BSC\b', text, re.I):
        result['academic_level'] = 'UNDERGRADUATE'

    # Strongly labeled summary formats; do not use generic term GPA.
    patterns = [
        ('CAREER_SUMMARY', r'Cumulative\s+GPA\s*:\s*' + NUM),
        ('ISU_CUMULATIVE', r'ISU\s+CUM\s+GPA\s*[:=]?\s*' + NUM),
    ]
    for label, pat in patterns:
        val = number(pat, text, re.I)
        if val is not None:
            result.update(overall_gpa=val, extraction_method=label)
            break

    # Transcript totals: read the Overall row only within a local totals block.
    if result['overall_gpa'] is None:
        match = re.search(r'TRANSCRIPT\s+TOTALS(?:\s*\([^)]*\))?[^\n]*\n(.{0,1600})', text, re.I | re.S)
        if match:
            segment = match.group(1).split('COURSES IN PROGRESS')[0]
            # Overall followed by six numerical fields, possibly separated by newlines.
            m = re.search(r'\bOverall\s*:\s*' + r'\s+'.join([NUM] * 6), segment, re.I)
            if m:
                vals = [float(v) for v in m.groups()]
                result.update(overall_gpa=vals[5], cumulative_credit_hours=vals[3],
                              cumulative_grade_points=vals[4], extraction_method='TRANSCRIPT_TOTALS_OVERALL')
            else:
                # Wayne State: OVERALL 97.00 92.00 285.71 3.10
                m = re.search(r'\bOVERALL\s+' + r'\s+'.join([NUM] * 4), segment, re.I)
                if m:
                    vals = [float(v) for v in m.groups()]
                    result.update(overall_gpa=vals[3], cumulative_credit_hours=vals[1],
                                  cumulative_grade_points=vals[2], extraction_method='TRANSCRIPT_TOTALS_OVERALL')

    # CGPA is cumulative, unlike SGPA or term GPA. Prefer the row with highest CCH.
    if result['overall_gpa'] is None:
        pairs = re.findall(r'\bCCH\s*[:=]?\s*' + NUM + r'.{0,110}?\bCGP\s*[:=]?\s*' + NUM + r'.{0,110}?\bCGPA\s*[:=]?\s*' + NUM, text, re.I | re.S)
        if pairs:
            hrs, pts, gpa = map(float, max(pairs, key=lambda x: float(x[0])))
            result.update(overall_gpa=gpa, cumulative_credit_hours=hrs,
                          cumulative_grade_points=pts, extraction_method='CCH_CGP_CGPA')
        else:
            matches = re.findall(r'\bCGPA\s*[:=]?\s*' + NUM, text, re.I)
            if matches:
                result.update(overall_gpa=float(matches[-1]), extraction_method='LAST_REPORTED_CGPA')
                result['warnings'].append('Last reported CGPA needs layout/chronology confirmation')

    if result['overall_gpa'] is None:
        # Iowa State numeric summary above a label row: 118.5 101.0 374.05 3.70
        m = re.search(r'(' + NUM + r'\s+' + NUM + r'\s+' + NUM + r'\s+' + NUM + r')\s*(?:TOTAL\s+HRS|ISU\s+CUM)', text, re.I)
        if m:
            values = [float(x) for x in re.findall(NUM, m.group(1))]
            if len(values) == 4:
                result.update(overall_gpa=values[3], cumulative_credit_hours=values[1],
                              cumulative_grade_points=values[2], extraction_method='CUMULATIVE_SUMMARY_TABLE')

    gpa = result['overall_gpa']
    if gpa is not None:
        if not (0 <= gpa <= 10):
            result['warnings'].append('Extracted GPA outside plausible range')
            result['overall_gpa'] = None
        elif gpa <= 4:
            result['gpa_scale'] = 4.0  # provisional: confirm from institution grading key
            result['warnings'].append('4.0 GPA scale inferred; confirm against grading key')
    hrs, pts = result['cumulative_credit_hours'], result['cumulative_grade_points']
    if hrs and pts is not None and gpa is not None and abs(pts / hrs - gpa) > 0.035:
        result['warnings'].append('Reported GPA differs from cumulative points/hours; manual review')
    return result


def extract_class_12(text: str) -> dict:
    result = {'academic_level': 'UNKNOWN', 'percentage': None, 'overall_gpa': None,
              'gpa_scale': None, 'total_marks': None, 'maximum_marks': None,
              'has_courses_in_progress': bool(re.search(r'IN\s+PROGRESS', text, re.I)),
              'degree_completed': None, 'extraction_method': None, 'warnings': []}
    if re.search(r'HIGH\s+SCHOOL\s+EXAMINATION', text, re.I) and not re.search(r'HIGHER\s+SECONDARY|CLASS\s*(?:XII|12)|INTERMEDIATE', text, re.I):
        result['academic_level'] = 'CLASS_10'
    elif re.search(r'HIGHER\s+SECONDARY|HSC\b|CLASS\s*(?:XII|12)|\b12TH\b|SENIOR\s+SECONDARY|INTERMEDIATE', text, re.I):
        result['academic_level'] = 'CLASS_12'
    # Only accept a clearly labeled percentage or aggregate; don't add arbitrary marks.
    pct = number(r'(?:OVERALL\s+PERCENTAGE|PERCENTAGE|PERCENT\s+OF\s+MARKS)\s*[:=]?\s*' + NUM, text, re.I)
    if pct is None:
        pct = number(r'\b(' + r'\d{1,2}\.\d{1,2}' + r')\s*%', text, re.I)
    if pct is None:
        m = re.search(r'Percentage\s+' + NUM + r'\s+' + NUM + r'\s+' + NUM, text, re.I)
        if m:
            maximum, obtained, pct = map(float, m.groups())
            if maximum > 0 and abs(100 * obtained / maximum - pct) < 0.2:
                result.update(total_marks=obtained, maximum_marks=maximum)
    if pct is not None and 0 <= pct <= 100:
        result.update(percentage=pct, extraction_method='EXPLICIT_PERCENTAGE')
    m = re.search(r'(?:GRAND\s+TOTAL|TOTAL\s+MARKS)\s*[:=]?\s*' + NUM + r'\s*(?:/|OUT\s+OF)\s*' + NUM, text, re.I)
    if m:
        obtained, maximum = map(float, m.groups())
        if maximum > 0 and 0 <= obtained <= maximum:
            result.update(total_marks=obtained, maximum_marks=maximum)
            calculated = round(obtained / maximum * 100, 2)
            if result['percentage'] is None:
                result.update(percentage=calculated, extraction_method='EXPLICIT_AGGREGATE')
            elif abs(calculated - result['percentage']) > 0.1:
                result['warnings'].append('Aggregate and percentage inconsistent')
    result['warnings'].append('Do not convert percentage to GPA without approved equivalency')
    return result


def extract_academic_record(pdf_bytes: bytes, document_type: str) -> dict:
    if document_type not in SUPPORTED:
        raise ValueError(f'Unsupported document type: {document_type}')
    text, methods = pdf_text(pdf_bytes)
    result = extract_class_12(text) if document_type == 'CLASS_12_MARKSHEET' else extract_undergraduate(text)
    result.update(document_type=document_type, extraction_methods=methods,
                  extraction_status='REVIEW_REQUIRED' if result['warnings'] or (result['overall_gpa'] is None and result['percentage'] is None) else 'EXTRACTED')
    return result

if __name__ == '__main__':
    import argparse, json
    p = argparse.ArgumentParser()
    p.add_argument('pdf')
    p.add_argument('--type', required=True, choices=sorted(SUPPORTED))
    args = p.parse_args()
    print(json.dumps(extract_academic_record(Path(args.pdf).read_bytes(), args.type), indent=2))
