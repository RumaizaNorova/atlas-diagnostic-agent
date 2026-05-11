import jwt
from mcp.server.fastmcp import Context

from fhir_context import FhirContext

FHIR_SERVER_URL_HEADER = "x-fhir-server-url"
FHIR_ACCESS_TOKEN_HEADER = "x-fhir-access-token"
PATIENT_ID_HEADER = "x-patient-id"


def get_fhir_context(ctx: Context) -> FhirContext | None:
    if not ctx or not ctx.request_context:
        return None
    req = ctx.request_context.request
    url = req.headers.get(FHIR_SERVER_URL_HEADER)
    if not url:
        return None
    token = req.headers.get(FHIR_ACCESS_TOKEN_HEADER)
    return FhirContext(url=url, token=token)


def get_patient_id_if_context_exists(ctx: Context) -> str | None:
    if not ctx or not ctx.request_context:
        return None
    req = ctx.request_context.request
    fhir_token = req.headers.get(FHIR_ACCESS_TOKEN_HEADER)
    if fhir_token:
        try:
            claims = jwt.decode(fhir_token, options={"verify_signature": False})
            patient = claims.get("patient")
            if patient:
                return str(patient)
        except Exception:
            pass
    return req.headers.get(PATIENT_ID_HEADER)
