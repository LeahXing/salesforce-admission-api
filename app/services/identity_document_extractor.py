"""Passport OCR for Admission Agent. MRZ checks verify transcription, not authenticity."""
from __future__ import annotations
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Optional
import cv2
import fitz
import numpy as np
import pytesseract
from app.core.admission_document_config import VERIFY_APPLICANT_NAME


def normalize_name(value: str) -> str:
    value = unicodedata.normalize('NFKD', value or '').upper()
    return ' '.join(re.sub(r'[^A-Z ]', ' ', value).split())


def compare_names(extracted: str, expected: str) -> str:
    a, b = sorted(normalize_name(extracted).split()), sorted(normalize_name(expected).split())
    if not a or not b: return 'UNCERTAIN'
    if a == b: return 'MATCH'
    if set(a).issubset(set(b)) or set(b).issubset(set(a)): return 'UNCERTAIN'
    return 'MISMATCH'


def _check(data: str, digit: str) -> bool:
    vals = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    total = 0
    for i, c in enumerate(data):
        n = 0 if c == '<' else vals.find(c)
        if n < 0: return False
        total += n * (7, 3, 1)[i % 3]
    return digit.isdigit() and total % 10 == int(digit)


def _date_yyMMdd(raw: str, *, expiry: bool = False) -> Optional[str]:
    if not re.fullmatch(r'\d{6}', raw): return None
    yy, mm, dd = int(raw[:2]), int(raw[2:4]), int(raw[4:])
    today = date.today()
    # Expiry year: select a plausible date near present (old and new samples).
    years = [1900 + yy, 2000 + yy, 2100 + yy]
    if expiry:
        years = [y for y in years if today.year - 20 <= y <= today.year + 30]
    else:
        years = [y for y in years if today.year - 110 <= y <= today.year]
    for y in sorted(years, key=lambda y: abs(y - (today.year + (5 if expiry else -30)))):
        try: return date(y, mm, dd).isoformat()
        except ValueError: pass
    return None


def _parse_mrz(line1: str, line2: str) -> Optional[dict]:
    # ICAO TD3 passport MRZ: exactly two lines, 44 characters each.
    a = re.sub(r'\s+', '', line1.upper())
    b = re.sub(r'\s+', '', line2.upper())
    if len(a) != 44 or len(b) != 44 or not re.fullmatch(r'P<[A-Z<]{42}', a):
        return None
    if not re.fullmatch(r'[A-Z0-9<]{44}', b): return None
    if not re.fullmatch(r'[A-Z]{3}', a[2:5]): return None
    if '<<' not in a[5:]: return None
    surname, given = a[5:].split('<<', 1)
    name = normalize_name(given.replace('<', ' ') + ' ' + surname.replace('<', ' '))
    if len(name.split()) < 2: return None
    # Check digits on passport number, birth, expiry, and composite field.
    checks = {
        'passport_number': _check(b[:9], b[9]),
        'birth_date': _check(b[13:19], b[19]),
        'expiry_date': _check(b[21:27], b[27]),
        'composite': _check(b[:10] + b[13:20] + b[21:43], b[43]),
    }
    dob = _date_yyMMdd(b[13:19])
    expiry = _date_yyMMdd(b[21:27], expiry=True)
    if not dob or not expiry: return None
    return {'name': name, 'passport_number': b[:9].rstrip('<'),
            'nationality': b[10:13], 'date_of_birth': dob,
            'expiry_date': expiry, 'sex': b[20], 'checks': checks,
            'mrz_valid': all(checks.values()), 'mrz_line_1': a, 'mrz_line_2': b}


def _mrz_lines(text: str) -> list[str]:
    # Normalize OCR's spaces, but never silently alter check-digit characters.
    lines = [re.sub(r'\s+', '', x.upper()) for x in text.splitlines()]
    # Some PDF text layers drop the '<' in the P< passport-type prefix.
    # Only correct this prefix; full MRZ check digits must still validate.
    lines = [('P<' + x[2:] if x.startswith('PK') and len(x) == 44 else x) for x in lines]
    return [x for x in lines if 35 <= len(x) <= 46 and re.fullmatch(r'[A-Z0-9<]+', x)]


def _find_mrz(text: str) -> list[dict]:
    lines = _mrz_lines(text)
    found = []
    for i, a in enumerate(lines):
        if not a.startswith('P<'): continue
        for b in lines[i+1:i+4]:
            result = _parse_mrz(a, b)
            if result: found.append(result)
    return found


def _ocr(img: np.ndarray, *, mrz: bool = False) -> str:
    config = ('--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<' if mrz else '--psm 11')
    return pytesseract.image_to_string(img, config=config)


def _page_images(page: fitz.Page):
    pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
    arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4: arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)
    if pix.n == 1: arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
    yield arr
    # A passport scan may be upside down or sideways.
    yield cv2.rotate(arr, cv2.ROTATE_180)
    yield cv2.rotate(arr, cv2.ROTATE_90_CLOCKWISE)
    yield cv2.rotate(arr, cv2.ROTATE_90_COUNTERCLOCKWISE)


