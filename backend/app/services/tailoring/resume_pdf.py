import html as html_lib
import re

import markdown
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.errors import FPDFUnicodeEncodingException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import Profile
from app.models.resume_variant import ResumeVariant

# The built-in PDF fonts are Latin-1 only, and LLM output routinely contains
# typographic punctuation outside that range. Folding to ASCII equivalents keeps
# v1 free of a ~750KB bundled Unicode TTF; anything left outside Latin-1 (a name
# in a non-Latin script, say) raises UnrenderableResumeContent rather than
# silently mangling it. See automation-plan.md §6.
_PUNCTUATION_FOLDING = str.maketrans(
    {
        "–": "-",
        "—": "-",
        "‐": "-",
        "‑": "-",
        "−": "-",
        "‘": "'",
        "’": "'",
        "ʼ": "'",
        "“": '"',
        "”": '"',
        "•": "-",
        "·": "-",
        "…": "...",
        "†": "",
        "™": "",
        "€": "EUR",
        # Found live in a real user's resume: "↗" as a "this opens externally"
        # icon after a link label ("Joining Letter ↗"), and "→" used inline to
        # mean "leads to" ("rules → LLM"). Both genuine, intentional characters
        # someone typed on purpose — not a rendering bug, just outside the
        # built-in Latin-1 fonts, exactly like the dashes and quotes above.
        "↗": "->",
        "→": "->",
        " ": " ",
    }
)

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class UnrenderableResumeContent(ValueError):
    """Content holds characters the built-in Latin-1 fonts cannot represent."""


def _fold(text: str) -> str:
    return text.translate(_PUNCTUATION_FOLDING)


def _to_pdf_html(markdown_text: str) -> str:
    # Escaped before conversion because resume content is prose, never markup:
    # without this, raw HTML in LLM output reaches fpdf2's parser, including
    # <img src="http://..."> tags it would try to fetch over the network.
    escaped = html_lib.escape(_fold(markdown_text), quote=False)
    return markdown.markdown(escaped)


def resume_pdf_filename(profile: Profile, variant: ResumeVariant) -> str:
    """Sanitized hard: this value goes into a Content-Disposition header, and both
    inputs are user-supplied.
    """
    stem = _UNSAFE_FILENAME_CHARS.sub("_", f"{profile.name}_{variant.role_label}").strip("_")
    return f"{stem or 'resume'}.pdf"


def base_resume_pdf_filename(profile: Profile) -> str:
    stem = _UNSAFE_FILENAME_CHARS.sub("_", f"{profile.name}_resume").strip("_")
    return f"{stem or 'resume'}.pdf"


def _render_pdf(profile: Profile, content_md: str) -> bytes:
    """Shared skeleton (contact header + rule + body) for both a tailored resume
    variant and the untailored fallback — pure, no DB, no network, no clock.
    """
    pdf = FPDF(format="Letter", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(left=18, top=15, right=18)
    pdf.add_page()

    contact_line = "   |   ".join(
        bit for bit in (profile.email, profile.phone, profile.location) if bit
    )

    try:
        pdf.set_font("Helvetica", style="B", size=20)
        pdf.cell(0, 9, text=_fold(profile.name), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_font("Helvetica", size=9.5)
        pdf.cell(0, 5, text=_fold(contact_line), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.ln(1)
        rule_y = pdf.get_y()
        pdf.line(pdf.l_margin, rule_y, pdf.w - pdf.r_margin, rule_y)
        pdf.ln(3)

        pdf.set_font("Helvetica", size=10.5)
        # An ASCII bullet rather than fpdf2's default disc: resume PDFs get parsed
        # by ATS software, which handles "-" far more reliably than the WinAnsi
        # bullet byte, and it matches the literal "-" lists the LLM also emits.
        pdf.write_html(_to_pdf_html(content_md), ul_bullet_char="-")
    except FPDFUnicodeEncodingException as exc:
        raise UnrenderableResumeContent(str(exc)) from exc

    return bytes(pdf.output())


def render_resume_pdf(profile: Profile, variant: ResumeVariant) -> bytes:
    """The variant's generated text plus the profile's contact details, as a real
    uploadable document.
    """
    return _render_pdf(profile, variant.generated_content)


def render_base_resume_pdf(profile: Profile) -> bytes:
    """The candidate's own resume text and project write-ups, untailored to any
    job. Used by fill_application_form when an application has no linked
    ResumeVariant yet — there is currently no workflow that ever sets
    Application.resume_variant_id, so without this fallback the resume upload
    field would be skipped on every single application, always. Not cached:
    unlike a ResumeVariant (immutable once generated), a Profile can be edited,
    and this render is pure CPU with no LLM call — cheap enough to redo per fill.
    """
    return _render_pdf(profile, profile.full_resume_text)


async def ensure_resume_pdf(profile: Profile, variant: ResumeVariant, db: AsyncSession) -> bytes:
    """Render-once per variant. Safe to cache indefinitely because a ResumeVariant
    is never updated in place - regenerating for a role creates a new row.
    """
    if variant.pdf_bytes is not None:
        return variant.pdf_bytes

    pdf_bytes = render_resume_pdf(profile, variant)
    variant.pdf_bytes = pdf_bytes
    await db.commit()
    return pdf_bytes
