"""Extract and reconcile controller changes and large-holding reports from local OpenDART."""

import argparse
import json
import re
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile

from ..config import get_paths
from .contract_pilot import TableRows, compact, date_iso, read_archive

DATE = re.compile(r"(?<!\d)(\d{4})\s*[-.년/]\s*(\d{1,2})\s*[-.월/]\s*(\d{1,2})(?!\d)")
NUMBER = re.compile(r"(?<![\d.])(?:\d{1,3}(?:,\d{3})+|\d{4,})(?![\d.%])")
LABELS = {
    "변경사유": "change_reason",
    "변경일자": "change_date",
    "변경확인일자": "confirmation_date",
    "지분인수목적": "acquisition_purpose",
    "기타투자판단과관련한중요사항": "notes",
    "정정관련공시서류제출일": "corrected_date",
    "정정대상공시서류의최초제출일": "corrected_date",
    "정정관련공시서류": "corrected_title",
    "정정대상공시서류": "corrected_title",
    "정정사유": "correction_reason",
    "관련공시": "related_filing",
    "보고사유": "report_reason",
    "변동방법": "change_method",
    "변동사유": "holding_reason",
    "보유목적": "holding_purpose",
    "보고의무발생일": "report_trigger_date",
    "보고서작성기준일": "holding_as_of",
    "보고자": "reporter",
    "발행회사명": "issuer",
}
MATCH_FIELDS = (
    "change_reason",
    "holding_reason",
    "report_reason",
    "change_method",
    "notes",
)
TRANSACTIONS = {
    "block": r"시간외대량매매",
    "transfer": r"양수도|주식매매계약|장외(?:거래|매도|매수)",
    "merger": r"흡수합병|합병",
    "inheritance": r"상속",
    "gift": r"증여",
    "issuance": r"유상증자|제3자배정",
}


def filing_type(title):
    prefixes = re.match(r"^(?:\s*\[[^]]+\])*", title).group()
    title = compact(title[len(prefixes) :])
    correction = "정정" in prefixes
    if title == "최대주주변경":
        return "controller", correction
    if title.startswith("주식등의대량보유상황보고서"):
        return "holding", correction
    return None


def parse_date(text):
    match = DATE.search(text)
    if match:
        try:
            return date(*(int(v) for v in match.groups())).isoformat()
        except ValueError:
            pass
    return None


def label(text):
    return compact(re.sub(r"^\s*\d+\.\s*", "", text))


def fact(field, cell, **extra):
    return dict(field=field, value=cell[0], line=cell[1], **extra)


class LocatedRows(TableRows):
    def __init__(self):
        super().__init__()
        self.table_stack = []
        self.row_tables = []
        self.table_number = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table_number += 1
            self.table_stack.append(self.table_number)
        super().handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "tr" and self.row is not None:
            self.row_tables.append(self.table_stack[-1] if self.table_stack else 0)
        if tag == "table" and self.table_stack:
            self.table_stack.pop()
        super().handle_endtag(tag)


