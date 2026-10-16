"""W-9 extraction: upload a W-9 (PDF or image), get back structured tax data for review.

Pipeline (first hit wins):
  1. Form fields — a filled W-9 PDF carries its entries as AcroForm widget values.
     These are the user's actual keystrokes, so mapping is exact and labels can
     never leak into values. Blank stays blank (null).
  2. Digital text — PyMuPDF extracts embedded text, parsed with IRS-layout-aware
     heuristics that exclude labels/instructions (never the line after a label).
  3. OCR — scanned PDFs are rasterized with PyMuPDF and read with Tesseract
     (pytesseract). Needs the `tesseract` binary on the machine; Vercel's
     serverless runtime doesn't ship it, so scans fall back to guided manual
     entry there. `ocr_available()` reports which path applies.
  4. Manual — the review form is always editable; nothing is trusted blindly.

Only parsed fields leave this module — never the raw document text.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import shutil

log = logging.getLogger("mytrakin.w9")

MIN_TEXT_CHARS = 200       # below this, embedded text is useless (scanned PDF)
OCR_MAX_PAGES = 3
OCR_DPI = 300

_EIN_RE = re.compile(r"(?<!\d)(\d{2})-?(\d{7})(?!\d)")
_SSN_RE = re.compile(r"(?<!\d)(\d{3})-?(\d{2})-?(\d{4})(?!\d)")
_ZIP_RE = re.compile(r"(?<!\d)(\d{5})(?:-?\d{4})?(?!\d)")
_STATE_RE = re.compile(r"\b([A-Z]{2})\s+\d{5}")

# Lines that are form labels/instructions — never treated as values.
_SEC_NUM_RE = re.compile(r"^(\d{1,2}[a-z]?)([.)]?)\s+(?=[A-Za-z(])")
# Numbered W-9 sections only: a house number ("9 Long Street") is a value, not a header.
_SEC_NUMBERS = {"1", "2", "3a", "3b", "4", "5", "6", "7"}
_SEC_WORDS = ("name", "business", "check", "exemptions", "address", "city", "list",
              "requester", "social", "employer", "part", "signature", "date", "form",
              "see", "enter", "give", "under", "step", "account", "exempt", "fatca",
              "certification", "backup", "penalties", "purpose", "definition", "payee",
              "caution", "note", "go to", "department", "rev.", "cat.", "print or type")
# A business-name line misclassified as a label ("Exempt Holdings LLC"): entity
# designators that essentially never start an instruction line.
_ENTITY_RE = re.compile(
    r"\b(LLC|Inc\.?|Corp\.?|LLP|Co\.|Company|Holdings|Group|Partners|Enterprises|Ltd\.?|PLLC|Trust|Bank)\b",
    re.IGNORECASE)
_LABEL_START_RE = re.compile(
    r"^(business name|check appropriate|exempt|fatca|address|city|list account|requester|"
    r"social security|employer identification|part i\b|part ii\b|certification|signature|"
    r"date\b|form w-9|rev\.|cat\.|department of|go to |give form|backup withholding|penalties|"
    r"specific instructions|general instructions|purpose of|definition of|payee|what is|"
    r"caution|note:|see |enter your|print or type|line \d|account number)", re.IGNORECASE)
# Only these sections hold values we store; same-line remainders elsewhere are dropped
# (e.g. a TIN after "Employer identification number:" — TINs come from patterns).
_VALUE_SECTIONS = {"1", "2", "5", "6", "7"}


def _section_remainder(line: str, key: str | None) -> str | None:
    if ":" in line and key in _VALUE_SECTIONS:
        tail = line.split(":", 1)[1].strip()
        if len(tail) >= 2 and not _LABEL_START_RE.match(tail) and not re.fullmatch(r"[\d\s\-–—/.]+", tail):
            return tail
    return None


def _split_section(line: str) -> tuple[str | None, str | None]:
    """(section_key, same_line_remainder) for a label line; (None, None) otherwise."""
    m = _SEC_NUM_RE.match(line)
    if m:
        word = re.sub(r"[^a-z]", "", line[m.end():].split(" ", 1)[0].lower())
        key = m.group(1).rstrip(".)")
        if key in _SEC_NUMBERS and word in _SEC_WORDS:
            return key, _section_remainder(line, key)
        if m.group(2):
            # Enumerated item ("1. The number shown ...") — a break, never a value.
            return "label", None
        # A leading number that isn't a W-9 section ("9 Long Street",
        # "4100 Commerce ...") — a value, not a header.
        return None, None
    elif _LABEL_START_RE.match(line):
        key = "part" if line.lower().startswith("part") else "label"
        return key, _section_remainder(line, key)
    elif re.fullmatch(r"[.\-_\s]+", line):
        return "skip", None
    elif re.fullmatch(r"[\d\s\-–—/.]+", line):
        return "skip", None   # stray digit-box renderings, page numbers
    else:
        return None, None


def ocr_available() -> bool:
    """Is the Tesseract binary installed (scanned W-9s readable)?"""
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


# ---------------------------------------------------------------- form fields
def _classify_label(label: str) -> str:
    """Map nearby static text to a W-9 slot. Unknown labels → 'ignore' (never a value)."""
    low = label.lower()
    if "requester" in low:
        return "ignore"
    if "disregarded" in low or "business name" in low:
        return "dba"
    if "account number" in low:
        return "ignore"
    if "city" in low or "zip" in low:
        return "city_state_zip"
    if "address" in low or "street" in low or "apt" in low or "suite" in low:
        return "address"
    if "social security" in low:
        return "ssn"
    if "employer identification" in low:
        return "ein"
    if "exempt" in low or "fatca" in low or "signature" in low or "certification" in low:
        return "ignore"
    if "income tax return" in low or re.search(r"(^|\s)1\s+name", low) or ("name" in low and "shown" in low):
        return "legal_name"
    return "unknown"


def _classify_check_label(label: str) -> str | None:
    low = label.lower()
    for keyword, classification in (
        ("individual", "Individual/sole proprietor"), ("c corporation", "C Corporation"),
        ("s corporation", "S Corporation"), ("partnership", "Partnership"),
        ("trust", "Trust/estate"), ("limited liability", "Limited liability company"),
        ("exempt payee", "Exempt payee"),
    ):
        if keyword in low:
            return classification
    return None


def _group_lines(words: list) -> list[dict]:
    grouped: dict[tuple, dict] = {}
    for x0, y0, x1, y1, word, block, line, _no in words:
        key = (block, line)
        g = grouped.setdefault(key, {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "words": []})
        g["x0"] = min(g["x0"], x0)
        g["y0"] = min(g["y0"], y0)
        g["x1"] = max(g["x1"], x1)
        g["y1"] = max(g["y1"], y1)
        g["words"].append((x0, word))
    out = [{"text": " ".join(w for _, w in sorted(g["words"])), **{k: g[k] for k in ("x0", "y0", "x1", "y1")}}
           for g in grouped.values()]
    return out


def _is_rendering(ln: dict, top: float, bottom: float, left: float, right: float) -> bool:
    """A filled widget's own appearance (value text, check glyph) shows up in page
    text exactly on top of the widget — it is never a label."""
    cx, cy = (ln["x0"] + ln["x1"]) / 2, (ln["y0"] + ln["y1"]) / 2
    return left - 2 <= cx <= right + 2 and top - 2 <= cy <= bottom + 2


def _label_near(lines: list[dict], top: float, bottom: float, left: float, right: float,
                prefer_row: bool = False) -> str:
    """Nearest static-text line: above the widget (IRS entry labels sit above their
    fields), or on the same row (checkbox labels sit beside their box)."""
    above, above_y = "", -1.0
    for ln in lines:
        if _is_rendering(ln, top, bottom, left, right):
            continue
        if ln["y1"] <= top + 2 and top - ln["y1"] <= 80 and ln["y1"] > above_y:
            above, above_y = ln["text"], ln["y1"]
    row, row_gap = "", float("inf")
    height = max(bottom - top, 1.0)
    for ln in lines:
        if _is_rendering(ln, top, bottom, left, right):
            continue
        # The line must genuinely share the row: ≥50% vertical overlap with the widget.
        overlap = min(bottom, ln["y1"]) - max(top, ln["y0"])
        if overlap < 0.5 * height:
            continue
        gap = left - ln["x1"] if ln["x1"] <= left else (ln["x0"] - right if ln["x0"] >= right else 0)
        if 0 <= gap <= 160 and gap < row_gap:
            row, row_gap = ln["text"], gap
    if prefer_row:
        return row or above
    return above or row


def _extract_form_fields(data: bytes) -> dict | None:
    """Read AcroForm widget values. Returns None when the PDF has no filled fields."""
    try:
        import pymupdf
    except ImportError:
        return None
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        return None

    slots: dict[str, str] = {}
    unmapped: list[str] = []   # exact values geometry couldn't place (mapped by text order later)
    check_labels: list[tuple[float, str]] = []
    digit_rows: list[tuple[float, float, str]] = []   # (page, top, digits) for TIN boxes
    found_any = False
    try:
        for pno, page in enumerate(doc):
            try:
                widgets = list(page.widgets() or [])
            except Exception:
                continue
            if not widgets:
                continue
            lines = _group_lines(page.get_text("words"))
            singles: dict[tuple, list] = {}
            for w in widgets:
                value = w.field_value
                is_box = w.field_type == pymupdf.PDF_WIDGET_TYPE_CHECKBOX
                label = _label_near(lines, w.rect.y0, w.rect.y1, w.rect.x0, w.rect.x1,
                                    prefer_row=is_box)
                if is_box:
                    found_any = True
                    # Per the PDF spec the unchecked state is always Off (or empty);
                    # anything else is the checked export value.
                    if str(value or "").strip().lower() not in ("off", "", "0", "false", "no"):
                        classification = _classify_check_label(label)
                        if classification:
                            check_labels.append((w.rect.y0, classification))
                    continue
                if w.field_type != pymupdf.PDF_WIDGET_TYPE_TEXT:
                    continue
                text = (value if isinstance(value, str) else "" if value is None else str(value)).strip()
                if not text:
                    continue   # blank field: genuinely null, never the next label
                found_any = True
                if len(text) <= 1 and w.rect.width < 30 and w.rect.height < 30:
                    key = (pno, round(w.rect.y0 / 4))
                    singles.setdefault(key, []).append((w.rect.x0, text, w.rect.y0))
                    continue
                slot = _classify_label(label)
                if slot in ("legal_name", "dba", "address", "city_state_zip") and slot not in slots:
                    slots[slot] = text
                elif slot in ("ssn", "ein"):
                    digits = re.sub(r"\D", "", text)
                    if len(digits) == 9 and "tin" not in slots:
                        slots["tin"] = _format_tin(digits, slot)
                        slots["tin_type"] = slot
                else:
                    unmapped.append(text)
            for (pno, _bucket), cells in singles.items():
                row = "".join(t for _, t, _ in sorted(cells))
                digits = re.sub(r"\D", "", row)
                if len(digits) >= 7:
                    top = min(y for _, _, y in cells)
                    left = min(x for x, _, _ in cells)
                    right = max(x for x, _, _ in cells) + 14
                    row_label = _label_near(lines, top, top + 20, left, right)
                    digit_rows.append((pno, top, row, row_label))
        if not found_any:
            return None
    finally:
        doc.close()

    for _pno, _top, row, row_label in sorted(digit_rows):
        digits = re.sub(r"\D", "", row)
        if len(digits) < 9 or "tin" in slots:
            continue
        slot = _classify_label(row_label)
        if slot in ("ssn", "ein"):
            slots["tin"] = _format_tin(digits[:9], slot)
            slots["tin_type"] = slot
    if check_labels and "tax_classification" not in slots:
        slots["tax_classification"] = sorted(check_labels)[0][1]
    return {"slots": slots, "unmapped": unmapped}


def _format_tin(digits: str, kind: str) -> str:
    digits = re.sub(r"\D", "", digits)[:9]
    if kind == "ssn" and len(digits) == 9:
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    if len(digits) == 9:
        return f"{digits[:2]}-{digits[2:]}"
    return digits


# ---------------------------------------------------------------- text layers
def _pdf_text(data: bytes) -> str:
    try:
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return "\n".join(page.get_text() or "" for page in doc)
    except Exception:
        log.warning("PyMuPDF text extraction failed", exc_info=True)
        return ""


def _ocr_image(data: bytes) -> str:
    """OCR one image (PNG/JPEG/WebP bytes). Empty string when unavailable."""
    if not ocr_available():
        return ""
    import pytesseract
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        return pytesseract.image_to_string(img) or ""


def _ocr_pdf(data: bytes) -> str:
    """Rasterize the first pages of a scanned PDF and OCR them."""
    if not ocr_available():
        return ""
    try:
        import pymupdf
        out: list[str] = []
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            for page in doc[:OCR_MAX_PAGES]:
                pix = page.get_pixmap(dpi=OCR_DPI)
                out.append(_ocr_image(pix.tobytes("png")))
        return "\n".join(out)
    except Exception:
        log.warning("PDF OCR failed", exc_info=True)
        return ""


# A checked box in extracted text: a check mark immediately before the option.
# Plain option labels (present on every blank W-9) must never count.
_MARK_RE = r"(?:[☒☑■▪▣✓✔]|\[[Xx]\]|\([Xx]\))"


def _classify_from_markers(text: str) -> str | None:
    for keyword, classification in (
        ("Individual/sole proprietor", "Individual/sole proprietor"),
        ("C Corporation", "C Corporation"), ("S Corporation", "S Corporation"),
        ("Partnership", "Partnership"), ("Trust/estate", "Trust/estate"),
        ("Limited liability company", "Limited liability company"),
        ("Exempt payee", "Exempt payee"),
    ):
        if re.search(_MARK_RE + r"\s*" + re.escape(keyword), text):
            return classification
    return None


def _looks_like_name(value: str | None) -> bool:
    """A legal name or street address always contains letters. Bare numbers
    (page fragments, digit-box strays, checkbox glyphs) are never names —
    returning them as legal_name is how "98" ends up in the response."""
    return bool(value) and bool(re.search(r"[A-Za-z]", value))


def _sanitize_names(parsed: dict) -> dict:
    for key in ("legal_name", "address"):
        if parsed.get(key) and not _looks_like_name(parsed[key]):
            parsed[key] = None
    return parsed


def _sections_of(text: str) -> list[tuple[str | None, str]]:
    """Split text into (section_key, line) with section tracking (None = preamble)."""
    out: list[tuple[str | None, str]] = []
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        key, _remainder = _split_section(line)
        if key == "skip":
            continue
        if key is not None:
            if key in _VALUE_SECTIONS:
                current = key
            out.append((key, line))
            continue
        out.append((current, line))
    return out


def _map_values_by_text_order(values: list[str], text: str) -> dict[str, str]:
    """Assign exact widget values to sections by text order. Values can only come
    from the widgets themselves — this decides mapping, never content."""
    sectioned = _sections_of(text)

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    assigned: dict[str, str] = {}
    for value in values:
        needle = norm(value)
        if len(needle) < 2:
            continue
        for section, line in sectioned:
            if section in _VALUE_SECTIONS and needle in norm(line) and section not in assigned:
                assigned[section] = value
                break
    return assigned


def _split_city_state_zip(value: str | None) -> tuple[str | None, str | None, str | None]:
    if not value:
        return None, None, None
    m = re.search(r"^(.*?),\s*([A-Za-z]{2})\s+(\d{5}(?:-\d{4})?)", value)
    if m:
        return m.group(1).strip() or None, m.group(2).upper(), m.group(3)
    zip_m = _ZIP_RE.search(value)
    state_m = _STATE_RE.search(value)
    return None, (state_m.group(1) if state_m else None), (zip_m.group(1) if zip_m else None)


def parse_w9_text(text: str) -> dict:
    """IRS-layout-aware text fallback. The page is split into labeled sections; values
    belong to their section, option lines belong to none — so a blank field yields
    null instead of the next label down the page."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    label_wraps = False   # a section label split mid-sentence across lines ("... enter the
    # business/disregarded" / "entity's name on line 2.)"): while its parentheses stay
    # unbalanced, the following lines continue the label — never a value.
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln:
            continue
        # A business-name line misread as a label ("Exempt Holdings LLC"): entity
        # designators essentially never start an instruction, so inside sections
        # 1/2/5/6 a colon-free, number-free line carrying one belongs to the section.
        if (current in ("1", "2", "5", "6") and ":" not in ln
                and not _SEC_NUM_RE.match(ln) and _ENTITY_RE.search(ln)):
            sections.setdefault(current, []).append(ln)
            continue
        key, remainder = _split_section(ln)
        if key == "skip":
            continue
        if key is not None:
            current = key if key in _VALUE_SECTIONS else None
            label_wraps = (key in _VALUE_SECTIONS and ln.count("(") > ln.count(")"))
            if remainder:
                sections.setdefault(current or "", []).append(remainder)
            continue
        if label_wraps:
            if ")" in ln:
                label_wraps = False
            continue
        if current:
            sections.setdefault(current, []).append(ln)

    def joined(key: str) -> str | None:
        value = " ".join(sections.get(key, [])).strip()
        return value or None

    legal_name = joined("1")
    dba = joined("2")
    # Classification only from an actual check mark — every blank W-9 lists all
    # options as static labels, so keyword matching would always lie.
    classification = _classify_from_markers(text)

    address = joined("5")
    city, state, zip_code = _split_city_state_zip(joined("6"))
    if not zip_code:
        m = _ZIP_RE.search(text)
        zip_code = m.group(1) if m else None
    if not state:
        m = _STATE_RE.search(text)
        state = m.group(1) if m else None

    tin = tin_type = None
    ein_at = text.find("Employer identification")
    ssn_at = text.find("Social security")
    found: dict[str, tuple[int, str]] = {}
    for m in _EIN_RE.finditer(text):
        found.setdefault(re.sub(r"\D", "", m.group(0)), (m.start(), "ein"))
    for m in _SSN_RE.finditer(text):
        found.setdefault(re.sub(r"\D", "", m.group(0)), (m.start(), "ssn"))
    # Digit-box renderings and OCR splits ("12 3456789", "1 2 3 4 5 6 7 8 9"):
    # merge runs joined only by spaces/dashes. The separator requirement keeps
    # unrelated neighbors ("75207" + "5550100") from fusing into a false TIN.
    for m in re.finditer(r"(?<!\d)\d(?:[\s\-]*\d){8}(?!\d)", text):
        if re.search(r"[\s\-]", m.group(0)):
            digits = re.sub(r"\D", "", m.group(0))
            if len(digits) == 9:
                found.setdefault(digits, (m.start(), "?"))
    if found:
        # Prefer the number printed nearest its label (Part I of the form).
        def distance(entry: tuple[str, tuple[int, str]]) -> float:
            _digits, (pos, typ) = entry
            if typ == "?":
                candidates = [abs(pos - a) for a in (ein_at, ssn_at) if a >= 0]
                return min(candidates) if candidates else 10**9
            anchor = ein_at if typ == "ein" else ssn_at
            return abs(pos - anchor) if anchor >= 0 else 10**9
        best_digits, (best_pos, best_typ) = min(found.items(), key=distance)
        if best_typ == "?":
            near_ein = abs(best_pos - ein_at) if ein_at >= 0 else 10**9
            near_ssn = abs(best_pos - ssn_at) if ssn_at >= 0 else 10**9
            best_typ = "ein" if near_ein <= near_ssn else "ssn"
        tin, tin_type = _format_tin(best_digits, best_typ), best_typ

    parsed = _sanitize_names({"legal_name": legal_name, "dba": dba, "tax_classification": classification,
                              "tin": tin, "tin_type": tin_type, "address": address, "city": city,
                              "state": state, "zip": zip_code})
    review = [k for k, v in {"legal_name": parsed["legal_name"], "tax_classification": parsed["tax_classification"],
                             "address": parsed["address"], "tin": parsed["tin"]}.items() if not v]
    if parsed["address"] and not parsed["city"]:
        review.append("city_state_zip")
    parsed["needs_review"] = review
    return parsed


