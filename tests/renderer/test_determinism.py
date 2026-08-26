"""
Determinism and non-mutation, for both renderers.

Neither makes an LLM call, so this is cheap to guarantee — but it is the
property the rest of the pipeline leans on when diffing generated output.
"""

from src.parser import ResumeParser
from src.renderer import LatexRenderer, MarkdownSerializer

from .conftest import CANONICAL_RESUMES, make_generated_resume, make_resume


class TestDeterminism:
    def test_two_serializations_are_byte_identical(self):
        resume = make_resume()
        serializer = MarkdownSerializer()
        assert serializer.serialize(resume) == serializer.serialize(resume)

    def test_five_serializations_are_byte_identical(self):
        resume = make_resume()
        serializer = MarkdownSerializer()
        outputs = {serializer.serialize(resume) for _ in range(5)}
        assert len(outputs) == 1

    def test_separate_instances_agree(self):
        resume = make_resume()
        assert MarkdownSerializer().serialize(resume) == MarkdownSerializer().serialize(
            resume
        )

    def test_canonical_resumes_serialize_identically_every_time(self):
        parser, serializer = ResumeParser(), MarkdownSerializer()
        for path in CANONICAL_RESUMES:
            resume = parser.parse(path)
            assert serializer.serialize(resume) == serializer.serialize(resume)

    def test_output_does_not_depend_on_id_or_source(self):
        # Runtime fields are not serialized, so changing them cannot move a byte.
        plain = make_resume()
        generated = make_generated_resume()
        assert MarkdownSerializer().serialize(plain) == MarkdownSerializer().serialize(
            generated
        )


class TestNoMutation:
    def test_the_resume_is_unchanged(self):
        resume = make_resume()
        before = resume.model_dump()
        MarkdownSerializer().serialize(resume)
        assert resume.model_dump() == before

    def test_nested_lists_are_not_reordered_in_place(self):
        resume = make_resume()
        before = list(resume.experiences[0].highlights)
        MarkdownSerializer().serialize(resume)
        assert resume.experiences[0].highlights == before

    def test_runtime_fields_are_not_cleared(self):
        resume = make_generated_resume()
        MarkdownSerializer().serialize(resume)
        assert resume.projects[0].id == "proj_002"
        assert resume.projects[0].source.value == "GENERATED"

    def test_a_failed_serialization_leaves_the_resume_alone(self):
        resume = make_resume()
        resume.experiences[0].highlights = ["fine", ""]
        before = resume.model_dump()
        try:
            MarkdownSerializer().serialize(resume)
        except Exception:
            pass
        assert resume.model_dump() == before

    def test_canonical_resumes_are_unchanged(self):
        parser, serializer = ResumeParser(), MarkdownSerializer()
        for path in CANONICAL_RESUMES:
            resume = parser.parse(path)
            before = resume.model_dump()
            serializer.serialize(resume)
            assert resume.model_dump() == before


class TestLatexDeterminism:
    def test_rendering_twice_is_byte_identical(self):
        renderer = LatexRenderer()
        resume = make_resume()
        assert renderer.render(resume) == renderer.render(resume)

    def test_two_renderer_instances_agree(self):
        resume = make_resume()
        assert LatexRenderer().render(resume) == LatexRenderer().render(resume)

    def test_the_canonical_resumes_render_identically_every_time(self):
        renderer = LatexRenderer()
        for path in CANONICAL_RESUMES:
            resume = ResumeParser().parse(path)
            assert renderer.render(resume) == renderer.render(resume)


class TestLatexNoMutation:
    def test_the_resume_is_unchanged_after_rendering(self):
        resume = make_resume()
        before = resume.model_dump()
        LatexRenderer().render(resume)
        assert resume.model_dump() == before

    def test_a_generated_resume_is_unchanged_after_rendering(self):
        resume = make_generated_resume()
        before = resume.model_dump()
        LatexRenderer().render(resume)
        assert resume.model_dump() == before

    def test_writing_to_a_file_does_not_mutate_the_resume(self, tmp_path):
        resume = make_resume()
        before = resume.model_dump()
        LatexRenderer().render_to_file(resume, str(tmp_path))
        assert resume.model_dump() == before
