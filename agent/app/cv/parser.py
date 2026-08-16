"""CV -> CandidateProfile extraction."""

from __future__ import annotations

from ..llm import structured
from ..schemas import CandidateProfile
from .extract import to_text

SYSTEM = """You are a technical recruiter. You are given the text of a candidate's
resume. Your task is to extract a structured candidate profile that will be used
for job matching.

Rules:
- Rely only on what the CV says. If information is missing, leave the field
  empty; never make it up.
- Compute years of experience from the job dates; count overlapping periods once.
- Normalize skills ("React.js" and "ReactJS" -> "React"), no duplicates.
- Put roles the candidate could realistically land in target_titles; one level up
  is fine if plausible, two levels up is not.
- Write the summary in English; leave the other list fields in the CV's own
  language (technology names are always English).
- The text was extracted from a PDF, so line order may be scrambled in places;
  infer the correct reading from context and ignore meaningless fragments.

Produce only the requested JSON, no other commentary."""


async def parse_cv(filename: str, data: bytes) -> CandidateProfile:
    text = to_text(filename, data)
    prompt = f"Extract the candidate profile from this resume.\n\n--- CV START ---\n{text}\n--- CV END ---"
    return await structured(schema=CandidateProfile, system=SYSTEM, prompt=prompt)
