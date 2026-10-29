"""Conservative passport evidence extraction for the Admissions API.

Dependencies: pymupdf, pytesseract, opencv-python, numpy; system Tesseract OCR.
OCR cannot establish document authenticity. Passport type detection is separate
from optional applicant-name comparison.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import fitz
import numpy as np
import pytesseract
from pytesseract import Output

from app.core.admission_document_config import VERIFY_APPLICANT_NAME


@dataclass
class NameCandidate:
    name: str
    source: str
    confidence: float


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.upper().replace("’", "'")
    value = re.sub(r"[^A-Z\s'-]", " ", value)
    value = re.sub(r"[-']", " ", value)
    return " ".join(value.split())


def name_tokens(value: str) -> tuple[str, ...]:
    return tuple(sorted(normalize_name(value).split()))


def compare_names(extracted: str, expected: str) -> str:
    """Conservative exact-token matching; OCR mismatches require review."""
    a, b = name_tokens(extracted), name_tokens(expected)
    if not a or not b:
        return "UNCERTAIN"
    if a == b:
        return "MATCH"
    if any(len(t) == 1 for t in a + b):
        return "UNCERTAIN"
    if set(a).issubset(set(b)) or set(b).issubset(set(a)):
        return "UNCERTAIN"
    return "MISMATCH"


def mrz_candidates(text: str) -> list[NameCandidate]:
    found = []
    for raw in text.upper().splitlines():
        line = re.sub(r"\s+", "", raw)
        if not re.match(r"^P<[A-Z]{3}", line):
            continue
        body = line[5:]
        if "<<" not in body:
            continue
        surname, given = body.split("<<", 1)
        surname = surname.replace("<", " ").strip()
        given = given.rstrip("<").replace("<", " ").strip()
        name = normalize_name(f"{given} {surname}")
        if surname and given and len(name) >= 5:
            found.append(NameCandidate(name, "MRZ", 0.98 if len(line) == 44 else 0.78))
    return found


def visual_name_candidates(text: str, confidence: float) -> list[NameCandidate]:
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines()]
    found = []
    for i, line in enumerate(lines):
        label = re.search(r"\b(SURNAME|FAMILY NAME|GIVEN NAMES?|FIRST NAME|FULL NAME)\b", line, re.I)
        if not label:
            continue
        field = label.group(1).upper()
        after = re.sub(r"^.*?\b(?:SURNAME|FAMILY NAME|GIVEN NAMES?|FIRST NAME|FULL NAME)\b", "", line, flags=re.I)
        after = re.sub(r"^[\s:/-]+", "", after)
        value = after if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{2,65}", after) else ""
        if not value and i + 1 < len(lines):
            nxt = lines[i + 1]
            if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{2,65}", nxt) and not re.search(
                r"\b(?:NATIONALITY|DATE|PASSPORT|PLACE|SEX|COUNTRY|ISSUE|EXPIRY)\b", nxt, re.I
            ):
                value = nxt
        if value:
            found.append((field, normalize_name(value)))
    output = []
    surnames = [v for k, v in found if k in ("SURNAME", "FAMILY NAME")]
    given = [v for k, v in found if k in ("GIVEN NAME", "GIVEN NAMES", "FIRST NAME")]
    for surname in surnames:
        for given_name in given:
            output.append(NameCandidate(f"{given_name} {surname}", "VISUAL_FIELDS", confidence))
    for field, value in found:
        if field == "FULL NAME":
            output.append(NameCandidate(value, "VISUAL_FULL_NAME", confidence))
    return output


def ocr_image(img: np.ndarray) -> tuple[str, float]:
    data = pytesseract.image_to_data(img, config="--psm 6", output_type=Output.DICT)
    scores = []
    for word, conf in zip(data["text"], data["conf"]):
        try:
            score = float(conf)
        except (TypeError, ValueError):
            continue
        if word.strip() and score >= 0:
            scores.append(score)
    text = pytesseract.image_to_string(img, config="--psm 6")
    return text, (sum(scores) / len(scores) / 100 if scores else 0.0)


def get_pages(pdf_bytes: bytes, max_pages: int = 3):
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i in range(min(len(doc), max_pages)):
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
            img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
            elif pix.n == 1:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
            yield page.get_text("text"), img


def _passport_mrz_present(text: str) -> bool:
    """Require plausible TD3 passport MRZ structure, not merely a name."""
    for raw in text.upper().splitlines():
        line = re.sub(r"\s+", "", raw)
        if re.match(r"^P<[A-Z]{3}[A-Z<]{5,39}<<[A-Z<]+", line) and 35 <= len(line) <= 46:
            return True
    return False


def _passport_visual_present(text: str) -> bool:
    """Visual labels are supporting evidence; not enough alone for auto-pass."""
    return bool(
        re.search(r"\bPASSPORT\b", text, re.I)
        and re.search(r"\b(?:NATIONALITY|DATE OF BIRTH|PASSPORT NO|PASSPORT NUMBER)\b", text, re.I)
    )


def extract_identity_document(pdf_bytes: bytes, applicant_name: Optional[str] = None) -> dict:
    """Extract passport evidence, optionally compare names based on configuration.

    A reliable passport MRZ or corroborated visual markers identify the document
    type, but never prove issuer authenticity or identity ownership.
    """
    name_enabled = VERIFY_APPLICANT_NAME
    if name_enabled and not normalize_name(applicant_name or ""):
        raise ValueError("Salesforce applicant name is required when name verification is enabled")

    candidates: list[NameCandidate] = []
    mrz_seen = False
    visual_observations = 0
    text_seen = False
    confidences: list[float] = []
    try:
        pages = list(get_pages(pdf_bytes))
    except Exception:
        return {
            "document_type": "ID_PROOF",
            "detected_document_type": None,
            "extraction_status": "REVIEW_REQUIRED",
            "verification_status": "REVIEW_REQUIRED",
            "reason_code": "UNREADABLE_DOCUMENT",
            "warnings": ["Could not read the identity document"],
            "name_match": None,
            "name_match_status": "REVIEW_REQUIRED" if name_enabled else "SKIPPED",
            "issuer_authenticity_verified": False,
        }

    for embedded, img in pages:
        observations = []
        if embedded.strip():
            observations.append((embedded, 0.90))
        for rotation in (0, 180):
            frame = cv2.rotate(img, cv2.ROTATE_180) if rotation else img
            try:
                text, confidence = ocr_image(frame)
            except (pytesseract.TesseractError, RuntimeError, OSError):
                text, confidence = "", 0.0
            if text.strip():
                observations.append((text, confidence))
                confidences.append(confidence)
            try:
                strip = frame[int(frame.shape[0] * 0.84):]
                gray = cv2.cvtColor(strip, cv2.COLOR_RGB2GRAY)
                mrz_text = pytesseract.image_to_string(
                    gray, config="--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
                )
                if mrz_text.strip():
                    observations.append((mrz_text, confidence))
            except (pytesseract.TesseractError, RuntimeError, OSError):
                pass

        for text, confidence in observations:
            text_seen = True
            mrz_seen |= _passport_mrz_present(text)
            if _passport_visual_present(text):
                visual_observations += 1
            if name_enabled:
                candidates.extend(mrz_candidates(text))
                candidates.extend(visual_name_candidates(text, confidence))

    # A plausible MRZ is strong evidence of passport type. Visual-only detection
    # remains reviewable because a header/labels alone can be misleading.
    detected_type = "ID_PROOF" if mrz_seen else None
    warnings = []
    if not mrz_seen:
        warnings.append("Passport MRZ not confidently identified; manual document-type review required")
    if not text_seen:
        warnings.append("No readable document text detected")

    name_match = None
    name_status = "SKIPPED" if not name_enabled else "REVIEW_REQUIRED"
    if name_enabled:
        good = [c for c in candidates if c.confidence >= 0.80 and len(name_tokens(c.name)) >= 2]
        matches = [c for c in good if compare_names(c.name, applicant_name or "") == "MATCH"]
        distinct = {name_tokens(c.name) for c in good}
        has_mrz = any(c.source == "MRZ" and c.confidence >= 0.90 for c in good)
        if matches and len(distinct) == 1 and (has_mrz or len(matches) >= 2):
            name_match, name_status = True, "MATCH"
        else:
            warnings.append("Passport applicant name could not be reliably confirmed")

    extracted_ok = bool(mrz_seen and (not name_enabled or name_match is True))
    return {
        "document_type": "ID_PROOF",
        "detected_document_type": detected_type,
        "detected_document_type_match": True if mrz_seen else None,
        "extraction_status": "EXTRACTED" if extracted_ok else "REVIEW_REQUIRED",
        "verification_status": "PASSED" if extracted_ok else "REVIEW_REQUIRED",
        "reason_code": "PASSPORT_TYPE_DETECTED" if mrz_seen else "DOCUMENT_TYPE_UNCERTAIN",
        "warnings": warnings,
        "name_match": name_match,
        "name_match_status": name_status,
        "passport_mrz_detected": mrz_seen,
        "passport_visual_markers_detected": visual_observations > 0,
        "ocr_confidence": round(max(confidences) * 100, 2) if confidences else None,
        "issuer_authenticity_verified": False,
    }


def verify_passport_name(pdf_bytes: bytes, applicant_name: Optional[str] = None) -> dict:
    """Backward-compatible entry point; respects VERIFY_APPLICANT_NAME."""
    result = extract_identity_document(pdf_bytes, applicant_name)
    status = result["verification_status"]
    if result["name_match_status"] == "SKIPPED":
        message = ("Passport type was detected; applicant name verification was skipped."
                   if status == "PASSED" else
                   "Passport type could not be confirmed automatically; manual review required.")
    elif result["name_match"] is True and status == "PASSED":
        message = "The name on your passport matches the name on your application."
    else:
        message = "We could not confidently verify the passport and applicant name; manual review required."
    return {**result, "message": message,
            "action_required": "NONE" if status == "PASSED" else "MANUAL_REVIEW"}


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--applicant-name")
    args = parser.parse_args()
    print(json.dumps(verify_passport_name(Path(args.pdf).read_bytes(), args.applicant_name), indent=2))
