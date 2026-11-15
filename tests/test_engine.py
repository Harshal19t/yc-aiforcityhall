from pdcheck.check.engine import Proposal, evaluate


def ids(result):
    return {f.rule_id for f in result.findings}


def base(**kw):
    defaults = dict(
        dwelling_type="detached",
        extension_position="rear",
        storeys=1,
        height_m=3.5,
        eaves_height_m=2.8,
        rear_depth_m=3.5,
        distance_to_boundary_m=3.0,
        curtilage_cover_ratio=0.3,
        exceeds_highest_roof=False,
        exceeds_existing_eaves=False,
        beyond_principal_elevation=False,
        cladding=False,
        article_2_3_land=False,
        article_4=False,
        listed=False,
    )
    defaults.update(kw)
    return Proposal(**defaults)


def test_small_detached_rear_extension_has_no_hard_failures():
    r = evaluate(base())
    assert not any(f.outcome == "needs_permission" for f in r.findings)
    # Interpretive rules are always surfaced for review.
    assert r.status == "needs_review"


def test_semi_detached_3_5m_needs_prior_approval_route():
    r = evaluate(base(dwelling_type="semi", rear_depth_m=3.5))
    assert "rear_depth_other_basic" in ids(r)
    assert r.status == "prior_approval_possible"


def test_semi_detached_over_6m_needs_permission():
    r = evaluate(base(dwelling_type="semi", rear_depth_m=6.5))
    assert "rear_depth_other_cap" in ids(r)
    assert r.status == "needs_permission"


def test_conservation_area_rules_out_larger_extension_route():
    r = evaluate(base(dwelling_type="semi", rear_depth_m=3.5, article_2_3_land=True))
    assert "larger_extension_not_on_article_2_3_or_sssi" in ids(r)
    assert r.status == "needs_permission"


def test_side_extension_in_conservation_area_needs_permission():
    r = evaluate(base(extension_position="side", article_2_3_land=True, side_width_ratio=0.3))
    assert "article_2_3_no_side_extension" in ids(r)
    assert r.status == "needs_permission"


def test_flat_has_no_householder_rights():
    r = evaluate(base(dwelling_type="flat"))
    assert "not_a_flat" in ids(r)
    assert r.status == "needs_permission"


def test_listed_building_reports_other_consent_not_planning_failure():
    r = evaluate(base(listed=True))
    assert any(f.rule_id == "listed_building_consent" for f in r.other_consents)
    assert not any(f.rule_id == "listed_building_consent" for f in r.findings)


def test_unknown_inputs_are_reported_not_guessed():
    p = base(article_4=None)
    r = evaluate(p)
    assert "article_4" in r.unknown_fields


# --- New rules added after legislation verification (2026-11-15) ---

def test_multi_storey_rear_over_3m_needs_permission():
    """A.1(h)(i): multi-storey rear extension >3m depth always needs permission."""
    r = evaluate(base(storeys=2, rear_depth_m=3.5, distance_to_rear_boundary_m=10))
    assert "multi_storey_rear_depth_3m" in ids(r)
    assert r.status == "needs_permission"


def test_multi_storey_rear_within_7m_of_rear_boundary_needs_permission():
    """A.1(h)(ii): multi-storey rear extension within 7m of rear boundary needs permission."""
    r = evaluate(base(storeys=2, rear_depth_m=2.5, distance_to_rear_boundary_m=5))
    assert "multi_storey_rear_7m_from_boundary" in ids(r)
    assert r.status == "needs_permission"


def test_multi_storey_rear_compliant_has_no_hard_failures():
    """Multi-storey rear at 2.5m depth and 8m from rear boundary should not fail hard rules."""
    r = evaluate(base(storeys=2, rear_depth_m=2.5, distance_to_rear_boundary_m=8))
    assert "multi_storey_rear_depth_3m" not in ids(r)
    assert "multi_storey_rear_7m_from_boundary" not in ids(r)


def test_verandah_or_balcony_needs_permission():
    """A.1(k)(i): including a verandah, balcony or raised platform needs permission."""
    r = evaluate(base(includes_verandah_balcony_platform=True))
    assert "no_verandah_balcony_raised_platform" in ids(r)
    assert r.status == "needs_permission"


def test_part_20_house_blocked():
    """A.1(l): houses built under Part 20 cannot use Class A."""
    r = evaluate(base(built_under_part_20=True))
    assert "part_20_exclusion" in ids(r)
    assert r.status == "needs_permission"


def test_art_2_3_land_blocks_multi_storey_rear():
    """A.2(c): on article 2(3) land, multi-storey rear extensions need permission."""
    r = evaluate(base(storeys=2, article_2_3_land=True, rear_depth_m=2.5,
                      distance_to_rear_boundary_m=10))
    assert "article_2_3_no_multi_storey_rear" in ids(r)
    assert r.status == "needs_permission"


def test_conservation_area_renamed_rule():
    """Regression: renamed rule id still fires for conservation area + larger extension."""
    r = evaluate(base(dwelling_type="semi", rear_depth_m=3.5, article_2_3_land=True))
    assert "larger_extension_not_on_article_2_3_or_sssi" in ids(r)
    assert r.status == "needs_permission"