def fields_from_rows(rows, kind, correction):
    facts = []
    phase = scope = None
    correction_table = None
    for table, row in rows:
        texts = [cell[0] for cell in row]
        keys = [label(text) for text in texts]
        if not keys:
            continue
        if correction and "정정전" in keys and "정정후" in keys:
            correction_table = table
            continue
        first = keys[0]
        controller_phase = next(
            (key for key in keys[:2] if key in ("변경전", "변경후")), None
        )
        if kind == "controller" and controller_phase and len(row) >= 3:
            phase = "before" if controller_phase == "변경전" else "after"
            scope = "group" if "최대주주등" in keys[:-1] else "individual"
            facts.append(fact("controller_name", row[-1], phase=phase, scope=scope))
        elif (
            kind == "controller"
            and phase
            and len(row) == 2
            and first in ("소유주식수주", "소유비율")
        ):
            field = "shares" if first == "소유주식수주" else "ratio"
            facts.append(fact(field, row[1], phase=phase, scope=scope))
        elif table == correction_table and first and len(row) >= 3:
            facts.append(
                fact(
                    "correction_item",
                    row[0],
                    before=texts[-2],
                    after=texts[-1],
                    before_line=row[-2][1],
                    after_line=row[-1][1],
                )
            )
        if kind == "holding":
            if first in ("직전보고서", "이번보고서") and len(row) in (8, 9):
                phase = "previous_report" if first == "직전보고서" else "current_report"
                offset = len(row) - 8
                if offset:
                    facts.append(fact("holding_observation_date", row[1], phase=phase))
                for name, i, security in (
                    ("reported_holder", 1, None),
                    ("shares", 3, "shares_etc"),
                    ("ratio", 4, "shares_etc"),
                    ("shares", 5, "share_certificates"),
                    ("ratio", 6, "share_certificates"),
                    ("issued_shares", 7, None),
                ):
                    facts.append(
                        fact(
                            name,
                            row[i + offset],
                            phase=phase,
                            scope="reporting_group",
                            security=security,
                        )
                    )
            if len(row) >= 8 and first in ("보고자", "특별관계자"):
                # Skip personal identifiers in the adjacent source cell.
                facts.append(
                    fact(
                        "holding_party", row[1], role=first, holding_row_line=row[0][1]
                    )
                )
            movement = next(
                (
                    i
                    for i, key in enumerate(keys)
                    if i >= 2
                    and parse_date(texts[i - 1])
                    and re.search(
                        r"매수|매도|신규보고|장외거래|시간외|취득|처분|상속|증여|수증|명의개서|분할|계약이행",
                        key,
                    )
                ),
                None,
            )
            if movement is not None and len(row) >= movement + 6:
                i = movement
                facts.append(
                    fact(
                        "holding_movement",
                        row[i],
                        party=texts[0],
                        transaction_date=parse_date(texts[i - 1]),
                        security=texts[i + 1],
                        before=texts[i + 2],
                        delta=texts[i + 3],
                        after=texts[i + 4],
                        price=texts[i + 5],
                        note=texts[-1] if len(row) > i + 6 else "",
                        note_line=row[-1][1] if len(row) > i + 6 else None,
                    )
                )
        if any(
            re.search(r"양도인|양수인|거래종결일|매매상대방", text) for text in texts
        ):
            for cell in row:
                if re.search(
                    r"양도인\s*[:：]|양수인\s*[:：]|거래종결일\s*[:：]|매매상대방\s*[:：]",
                    cell[0],
                ):
                    facts.append(fact("transaction_note", cell))
        for i, key in enumerate(keys[:-1]):
            if key in LABELS and texts[i + 1] not in ("", "-", "－"):
                if key == "보고자" and len(row) > 3:
                    continue
                item = fact(LABELS[key], row[i + 1])
                if item["field"] in ("related_filing", "corrected_title"):
                    item["references"] = sorted(
                        set(
                            re.findall(
                                r"(?<!\d)\d{14}(?!\d)",
                                " ".join([texts[i + 1], *row[i + 1][2]]),
                            )
                        )
                    )
                facts.append(item)
    return facts


def values(document, *fields):
    return [f for f in document["facts"] if f["field"] in fields]


def first_date(document, field):
    return next(
        (parsed for f in values(document, field) if (parsed := parse_date(f["value"]))),
        None,
    )


def extract(row, path):
    kind, correction = filing_type(row["report_nm"])
    receipt = row["rcept_no"]
    document, member, digest = read_archive(path, receipt)
    parser = LocatedRows()
    parser.feed(document)
    facts = fields_from_rows(zip(parser.row_tables, parser.rows), kind, correction)
    return {
        "receipt": receipt,
        "corp_code": row["corp_code"],
        "company": row["corp_name"],
        "submitter": row.get("flr_nm", ""),
        "filed": date_iso(row["rcept_dt"]),
        "title": row["report_nm"],
        "kind": kind,
        "correction": correction,
        "archive": str(path),
        "member": member,
        "sha256": digest,
        "facts": facts,
    }


