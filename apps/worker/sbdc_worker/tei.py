import re
import xml.etree.ElementTree as ET
from typing import Any

import fitz


NS = {"tei": "http://www.tei-c.org/ns/1.0"}
SPACE_RE = re.compile(r"\s+")


def clean_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return SPACE_RE.sub(" ", "".join(element.itertext())).strip()


def first_text(root: ET.Element, paths: list[str]) -> str | None:
    for path in paths:
        value = clean_text(root.find(path, NS))
        if value:
            return value
    return None


def parse_coords(value: str | None) -> tuple[int | None, list[float] | None]:
    if not value:
        return None, None
    boxes = []
    for item in value.split(";"):
        parts = item.split(",")
        if len(parts) != 5:
            continue
        try:
            page = int(parts[0])
            x, y, width, height = (float(number) for number in parts[1:])
        except ValueError:
            continue
        boxes.append((page, [x, y, x + width, y + height]))
    if not boxes:
        return None, None
    page = boxes[0][0]
    same_page = [box for box_page, box in boxes if box_page == page]
    return page, [
        min(box[0] for box in same_page),
        min(box[1] for box in same_page),
        max(box[2] for box in same_page),
        max(box[3] for box in same_page),
    ]


def element_location(element: ET.Element) -> tuple[int | None, list[float] | None]:
    page, bbox = parse_coords(element.attrib.get("coords"))
    if page:
        return page, bbox
    for child in element.iter():
        page, bbox = parse_coords(child.attrib.get("coords"))
        if page:
            return page, bbox
    return None, None


def locate_text(pdf: fitz.Document, text: str) -> tuple[int | None, list[float] | None]:
    needle = SPACE_RE.sub(" ", text).strip()[:120]
    candidates = [needle, needle[:80], needle[:50]]
    for page_index in range(pdf.page_count):
        page = pdf[page_index]
        for candidate in candidates:
            if len(candidate) < 20:
                continue
            matches = page.search_for(candidate)
            if matches:
                rect = matches[0]
                return page_index + 1, [rect.x0, rect.y0, rect.x1, rect.y1]
    return None, None


def author_names(element: ET.Element) -> list[str]:
    result: list[str] = []
    for author in element.findall(".//tei:author", NS):
        person = author.find(".//tei:persName", NS)
        parts = []
        if person is not None:
            parts.extend(clean_text(item) for item in person.findall("tei:forename", NS))
            surname = clean_text(person.find("tei:surname", NS))
            if surname:
                parts.append(surname)
        name = " ".join(filter(None, parts)) or clean_text(person) or clean_text(author)
        if name and name not in result:
            result.append(name)
    return result


def parse_tei(tei: bytes, pdf_bytes: bytes) -> dict[str, Any]:
    root = ET.fromstring(tei)
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        title = first_text(
            root,
            [
                ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title[@type='main']",
                ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title",
            ],
        )
        header = root.find(".//tei:teiHeader", NS)
        authors = author_names(header) if header is not None else []
        abstract = first_text(root, [".//tei:teiHeader/tei:profileDesc/tei:abstract"])
        language = root.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")

        sections: list[dict[str, Any]] = []
        for index, div in enumerate(root.findall(".//tei:text/tei:body/tei:div", NS), start=1):
            heading = clean_text(div.find("tei:head", NS)) or f"未命名章节 {index}"
            paragraphs: list[dict[str, Any]] = []
            for paragraph in div.findall("tei:p", NS):
                text = clean_text(paragraph)
                if not text:
                    continue
                page, bbox = element_location(paragraph)
                if page is None:
                    page, bbox = locate_text(pdf, text)
                paragraphs.append({"text": text, "page": page, "bbox": bbox})
            if not paragraphs:
                text = " ".join(filter(None, (clean_text(p) for p in div.findall(".//tei:p", NS))))
                if text:
                    page, bbox = locate_text(pdf, text)
                    paragraphs.append({"text": text, "page": page, "bbox": bbox})
            first_located = next((item for item in paragraphs if item["page"] is not None), None)
            sections.append(
                {
                    "ordinal": index,
                    "heading": heading,
                    "page": first_located["page"] if first_located else None,
                    "bbox": first_located["bbox"] if first_located else None,
                    "paragraphs": paragraphs,
                }
            )

        references: list[dict[str, Any]] = []
        for ordinal, bibl in enumerate(root.findall(".//tei:listBibl/tei:biblStruct", NS), start=1):
            analytic = bibl.find("tei:analytic", NS)
            monogr = bibl.find("tei:monogr", NS)
            raw = first_text(bibl, ["tei:note[@type='raw_reference']"]) or clean_text(bibl)
            ref_title = first_text(
                bibl,
                ["tei:analytic/tei:title[@level='a']", "tei:analytic/tei:title", "tei:monogr/tei:title"],
            )
            authors_node = analytic if analytic is not None else monogr
            ref_authors = author_names(authors_node) if authors_node is not None else []
            date = bibl.find(".//tei:date", NS)
            year = date.attrib.get("when") if date is not None else None
            if year and len(year) >= 4:
                year = year[:4]
            venue = first_text(bibl, ["tei:monogr/tei:title"])
            doi = None
            for identifier in bibl.findall(".//tei:idno", NS):
                if identifier.attrib.get("type", "").upper() == "DOI":
                    doi = clean_text(identifier)
                    break
            page, bbox = element_location(bibl)
            parsed = bool(ref_title or (ref_authors and year))
            references.append(
                {
                    "ordinal": ordinal,
                    "raw_citation": raw or f"参考文献 {ordinal}",
                    "title": ref_title,
                    "authors": ref_authors,
                    "year": year,
                    "venue": venue,
                    "doi": doi,
                    "parse_status": "parsed" if parsed else "failed",
                    "failure_reason": None if parsed else "bibliographic_fields_missing",
                    "confidence": 1.0 if ref_title and ref_authors else (0.7 if parsed else 0.0),
                    "page": page,
                    "bbox": bbox,
                }
            )

        page_map = [
            {"page": number + 1, "width": pdf[number].rect.width, "height": pdf[number].rect.height}
            for number in range(pdf.page_count)
        ]
    return {
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "language": language,
        "sections": sections,
        "references": references,
        "page_map": page_map,
    }
