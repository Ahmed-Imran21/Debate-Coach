"""
Practice motions: the single source of truth.

GET /v1/motions serves this list, POST /v1/sessions validates
motion_id against it, and the pipeline looks a session's motion up
here to hand its wording to the coaching engine as plain text (the
engine never imports from app/).

Rules for editing:
- An id is permanent. Sessions store it, so never rename or delete
  one; set retired=True instead. A retired motion disappears from
  the dropdown but still resolves for sessions that used it.
- title is the short topic shown in the dropdown; description is
  the motion itself, in formal competitive-debate wording.
- Only text from this file ever reaches the coaching prompt. Users
  pick an id; free text is never accepted.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Motion:
    id: str
    title: str
    description: str
    retired: bool = False


MOTIONS: tuple[Motion, ...] = (
    # Politics
    Motion("compulsory-voting", "Compulsory voting", "This house would make voting compulsory."),
    Motion("lower-voting-age", "Voting age", "This house would lower the voting age to sixteen."),
    Motion("restore-student-unions", "Student unions", "This house would restore student unions in universities."),
    # Economics
    Motion("universal-basic-income", "Universal basic income", "This house would introduce a universal basic income."),
    Motion("wealth-tax", "Wealth tax", "This house would impose an annual tax on the wealth of the richest one percent."),
    Motion("growth-over-environment", "Growth and the environment", "This house believes developing nations should prioritise economic growth over environmental protection."),
    # Technology
    Motion("pause-frontier-ai", "Artificial intelligence", "This house would pause the development of AI systems more capable than those that exist today."),
    Motion("social-media-under-sixteen", "Children and social media", "This house would ban social media for children under the age of sixteen."),
    # Ethics
    Motion("assisted-dying", "Assisted dying", "This house would legalise assisted dying for terminally ill adults."),
    Motion("animal-testing", "Animal testing", "This house would ban the use of animals in medical research."),
    # Education
    Motion("primary-homework", "Homework", "This house would ban homework in primary schools."),
    Motion("mother-tongue-instruction", "Language of instruction", "This house would make the mother tongue, not English, the medium of instruction in primary schools."),
    # International relations
    Motion("security-council-veto", "UN Security Council", "This house would abolish the veto power of the permanent members of the UN Security Council."),
    Motion("climate-reparations", "Climate reparations", "This house believes that wealthy nations should pay climate reparations to developing nations."),
    # Social issues
    Motion("police-body-cameras", "Policing", "This house would require all police officers to wear body cameras while on duty."),
    Motion("platform-free-speech", "Free speech online", "This house believes that social media companies should not remove lawful speech."),
    # Science and environment
    Motion("space-funding", "Space exploration", "This house believes that governments should stop funding space exploration."),
    Motion("carbon-tax", "Climate policy", "This house would introduce a carbon tax."),
    # South Asia
    Motion("cricket-investment", "Cricket and other sports", "This house believes that South Asian governments overinvest in cricket at the expense of other sports."),
    Motion("graduate-emigration", "Brain drain", "This house would require graduates of publicly funded universities to work in their home country for five years before emigrating."),
    Motion("south-asian-common-market", "Regional integration", "This house believes that South Asian nations should form a common market."),
)

_BY_ID = {m.id: m for m in MOTIONS}
assert len(_BY_ID) == len(MOTIONS), "duplicate motion id"


def active_motions() -> list[Motion]:
    """The dropdown: every motion not retired, in list order."""
    return [m for m in MOTIONS if not m.retired]


def get_motion(motion_id: Optional[str]) -> Optional[Motion]:
    """Any known motion, retired or not; None for no motion or an unknown id."""
    if motion_id is None:
        return None
    return _BY_ID.get(motion_id)


def is_selectable(motion_id: str) -> bool:
    """What a new session may pick: known and not retired."""
    motion = _BY_ID.get(motion_id)
    return motion is not None and not motion.retired