def correction_target(document, peers):
    label_facts = values(document, "corrected_title", "corrected_date")
    explicit = {
        ref
        for f in values(document, "corrected_title")
        for ref in f.get("references", [])
    }
    day = first_date(document, "corrected_date")
    eligible = [
        d
        for d in peers
        if d["receipt"] != document["receipt"]
        and d["filed"] <= document["filed"]
        and (
            document["kind"] == "controller"
            or compact(d["submitter"]) == compact(document["submitter"])
        )
    ]
    if explicit:
        candidates = [d for d in eligible if d["receipt"] in explicit]
        reason = "explicit_receipt"
    else:
        candidates = [d for d in eligible if not d["correction"] and d["filed"] == day]
        reason = "unique_original_on_stated_date"
    target = candidates[0] if len(candidates) == 1 else None
    if not target and not candidates and document["kind"] == "controller":
        event_day = first_date(document, "change_date")
        candidates = [
            d
            for d in eligible
            if not d["correction"]
            and event_day
            and first_date(d, "change_date") == event_day
        ]
    return {
        "receipt": document["receipt"],
        "target": target["receipt"] if target else None,
        "candidates": sorted(d["receipt"] for d in candidates),
        "status": "linked" if target else "unresolved",
        "reason": reason if target else "missing_or_conflicting_correction_target",
        "evidence": label_facts,
    }


def name_key(text):
    return compact(
        text.replace("(주)", "").replace("㈜", "").replace("주식회사", "")
    ).lower()


def quantity_deltas(document):
    for f in values(document, "correction_item"):
        old = [int(n.replace(",", "")) for n in NUMBER.findall(f["before"])]
        new = [int(n.replace(",", "")) for n in NUMBER.findall(f["after"])]
        if len(old) == len(new):
            for a, b in zip(old, new):
                if a != b:
                    yield b - a, f


def link_evidence(document, facts):
    return [
        {"receipt": document["receipt"], "line": f["line"], "field": f["field"]}
        for f in facts
    ]


def classify(event, holding, event_corrections, holding_original):
    event_facts = values(event, *MATCH_FIELDS, "controller_name")
    holding_facts = values(holding, *MATCH_FIELDS)
    event_text = compact(" ".join(f["value"] for f in event_facts))
    holding_text = compact(" ".join(f["value"] for f in holding_facts))
    if not event_text or not holding_text:
        return (
            "unresolved",
            "missing_transaction_description",
            [(event, event_facts), (holding, holding_facts)],
        )
    evidence = [(event, event_facts), (holding, holding_facts)]
    holding_reason = compact(
        " ".join(
            f["value"]
            for f in values(holding, "report_reason", "holding_reason", "change_method")
        )
    )
    reasons = {
        compact(f["value"])
        for f in values(holding, "report_reason", "holding_reason", "change_method")
    }
    if (
        "담보" not in event_text
        and reasons
        and all(
            re.fullmatch(r"(?:주식)?담보계약(?:의)?(?:변경|해소|체결)(?:보고)?", r)
            for r in reasons
        )
    ):
        return "separate_event", "report_explicitly_describes_a_pledge_only", evidence

    event_numbers = {f["value"].replace(",", "") for f in values(event, "shares")}
    event_numbers.update(
        n.replace(",", "")
        for f in values(event, "notes")
        for n in NUMBER.findall(f["value"])
    )
    holdings = values(holding, "shares", "holding_movement")
    holding_numbers = {
        f["value"].replace(",", "") for f in holdings if f["field"] == "shares"
    }
    holding_numbers.update(
        f[k].replace(",", "").lstrip("+-")
        for f in holdings
        if f["field"] == "holding_movement"
        for k in ("before", "after", "delta")
    )
    common_quantity = any(
        n.isdigit() and int(n) > 0 for n in event_numbers & holding_numbers
    )
    parties = {
        name_key(re.split(r"\s*외\s*(?:특수관계인\s*)?\d+", f["value"])[0])
        for f in values(event, "controller_name")
    }
    parties.discard("")
    holding_party = name_key(holding["submitter"])
    party_matches = holding_party in parties or any(
        len(p) >= 3 and p in name_key(holding_text) for p in parties
    )
    transaction = next(
        (
            key
            for key, pattern in TRANSACTIONS.items()
            if re.search(pattern, event_text) and re.search(pattern, holding_text)
        ),
        None,
    )

    if holding_original and "장내매수" in holding_reason:
        previous = {
            (f.get("phase"), f.get("security")): f
            for f in values(holding_original, "shares")
        }
        current = {
            f.get("security"): f
            for f in values(holding, "shares")
            if f.get("phase") == "current_report"
        }
        for h in current.values():
            old = previous.get((h["phase"], h["security"]))
            a, b = (str(f["value"]).replace(",", "") if f else "" for f in (old, h))
            if not (a.isdigit() and b.isdigit()):
                continue
            for correction in event_corrections:
                for delta, item in quantity_deltas(correction):
                    if (
                        delta == int(b) - int(a)
                        and party_matches
                        and a in event_numbers
                    ):
                        return (
                            "quantity_support",
                            "matching_corrected_quantity_delta",
                            evidence
                            + [
                                (correction, [item]),
                                (holding_original, [old]),
                                (holding, [h]),
                            ],
                        )
    if transaction and common_quantity and party_matches:
        return (
            "same_transaction",
            "matching_party_transaction_type_and_share_quantity",
            evidence
            + [(event, values(event, "shares", "change_date")), (holding, holdings)],
        )
    return "unresolved", "insufficient_evidence_for_same_transaction", evidence


