import json

from hsge.webarena.predicates import (
    CommercePredicateExtractor,
    CorePredicateExtractor,
)
from remine_planning_artifacts import remine


def test_core_extracts_domain_neutral_collection_and_detail_views():
    extractor = CorePredicateExtractor()
    collection = "\n".join(f"[{i}] link 'Record {i}'" for i in range(1, 6))
    detail = "[1] heading 'Record'\n[2] StaticText 'Details and attributes'"

    assert "view:collection" in extractor.extract("https://example.test/records", collection)
    assert "view:detail" in extractor.extract("https://example.test/records/42", detail)


def test_commerce_predicates_are_canonical_across_product_urls():
    extractor = CommercePredicateExtractor()
    axtree = "[1] heading 'Product'\n[2] button 'Add to Cart'\n[3] StaticText 'SKU 42'"

    first = extractor.extract("https://shop.test/product/red.html", axtree)
    second = extractor.extract("https://shop.test/product/blue.html", axtree)

    assert "item_selected" in first
    assert first == second


def test_terminal_and_payment_predicates_require_state_evidence_not_controls():
    core = CorePredicateExtractor()
    commerce = CommercePredicateExtractor()

    assert "has_confirmation_cue" not in core.extract(
        "https://example.test/form", "[1] button 'Complete'"
    )
    assert "payment_entered" not in commerce.extract(
        "https://shop.test/checkout", "[1] heading 'Payment Method'"
    )
    assert "payment_entered" in commerce.extract(
        "https://shop.test/checkout",
        "[1] radio 'Check / Money Order' checked=true",
    )


def test_remine_does_not_invent_last_step_effect_without_final_axtree(tmp_path):
    source = tmp_path / "wa_run_20"
    episode = source / "episodes" / "ep_0000"
    state = episode / "page_state"
    state.mkdir(parents=True)
    (state / "step_000_axtree.txt").write_text(
        "[1] button 'Add to Cart'", encoding="utf-8"
    )
    (episode / "episode_meta.json").write_text(json.dumps({
        "goal": "Add the product to cart",
        "outcome": {"success": True},
        "metadata": {"tags": ["LOCAL"]},
    }), encoding="utf-8")
    (episode / "episode.jsonl").write_text(json.dumps({
        "record_type": "step",
        "index": 0,
        "parsed_action": "click('1')",
        "observation": {
            "url": "https://shop.test/product/one",
            "axtree_txt": {"path": "page_state/step_000_axtree.txt"},
        },
    }) + "\n", encoding="utf-8")
    (source / "events.jsonl").write_text(json.dumps({
        "component": "solver",
        "event": "url_discovered",
        "episode_id": 0,
        "data": {
            "source_url": "https://shop.test/product/one",
            "target_url": "https://shop.test/checkout/cart",
        },
    }) + "\n", encoding="utf-8")

    output = tmp_path / "wa_run_20_remined"
    report = remine(source, output, ["commerce"])
    evidence = json.loads((output / "planning_evidence.jsonl").read_text())

    assert report["status"] == "best_effort_incomplete"
    assert evidence["complete"] is False
    assert evidence["effects"] == []
    assert evidence["post_url"] == "https://shop.test/checkout/cart"
    assert json.loads((output / "graph.json").read_text())["high_level"]["operators"] == {}
