from datetime import date
from mcp.server.fastmcp import Context


# Diseases known to be rapidly progressive or life-threatening if untreated
_HIGH_URGENCY_KEYWORDS = {
    "wilson", "fabry", "gaucher", "pompe", "mps", "mucopolysaccharidosis",
    "phenylketonuria", "pku", "tyrosinemia", "organic acidemia", "urea cycle",
    "mitochondrial", "adrenoleukodystrophy", "ald", "niemann-pick",
    "hunter", "hurler", "morquio", "spinal muscular atrophy", "sma",
    "duchenne", "hemophilia", "pnh", "paroxysmal nocturnal",
    "aplastic anemia", "myelodysplastic", "amyloidosis", "vasculitis",
    "systemic lupus", "scleroderma", "dermatomyositis", "polymyositis",
}

_MODERATE_URGENCY_KEYWORDS = {
    "ehlers-danlos", "marfan", "loeys-dietz", "stickler", "noonan",
    "turner", "klinefelter", "williams", "fragile x", "angelman",
    "prader-willi", "rett", "tuberous sclerosis", "neurofibromatosis",
    "von hippel-lindau", "hereditary hemorrhagic telangiectasia",
    "periodic fever", "autoinflammatory", "hereditary angioedema",
}


def _score_delay(delay_years: int | None) -> tuple[int, str]:
    if delay_years is None:
        return 0, "Diagnostic delay unknown"
    if delay_years >= 10:
        return 3, f"Severe diagnostic delay: {delay_years} years"
    if delay_years >= 5:
        return 2, f"Significant diagnostic delay: {delay_years} years"
    if delay_years >= 2:
        return 1, f"Moderate diagnostic delay: {delay_years} years"
    return 0, f"Diagnostic delay: {delay_years} years"


def _score_candidates(top_candidates: list) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    for c in top_candidates[:3]:
        name_lower = c.get("disease_name", "").lower()
        strength = c.get("match_strength", "")
        if any(k in name_lower for k in _HIGH_URGENCY_KEYWORDS):
            score += 3
            reasons.append(f"{c['disease_name']} is a high-urgency condition requiring prompt workup")
        elif any(k in name_lower for k in _MODERATE_URGENCY_KEYWORDS):
            score += 1
            reasons.append(f"{c['disease_name']} benefits from early diagnosis and management")
        if strength == "Strong":
            score += 2
            reasons.append(f"Strong phenotype match for {c['disease_name']}")
        elif strength == "Moderate":
            score += 1
    return score, reasons


def _score_labs(persistent_abnormalities: list, worsening_trends: list) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    if len(persistent_abnormalities) >= 3:
        score += 3
        reasons.append(f"{len(persistent_abnormalities)} persistent multi-year lab abnormalities")
    elif len(persistent_abnormalities) >= 1:
        score += 1
        reasons.append(f"{len(persistent_abnormalities)} persistent lab abnormality")
    if len(worsening_trends) >= 2:
        score += 2
        reasons.append(f"{len(worsening_trends)} worsening lab trends detected")
    elif len(worsening_trends) == 1:
        score += 1
        reasons.append(f"1 worsening lab trend: {worsening_trends[0].get('test', '')}")
    return score, reasons


def _score_red_flags(red_flags: list) -> tuple[int, list[str]]:
    if len(red_flags) >= 4:
        return 2, [f"{len(red_flags)} missed red flags identified"]
    if len(red_flags) >= 2:
        return 1, [f"{len(red_flags)} missed red flags identified"]
    return 0, []


async def compute_urgency_score(
    atlas_result: dict,
    ctx: Context = None,
) -> dict:
    """Compute a structured urgency/triage score for rare disease workup based on ATLAS findings.

    Scores the patient from 1-5 across four dimensions: diagnostic delay, disease severity
    of top candidates, lab trend severity, and number of missed red flags. Returns an
    overall urgency level (Routine / Soon / Urgent / Emergent) with specific rationale
    to help clinicians prioritise rare disease referrals.
    """

    report = atlas_result.get("atlas_report", atlas_result)
    if not report or "executive_summary" not in report:
        return {"error": "Invalid ATLAS report. Run RunATLASAnalysis first."}

    lab_analysis = atlas_result.get("lab_analysis", {})
    persistent_abnormalities = lab_analysis.get("persistent_abnormalities", [])
    worsening_trends = lab_analysis.get("worsening_trends", [])

    delay_score, delay_reason = _score_delay(report.get("estimated_diagnostic_delay_years"))
    candidate_score, candidate_reasons = _score_candidates(report.get("top_candidates", []))
    lab_score, lab_reasons = _score_labs(persistent_abnormalities, worsening_trends)
    flag_score, flag_reasons = _score_red_flags(report.get("red_flags_missed", []))

    raw_score = delay_score + candidate_score + lab_score + flag_score
    max_score = 10

    # Normalize to 1-5
    normalized = max(1, min(5, round(1 + (raw_score / max_score) * 4)))

    urgency_map = {
        1: ("Routine", "Rare disease workup can be scheduled routinely within 3-6 months."),
        2: ("Soon", "Rare disease workup should be scheduled within 4-8 weeks."),
        3: ("Elevated", "Genetics referral warranted within 2-4 weeks given multi-year delay and abnormal findings."),
        4: ("Urgent", "Urgent genetics referral recommended within 1-2 weeks. Multiple high-risk findings present."),
        5: ("Emergent", "Immediate genetics/metabolism consultation recommended. Findings suggest rapidly progressive rare disease."),
    }

    urgency_level, urgency_description = urgency_map[normalized]

    all_reasons = [delay_reason] + candidate_reasons + lab_reasons + flag_reasons
    all_reasons = [r for r in all_reasons if r]

    return {
        "urgency_score": normalized,
        "urgency_level": urgency_level,
        "urgency_description": urgency_description,
        "score_breakdown": {
            "diagnostic_delay": delay_score,
            "disease_severity": candidate_score,
            "lab_abnormalities": lab_score,
            "missed_red_flags": flag_score,
            "raw_total": raw_score,
            "max_possible": max_score,
        },
        "rationale": all_reasons,
        "recommended_timeframe": urgency_description.split(".")[0],
    }