def _review_of(parsed: dict) -> list[str]:
    review = [k for k in ("legal_name", "tax_classification", "address", "tin") if not parsed.get(k)]
    if parsed.get("address") and not parsed.get("city"):
        review.append("city_state_zip")
    return review


async def extract_w9(data: bytes, content_type: str) -> dict:
    """Extract W-9 fields from uploaded bytes. Blocking work runs in a thread."""
    kind = "pdf" if content_type == "application/pdf" else "image" if content_type in {
        "image/jpeg", "image/png", "image/webp"} else "other"
    if kind == "other":
        return {"engine": "none", "needs_manual": True, "needs_review": ["upload"],
                "note": "Upload the W-9 as a PDF, JPEG, PNG or WebP file."}

    def _work() -> tuple[str, str, dict | None]:
        if kind == "image":
            text = _ocr_image(data)
            return text, ("ocr" if text.strip() else "none"), None
        fields = _extract_form_fields(data)
        if fields:
            return "", "form-fields", fields
        text = _pdf_text(data)
        stripped = text.strip()
        if stripped:
            # Digital text counts when it yields a name/TIN — or is substantial
            # enough to review field by field (short fragments go to OCR/none).
            probe = parse_w9_text(text)
            if probe.get("legal_name") or probe.get("tin") or len(stripped) >= MIN_TEXT_CHARS:
                return text, "pdf-text", None
        ocr_text = _ocr_pdf(data)
        if len(ocr_text.strip()) >= 40:
            return ocr_text, "ocr", None
        return text, "none", None

    text, engine, fields = await asyncio.to_thread(_work)
    if engine == "form-fields":
        assert fields is not None
        slots = fields["slots"]
        # Values geometry couldn't place: map them by position in the text.
        # They are still exact keystrokes — this only decides which field each is.
        # Values without letters can never be names/addresses (digit-box strays,
        # checkbox glyphs) — the TIN path handles numbers separately.
        if fields["unmapped"]:
            pdf_text = await asyncio.to_thread(_pdf_text, data)
            for section, value in _map_values_by_text_order(fields["unmapped"], pdf_text).items():
                if not re.search(r"[A-Za-z]", value):
                    continue
                if section == "1" and slots.get("legal_name") is None:
                    slots["legal_name"] = value
                elif section == "2" and slots.get("dba") is None:
                    slots["dba"] = value
                elif section == "5" and slots.get("address") is None:
                    slots["address"] = value
                elif section == "6" and slots.get("city_state_zip") is None:
                    slots["city_state_zip"] = value
        city, state, zip_code = _split_city_state_zip(slots.get("city_state_zip"))
        parsed = {"legal_name": slots.get("legal_name"), "dba": slots.get("dba"),
                  "tax_classification": slots.get("tax_classification"),
                  "tin": slots.get("tin"), "tin_type": slots.get("tin_type"),
                  "address": slots.get("address"), "city": city, "state": state, "zip": zip_code}
        # Text corroboration for slots the form left blank — TIN (bare numbers can't
        # be labels) and marker-detected classification only. Names/addresses stay
        # null rather than risk label bleed.
        if parsed.get("tin") is None or parsed.get("tax_classification") is None:
            pdf_text = text or await asyncio.to_thread(_pdf_text, data)
            backup = await asyncio.to_thread(parse_w9_text, pdf_text)
            if parsed.get("tin") is None and backup.get("tin"):
                parsed["tin"], parsed["tin_type"] = backup["tin"], backup["tin_type"]
        if parsed.get("tax_classification") is None and backup.get("tax_classification"):
            parsed["tax_classification"] = backup["tax_classification"]
        parsed = _sanitize_names(parsed)
        parsed["needs_review"] = _review_of(parsed)
        parsed["engine"] = engine
        parsed["needs_manual"] = False
        parsed["note"] = ("Check every field against the document before submitting."
                          if parsed["needs_review"] else None)
        return parsed
    if engine == "none":
        reason = ("no Tesseract on this machine" if not ocr_available()
                  else "no readable text found")
        return {"engine": "none", "needs_manual": True,
                "needs_review": ["legal_name", "tax_classification", "address", "tin"],
                "note": f"This looks like a scanned W-9 ({reason}). Type the details below — the document is still attached."}

    parsed = await asyncio.to_thread(parse_w9_text, text)
    return {"engine": engine, "needs_manual": False, **parsed,
            "note": "Check every field against the document before submitting." if parsed["needs_review"] else None}