def classify_detailed(event, holding):
    """Match explicit cross-filing references or dated, scoped transaction evidence."""
    event_reason = compact(" ".join(f["value"] for f in values(event, "change_reason")))
    report_reason = compact(
        " ".join(f["value"] for f in values(holding, *MATCH_FIELDS))
    )
    shared_reason = any(
        re.search(pattern, event_reason) and re.search(pattern, report_reason)
        for pattern in (*TRANSACTIONS.values(), r"분할", r"공개매수", r"장내매수")
    )
    event_dates = {first_date(event, "change_date")} - {None}
    event_fields = values(
        event,
        "change_reason",
        "change_date",
        "controller_name",
        "notes",
        "transaction_note",
    )
    notes = values(event, "change_reason", "notes", "transaction_note")
    event_text = " ".join(f["value"] for f in event_fields)
    holding_fields = values(holding, *MATCH_FIELDS, "report_trigger_date")
    holding_text = " ".join(f["value"] for f in holding_fields)
    parties = {
        name_key(re.split(r"\s*(?:외|外)\s*(?:특수관계인\s*)?\d+", f["value"])[0])
        for f in values(event, "controller_name")
    } - {""}
    amounts = {f["value"].replace(",", "") for f in values(event, "shares")}
    amounts.update(
        n.replace(",", "")
        for f in notes
        for n in re.findall(r"([0-9][0-9,]*)\s*주(?:를|가|의|\b)", f["value"])
    )
    report_date = first_date(holding, "report_trigger_date")
    scoped_quantities = {f["value"].replace(",", "") for f in values(holding, "shares")}
    reference_temporal_evidence = (
        report_date in event_dates
        or any(
            m["transaction_date"] in event_dates
            for m in values(holding, "holding_movement")
        )
        or (
            any(
                re.search(p, event_reason) and re.search(p, report_reason)
                for p in (r"합병", r"분할")
            )
            and bool(
                {n for n in amounts & scoped_quantities if n.isdigit() and int(n) > 0}
            )
            and report_date is not None
            and any(
                abs((date.fromisoformat(report_date) - date.fromisoformat(day)).days)
                <= 7
                for day in event_dates
            )
        )
    )
    for source, target in ((event, holding), (holding, event)):
        for reference in values(source, "related_filing"):
            if (
                shared_reason
                and reference_temporal_evidence
                and target["receipt"] in reference.get("references", [])
                and (
                    "최대주주변경" in compact(reference["value"])
                    or "주식등의대량보유" in compact(reference["value"])
                )
            ):
                return (
                    "same_transaction",
                    "explicit_transaction_filing_reference",
                    [
                        (source, [reference]),
                        (event, event_fields),
                        (holding, holding_fields + values(holding, "shares")),
                    ],
                )
    issuer_party = name_key(holding["submitter"])
    if (
        issuer_party in parties
        and first_date(holding, "report_trigger_date") in event_dates
        and any(
            re.search(p, event_text) and re.search(p, holding_text)
            for p in (r"합병", r"분할", r"공개매수")
        )
        and any(
            f["value"].replace(",", "") in amounts
            and f["value"].replace(",", "").isdigit()
            and int(f["value"].replace(",", "")) > 0
            for f in values(holding, "shares")
        )
    ):
        return (
            "same_transaction",
            "matching_event_type_trigger_date_party_and_holding",
            [
                (event, event_fields),
                (holding, holding_fields + values(holding, "shares")),
            ],
        )
    for movement in values(holding, "holding_movement"):
        if movement["transaction_date"] not in event_dates:
            continue
        delta = movement["delta"].replace(",", "").lstrip("+-")
        if not delta.isdigit() or int(delta) <= 0 or delta not in amounts:
            continue
        actor = name_key(movement["party"])
        note = name_key(movement["note"])
        counterparty = any(len(p) >= 2 and p != actor and p in note for p in parties)
        if (
            actor in parties
            and counterparty
            and re.search(r"매수|매도|매매|취득|처분", movement["value"])
        ):
            return (
                "same_transaction",
                "matching_transaction_row_parties_quantity_and_date",
                [
                    (event, event_fields + values(event, "shares")),
                    (holding, [movement]),
                ],
            )
    return None


