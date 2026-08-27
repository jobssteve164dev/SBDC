import fitz
import pytest

from sbdc_api.storage import source_storage_key
from sbdc_domain import TaskStatus, transition_task
from sbdc_worker.tei import parse_tei


def make_pdf() -> bytes:
    pdf = fitz.open()
    first = pdf.new_page()
    first.insert_text((72, 90), "A Real Research Paper", fontsize=18)
    first.insert_text((72, 140), "Introduction", fontsize=14)
    first.insert_text((72, 175), "This study examines reproducible document parsing in practice.")
    second = pdf.new_page()
    second.insert_text((72, 90), "References", fontsize=14)
    second.insert_text((72, 125), "Smith J. Reliable Parsing. Journal of Tests. 2024.")
    data = pdf.tobytes()
    pdf.close()
    return data


TEI = b'''<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="en">
  <teiHeader>
    <fileDesc><titleStmt><title type="main">A Real Research Paper</title>
      <author><persName><forename>Alex</forename><surname>Chen</surname></persName></author>
    </titleStmt></fileDesc>
    <profileDesc><abstract><p>A study of document parsing.</p></abstract></profileDesc>
  </teiHeader>
  <text><body><div><head>Introduction</head>
    <p coords="1,72,160,410,24">This study examines reproducible document parsing in practice.</p>
  </div></body><back><div><listBibl>
    <biblStruct coords="2,72,110,420,28"><analytic>
      <title level="a">Reliable Parsing</title>
      <author><persName><forename>Jane</forename><surname>Smith</surname></persName></author>
    </analytic><monogr><title level="j">Journal of Tests</title><imprint><date when="2024"/></imprint></monogr>
      <note type="raw_reference">Smith J. Reliable Parsing. Journal of Tests. 2024.</note>
      <idno type="DOI">10.1000/test</idno>
    </biblStruct>
  </listBibl></div></back></text>
</TEI>'''


def test_task_state_machine_rejects_invalid_transition():
    assert transition_task(TaskStatus.CREATED, TaskStatus.VALIDATING) == TaskStatus.VALIDATING
    with pytest.raises(ValueError):
        transition_task(TaskStatus.CREATED, TaskStatus.REFERENCES_READY)


def test_storage_key_uses_only_system_ids():
    key = source_storage_key("task-id", "asset-id")
    assert key == "tasks/task-id/source/asset-id.pdf"
    assert "../" not in key


def test_tei_parser_preserves_structure_references_and_pdf_locations():
    parsed = parse_tei(TEI, make_pdf())
    assert parsed["title"] == "A Real Research Paper"
    assert parsed["authors"] == ["Alex Chen"]
    assert parsed["sections"][0]["heading"] == "Introduction"
    assert parsed["sections"][0]["page"] == 1
    assert parsed["sections"][0]["bbox"] == [72.0, 160.0, 482.0, 184.0]
    assert parsed["references"][0]["title"] == "Reliable Parsing"
    assert parsed["references"][0]["page"] == 2
    assert parsed["references"][0]["doi"] == "10.1000/test"
    assert parsed["page_map"] == [
        {"page": 1, "width": 595.0, "height": 842.0},
        {"page": 2, "width": 595.0, "height": 842.0},
    ]
