from __future__ import annotations

import pytest

from app.services.roles import (
    ALL_FAMILY_KEYS,
    catalog,
    is_tech_title,
    matches_roles,
    matching_families,
    search_phrases_for,
    split_role_values,
)


@pytest.mark.parametrize(
    ("title", "family"),
    [
        ("Senior Backend Engineer", "backend"),
        ("Front-End Developer", "frontend"),
        ("Full Stack Engineer", "full-stack"),
        ("Software Engineer, Payments", "software-engineer"),
        ("Python Developer", "software-engineer"),
        ("iOS Engineer", "mobile"),
        ("Site Reliability Engineer", "devops"),
        ("Platform Engineer", "devops"),
        ("Data Analyst", "data"),
        ("Machine Learning Engineer", "ml-ai"),
        ("AI Engineer", "ml-ai"),
        ("Senior Product Designer", "design"),
        ("Technical Program Manager", "product"),
        ("QA Automation Engineer", "qa"),
        ("Application Security Engineer", "security"),
        ("Technical Writer", "devrel-docs"),
        ("Solutions Engineer", "support"),
        ("Engineering Manager", "engineering-management"),
        ("Firmware Engineer", "embedded"),
        ("Gameplay Programmer", "game"),
        ("Solidity Developer", "web3"),
    ],
)
def test_tech_titles_are_recognised(title: str, family: str) -> None:
    assert family in matching_families(title)
    assert is_tech_title(title)


@pytest.mark.parametrize(
    "title",
    ["Account Executive", "Sales Manager", "Marketing Manager", "Recruiter", "Business Developer",
     "AI Sales Manager", "Designer", "Office Manager", ""],
)
def test_non_tech_titles_are_not_tech(title: str) -> None:
    assert not is_tech_title(title)


def test_matches_roles_uses_selected_families_only() -> None:
    assert matches_roles("Backend Engineer", ["backend", "full-stack"])
    assert not matches_roles("DevOps Engineer", ["backend", "full-stack"])
    assert matches_roles("DevOps Engineer", ["devops"])


def test_empty_selection_means_every_tech_role_but_not_other_jobs() -> None:
    assert matches_roles("Data Engineer", [])
    assert matches_roles("QA Engineer", None)
    assert not matches_roles("Account Executive", [])


def test_custom_keywords_and_legacy_free_text() -> None:
    assert matches_roles("Technical Recruiter", [], ["recruiter"])
    assert not matches_roles("Backend Engineer", [], ["recruiter"])  # custom words replace "all tech"
    assert matches_roles("Cloud Wizard", ["wizard"])  # free text kept from older profiles


def test_split_role_values_separates_keys_from_free_text() -> None:
    assert split_role_values(["Backend", "full-stack", "  ", "wizard", "backend"]) == (
        ["backend", "full-stack"],
        ["wizard"],
    )


def test_search_phrases_and_catalog() -> None:
    assert search_phrases_for(["backend"]) == ["backend engineer", "backend developer"]
    assert len(search_phrases_for([])) > 20
    assert [item["key"] for item in catalog()] == list(ALL_FAMILY_KEYS)
