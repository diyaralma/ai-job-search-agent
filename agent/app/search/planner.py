"""Candidate profile + user criteria -> search plan."""

from __future__ import annotations

import json

from ..llm import structured
from ..schemas import CandidateProfile, SearchCriteria, SearchPlan

SYSTEM = """You are a job search strategist. You are given a candidate profile and
the candidate's criteria. Your task is to produce a search plan that will be sent
to job board APIs.

Job boards will run these queries, so:
- Queries must be SHORT and GENERAL (1-3 words). Not "senior python backend
  developer with kubernetes experience" but "python backend" and "django".
- Vary the queries: one by job title, one by core technology, one by domain.
  They should not all search for the same thing.
- Write queries in English; most job pools are English.
- Put skills the candidate actually has AND that are core to the role in
  must_have_skills. Never require something the candidate does not have.
- Put terms far above/below the candidate's level, or from unrelated fields, in
  exclude_terms (e.g. "principal", "director" for a junior candidate; "sales"
  for a backend engineer).
- Put the cities/countries from the criteria in locations; add "remote" if
  remote work is enabled.

Produce only the requested JSON, no other commentary."""


async def build_plan(profile: CandidateProfile, criteria: SearchCriteria) -> SearchPlan:
    payload = {
        "candidate_profile": profile.model_dump(),
        "criteria": criteria.model_dump(),
    }
    prompt = (
        "Produce the search plan for the profile and criteria below.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    )
    return await structured(schema=SearchPlan, system=SYSTEM, prompt=prompt)
