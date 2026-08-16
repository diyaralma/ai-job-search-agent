"""Job-specific CV + cover letter generation.

The constraint at the centre of the design: **nothing is invented.** The model
only reframes facts already in the profile, in the language of the posting. Two
reasons:
1. An interview won through a false claim collapses at the first technical
   question; that harms the user.
2. An application cannot be recalled — a fabricated line stays a liability for
   as long as the CV is out there.

For transparency the model separately reports what it highlighted
(`emphasized`), what it pushed to the background (`downplayed`) and the gaps it
could not close (`gaps_to_expect`); the UI shows these so the user knows exactly
what they are signing.
"""

from __future__ import annotations

import json

from ..llm import structured
from ..schemas import ApplicationKit, CandidateProfile, JobPosting

SYSTEM = """You are an experienced career coach and technical recruiter. You are
given a candidate's profile and a job posting they want to apply to. Produce a CV
and cover letter tailored to that posting.

ABSOLUTE RULE — NO FABRICATION:
- Never add a technology, experience, company, degree, certification or number
  that is not in the profile. Not a single one.
- Do not stretch tenure, inflate titles or change company names.
- If the posting asks for something the candidate does not have, DO NOT put it
  in the CV. Put it in gaps_to_expect so the candidate walks into the interview
  prepared.
- Rephrasing an item from the profile in the posting's language is allowed;
  adding something absent because it is "similar" is not.

WHAT TO DO:
- Highlight the experience that overlaps with what the posting asks for, and
  order the content accordingly.
- Use the posting's vocabulary (if the candidate wrote "REST API" and the
  posting says "RESTful services", you may use the latter — same thing).
- Shorten unrelated experience, do not delete it entirely.
- Write concrete bullets: what they did, at what scale, what the outcome was.
  Take numbers from the profile; never invent them.
- Keep ATS scans in mind: the posting's key terms should appear naturally, but
  do not keyword-stuff.

LANGUAGE:
- The kit's language must match the posting's language. If the posting is in
  Turkish everything is Turkish; if English, everything is English. Write 'tr'
  or 'en' in the language field.
- Technology names stay in English in either language.

COVER LETTER:
- 4-6 paragraphs, keep it short. NO cliché opener like "I would like to apply
  for this position because your company is an industry leader".
- In the first paragraph, say why they fit this role with a concrete example.
- Do not praise things you do not know about the company; rely on the posting
  text only.

Produce only the requested JSON, no other commentary."""


async def build_kit(profile: CandidateProfile, job: JobPosting) -> ApplicationKit:
    prompt = (
        "CANDIDATE PROFILE (the single source of truth — never go beyond it):\n"
        + json.dumps(profile.model_dump(), ensure_ascii=False, indent=2)
        + "\n\nTARGET POSTING:\n"
        + job.digest(max_chars=6000)
        + "\n\nPrepare the CV and cover letter tailored to this posting."
    )
    return await structured(
        schema=ApplicationKit,
        system=SYSTEM,
        prompt=prompt,
        # Kit generation is one-shot with long output; more generous than scoring
        timeout=420,
    )
