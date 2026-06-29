"""Composable, versioned predicate extraction for operator planning."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlparse


CORE_PREDICATES = frozenset({
    "has_search_input", "has_form_input", "has_filter_or_sort", "has_menu",
    "has_feedback", "has_numeric_content", "has_record_status",
    "has_progress_control", "has_confirmation_cue", "view:collection",
    "view:detail",
})
COMMERCE_PREDICATES = frozenset({
    "results_shown", "item_selected", "cart_nonempty", "on_cart",
    "on_checkout", "payment_entered", "order_confirmed",
})


class PredicateExtractor(Protocol):
    schema_version: str
    terminal_predicates: frozenset[str]

    def extract(self, url: str, axtree: str = "") -> set[str]: ...


@dataclass(frozen=True)
class CorePredicateExtractor:
    schema_version: str = "core-v2"
    terminal_predicates: frozenset[str] = frozenset({"has_confirmation_cue"})

    def extract(self, url: str, axtree: str = "") -> set[str]:
        p: set[str] = set()
        ax = (axtree or "").lower()
        lines = [line.strip() for line in ax.splitlines() if line.strip()]
        link_count = sum(bool(re.search(r"\b(link|listitem|row)\b", line)) for line in lines)
        rules = {
            "has_search_input": r"\b(searchbox|search)\b",
            "has_form_input": r"\b(textbox|combobox|checkbox|radio|spinbutton)\b",
            "has_filter_or_sort": r"\b(sort|filter|facet|refine)\b",
            "has_menu": r"\b(menuitem|haspopup|expanded=true|submenu)\b",
            "has_feedback": r"\b(review|rating|feedback|comment|discussion|stars?)\b",
            "has_numeric_content": r"\$|amount|cost|total|date|percent|%|\b\d+(?:[.,]\d+)?\b",
            "has_record_status": r"\b(status|history|record|request|case|incident|ticket|order)\b",
            "has_progress_control": r"\b(next|continue|confirm|finish|complete|submit|save|apply)\b",
        }
        for predicate, pattern in rules.items():
            if re.search(pattern, ax):
                p.add(predicate)
        confirmation_text = "\n".join(
            line for line in lines
            if not re.search(r"\b(button|link|textbox|checkbox|radio|menuitem)\b", line)
        )
        if re.search(
            r"\b(success|successful|saved|submitted|confirmed|completed|thank you)\b",
            confirmation_text,
        ):
            p.add("has_confirmation_cue")
        if link_count >= 4 or ("has_filter_or_sort" in p and link_count >= 2):
            p.add("view:collection")
        if re.search(r"\bheading\b", ax) and re.search(
            r"\b(details?|description|properties|attributes?|metadata)\b", ax
        ):
            p.add("view:detail")
        return p


@dataclass(frozen=True)
class CommercePredicateExtractor:
    schema_version: str = "commerce-v1"
    terminal_predicates: frozenset[str] = frozenset({"order_confirmed"})

    def extract(self, url: str, axtree: str = "") -> set[str]:
        p: set[str] = set()
        path = urlparse(url or "").path.lower()
        ax = (axtree or "").lower()
        if re.search(r"catalogsearch|/search|search-results?|product_list", path) or (
            re.search(r"\b(sort by|filter|items? found|search results?)\b", ax)
            and len(re.findall(r"\blink\b", ax)) >= 2
        ):
            p.add("results_shown")
        detail = bool(re.search(
            r"\b(add to cart|add to basket|quantity|sku|product details?|product description)\b",
            ax,
        ))
        listing = bool(re.search(r"\b(sort by|filter|items? found|search results?)\b", ax))
        if detail and not listing and not re.search(r"/(cart|checkout)(/|$)", path):
            p.add("item_selected")
        cart_count = re.search(
            r"(?:cart|basket)[^\n]{0,50}(?:count|items?)?[^\n]{0,20}\b([1-9]\d*)\b",
            ax,
        )
        if cart_count or re.search(r"\badded to (?:your )?(?:cart|basket)\b", ax):
            p.add("cart_nonempty")
        if re.search(r"/(checkout/)?cart(?:/|$)", path) or re.search(
            r"\b(shopping cart|your cart|basket summary)\b", ax
        ):
            p.add("on_cart")
        cart_empty = bool(re.search(
            r"\b(?:cart|basket) is empty\b|\bno items? in (?:your )?(?:cart|basket)\b",
            ax,
        ))
        if (
            "on_cart" in p
            and not cart_empty
            and re.search(r"\b(product|item|subtotal|quantity)\b", ax)
        ):
            p.add("cart_nonempty")
        if (
            re.search(r"/checkout(?:/|$)", path) and "on_cart" not in p
        ) or re.search(r"\b(shipping address|billing address|payment method|order review)\b", ax):
            p.add("on_checkout")
        if "on_checkout" in p and re.search(
            r"(?:payment|card|money order)[^\n]{0,100}"
            r"(?:checked\s*=\s*true|selected\s*=\s*true|ending in|\*{4}|•{2,})|"
            r"(?:checked\s*=\s*true|selected\s*=\s*true)[^\n]{0,100}"
            r"(?:payment|card|money order)",
            ax,
        ):
            p.add("payment_entered")
        if re.search(r"/(success|confirmation)(?:/|$)", path) or re.search(
            r"\b(thank you for your (?:purchase|order)|order (?:number|confirmation)|order has been placed)\b",
            ax,
        ):
            p.add("order_confirmed")
        return p


@dataclass(frozen=True)
class CompositePredicateExtractor:
    extractors: tuple[PredicateExtractor, ...] = field(
        default_factory=lambda: (CorePredicateExtractor(),)
    )

    @property
    def schema_version(self) -> str:
        return "+".join(extractor.schema_version for extractor in self.extractors)

    @property
    def terminal_predicates(self) -> frozenset[str]:
        return frozenset(p for extractor in self.extractors for p in extractor.terminal_predicates)

    def extract(self, url: str, axtree: str = "") -> set[str]:
        out: set[str] = set()
        for extractor in self.extractors:
            out |= extractor.extract(url, axtree)
        return out


def build_predicate_extractor(plugins=None) -> CompositePredicateExtractor:
    names = [str(name).lower() for name in (plugins or []) if str(name).lower() != "auto"]
    unknown = sorted(set(names) - {"commerce"})
    if unknown:
        raise ValueError(f"unknown predicate plugin(s): {', '.join(unknown)}")
    extractors: list[PredicateExtractor] = [CorePredicateExtractor()]
    if "commerce" in names:
        extractors.append(CommercePredicateExtractor())
    return CompositePredicateExtractor(tuple(extractors))


DEFAULT_EXTRACTOR = build_predicate_extractor()
PREDICATES = CORE_PREDICATES
TERMINALS: dict[str, dict[str, str | None]] = {}


def predicates_from(url, axtree="", extractor: PredicateExtractor | None = None) -> set[str]:
    return (extractor or DEFAULT_EXTRACTOR).extract(url, axtree)


def reached(goal, url, axtree="", extractor: PredicateExtractor | None = None) -> bool:
    if not goal:
        return False
    active = extractor or DEFAULT_EXTRACTOR
    spec = TERMINALS.get(goal)
    if not spec:
        return goal in active.extract(url, axtree)
    ok = bool(re.search(spec["url"], url))
    if spec["text"]:
        ok = ok and spec["text"] in (axtree or "").lower()
    return ok