def extract_identity_document(pdf_bytes: bytes, applicant_name: Optional[str] = None) -> dict:
    name_enabled = bool(VERIFY_APPLICANT_NAME)
    if name_enabled and not normalize_name(applicant_name or ''):
        raise ValueError('Salesforce applicant name is required when name verification is enabled')
    observations, warnings, mrz_results = [], [], []
    try:
        with fitz.open(stream=pdf_bytes, filetype='pdf') as doc:
            for page in list(doc)[:3]:
                embedded = page.get_text('text', sort=True)
                observations.append(embedded)
                mrz_results.extend(_find_mrz(embedded))
                # If embedded text already provides a checksum-valid MRZ, no OCR is necessary.
                if any(r['mrz_valid'] for r in mrz_results): continue
                for img in _page_images(page):
                    try:
                        full = _ocr(img)
                        observations.append(full)
                        mrz_results.extend(_find_mrz(full))
                        if any(r['mrz_valid'] for r in mrz_results): break
                        # MRZ typically occupies the bottom of the identity page.
                        for start in (0.72, 0.82):
                            strip = img[int(img.shape[0] * start):]
                            gray = cv2.cvtColor(strip, cv2.COLOR_RGB2GRAY)
                            gray = cv2.resize(gray, None, fx=1.5, fy=1.5)
                            for thresholded in (gray, cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]):
                                mrz_results.extend(_find_mrz(_ocr(thresholded, mrz=True)))
                                if any(r['mrz_valid'] for r in mrz_results): break
                            if any(r['mrz_valid'] for r in mrz_results): break
                    except (pytesseract.TesseractError, RuntimeError, OSError) as exc:
                        warnings.append(f'OCR unavailable: {type(exc).__name__}')
                    if any(r['mrz_valid'] for r in mrz_results): break
    except (fitz.FileDataError, ValueError, RuntimeError) as exc:
        warnings.append(f'Unable to read PDF: {type(exc).__name__}')

    valid = next((r for r in mrz_results if r['mrz_valid']), None)
    best = valid or (mrz_results[0] if mrz_results else None)
    name_status = 'SKIPPED' if not name_enabled else ('MATCH' if valid and compare_names(valid['name'], applicant_name or '') == 'MATCH' else 'REVIEW_REQUIRED')
    if not valid: warnings.append('No checksum-valid TD3 passport MRZ could be extracted')
    if name_enabled and name_status != 'MATCH': warnings.append('Applicant name requires manual verification')
    # Never automatically pass an expired passport.
    not_expired = bool(valid and valid['expiry_date'] >= date.today().isoformat())
    if valid and not not_expired: warnings.append('Passport is expired')
    passed = bool(valid and not_expired and (not name_enabled or name_status == 'MATCH'))
    return {
        'document_type': 'ID_PROOF',
        'detected_document_type': 'ID_PROOF' if best else None,
        'detected_document_type_match': True if best else None,
        'extraction_status': 'EXTRACTED' if passed else 'REVIEW_REQUIRED',
        'verification_status': 'PASSED' if passed else 'REVIEW_REQUIRED',
        'reason_code': 'PASSPORT_MRZ_VALIDATED' if valid else 'DOCUMENT_TYPE_UNCERTAIN',
        'warnings': list(dict.fromkeys(warnings)),
        'name_match': True if name_status == 'MATCH' else None,
        'name_match_status': name_status,
        'passport_mrz_detected': bool(best),
        'passport_mrz_checksum_valid': bool(valid),
        'passport_visual_markers_detected': bool(re.search(r'PASSPORT|REPUBLIC OF|NATIONALITY', '\n'.join(observations), re.I)),
        'passport_number': best['passport_number'] if best else None,
        'student_name': best['name'] if best else None,
        'nationality': best['nationality'] if best else None,
        'date_of_birth': best['date_of_birth'] if best else None,
        'expiry_date': best['expiry_date'] if best else None,
        'mrz_check_results': best['checks'] if best else None,
        'issuer_authenticity_verified': False,
    }


def verify_passport_name(pdf_bytes: bytes, applicant_name: Optional[str] = None) -> dict:
    result = extract_identity_document(pdf_bytes, applicant_name)
    return {**result, 'message': ('Passport MRZ validated; issuer authenticity not verified.' if result['verification_status'] == 'PASSED' else 'Passport requires manual review.'),
            'action_required': 'NONE' if result['verification_status'] == 'PASSED' else 'MANUAL_REVIEW'}


if __name__ == '__main__':
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf')
    parser.add_argument('--applicant-name')
    args = parser.parse_args()
    print(json.dumps(verify_passport_name(Path(args.pdf).read_bytes(), args.applicant_name), indent=2))
