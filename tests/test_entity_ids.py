"""
Tests for the shared runtime entity ID minter.

The Parser numbers a freshly parsed resume positionally; the Generator mints
IDs for entities that did not exist in the source. Both go through
``src.entity_ids``.
"""

from src.entity_ids import (
    EXPERIENCE_PREFIX,
    PROJECT_PREFIX,
    SKILL_PREFIX,
    assign_sequential_ids,
    format_id,
    highest_number,
    mint_id,
    mint_ids,
)
from src.parser.models import Project


class TestFormatId:
    def test_pads_to_three_digits(self):
        assert format_id(PROJECT_PREFIX, 1) == "proj_001"
        assert format_id(PROJECT_PREFIX, 42) == "proj_042"

    def test_does_not_truncate_wide_numbers(self):
        assert format_id(PROJECT_PREFIX, 1234) == "proj_1234"

    def test_uses_the_given_prefix(self):
        assert format_id(SKILL_PREFIX, 2) == "skill_002"
        assert format_id(EXPERIENCE_PREFIX, 2) == "exp_002"


class TestHighestNumber:
    def test_empty_input_is_zero(self):
        assert highest_number(PROJECT_PREFIX, []) == 0

    def test_finds_the_maximum_not_the_last(self):
        assert highest_number(PROJECT_PREFIX, ["proj_003", "proj_001"]) == 3

    def test_ignores_other_prefixes(self):
        assert highest_number(PROJECT_PREFIX, ["skill_009", "proj_002"]) == 2

    def test_ignores_unparseable_ids(self):
        # A malformed id should never be able to block minting.
        assert highest_number(PROJECT_PREFIX, ["proj_abc", "", "proj_004"]) == 4

    def test_all_unparseable_is_zero(self):
        assert highest_number(PROJECT_PREFIX, ["nonsense", None, ""]) == 0


class TestMintId:
    def test_first_id_for_an_empty_resume(self):
        assert mint_id(PROJECT_PREFIX, []) == "proj_001"

    def test_next_id_follows_the_maximum(self):
        assert mint_id(PROJECT_PREFIX, ["proj_001", "proj_002"]) == "proj_003"

    def test_max_plus_one_survives_a_removal(self):
        # The reason this is max+1 rather than count+1: proj_001 was removed,
        # and counting the survivors would mint an id proj_002 already owns.
        assert mint_id(PROJECT_PREFIX, ["proj_002", "proj_003"]) == "proj_004"

    def test_gap_in_the_sequence_is_not_reused(self):
        assert mint_id(PROJECT_PREFIX, ["proj_001", "proj_005"]) == "proj_006"

    def test_skill_categories_use_the_skill_prefix(self):
        assert mint_id(SKILL_PREFIX, ["skill_001", "skill_002"]) == "skill_003"


class TestMintIds:
    def test_returns_ascending_ids(self):
        assert mint_ids(PROJECT_PREFIX, ["proj_002"], 3) == [
            "proj_003",
            "proj_004",
            "proj_005",
        ]

    def test_zero_count_returns_empty(self):
        assert mint_ids(PROJECT_PREFIX, ["proj_001"], 0) == []

    def test_matches_repeated_mint_id_calls(self):
        existing = ["proj_001"]
        batch = mint_ids(PROJECT_PREFIX, existing, 2)

        one_at_a_time = []
        pool = list(existing)
        for _ in range(2):
            new_id = mint_id(PROJECT_PREFIX, pool)
            one_at_a_time.append(new_id)
            pool.append(new_id)

        assert batch == one_at_a_time


class TestAssignSequentialIds:
    def _project(self, name: str) -> Project:
        return Project(name=name, type="Personal", highlights=["did a thing"])

    def test_numbers_positionally_from_one(self):
        projects = [self._project("A"), self._project("B")]
        assign_sequential_ids(projects, PROJECT_PREFIX)
        assert [p.id for p in projects] == ["proj_001", "proj_002"]

    def test_overwrites_any_existing_ids(self):
        # IDs are runtime-only and regenerated on every parse.
        projects = [self._project("A")]
        projects[0].id = "proj_099"
        assign_sequential_ids(projects, PROJECT_PREFIX)
        assert projects[0].id == "proj_001"

    def test_empty_list_is_a_no_op(self):
        assign_sequential_ids([], PROJECT_PREFIX)