def build(documents, window_days=35, *, detailed=True):
    if window_days < 0:
        raise ValueError("window-days must be nonnegative")
    extracted = {}
    failures = []
    counts = Counter()
    documents = sorted(documents, key=lambda item: item[0]["rcept_no"])
    for row, path in documents:
        kind, _correction = filing_type(row["report_nm"])
        receipt = row["rcept_no"]
        counts[kind + "_title_candidates"] += 1
        if not path.is_file():
            counts[kind + "_missing_archive"] += 1
            continue
        try:
            document = extract(row, path)
        except (ValueError, OSError, BadZipFile) as error:
            failures.append({"receipt": receipt, "error": str(error)})
            counts[kind + "_archive_error"] += 1
            continue
        counts[kind + "_read"] += 1
        if not document["facts"]:
            counts[kind + "_no_fields"] += 1
        extracted[receipt] = document
    dates = [date_iso(row["rcept_dt"]) for row, _ in documents]
    return reconcile(
        extracted.values(),
        counts,
        {"start": min(dates, default=None), "end": max(dates, default=None)},
        failures,
        window_days,
        detailed=detailed,
    )


def reconcile(documents, counts, filing_dates, failures, window_days, *, detailed=True):
    extracted = {doc["receipt"]: doc for doc in documents}
    groups = defaultdict(list)
    for document in extracted.values():
        groups[document["corp_code"], document["kind"]].append(document)
    events, corrections, links = [], [], []
    targets = {}
    corrections_by_target = defaultdict(list)
    for (company, kind), peers in groups.items():
        for document in peers:
            if document["correction"]:
                decision = correction_target(document, peers)
                corrections.append(dict(kind=kind, **decision))
                if decision["target"]:
                    targets[document["receipt"]] = decision["target"]
                    corrections_by_target[decision["target"]].append(document)
                elif kind == "controller":
                    for candidate in decision["candidates"]:
                        links.append(
                            {
                                "event_receipt": candidate,
                                "related_receipt": document["receipt"],
                                "classification": "unresolved",
                                "reason": decision["reason"],
                                "evidence": link_evidence(
                                    document, decision["evidence"]
                                ),
                            }
                        )
            elif kind == "controller":
                events.append(
                    {
                        "id": "controller:" + document["receipt"],
                        "receipt": document["receipt"],
                        "corp_code": company,
                        "change_date": first_date(document, "change_date"),
                    }
                )

    holding_indexes = {}
    for (company, kind), peers in groups.items():
        if kind == "holding":
            ordered = sorted(peers, key=lambda d: (d["filed"], d["receipt"]))
            holding_indexes[company] = (
                [date.fromisoformat(d["filed"]).toordinal() for d in ordered],
                ordered,
            )
    for event in events:
        document = extracted[event["receipt"]]
        days, peers = holding_indexes.get(event["corp_code"], ([], []))
        centers = [
            date.fromisoformat(d).toordinal()
            for d in (event["change_date"], document["filed"])
            if d
        ]
        indices = set()
        for center in centers:
            indices.update(
                range(
                    bisect_left(days, center - window_days),
                    bisect_right(days, center + window_days),
                )
            )
        related = corrections_by_target[event["receipt"]]
        for i in sorted(indices):
            holding = peers[i]
            label, reason, sources = classify(
                document,
                holding,
                related,
                extracted.get(targets.get(holding["receipt"])),
            )
            if (
                label == "same_transaction"
                and min(abs(days[i] - center) for center in centers) > 7
            ):
                label, reason = "unresolved", "outside_seven_day_transaction_gate"
            if detailed and label == "unresolved":
                detail = classify_detailed(document, holding)
                if detail:
                    label, reason, sources = detail
            links.append(
                {
                    "event_receipt": event["receipt"],
                    "related_receipt": holding["receipt"],
                    "classification": label,
                    "reason": reason,
                    "evidence": [
                        item
                        for source, facts in sources
                        for item in link_evidence(source, facts)
                    ],
                }
            )

    positive = Counter(
        link["related_receipt"]
        for link in links
        if link["classification"] in ("same_transaction", "quantity_support")
    )
    for link in links:
        if positive[link["related_receipt"]] > 1 and link["classification"] in (
            "same_transaction",
            "quantity_support",
        ):
            link.update(
                classification="unresolved",
                reason="multiple_competing_controller_events",
            )
    pair_counts = Counter(link["classification"] for link in links)
    matched = [
        link
        for link in links
        if link["classification"] in ("same_transaction", "quantity_support")
    ]
    summary = {
        "documents": dict(counts),
        "candidate_filing_dates": filing_dates,
        "controller_events": len(events),
        "controller_companies": len({event["corp_code"] for event in events}),
        "correction_counts": {
            kind: dict(Counter(d["status"] for d in corrections if d["kind"] == kind))
            for kind in ("controller", "holding")
        },
        "pair_counts": {
            name: pair_counts[name]
            for name in (
                "same_transaction",
                "quantity_support",
                "separate_event",
                "unresolved",
            )
        },
        "matched_controller_events": len({link["event_receipt"] for link in matched}),
        "matched_holding_filings": len({link["related_receipt"] for link in matched}),
        "window_days": window_days,
        "transaction_gate_days": 7,
    }
    return {
        "summary": summary,
        "documents": list(extracted.values()),
        "events": events,
        "corrections": corrections,
        "links": links,
        "failures": failures,
    }


