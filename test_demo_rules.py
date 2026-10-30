from app.services.document_validation_service import validate_document
from app.core.admission_document_config import evaluate_application
from app.services.eligibility_service import evaluate_eligibility

cases = [
    ('BACHELOR','CLASS_12_MARKSHEET','percentage',70,'PASSED'),
    ('BACHELOR','CLASS_12_MARKSHEET','percentage',69.9,'FAILED'),
    ('MASTER','UNDERGRADUATE_TRANSCRIPT','overall_gpa',3.2,'PASSED'),
    ('MASTER','UNDERGRADUATE_TRANSCRIPT','candidate_gpa',2.33,'FAILED'),
    ('MASTER','UNDERGRADUATE_TRANSCRIPT','overall_gpa',None,'REVIEW_REQUIRED'),
    ('BACHELOR','SAT','total_score',1100,'PASSED'),
    ('BACHELOR','SAT','total_score',1099,'FAILED'),
    ('BACHELOR','SAT','total_score',1101,'PASSED'),
    ('MASTER','GRE','total_score',290,'PASSED'),
    ('MASTER','GRE','total_score',289,'FAILED'),
    ('MASTER','GRE','total_score',291,'PASSED'),
    ('MBA','GMAT','total_score',600,'PASSED'),
    ('MBA','GMAT','total_score',599,'FAILED'),
    ('MBA','GMAT','total_score',601,'PASSED'),
    ('MASTER','IELTS','overall_band',6.5,'PASSED'),
    ('MASTER','IELTS','overall_band',6.0,'FAILED'),
    ('MASTER','TOEFL','total_score',72,'PASSED'),
    ('MASTER','TOEFL','total_score',71,'FAILED'),
    ('MASTER','TOEFL','total_score',73,'PASSED'),
]
for program, dtype, field, score, expected in cases:
    result = validate_document(program=program, document_type=dtype,
        applicant_name='ANY DIFFERENT NAME', extracted_data={field:score})
    assert result['validation_status'] == expected, (dtype, score, result)
    assert result['name_match_status'] == 'SKIPPED'
assert evaluate_application('MASTER', [])['validation_status'] == 'MISSING'
assert evaluate_eligibility(application_no='DEMO-1',program='MASTER',document_results=[])['validation_status'] == 'MISSING'
print(f'PASS: {len(cases)} threshold/name tests + 2 missing-document aggregation tests')
