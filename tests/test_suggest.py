from collections import Counter

import pytest

from ms_data_quality.suggest import (
    accept_model_answer,
    build_prompt,
    choose_canonical,
    get_backend,
    rules_choice,
)

VARIANTS = Counter({"Delta Logistiks": 2, "Delta Logistics": 1, "Delta Logistics BVBA": 1})


class Fake:
    name = "fake"

    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.prompts = reply, error, []

    def complete(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.reply


def test_rules_pick_the_most_frequent_spelling_even_when_it_is_a_typo():
    assert rules_choice(VARIANTS) == "Delta Logistiks"


def test_rules_prefer_a_legal_form_and_normal_casing_on_ties():
    assert rules_choice(Counter({"acme": 1, "ACME": 1, "Acme NV": 1})) == "Acme NV"


def test_model_answer_is_used_when_it_matches_a_real_spelling():
    fake = Fake("Delta Logistics BVBA\n")
    assert choose_canonical(VARIANTS, fake) == ("Delta Logistics BVBA", "model")
    assert "Delta Logistiks (2x)" in fake.prompts[0]


def test_model_may_fix_a_typo_but_not_invent_a_company():
    assert accept_model_answer('"Delta Logistics"', VARIANTS) == "Delta Logistics"
    assert accept_model_answer("Totally Different Corp", VARIANTS) is None
    assert accept_model_answer("", VARIANTS) is None
    assert accept_model_answer("x" * 200, VARIANTS) is None


@pytest.mark.parametrize("reply", ["Totally Different Corp", ""])
def test_invented_or_empty_answers_fall_back_to_rules(reply):
    assert choose_canonical(VARIANTS, Fake(reply)) == ("Delta Logistiks", "rules-fallback")


def test_a_failing_model_never_blocks_cleaning():
    result = choose_canonical(VARIANTS, Fake(error=TimeoutError("slow")))
    assert result == ("Delta Logistiks", "rules-fallback")


def test_no_backend_means_rules_and_unknown_backend_is_rejected():
    assert choose_canonical(VARIANTS, None)[1] == "rules"
    assert get_backend("rules") is None
    with pytest.raises(ValueError):
        get_backend("nonsense")


def test_prompt_lists_every_spelling_with_counts():
    prompt = build_prompt(VARIANTS)
    assert "Delta Logistics BVBA (1x)" in prompt
    assert "name only" in prompt.lower()
