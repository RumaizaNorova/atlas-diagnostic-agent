"""
Synthetic FHIR patient for the ATLAS demo endpoint.

Clinical case: 31-year-old female with a 9-year diagnostic odyssey.
Misdiagnosed with fibromyalgia, anxiety, and IBS. True presentation
is consistent with hypermobile Ehlers-Danlos Syndrome (hEDS) + POTS.
Classic missed rare disease combination affecting ~1 in 5,000 people.
"""

DEMO_PATIENT_HISTORY = {
    "patient_id": "demo-patient-atlas-001",
    "conditions": [
        {"display": "Fibromyalgia syndrome", "code": "729.1", "onset": "2016-03-10", "status": "active"},
        {"display": "Generalized anxiety disorder", "code": "300.02", "onset": "2015-08-22", "status": "active"},
        {"display": "Irritable bowel syndrome", "code": "K58.9", "onset": "2017-01-15", "status": "active"},
        {"display": "Chronic fatigue", "code": "R53.82", "onset": "2015-06-01", "status": "active"},
        {"display": "Migraine without aura", "code": "G43.009", "onset": "2014-11-03", "status": "active"},
        {"display": "Recurrent shoulder subluxation", "code": "M24.312", "onset": "2018-07-20", "status": "active"},
        {"display": "Recurrent patellar subluxation", "code": "M22.10", "onset": "2019-02-14", "status": "active"},
        {"display": "Orthostatic hypotension", "code": "I95.1", "onset": "2020-05-08", "status": "active"},
        {"display": "Chronic widespread pain", "code": "M79.3", "onset": "2015-09-30", "status": "active"},
        {"display": "Gastroesophageal reflux disease", "code": "K21.0", "onset": "2016-12-01", "status": "active"},
        {"display": "Raynaud phenomenon", "code": "I73.00", "onset": "2017-08-15", "status": "active"},
        {"display": "Dysautonomia", "code": "G90.3", "onset": "2021-03-22", "status": "active"},
    ],
    "observations": [
        # Heart rate on standing (orthostatic tilt)
        {"name": "Heart rate - standing", "code": "8867-4", "value": "128 /min", "interpretation": "H", "date": "2023-04-10", "abnormal": True},
        {"name": "Heart rate - supine", "code": "8867-4", "value": "72 /min", "interpretation": "N", "date": "2023-04-10", "abnormal": False},
        {"name": "Heart rate - standing", "code": "8867-4", "value": "134 /min", "interpretation": "H", "date": "2022-09-05", "abnormal": True},
        {"name": "Heart rate - standing", "code": "8867-4", "value": "121 /min", "interpretation": "H", "date": "2021-11-18", "abnormal": True},
        # Blood pressure
        {"name": "Systolic blood pressure - standing", "code": "8480-6", "value": "88 mmHg", "interpretation": "L", "date": "2023-04-10", "abnormal": True},
        {"name": "Systolic blood pressure - standing", "code": "8480-6", "value": "84 mmHg", "interpretation": "L", "date": "2022-09-05", "abnormal": True},
        # Beighton score components (documented separately)
        {"name": "Thumb to forearm (Beighton)", "code": "custom-beighton-1", "value": "Positive bilateral", "interpretation": "A", "date": "2022-03-14", "abnormal": True},
        {"name": "Little finger hyperextension (Beighton)", "code": "custom-beighton-2", "value": "Positive bilateral", "interpretation": "A", "date": "2022-03-14", "abnormal": True},
        {"name": "Elbow hyperextension >10 degrees", "code": "custom-beighton-3", "value": "Positive bilateral", "interpretation": "A", "date": "2022-03-14", "abnormal": True},
        # Inflammatory markers (mildly elevated, confusing picture)
        {"name": "C-reactive protein", "code": "1988-5", "value": "8.2 mg/L", "interpretation": "H", "date": "2023-01-20", "abnormal": True},
        {"name": "C-reactive protein", "code": "1988-5", "value": "6.7 mg/L", "interpretation": "H", "date": "2022-06-15", "abnormal": True},
        {"name": "C-reactive protein", "code": "1988-5", "value": "9.1 mg/L", "interpretation": "H", "date": "2021-08-30", "abnormal": True},
        {"name": "C-reactive protein", "code": "1988-5", "value": "7.4 mg/L", "interpretation": "H", "date": "2020-03-12", "abnormal": True},
        # ANA (mildly positive, contributing to diagnostic confusion)
        {"name": "Antinuclear antibody (ANA)", "code": "5048-4", "value": "1:80 speckled", "interpretation": "A", "date": "2023-02-28", "abnormal": True},
        {"name": "Antinuclear antibody (ANA)", "code": "5048-4", "value": "1:80 speckled", "interpretation": "A", "date": "2020-11-10", "abnormal": True},
        # Ferritin (low, common in hEDS due to GI issues)
        {"name": "Ferritin", "code": "2276-4", "value": "6 ng/mL", "interpretation": "L", "date": "2023-03-15", "abnormal": True},
        {"name": "Ferritin", "code": "2276-4", "value": "8 ng/mL", "interpretation": "L", "date": "2022-01-20", "abnormal": True},
        {"name": "Ferritin", "code": "2276-4", "value": "5 ng/mL", "interpretation": "L", "date": "2020-07-08", "abnormal": True},
        # Normal CBC, thyroid (ruling out common causes — adds clinical authenticity)
        {"name": "TSH", "code": "3016-3", "value": "2.1 mIU/L", "interpretation": "N", "date": "2023-01-20", "abnormal": False},
        {"name": "Hemoglobin", "code": "718-7", "value": "12.8 g/dL", "interpretation": "L", "date": "2023-01-20", "abnormal": True},
        {"name": "Hemoglobin", "code": "718-7", "value": "11.9 g/dL", "interpretation": "L", "date": "2021-05-14", "abnormal": True},
    ],
    "medications": [
        {"name": "Duloxetine 60 mg", "status": "active", "date": "2018-04-01"},
        {"name": "Gabapentin 300 mg TID", "status": "active", "date": "2019-11-15"},
        {"name": "Omeprazole 20 mg", "status": "active", "date": "2017-02-10"},
        {"name": "Propranolol 10 mg PRN", "status": "active", "date": "2021-06-22"},
        {"name": "Ondansetron 4 mg PRN", "status": "active", "date": "2020-08-30"},
        {"name": "Cyclobenzaprine 5 mg", "status": "stopped", "date": "2017-09-01"},
        {"name": "Amitriptyline 10 mg", "status": "stopped", "date": "2016-05-15"},
        {"name": "Naproxen 500 mg PRN", "status": "active", "date": "2015-07-20"},
    ],
    "procedures": [
        {"name": "Shoulder stabilization surgery", "status": "completed", "date": "2019-08-12"},
        {"name": "Upper GI endoscopy", "status": "completed", "date": "2020-03-05"},
        {"name": "Tilt table test", "status": "completed", "date": "2021-04-18"},
        {"name": "MRI lumbar spine", "status": "completed", "date": "2022-07-22"},
        {"name": "Echocardiogram", "status": "completed", "date": "2021-05-30"},
        {"name": "Sleep study (polysomnography)", "status": "completed", "date": "2022-11-14"},
    ],
    "family_history": [
        {"relationship": "Mother", "conditions": ["Hypermobile joints", "Chronic pain syndrome"], "deceased": False},
        {"relationship": "Maternal aunt", "conditions": ["Mitral valve prolapse", "Chronic fatigue"], "deceased": False},
        {"relationship": "Sister", "conditions": ["Joint hypermobility", "Anxiety"], "deceased": False},
        {"relationship": "Maternal grandmother", "conditions": ["Recurrent joint dislocations"], "deceased": True},
    ],
    "diagnostic_reports": [
        {"name": "Tilt table test report", "status": "final", "date": "2021-04-18",
         "conclusion": "Heart rate increase of 49 bpm on standing. Consistent with postural orthostatic tachycardia syndrome (POTS). Clinical correlation recommended."},
        {"name": "Echocardiogram report", "status": "final", "date": "2021-05-30",
         "conclusion": "Mild mitral valve prolapse noted. No significant regurgitation. Normal left ventricular function."},
        {"name": "Sleep study report", "status": "final", "date": "2022-11-14",
         "conclusion": "Mild sleep fragmentation. No obstructive sleep apnea. Alpha intrusion noted on delta sleep consistent with non-restorative sleep."},
        {"name": "Lumbar MRI report", "status": "final", "date": "2022-07-22",
         "conclusion": "Mild diffuse disc bulging L4-L5, L5-S1. Facet joint laxity noted. No significant neural foraminal stenosis."},
    ],
    "allergies": [
        {"substance": "NSAIDs (partial intolerance)", "type": "intolerance", "criticality": "low",
         "reactions": ["Nausea", "Gastric pain"]},
        {"substance": "Latex", "type": "allergy", "criticality": "low", "reactions": ["Contact urticaria"]},
    ],
}
