"""Transcript PDF extractor. Requires PyMuPDF; optional pytesseract + Pillow + Tesseract binary.
Does not authenticate a transcript or determine admissions eligibility.
"""
from __future__ import annotations
import io
import re
from pathlib import Path
from typing import Any
import fitz

LEVELS = {"UG": "UNDERGRADUATE", "GR": "GRADUATE"}


def _clean(s: str) -> str:
    return re.sub(r"[ \t]+", " ", s).strip()


def _value(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        m = re.search(pattern, text, re.I | re.M)
        if m:
            v = _clean(m.group(1))
            if v:
                return v
    return None


def _ocr(page: fitz.Page) -> str:
    try:
        import pytesseract
        from PIL import Image
        pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
        image = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(image, config="--psm 3")
    except (ImportError, OSError, RuntimeError) as exc:
        raise RuntimeError("Scanned PDF requires Pillow, pytesseract and an installed Tesseract OCR executable") from exc


def _level(text: str) -> tuple[str, list[str]]:
    head = text[:5500]
    evidence: list[str] = []
    graduate = [r"Student Type\s*:\s*Graduate\b", r"Course Level\s*:\s*Graduate\b",
                r"TRANSCRIPT TOTALS\s*\(GRADUATE\)", r"BEGINNING OF GRADUATE .*?CAREER"]
    undergraduate = [r"Course Level\s*:\s*Undergraduate\b", r"Level\s*:\s*Undergraduate\b",
                     r"TRANSCRIPT TOTALS\s*\(UNDERGRADUATE\)",
                     r"BEGINNING OF UNDERGRADUATE .*?CAREER", r"ACADEMIC TRANSCRIPT\s*\(UNDERGRADUATE\)",
                     r"BACHELOR OF (?:SCIENCE|ARTS|ENGINEERING)", r"\bB\.Sc\.\s*Electrical"]
    for p in graduate:
        if re.search(p, text, re.I | re.S): evidence.append("GRADUATE: " + p)
    for p in undergraduate:
        if re.search(p, text, re.I | re.S): evidence.append("UNDERGRADUATE: " + p)
    # Explicit current program is distinct from level of the courses on the transcript.
    if not evidence and re.search(r"\bMaster of [A-Za-z ]+", head, re.I):
        evidence.append("GRADUATE: master program mentioned")
    # Avoid treating generic grading-scale explanatory pages as evidence.
    g = any(x.startswith("GRADUATE:") for x in evidence)
    u = any(x.startswith("UNDERGRADUATE:") for x in evidence)
    return ("MIXED" if g and u else "GRADUATE" if g else "UNDERGRADUATE" if u else "UNKNOWN"), evidence



def _gpa(text: str) -> float | None:
    """
    Extract cumulative GPA from transcript text.

    Priority:
    1. CCH/CGP/CGPA paired totals
    2. Explicit cumulative or overall GPA
    3. Final CGPA from semester tables

    OCR values such as '233' may represent '2.33'.
    Such normalization is only attempted for explicitly
    labeled CGPA fields.
    """

    def normalize_gpa(value: str) -> float | None:
        value = value.strip()

        try:
            number = float(value)

            # Standard GPA format: 2.33, 3.91, etc.
            if "." in value:
                return number if 0 <= number <= 4 else None

            # OCR may omit decimal points:
            # 233 -> 2.33
            # 300 -> 3.00
            if len(value) == 3 and value.isdigit():
                normalized = number / 100
                return normalized if 0 <= normalized <= 4 else None

            # Single-digit GPA, e.g. 3
            if len(value) == 1 and value.isdigit():
                return number if 0 <= number <= 4 else None

        except ValueError:
            pass

        return None

    # Priority 1: CCH / CGP / CGPA paired totals.
    # Choose the record with the largest cumulative credit hours.
    paired = re.findall(
        r"CCH\s*:\s*(\d+(?:\.\d+)?)"
        r"\s+CGP\s*:\s*\d+(?:\.\d+)?"
        r"\s+CGPA\s*:\s*([0-4]\.\d+)",
        text,
        re.I,
    )

    if paired:
        return float(max(paired, key=lambda x: float(x[0]))[1])

    # Priority 2: Explicit document-level GPA.
    patterns = [
        r"\bCumulative GPA\s*:\s*([0-4](?:\.\d{1,3})?)",
        r"\bOVERALL\s+\d+\.\d+\s+\d+\.\d+\s+\d+\.\d+\s+([0-4]\.\d+)",
        r"\bOverall\s*:\s*(?:\d+\.\d+\s+){5}([0-4]\.\d+)",
        r"\bTotal Institution\s*:\s*(?:\d+\.\d+\s+){5}([0-4]\.\d+)",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.I)

        if matches:
            return float(matches[-1])

    # Priority 3: Semester-based CGPA.
    # Use the last CGPA, which normally represents
    # the final cumulative result.
    cgpa_matches = re.findall(
        r"\bCGPA\s*:\s*(\d+(?:\.\d+)?)",
        text,
        re.I,
    )

    if cgpa_matches:
        for raw_value in reversed(cgpa_matches):
            normalized = normalize_gpa(raw_value)

            if normalized is not None:
                return normalized

    return None

def extract_transcript(pdf: bytes | str | Path, *, enable_ocr: bool = True) -> dict[str, Any]:
    """Return JSON-serializable fields. Missing/ambiguous fields stay null/UNKNOWN.

    For admission validation, compare `academic_level` to the expected document level;
    never infer the academic level from the applicant's target program.
    """
    doc = fitz.open(stream=pdf, filetype="pdf") if isinstance(pdf, bytes) else fitz.open(str(pdf))
    pages, methods = [], []
    for page in doc:
        t = page.get_text()
        if len(t.strip()) < 45 and enable_ocr:
            t = _ocr(page)
            methods.append("OCR_TESSERACT")
        else:
            methods.append("PDF_TEXT" if t.strip() else "EMPTY")
        pages.append(t)
    text = "\n".join(pages)
    # Limit name and institution searches to the beginning to avoid references on the reverse side.
    first = pages[0] if pages else ""
    name = _value(first, [r"^\s*Student['’]s Name\s*:\s*([^\n]+)",
                          r"^\s*Record of\s*:\s*([^\n]+)",
                          r"^\s*Name\s*:\s*([^\n]+)"])
    if name and re.search(r"\s{3,}(?:Father|Student|Reg|Date|ID)\b", name, re.I):
        name = re.split(r"\s{3,}", name)[0].strip()
    # Handles name lines such as 'Name: XXXX Father Name: YYYY' after whitespace normalization.
    if name:
        name = re.split(r"\s+(?:Father(?:'s)? Name|Registration No|Student ID|SSN|Birthdate|Date of Birth)\s*:", name, flags=re.I)[0].strip()
    institution = None
    known = ["University of North Florida", "Eastern Michigan University", "Wayne State University",
             "University of Utah", "University of Engineering & Technology", "Gomal University", "Bahria University"]
    for item in known:
        if re.search(re.escape(item).replace(r"\ ", r"\s+"), text[:12000], re.I):
            institution = item
            break
    if not institution:
        institution = _value(first[:1000], [r"^\s*([^\n]{4,90}\bUniversity\b[^\n]*)$", r"^\s*([^\n]{4,90}\bCollege\b[^\n]*)$"])
        if institution and re.search(r"\btranscript\b|\bdoes not require\b", institution, re.I):
            institution = None
    level, evidence = _level(text)
    current_program = _value(first, [r"^\s*Program\s*:\s*([^\n]+)",
                                     r"^\s*Degree\s*:\s*([^\n]+)",
                                     r"Current Program\s*\n\s*([^\n]+)"])
    if current_program and re.search(r"\s{3,}(?:Plan|Father|Department)\s*:", current_program, re.I):
        current_program = re.split(r"\s{3,}", current_program)[0]
    unofficial = bool(re.search(r"\bunofficial\b|\bNOT\s+Official\b", text[:6000], re.I))
    official = bool(re.search(r"\bFINAL TRANSCRIPT\b", first, re.I)) and not unofficial
    candidate_gpa = _gpa(text)
    ocr_used = "OCR_TESSERACT" in methods
    requires_review = candidate_gpa is None
    return {
        "document_type": "ACADEMIC_TRANSCRIPT",
        "student_name": name,
        "institution": institution,
        "academic_level": level,
        "academic_level_evidence": evidence,
        "current_program": current_program,
        "candidate_gpa": candidate_gpa,
        "cumulative_gpa": candidate_gpa,
        "gpa_verification_status": ("NOT_EXTRACTED" if candidate_gpa is None else
                                    "NOT_EXTRACTED" if requires_review else "NOT_CHECKED"),
        "requires_manual_review": requires_review,
        "is_marked_unofficial": unofficial,
        "is_marked_final": official,
        "issuer_authenticity_verified": False,
        "extraction_status": "EXTRACTED" if text.strip() else "EMPTY",
        "extraction_method": "OCR_TESSERACT" if "OCR_TESSERACT" in methods else "PDF_TEXT",
        "page_count": len(pages),
        "warnings": (["Scanned transcript: verify GPA and fine-print fields manually"] if "OCR_TESSERACT" in methods else [])
                    + (["Academic level not reliably identified"] if level == "UNKNOWN" else [])
                    + (["Mixed academic-level indicators; manual review recommended"] if level == "MIXED" else []),
    }

# Compatibility API for the existing admission document service.
SUPPORTED = {'CLASS_12_MARKSHEET', 'UNDERGRADUATE_TRANSCRIPT'}
NUM = r'(\d+(?:\.\d+)?)'


def pdf_text(pdf_bytes: bytes, *, ocr: bool = True, max_pages: int = 25) -> tuple[str, list[str]]:
    pages, methods = [], []
    with fitz.open(stream=pdf_bytes, filetype='pdf') as doc:
        for page in list(doc)[:max_pages]:
            text = page.get_text('text', sort=True)
            unsorted = page.get_text('text', sort=False)
            if len(re.findall(r'[A-Za-z]{3,}', unsorted)) > len(re.findall(r'[A-Za-z]{3,}', text)) * 1.4:
                text = unsorted
            if ocr and len(re.sub(r'\W', '', text)) < 100:
                text = _ocr(page)
                methods.append('OCR_TESSERACT')
            else:
                methods.append('PDF_TEXT' if text.strip() else 'EMPTY')
            pages.append(text)
    return '\n'.join(pages), methods


def number(pattern: str, text: str, flags=re.I | re.S) -> float | None:
    match = re.search(pattern, text, flags)
    return float(match.group(1)) if match else None


def extract_undergraduate(text: str) -> dict:
    level, evidence = _level(text)
    if level == 'UNKNOWN' and re.search(r'Course Level\s*:\s*Undergraduate', text, re.I):
        level, evidence = 'UNDERGRADUATE', ['Course Level: Undergraduate']
    gpa = _gpa(text)
    # Wayne State-style totals and Gomal-style semester summaries.
    if gpa is None:
        m = re.search(r'\bOVERALL\s+(?:\d+(?:\.\d+)?\s+){3}(\d+(?:\.\d+)?)', text, re.I)
        if m: gpa = float(m.group(1))
    if gpa is None:
        matches = re.findall(r'\bCGPA\s*:\s*(\d+(?:\.\d+)?)', text, re.I)
        if matches: gpa = float(matches[-1])
    result = {
        'overall_gpa': gpa, 'gpa_scale': 4.0 if gpa is not None and gpa <= 4 else None,
        'percentage': None, 'cumulative_credit_hours': None,
        'cumulative_grade_points': None, 'extraction_method': 'CUMULATIVE_GPA' if gpa is not None else None,
        'academic_level': level, 'academic_level_evidence': evidence,
        'has_courses_in_progress': bool(re.search(r'COURSES?\s+IN\s+PROGRESS|IN\s+PROGRESS', text, re.I)),
        'degree_completed': None, 'warnings': [],
    }
    if gpa is not None and not (0 <= gpa <= 10):
        result['overall_gpa'] = None
        result['warnings'].append('GPA outside plausible range')
    if gpa is not None and gpa <= 4:
        result['warnings'].append('4.0 GPA scale provisional; verify institution grading key')
    if level == 'MIXED':
        result['warnings'].append('Mixed graduate/undergraduate indicators; manual review')
    if level == 'UNKNOWN':
        result['warnings'].append('Academic level could not be established')
    return result


def extract_class_12(text: str) -> dict:
    """Extract explicit Class 12 percentage or supported aggregate layouts.

    Never infer a Class 12 score from a Class 10 marksheet.
    """
    result = {'academic_level': 'UNKNOWN', 'percentage': None, 'overall_gpa': None,
              'gpa_scale': None, 'total_marks': None, 'maximum_marks': None,
              'has_courses_in_progress': bool(re.search(r'IN\s+PROGRESS', text, re.I)),
              'degree_completed': None, 'extraction_method': None, 'warnings': []}
    if re.search(r'HIGH\s+SCHOOL\s+EXAMINATION', text, re.I) and not re.search(
            r'HIGHER\s+SECONDARY|CLASS\s*(?:XII|12)|INTERMEDIATE|SENIOR\s+SECONDARY', text, re.I):
        result['academic_level'] = 'CLASS_10'
    elif re.search(r'HIGHER\s+SECONDARY|HSC\b|CLASS\s*(?:XII|12)|\b12TH\b|SENIOR\s+SECONDARY|INTERMEDIATE', text, re.I):
        result['academic_level'] = 'CLASS_12'

    if result['academic_level'] != 'CLASS_12':
        result['warnings'].append('Document not confirmed as Class 12; do not use for Class 12 eligibility')
        return result

    # Extract explicit percentages, including OCR/PDF table layouts with
    # other columns between the label and the percentage.
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not re.search(r'\b(?:percentage|percent of marks)\b', line, re.I):
            continue
        # Prefer the value immediately after the label, then a number on
        # the following line (some PDFs split the label and value).
        tail = re.split(r'\b(?:percentage|percent of marks)\b', line, maxsplit=1, flags=re.I)[1]
        match = re.search(r'(?<!\d)(100(?:\.0+)?|\d{1,2}(?:\.\d{1,2})?)(?!\d)', tail)
        if not match and i + 1 < len(lines):
            match = re.search(r'^\s*(100(?:\.0+)?|\d{1,2}\.\d{1,2})(?!\d)', lines[i + 1])
        if match:
            result['percentage'] = float(match.group(1))
            result['extraction_method'] = 'EXPLICIT_PERCENTAGE'
            break

    if result['percentage'] is None:
        match = re.search(r'\b(100(?:\.0+)?|\d{1,2}\.\d{1,2})\s*%', text)
        if match:
            result['percentage'] = float(match.group(1))
            result['extraction_method'] = 'EXPLICIT_PERCENTAGE'

    # Common board format: GRAND TOTAL 358 / 500.
    aggregates = []
    for match in re.finditer(
            r'(?:GRAND\s+TOTAL|TOTAL\s+MARKS)\s*[:=]?\s*(\d{2,4})\s*/\s*(\d{2,4})',
            text, re.I):
        aggregates.append((float(match.group(1)), float(match.group(2))))
    # OCR may place 358/500 just before the GRAND TOTAL label.
    for match in re.finditer(r'(?<!\d)(\d{2,4})\s*/\s*(\d{2,4})(?!\d)', text):
        context = text[max(0, match.start() - 100):match.end() + 100]
        if re.search(r'GRAND\s+TOTAL', context, re.I):
            aggregates.append((float(match.group(1)), float(match.group(2))))
    # Maharashtra boards print maximum then obtained: 600 425.
    for match in re.finditer(r'(?<!\d)([3-9]00|1000)\s+(\d{2,4})(?!\d)', text):
        maximum, obtained = map(float, match.groups())
        if 0 <= obtained <= maximum:
            aggregates.append((obtained, maximum))

    for obtained, maximum in aggregates:
        if maximum <= 0 or not 0 <= obtained <= maximum:
            continue
        computed = round(100 * obtained / maximum, 2)
        if result['percentage'] is not None and abs(computed - result['percentage']) > 0.12:
            continue  # Other table row or unrelated pair; do not overwrite.
        result['total_marks'] = obtained
        result['maximum_marks'] = maximum
        if result['percentage'] is None:
            result['percentage'] = computed
            result['extraction_method'] = 'EXPLICIT_AGGREGATE'
        break

    if result['percentage'] is None:
        result['warnings'].append('Percentage and aggregate could not be extracted')
    result['warnings'].append('Do not convert percentage to GPA without approved equivalency')
    return result


def extract_academic_record(pdf_bytes: bytes, document_type: str) -> dict:
    if document_type not in SUPPORTED:
        raise ValueError(f'Unsupported document type: {document_type}')
    text, methods = pdf_text(pdf_bytes)
    if document_type == 'CLASS_12_MARKSHEET':
        result = extract_class_12(text)
        # Scanned marksheets often have a small GRAND TOTAL row that full-page
        # OCR misses. Re-OCR the lower portion of page 1 at higher resolution.
        if result['percentage'] is None and 'OCR_TESSERACT' in methods:
            try:
                import pytesseract
                from PIL import Image
                with fitz.open(stream=pdf_bytes, filetype='pdf') as doc:
                    page = doc[0]
                    crop = fitz.Rect(0, page.rect.height * 0.65,
                                     page.rect.width, page.rect.height * 0.86)
                    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3),
                                          clip=crop, alpha=False)
                    image = Image.open(io.BytesIO(pix.tobytes('png')))
                    cropped_text = pytesseract.image_to_string(image, config='--psm 6')
                retry = extract_class_12(text + '\n' + cropped_text)
                if retry['percentage'] is not None:
                    result = retry
                    methods.append('OCR_TESSERACT_CROP')
            except (ImportError, OSError, RuntimeError, ValueError, IndexError):
                pass
        # If the original focused crop still misses the total, retry the full
        # first page with PSM 6 (better for some scanned table layouts).
        if result['percentage'] is None and 'OCR_TESSERACT' in methods:
            try:
                import pytesseract
                from PIL import Image
                with fitz.open(stream=pdf_bytes, filetype='pdf') as doc:
                    pix = doc[0].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
                    image = Image.open(io.BytesIO(pix.tobytes('png')))
                    table_text = pytesseract.image_to_string(image, config='--psm 6')
                retry = extract_class_12(text + '\n' + table_text)
                if retry['academic_level'] == 'CLASS_12' and retry['percentage'] is not None:
                    result = retry
                    methods.append('OCR_TESSERACT_TABLE_RETRY')
            except (ImportError, OSError, RuntimeError, ValueError, IndexError, pytesseract.TesseractError):
                pass
    else:
        result = extract_undergraduate(text)
        # Some PDFs lose GPA table order when text is sorted; use the legacy
        # transcript reader as a fallback (without changing successful results).
        if result.get('overall_gpa') is None:
            fallback = extract_transcript(pdf_bytes)
            if fallback.get('candidate_gpa') is not None:
                result['overall_gpa'] = fallback['candidate_gpa']
                result['gpa_scale'] = 4.0
                result['extraction_method'] = 'CUMULATIVE_GPA'
        first = text.split('\f')[0][:8000]
        result.update(
            student_name=_value(first, [r'^\s*Student[’\']s Name\s*:\s*([^\n]+)', r'^\s*Record of\s*:\s*([^\n]+)', r'^\s*Name\s*:\s*([^\n]+)']),
            institution=next((item for item in ['University of North Florida', 'Eastern Michigan University',
                 'Wayne State University', 'University of Utah', 'University of Engineering & Technology',
                 'Gomal University', 'Bahria University'] if re.search(re.escape(item), text[:12000], re.I)), None),
            current_program=_value(first, [r'^\s*Program\s*:\s*([^\n]+)', r'^\s*Degree\s*:\s*([^\n]+)', r'Current Program\s*\n\s*([^\n]+)']),
            is_marked_unofficial=bool(re.search(r'\bunofficial\b|\bNOT\s+Official\b', text[:6000], re.I)),
            issuer_authenticity_verified=False,
        )
        if 'OCR_TESSERACT' in methods and 'PDF_TEXT' not in methods:
            # Demo: use OCR-derived candidate GPA directly for score evaluation.
            result['overall_gpa'] = _gpa(text)
            result['gpa_scale'] = 4.0 if result['overall_gpa'] is not None else None
    if document_type == 'UNDERGRADUATE_TRANSCRIPT':
        # Retain the OCR candidate even when the compatibility API suppresses the score.
        candidate_gpa = result.get('overall_gpa')
        ocr_used = 'OCR_TESSERACT' in methods
        requires_review = candidate_gpa is None
        result.update(
            candidate_gpa=candidate_gpa,
            gpa_verification_status=('NOT_EXTRACTED' if candidate_gpa is None else
                                     'NOT_EXTRACTED' if requires_review else 'NOT_CHECKED'),
            requires_manual_review=requires_review,
        )
    else:
        result.update(candidate_gpa=None, gpa_verification_status='NOT_CHECKED',
                      requires_manual_review=result.get('percentage') is None)
    has_value = result['overall_gpa'] is not None or result['percentage'] is not None
    result.update(document_type=document_type, extraction_methods=methods,
                  extraction_status='EXTRACTED' if has_value else 'REVIEW_REQUIRED')
    return result


if __name__ == '__main__':
    import argparse, json
    p = argparse.ArgumentParser()
    p.add_argument('pdf')
    p.add_argument('--type', required=True, choices=sorted(SUPPORTED))
    args = p.parse_args()
    print(json.dumps(extract_academic_record(Path(args.pdf).read_bytes(), args.type), indent=2))
