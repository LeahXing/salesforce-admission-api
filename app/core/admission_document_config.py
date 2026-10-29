"""Canonical admissions document types and application requirement rules.

No Salesforce or OCR dependencies. Program rules can later be loaded from CRM.
"""
from __future__ import annotations
from typing import Any

# ==========================================
# Document Verification Settings
# ==========================================

# Temporary testing mode:
# False = Skip applicant name matching
# True  = Verify applicant name against the document
VERIFY_APPLICANT_NAME = False

DOCUMENT_TYPES = (
    'ID_PROOF', 'CLASS_12_MARKSHEET', 'UNDERGRADUATE_TRANSCRIPT',
    'SAT', 'GRE', 'GMAT', 'IELTS', 'TOEFL',
)
DOCUMENT_CATEGORIES = {
    'ID_PROOF': 'ID_PROOF',
    'CLASS_12_MARKSHEET': 'ACADEMIC_RECORD',
    'UNDERGRADUATE_TRANSCRIPT': 'ACADEMIC_RECORD',
    'SAT': 'ENTRANCE_EXAM', 'GRE': 'ENTRANCE_EXAM', 'GMAT': 'ENTRANCE_EXAM',
    'IELTS': 'ENGLISH_PROFICIENCY', 'TOEFL': 'ENGLISH_PROFICIENCY',
}
ALIASES = {
    '12TH MARKSHEET': 'CLASS_12_MARKSHEET',
    'HIGH SCHOOL TRANSCRIPT': 'CLASS_12_MARKSHEET',
    'UNDERGRADUATE MARKSHEET': 'UNDERGRADUATE_TRANSCRIPT',
    'ACADEMIC TRANSCRIPT': 'UNDERGRADUATE_TRANSCRIPT',
    'PASSPORT': 'ID_PROOF',
}
PROGRAM_RULES = {
    'BACHELOR': {
        'ID_PROOF': ('ID_PROOF',),
        'ACADEMIC_RECORD': ('CLASS_12_MARKSHEET',),
        'ENTRANCE_EXAM': ('SAT',),
        'ENGLISH_PROFICIENCY': ('IELTS', 'TOEFL'),
    },
    'MASTER': {
        'ID_PROOF': ('ID_PROOF',),
        'ACADEMIC_RECORD': ('UNDERGRADUATE_TRANSCRIPT',),
        'ENTRANCE_EXAM': ('GRE',),
        'ENGLISH_PROFICIENCY': ('IELTS', 'TOEFL'),
    },
    'MBA': {
        'ID_PROOF': ('ID_PROOF',),
        'ACADEMIC_RECORD': ('UNDERGRADUATE_TRANSCRIPT',),
        'ENTRANCE_EXAM': ('GMAT',),
        'ENGLISH_PROFICIENCY': ('IELTS', 'TOEFL'),
    },
}
SCORE_THRESHOLDS = {
    'SAT': ('>', 1100), 'GRE': ('>', 290), 'GMAT': ('>', 600),
    'IELTS': ('>=', 6.5), 'TOEFL': ('>', 72),
}

def normalize_document_type(value: str) -> str:
    key = (value or '').strip().upper().replace('-', '_').replace(' ', '_')
    canonical = ALIASES.get(key.replace('_', ' '), key)
    if canonical not in DOCUMENT_TYPES:
        raise ValueError(f'Unsupported document_type: {value!r}. Allowed: {", ".join(DOCUMENT_TYPES)}')
    return canonical

def normalize_program(value: str) -> str:
    key = (value or '').strip().upper()
    key = {'BACHELORS': 'BACHELOR', 'BACHELOR\'S': 'BACHELOR', 'BTECH': 'BACHELOR',
           'B.TECH': 'BACHELOR', 'MASTERS': 'MASTER', 'MASTER\'S': 'MASTER'}.get(key, key)
    if key not in PROGRAM_RULES:
        raise ValueError(f'Unsupported program: {value!r}')
    return key

def required_documents(program: str) -> dict[str, list[str]]:
    return {category: list(types) for category, types in PROGRAM_RULES[normalize_program(program)].items()}

def check_document_allowed(program: str, document_type: str) -> bool:
    canonical = normalize_document_type(document_type)
    return canonical in PROGRAM_RULES[normalize_program(program)][DOCUMENT_CATEGORIES[canonical]]

def score_meets_requirement(document_type: str, score: float) -> bool:
    operator, threshold = SCORE_THRESHOLDS[normalize_document_type(document_type)]
    return score >= threshold if operator == '>=' else score > threshold

def evaluate_application(program: str, document_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate normalized document results; never infer success from mere upload.

    Each result: document_type, verification_status, requirement_status.
    requirement_status: SATISFIED, PROVISIONAL, BELOW_THRESHOLD, REVIEW_REQUIRED.
    A single accepted alternative satisfies each category (IELTS OR TOEFL).
    """
    rules = required_documents(program)
    summary = []
    for category, accepted in rules.items():
        matches = [r for r in document_results if r.get('document_type') in accepted]
        statuses = []
        for r in matches:
            verification = r.get('verification_status')
            requirement = r.get('requirement_status')
            if verification == 'PASSED' and requirement == 'SATISFIED':
                statuses.append('SATISFIED')
            elif verification in ('PASSED', 'PROVISIONAL') and requirement == 'PROVISIONAL':
                statuses.append('PROVISIONAL')
            elif verification == 'PASSED' and requirement == 'BELOW_THRESHOLD':
                statuses.append('BELOW_THRESHOLD')
            else:
                statuses.append('REVIEW_REQUIRED')
        if 'SATISFIED' in statuses:
            status = 'SATISFIED'
        elif 'PROVISIONAL' in statuses:
            status = 'PROVISIONAL'
        elif 'REVIEW_REQUIRED' in statuses:
            status = 'REVIEW_REQUIRED'
        elif 'BELOW_THRESHOLD' in statuses:
            status = 'BELOW_THRESHOLD'
        else:
            status = 'MISSING'
        summary.append({'category': category, 'accepted_document_types': accepted, 'status': status})
    states = {x['status'] for x in summary}
    if 'BELOW_THRESHOLD' in states:
        overall = 'NOT_ELIGIBLE'
    elif 'REVIEW_REQUIRED' in states:
        overall = 'REVIEW_REQUIRED'
    elif 'MISSING' in states:
        overall = 'INCOMPLETE'
    elif 'PROVISIONAL' in states:
        overall = 'PROVISIONALLY_ELIGIBLE'
    else:
        overall = 'ELIGIBLE'
    return {'program': normalize_program(program), 'eligibility_status': overall, 'requirements': summary}