def collection_documents(collections):
    candidates = {}
    roots = sorted(set(collections))
    for root in roots:
        index = root / "filings.json"
        if index.is_file():
            rows = json.loads(index.read_text())
        else:
            rows = [
                row
                for path in sorted((root / "daily_indexes").glob("*.json"))
                for row in json.loads(path.read_text())["filings"]
            ]
            rows.extend(
                row
                for path in sorted((root / "raw" / "list.json").glob("*.json"))
                for row in json.loads(path.read_text())
                .get("payload", {})
                .get("list", [])
            )
        for row in rows:
            receipt = row.get("rcept_no", "")
            company = row.get("corp_code", "")
            if not (
                re.fullmatch(r"\d{14}", receipt)
                and re.fullmatch(r"\d{8}", company)
                and filing_type(row.get("report_nm", ""))
            ):
                continue
            path = root / "documents" / company / (receipt + ".zip")
            if receipt not in candidates or (
                path.is_file() and not candidates[receipt][1].is_file()
            ):
                candidates[receipt] = row, path
    # A receipt in the catalogue can also have a package from an incremental run.
    for receipt, (row, path) in candidates.items():
        if not path.is_file():
            for root in roots:
                alternative = root / "documents" / row["corp_code"] / path.name
                if alternative.is_file():
                    path = alternative
                    break
        yield row, path


def main():
    paths = get_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collection",
        type=Path,
        action="append",
        help="Repeatable input collection or run directory",
    )
    parser.add_argument("--window-days", type=int, default=35)
    parser.add_argument(
        "--baseline", action="store_true", help="Use the original linking rules"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=paths.artifacts / "control_ownership" / "snapshot.json",
    )
    args = parser.parse_args()
    roots = args.collection or list((paths.raw / "collections").glob("*")) + list(
        (paths.raw / "runs").glob("*")
    )
    documents = list(collection_documents(roots))
    if not documents:
        raise ValueError("No matching OpenDART index entries found")
    result = build(documents, args.window_days, detailed=not args.baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=args.output.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            json.dump(result, output, ensure_ascii=False)
            output.write("\n")
        temporary.replace(args.output)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
