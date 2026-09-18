import io

import pytest
from pypdf import PdfReader

from app.models.profile import Profile, ProfileProject
from app.models.resume_variant import ResumeVariant
from app.services.tailoring.resume_pdf import (
    UnrenderableResumeContent,
    _to_pdf_html,
    base_resume_pdf_filename,
    render_base_resume_pdf,
    render_resume_pdf,
    resume_pdf_filename,
)


def make_profile(**overrides) -> Profile:
    fields = {
        "name": "Ada Lovelace",
        "email": "ada@example.dev",
        "phone": "555-0100",
        "location": "London, UK",
        "resume_text": "Backend engineer.",
        "years_experience": 5.0,
    }
    return Profile(**{**fields, **overrides})


def make_variant(content: str) -> ResumeVariant:
    return ResumeVariant(role_label="Backend Engineer", generated_content=content)


def pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


def test_renders_a_real_pdf_with_contact_header_and_body() -> None:
    variant = make_variant("## Experience\n\nBuilt the Analytical Engine.\n\n* Compilers\n")

    pdf_bytes = render_resume_pdf(make_profile(), variant)

    assert pdf_bytes.startswith(b"%PDF-")
    text = pdf_text(pdf_bytes)
    assert "Ada Lovelace" in text
    assert "ada@example.dev" in text
    assert "555-0100" in text
    assert "London, UK" in text
    assert "Built the Analytical Engine." in text
    assert "Compilers" in text


def test_absent_optional_contact_fields_leave_no_dangling_separator() -> None:
    profile = make_profile(phone=None, location=None)

    text = pdf_text(render_resume_pdf(profile, make_variant("Content.")))

    assert "ada@example.dev" in text
    assert "|" not in text


def test_typographic_punctuation_is_folded_rather_than_fatal() -> None:
    # Exactly what an LLM emits, and what the built-in Latin-1 fonts reject.
    variant = make_variant("Scaled a system — 10k req/s — with “high” uptime.\n\n• Python\n")

    text = pdf_text(render_resume_pdf(make_profile(), variant))

    assert "10k req/s" in text
    assert "—" not in text
    assert "“" not in text


def test_extra_typographic_symbols_are_folded_rather_than_fatal() -> None:
    """Found live in a real user's resume: "↗" as a "this opens externally" icon
    after a link label, and "→" used inline for "leads to" — both genuine,
    intentional characters, just outside the built-in Latin-1 fonts, the same
    class of gap as the em-dash/curly-quote folds above.
    """
    variant = make_variant("Joining Letter ↗\n\nA deterministic-first cascade (rules → LLM).\n")

    text = pdf_text(render_resume_pdf(make_profile(), variant))

    assert "Joining Letter ->" in text
    assert "rules -> LLM" in text


def test_markdown_list_bullets_render_as_plain_ascii() -> None:
    # fpdf2's default disc bullet encodes to a WinAnsi byte that ATS parsers and
    # text extractors mishandle; a resume has to survive both.
    variant = make_variant("Skills:\n\n* Python\n* Distributed systems\n")

    text = pdf_text(render_resume_pdf(make_profile(), variant))

    assert "�" not in text
    assert "- Python" in text
    assert "- Distributed systems" in text


def test_latin1_accents_survive_unchanged() -> None:
    profile = make_profile(name="Zoë Müller", location="Zürich")

    text = pdf_text(render_resume_pdf(profile, make_variant("Café work.")))

    assert "Zoë Müller" in text
    assert "Zürich" in text


def test_characters_outside_latin1_raise_a_domain_error() -> None:
    profile = make_profile(name="वैभव चौबे")

    with pytest.raises(UnrenderableResumeContent):
        render_resume_pdf(profile, make_variant("Content."))


def test_raw_html_in_content_is_escaped_not_interpreted() -> None:
    html = _to_pdf_html('Before <img src="http://attacker.test/x.png"> after')

    assert "<img" not in html
    assert "&lt;img" in html


def test_render_base_resume_pdf_uses_the_profiles_own_text_and_projects() -> None:
    """No workflow ever sets Application.resume_variant_id today (confirmed by
    grep — nothing writes to that column), so this untailored fallback is what
    every single automated fill actually uploads in practice, not a rare edge
    case for a candidate who skipped tailoring.
    """
    profile = make_profile(resume_text="Backend engineer with distributed systems experience.")
    profile.projects = [ProfileProject(title="Analytical Engine", content_md="Built it from scratch.")]

    pdf_bytes = render_base_resume_pdf(profile)

    assert pdf_bytes.startswith(b"%PDF-")
    text = pdf_text(pdf_bytes)
    assert "Ada Lovelace" in text
    assert "Backend engineer with distributed systems experience." in text
    assert "Analytical Engine" in text
    assert "Built it from scratch." in text


def test_base_resume_pdf_filename_does_not_reference_a_variant() -> None:
    profile = make_profile(name='Ada "Hacker"\r\nX-Injected: yes')

    filename = base_resume_pdf_filename(profile)

    assert filename == "Ada_Hacker_X-Injected_yes_resume.pdf"


def test_filename_strips_characters_that_would_break_the_header() -> None:
    profile = make_profile(name='Ada "Hacker"\r\nX-Injected: yes')
    variant = make_variant("Content.")
    variant.role_label = "Backend / Platform"

    filename = resume_pdf_filename(profile, variant)

    assert filename == "Ada_Hacker_X-Injected_yes_Backend_Platform.pdf"
    assert '"' not in filename
    assert "\r" not in filename and "\n" not in filename
