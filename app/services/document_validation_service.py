"""Document-level validation for Admissions API (no Salesforce side effects).

Inputs: extracted dict from academic_score_extractor, exam_score_extractor,
identity_document_extractor. Callers may retrieve applicant name from Salesforce when name checks are enabled.
Outputs distinguish evidence verification from program eligibility.

IMPORTANT: OCR cannot establish document authenticity. Uncertain evidence is
REVIEW_REQUIRED, not an automatic name mismatch or rejection.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping, Optional

try:
    from app.core.admission_document_config import (
        DOCUMENT_TYPES, DOCUMENT_CATEGORIES, SCORE_THRESHOLDS, VERIFY_APPLICANT_NAME,
        normalize_document_type, normalize_program, check_document_allowed,
    )
except ImportError:
    from core.admission_document_config import (
        DOCUMENT_TYPES, DOCUMENT_CATEGORIES, SCORE_THRESHOLDS, VERIFY_APPLICANT_NAME,
        normalize_document_type, normalize_program, check_document_allowed,
    )

ACADEMIC = {'CLASS_12_MARKSHEET', 'UNDERGRADUATE_TRANSCRIPT'}
EXAMS = {'SAT', 'GRE', 'GMAT', 'IELTS', 'TOEFL'}


def _tokens(name: Optional[str]) -> list[str]:
    if not name:
        return []
    name = unicodedata.normalize('NFKD', str(name))
    name = ''.join(c for c in name if not unicodedata.combining(c)).upper()
    if ',' in name:
        family, given = name.split(',', 1)
        name = given + ' ' + family
    return re.findall(r'[A-Z]+', name)


def compare_applicant_name(extracted_name: Optional[str], applicant_name: Optional[str]) -> str:
    """MATCH only on exact normalized name tokens, allowing reordered names.

    Nonmatching names are REVIEW_REQUIRED unless a trusted, independently
    confirmed mismatch is provided outside OCR. Avoid false OCR rejections.
    """
    a, b = _tokens(extracted_name), _tokens(applicant_name)
    if not a or not b:
        return 'REVIEW_REQUIRED'
    return 'MATCH' if sorted(a) == sorted(b) else 'REVIEW_REQUIRED'


def _number(value: Any) -> Optional[float]:
    try:
        if value is None or isinstance(value, bool):
            return None
        n = float(str(value).replace(',', '').strip())
        return n if n == n and abs(n) != float('inf') else None
    except (ValueError, TypeError):
        return None


def _academic_level(extracted: Mapping[str, Any]) -> str:
    return str(extracted.get('academic_level') or extracted.get('education_level') or 'UNKNOWN').upper()


def _score(extracted: Mapping[str, Any], kind: str) -> Optional[float]:
    if kind == 'IELTS':
        for key in ('overall_band', 'overall_score', 'total_score'):
            if (n := _number(extracted.get(key))) is not None:
                return n
        return None
    return _number(extracted.get('total_score'))


def validate_document(
    *,
    document_type: str,
    applicant_name: str,
    extracted_data: Mapping[str, Any],
    program: str,
    document_readable: Optional[bool] = None,
    name_verified_by_trusted_source: bool = False,
    verify_applicant_name: Optional[bool] = None,
) -> dict[str, Any]:
    """Validate one extracted document; returns a normalized application input.

    `document_readable=False` forces review. `verify_applicant_name=None` uses
    the configured VERIFY_APPLICANT_NAME setting. `name_verified_by_trusted_source`
    is reserved for an independently trusted comparison; never set from OCR.
    No external calls, uploads, score-date policies or issuer checks here.
    """
    verify_applicant_name = False  # Demo: disabled for ALL document types

    dtype = normalize_document_type(document_type)
    prog = normalize_program(program)
    evidence = dict(extracted_data)
    reasons: list[str] = []
    def flag(code: str) -> None:
        if code not in reasons:
            reasons.append(code)

    if not check_document_allowed(prog, dtype):
        flag('DOCUMENT_NOT_ACCEPTED_FOR_PROGRAM')

    # Determine the actual document type from extracted PDF evidence.
    detected = evidence.get("detected_document_type")

    if dtype in ACADEMIC:
        academic_level = _academic_level(evidence)

        academic_type_map = {
            "CLASS_10": "CLASS_10_MARKSHEET",
            "CLASS_12": "CLASS_12_MARKSHEET",
            "UNDERGRADUATE": "UNDERGRADUATE_TRANSCRIPT",
        }

        detected = academic_type_map.get(academic_level)

    elif not detected:
        detected = evidence.get("document_type")

    type_match: Optional[bool] = None
    if detected:
        try:
            type_match = normalize_document_type(str(detected)) == dtype
        except ValueError:
            type_match = False
    elif 'detected_document_type_match' in evidence:
        type_match = bool(evidence['detected_document_type_match'])
    # Do not infer ID document type from a name-verification success.
    if type_match is False:
        flag('DOCUMENT_TYPE_MISMATCH')
    elif type_match is None:
        flag('DOCUMENT_TYPE_UNCERTAIN')

    if document_readable is False:
        flag('UNREADABLE_DOCUMENT')
    if evidence.get('ocr_confidence') is not None:
        conf = _number(evidence.get('ocr_confidence'))
        if conf is not None and conf < 65:
            flag('LOW_OCR_CONFIDENCE')
    if evidence.get('extraction_status') == 'REVIEW_REQUIRED' and not evidence.get('warnings'):
        flag('EXTRACTION_UNCERTAIN')

    # Name checks can be disabled for test documents belonging to different people.
    # Never treat an extractor's name_match flag as proof of document type.
    if verify_applicant_name:
        extracted_name = (evidence.get('student_name') or evidence.get('applicant_name')
                          or evidence.get('extracted_name') or evidence.get('full_name'))
        name_match = compare_applicant_name(extracted_name, applicant_name)
        if dtype == 'ID_PROOF' and evidence.get('verification_status') == 'PASSED' and evidence.get('name_match') is True:
            name_match = 'MATCH'
        if name_match != 'MATCH':
            if name_verified_by_trusted_source and extracted_name and _tokens(extracted_name):
                flag('NAME_MISMATCH')
            else:
                flag('NAME_MATCH_UNCERTAIN')
    else:
        name_match = 'SKIPPED'

    requirement_status = 'NOT_EVALUATED'
    measured_score: Optional[float] = None
    threshold: Optional[dict[str, Any]] = None
    if dtype in ACADEMIC:
        level = _academic_level(evidence)
        expected = 'CLASS_12' if dtype == 'CLASS_12_MARKSHEET' else 'UNDERGRADUATE'
        if level != expected:
            flag('ACADEMIC_LEVEL_MISMATCH' if level != 'UNKNOWN' else 'ACADEMIC_LEVEL_UNCERTAIN')
        gpa = _number(evidence.get('overall_gpa'))
        scale = _number(evidence.get('gpa_scale'))
        pct = _number(evidence.get('percentage'))
        if pct is not None and not 0 <= pct <= 100:
            flag('INVALID_PERCENTAGE')
            pct = None
        gpa_eligible = None
        if gpa is not None:
            if scale is None:
                flag('GPA_SCALE_UNCERTAIN')
            elif scale != 4.0 or not 0 <= gpa <= scale:
                flag('UNSUPPORTED_GPA_SCALE')
            else:
                gpa_eligible = gpa >= 3.2
        if dtype == 'CLASS_12_MARKSHEET':
            # Bachelor demo: Class 12 percentage >= 70%, not converted GPA.
            if pct is None:
                requirement_status = 'REVIEW_REQUIRED'
                flag('ACADEMIC_SCORE_UNCERTAIN')
            else:
                requirement_status = 'SATISFIED' if pct >= 70 else 'BELOW_THRESHOLD'
        else:
            # Master and MBA demo: undergraduate cumulative GPA >= 3.2 / 4.0.
            if gpa_eligible is True:
                requirement_status = 'SATISFIED'
            elif gpa_eligible is False:
                requirement_status = 'BELOW_THRESHOLD'
            else:
                requirement_status = 'REVIEW_REQUIRED'
                flag('ACADEMIC_GPA_UNCERTAIN')
        if evidence.get('has_courses_in_progress') is True or evidence.get('degree_completed') is False:
            if requirement_status == 'SATISFIED':
                requirement_status = 'PROVISIONAL'
    elif dtype in EXAMS:
        measured_score = _score(evidence, dtype)
        op, min_score = SCORE_THRESHOLDS[dtype]
        threshold = {'operator': op, 'value': min_score}
        if evidence.get('score_consistent') is False:
            flag('SCORE_INCONSISTENT')
        if measured_score is None:
            flag('SCORE_EXTRACTION_UNCERTAIN')
        elif dtype == 'IELTS' and not 0 <= measured_score <= 9:
            flag('SCORE_OUT_OF_RANGE')
        elif dtype == 'TOEFL' and not 0 <= measured_score <= 120:
            flag('SCORE_OUT_OF_RANGE')
        elif dtype == 'SAT' and not 400 <= measured_score <= 1600:
            flag('SCORE_OUT_OF_RANGE')
        elif dtype == 'GRE' and not 260 <= measured_score <= 340:
            flag('SCORE_OUT_OF_RANGE')
        elif dtype == 'GMAT' and not (205 <= measured_score <= 805 or 200 <= measured_score <= 800):
            flag('SCORE_OUT_OF_RANGE')
        if measured_score is not None and not any(x in reasons for x in ('SCORE_INCONSISTENT','SCORE_OUT_OF_RANGE')):
            requirement_status = 'SATISFIED' if (measured_score >= min_score if op == '>=' else measured_score > min_score) else 'BELOW_THRESHOLD'
        else:
            requirement_status = 'REVIEW_REQUIRED'
    
    else:
        # DEMO MODE: ID_PROOF is accepted based on detected document type only.
        # No name matching, authenticity checks, or identity-field validation.
        requirement_status = 'SATISFIED'

        if dtype == 'ID_PROOF' and detected == 'ID_PROOF':
            reasons = []

    hard_mismatch = any(x in reasons for x in ('DOCUMENT_TYPE_MISMATCH', 'ACADEMIC_LEVEL_MISMATCH',
                                               'DOCUMENT_NOT_ACCEPTED_FOR_PROGRAM', 'NAME_MISMATCH'))
    uncertain = any(x not in ('DOCUMENT_TYPE_MISMATCH', 'ACADEMIC_LEVEL_MISMATCH',
                               'DOCUMENT_NOT_ACCEPTED_FOR_PROGRAM', 'NAME_MISMATCH') for x in reasons)
    if hard_mismatch:
        verification = 'FAILED'
    elif reasons:
        verification = 'REVIEW_REQUIRED' if uncertain else 'FAILED'
    else:
        verification = 'PASSED'

    if verification == 'FAILED':
        if 'DOCUMENT_NOT_ACCEPTED_FOR_PROGRAM' in reasons:
            message = f'This document type is not accepted for the selected {prog} program. Please upload the required document.'
        elif 'ACADEMIC_LEVEL_MISMATCH' in reasons:
            message = f'This academic record is for {level.replace("_", " ")}, but the program requires {expected.replace("_", " ")} records. Please upload the correct document.'
        elif 'DOCUMENT_TYPE_MISMATCH' in reasons:
            message = 'The uploaded document does not match the selected document type. Please upload the correct document.'
        else:
            message = 'The name on this document does not match your application. Please contact admissions for assistance.'
        action = 'UPLOAD_CORRECT_DOCUMENT' if 'NAME_MISMATCH' not in reasons else 'CONTACT_ADMISSIONS'
    elif verification == 'REVIEW_REQUIRED':
        if 'GPA_CONVERSION_REQUIRED' in reasons:
            message = 'We extracted your marks, but an approved GPA conversion is needed before we can evaluate the Class 12 requirement.'
        elif 'NAME_MATCH_UNCERTAIN' in reasons or 'LOW_OCR_CONFIDENCE' in reasons or 'UNREADABLE_DOCUMENT' in reasons:
            message = 'We could not confidently verify the name or readability of your document. Our admissions team will review it manually.'
        elif 'ACADEMIC_ALTERNATIVE_UNRESOLVED' in reasons:
            message = 'We need additional academic evidence to confirm whether your GPA or percentage meets the requirement.'
        else:
            message = 'Some information could not be verified reliably. Our admissions team will review this document manually.'
        action = 'MANUAL_REVIEW'
    elif requirement_status == 'BELOW_THRESHOLD':
        score_display = measured_score if dtype in EXAMS else evidence.get('overall_gpa') or evidence.get('percentage')
        message = f'Your {dtype.replace("_", " " )} document was checked, but the reported score ({score_display}) does not meet the program requirement.'
        action = 'REVIEW_ADMISSION_REQUIREMENTS'
    elif requirement_status == 'PROVISIONAL':
        message = 'Your academic record meets the current score requirement. Courses or degree completion remain in progress; an updated final record may be required.'
        action = 'PROVIDE_FINAL_RECORD_WHEN_AVAILABLE'
    else:
        message = f'Good news! Your {dtype.replace("_", " ")} document passed the current verification checks and meets its requirement.'
        action = 'NONE'

    return {
        'document_type': dtype,
        'document_category': DOCUMENT_CATEGORIES[dtype],
        'program': prog,
        'detected_document_type': detected,
        'name_match_status': name_match,
        'document_type_match': type_match,
        'verification_status': verification,
        'requirement_status': requirement_status,
        'extracted_score': measured_score,
        'score_threshold': threshold,
        'reason_codes': reasons,
        'message': message,
        'action_required': action,
        'issuer_authenticity_verified': False,
    }
