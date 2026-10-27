"""Application-level admission eligibility aggregation.

Consumes document_validation_service.validate_document() results; does not
perform OCR, contact Salesforce, decide admission, or issue an offer.
Only current, application-scoped evidence should be supplied by the caller.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

try:
    from app.core.admission_document_config import (
        DOCUMENT_CATEGORIES, normalize_document_type, normalize_program,
        required_documents,
    )
except ImportError:
    from core.admission_document_config import (
        DOCUMENT_CATEGORIES, normalize_document_type, normalize_program,
        required_documents,
    )

CATEGORIES = ('ID_PROOF', 'ACADEMIC_RECORD', 'ENTRANCE_EXAM', 'ENGLISH_PROFICIENCY')
VERIFICATIONS = {'PASSED', 'FAILED', 'REVIEW_REQUIRED', 'PROVISIONAL'}
REQUIREMENTS = {'SATISFIED', 'PROVISIONAL', 'BELOW_THRESHOLD', 'REVIEW_REQUIRED', 'NOT_EVALUATED'}


def _classify(record: Mapping[str, Any]) -> str:
    """An upload alone never satisfies a requirement."""
    verification = str(record.get('verification_status') or '').upper()
    requirement = str(record.get('requirement_status') or '').upper()
    if verification == 'PASSED' and requirement == 'SATISFIED':
        return 'SATISFIED'
    if verification in ('PASSED', 'PROVISIONAL') and requirement == 'PROVISIONAL':
        return 'PROVISIONAL'
    if verification == 'PASSED' and requirement == 'BELOW_THRESHOLD':
        return 'BELOW_THRESHOLD'
    if verification == 'FAILED':
        return 'INVALID_DOCUMENT'
    return 'REVIEW_REQUIRED'


def _best_status(statuses: list[str]) -> str:
    # Alternatives: an accepted passing IELTS makes a failed TOEFL irrelevant.
    for status in ('SATISFIED', 'PROVISIONAL', 'REVIEW_REQUIRED', 'BELOW_THRESHOLD', 'INVALID_DOCUMENT'):
        if status in statuses:
            return status
    return 'MISSING'


def evaluate_eligibility(
    *,
    application_no: str,
    program: str,
    document_results: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate a single application's current document verification results.

    The caller must filter by application and choose current versions of each
    document. This function ignores documents for unrelated program categories
    and rejects any record explicitly tagged with a different application_no.
    Missing evidence produces INCOMPLETE unless a verified failure already
    establishes NOT_ELIGIBLE; uncertain evidence produces REVIEW_REQUIRED.
    """
    if not str(application_no).strip():
        raise ValueError('application_no is required')
    program_key = normalize_program(program)
    rules = required_documents(program_key)
    records: list[dict[str, Any]] = []
    for index, source in enumerate(document_results):
        if not isinstance(source, Mapping):
            raise TypeError(f'document_results[{index}] must be a mapping')
        record = dict(source)
        if record.get('application_no') is not None and str(record['application_no']) != str(application_no):
            raise ValueError(f'document_results[{index}] belongs to a different application')
        try:
            dtype = normalize_document_type(str(record.get('document_type') or ''))
        except ValueError:
            # Unrecognized uploads cannot satisfy any requirement.
            continue
        record['document_type'] = dtype
        record['_classification'] = _classify(record)
        records.append(record)

    requirements: list[dict[str, Any]] = []
    for category in CATEGORIES:
        allowed = rules[category]
        candidates = [r for r in records if r['document_type'] in allowed]
        status = _best_status([r['_classification'] for r in candidates])
        chosen = next((r for r in candidates if r['_classification'] == status), None)
        requirements.append({
            'category': category,
            'accepted_document_types': allowed,
            'status': status,
            'document_type_used': chosen['document_type'] if chosen else None,
            'document_count': len(candidates),
            'message': _category_message(category, allowed, status),
            'reason_codes': list(chosen.get('reason_codes') or []) if chosen else [],
        })

    states = {r['status'] for r in requirements}
    # An invalid document may be replaced; it is not proof of score ineligibility.
    if 'BELOW_THRESHOLD' in states:
        overall = 'NOT_ELIGIBLE'
    elif 'REVIEW_REQUIRED' in states or 'INVALID_DOCUMENT' in states:
        overall = 'REVIEW_REQUIRED'
    elif 'MISSING' in states:
        overall = 'INCOMPLETE'
    elif 'PROVISIONAL' in states:
        overall = 'PROVISIONALLY_ELIGIBLE'
    else:
        overall = 'ELIGIBLE'

    missing = [r['category'] for r in requirements if r['status'] == 'MISSING']
    review = [r['category'] for r in requirements if r['status'] in ('REVIEW_REQUIRED', 'INVALID_DOCUMENT')]
    failed = [r['category'] for r in requirements if r['status'] == 'BELOW_THRESHOLD']
    provisional = [r['category'] for r in requirements if r['status'] == 'PROVISIONAL']
    return {
        'application_no': str(application_no),
        'program': program_key,
        'eligibility_status': overall,
        'requirements': requirements,
        'missing_categories': missing,
        'review_categories': review,
        'below_threshold_categories': failed,
        'provisional_categories': provisional,
        'all_four_categories_satisfied': all(r['status'] == 'SATISFIED' for r in requirements),
        'admission_decision': None,
        'offer_letter_authorized': False,
        'message': _overall_message(overall, missing, review, failed, provisional),
    }


def _category_message(category: str, allowed: list[str], status: str) -> str:
    label = category.replace('_', ' ').title()
    choices = ' or '.join(x.replace('_', ' ') for x in allowed)
    if status == 'SATISFIED':
        return f'{label} requirement satisfied.'
    if status == 'PROVISIONAL':
        return f'{label} currently meets the score requirement, pending final academic records.'
    if status == 'BELOW_THRESHOLD':
        return f'{label} document was verified, but its score is below the required threshold.'
    if status == 'INVALID_DOCUMENT':
        return f'{label} document did not pass verification; upload the correct document or contact admissions.'
    if status == 'REVIEW_REQUIRED':
        return f'{label} evidence requires manual verification.'
    return f'Missing {label}: upload {choices}.'


def _overall_message(status: str, missing: list[str], review: list[str], failed: list[str], provisional: list[str]) -> str:
    if status == 'ELIGIBLE':
        return 'All four document requirements are satisfied. This is not an admission decision or an offer.'
    if status == 'PROVISIONALLY_ELIGIBLE':
        return 'Current requirements are met provisionally. Final academic records may still be required.'
    if status == 'NOT_ELIGIBLE':
        return 'One or more verified scores do not meet the admission requirements: ' + ', '.join(failed) + '.'
    if status == 'REVIEW_REQUIRED':
        return 'Manual review or replacement documents are needed for: ' + ', '.join(review) + '.'
    return 'Upload the remaining required documents: ' + ', '.join(missing) + '.'


# Friendly alias for existing API integration code.
evaluate_application_eligibility = evaluate_eligibility
