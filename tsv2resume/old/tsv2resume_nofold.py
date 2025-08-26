#!/usr/bin/env python3
# tsv2resume.py
# Convert a 3-column TSV (heading, content, meta) into Grid + row-pair HTML.
# - First TSV row is discarded as a header.
# - Auto-paragraphing: plain text => <p>…</p> with <br> for single newlines.
# - If a cell already contains HTML, we still convert bare \n to <br>, BUT ONLY OUTSIDE TAGS.

import csv, sys, re, os, argparse
from typing import List, Dict
from string import Template

# ---- Auto-paragraphing helpers ----
AUTO_PARA = True  # set to False to disable globally
TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")  # detect presence of any HTML tag

def nl_to_br_outside_tags(t: str) -> str:
    """
    Replace newlines with <br> only when:
      - we're NOT inside an HTML tag, and
      - the newline is NOT just pretty-printed whitespace between tags (e.g., '>\n  <').
    This preserves multi-line HTML lists/blocks from getting extra <br>s between <li>s, etc.
    """
    out = []
    in_tag = False
    quote = None
    i = 0
    n = len(t)

    def prev_nonspace(idx: int) -> str:
        j = idx - 1
        while j >= 0 and t[j].isspace():
            j -= 1
        return t[j] if j >= 0 else ""

    def next_nonspace(idx: int) -> str:
        j = idx + 1
        while j < n and t[j].isspace():
            j += 1
        return t[j] if j < n else ""

    while i < n:
        ch = t[i]
        if in_tag:
            # inside a tag: keep characters as-is (normalize raw newlines to a space)
            if quote:
                if ch == quote:
                    quote = None
                out.append(ch)
            else:
                if ch in ("'", '"'):
                    quote = ch
                    out.append(ch)
                elif ch == ">":
                    in_tag = False
                    out.append(ch)
                elif ch == "\n":
                    out.append(" ")
                else:
                    out.append(ch)
            i += 1
            continue

        # outside tags
        if ch == "<":
            in_tag = True
            out.append(ch)
            i += 1
            continue

        if ch == "\n":
            # If the newline is just formatting between tags (e.g., ">\n   <"), don't insert <br>
            if prev_nonspace(i) == ">" and next_nonspace(i) == "<":
                # consume this newline AND any immediate whitespace after it
                i += 1
                while i < n and t[i].isspace():
                    i += 1
                continue
            # otherwise, real line break in text -> <br>
            out.append("<br>")
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)

def auto_html(text: str) -> str:
    """
    - Plain text (no tags): split on blank lines -> <p>…</p>; single \n -> <br>.
    - HTML present: don't wrap; convert bare \n to <br> outside tags only (preserving pretty-printed lists).
    """
    t = (text or "")
    if not t.strip():
        return ""
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    has_tags = TAG_RE.search(t) is not None
    if not has_tags:
        blocks = re.split(r"\n\s*\n", t.strip())
        return "\n".join("<p>{}</p>".format(b.strip().replace("\n", "<br>")) for b in blocks)
    else:
        return nl_to_br_outside_tags(t)

def maybe_html(text: str) -> str:
    return auto_html(text) if AUTO_PARA else (text or "")

# ---- HTML scaffolding ----
HTML_HEAD = Template("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<base target="_blank">
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>$title</title>
<style>
  :root {
    /* Column widths */
    --three-left: 110px; /* label */
    --three-mid: 575px;  /* main */
    /* controls space under the name (title) */
    --space-before-title: 35px;            
    --space-after-title: 50px;

    /* Optional: section separator border; set to e.g., 1px solid #ddd */
    /* --row-sep: 0; */
    --row-sep: 1px solid #ddd;

    /* Optional: quick debug outline for grid cells */
    /* --debug-outline: none; /* e.g., 1px dashed #ccc */
    --debug-outline: 1px solid #ccc;
  }

  body {
    font-family: arial, verdana, sans-serif;
    font-size: 10pt;
    margin: 0;
    padding: 0;
  }

  #container { width: 800px; margin: 0 auto; }
  /* Allow horizontal scroll on narrow screens so grid never stacks */
  #content { padding-bottom: 50px; overflow-x: visible; }
  .title { font-size: xx-large; font-weight: bold; margin: var(--space-before-title) 0 var(--space-after-title); }
  .subtitle { font-size: large; font-weight: bold; margin: 4px 0 16px; }
                     
  /* === Grid Entry with Row-Pair Pattern === */
  .entry {
    display: grid;
    grid-template-columns: var(--three-left) var(--three-mid) minmax(0, 1fr);
    column-gap: 12px;
    row-gap: 15px;         /* space between the pair and its desc */
    align-items: start;   /* like valign="top" */
    margin: 0 0 14px 0;   /* space between entries */
    border-bottom: var(--row-sep);
    padding-bottom: 8px;
    /* Optional hard minimum width to discourage squeezing columns */
    min-width: 0;
  }

  /* Basics */
  .entry > * { min-width: 0; outline: var(--debug-outline); }
  .label     { grid-column: 1; font-weight: bold; }
  .line-main { grid-column: 2; }
  .line-meta { grid-column: 3; text-align: right; justify-self: end; font-style: italic; }
  .desc      { grid-column: 2 / -1; }

  /* Two-column variant (entire section has no meta) */
  .entry.entry--two { grid-template-columns: var(--three-left) minmax(0,1fr); }
  .entry.entry--two .line-main { grid-column: 2; }
  .entry.entry--two .desc { grid-column: 2; }
  .entry.entry--two .line-meta { display: none; }

  /* Paragraph tidy */
  .entry p { margin: 0 0 8px; }
  /* Avoid extra spacing in the right/meta column when auto-paragraphing */
  .line-meta p { margin: 0; }
</style>
</head>
<body>
  <div id="container">
    <main id="content">
""")

HTML_TAIL = """    </main>
  </div>
</body>
</html>
"""

def slugify(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)  # strip tags if user put HTML in heading
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "section"

def read_tsv(path: str) -> List[List[str]]:
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter="\t", quotechar='"', doublequote=True, skipinitialspace=False)
        rows = list(reader)
    return rows[1:] if rows else []  # drop header row

def build_sections(rows: List[List[str]]) -> List[Dict]:
    sections: List[Dict] = []
    current = None

    def start_section(label: str):
        nonlocal current
        current = {"label": label, "id": slugify(label), "rows": []}
        sections.append(current)

    for raw in rows:
        row = (raw + ["", "", ""])[:3]  # normalize to exactly 3 columns
        heading = (row[0] or "").strip()
        content = (row[1] or "").strip()
        meta    = (row[2] or "").strip()

        if not heading and not content and not meta:
            continue

        # Force new section via sentinel in heading: "SECTION: Employment"
        sec_match = re.match(r"^\s*SECTION\s*:\s*(.+)$", heading, flags=re.IGNORECASE)
        if sec_match:
            label = sec_match.group(1).strip()
            start_section(label)
            if content or meta:
                current["rows"].append({"type": "pair", "main": content, "meta": meta})
            continue

        if heading:
            if (current is None) or (heading != current["label"]):
                start_section(heading)
            if content or meta:
                current["rows"].append({"type": "pair", "main": content, "meta": meta})
            continue

        # heading empty → stay in current section (create a default one if needed)
        if current is None:
            start_section("Section")

        if meta:
            current["rows"].append({"type": "pair", "main": content, "meta": meta})
        else:
            current["rows"].append({"type": "desc", "html": content})

    return sections

def render_html(title: str, sections: List[Dict]) -> str:
    out = [HTML_HEAD.substitute(title=title)]
    out.append(f'      <h1 class="title">{title}</h1>\n')

    for sec in sections:
        entry_classes = "entry"
        if not any(r.get("meta") for r in sec["rows"] if r["type"] == "pair"):
            entry_classes += " entry--two"

        out.append(f'      <section aria-labelledby="{sec["id"]}">\n')
        out.append(f'        <div class="{entry_classes}" id="{sec["id"]}">\n')
        out.append(f'          <div class="label">{sec["label"]}</div>\n')

        for r in sec["rows"]:
            if r["type"] == "pair":
                out.append(f'          <div class="line-main">{maybe_html(r["main"])}</div>\n')
                if r.get("meta"):
                    out.append(f'          <div class="line-meta">{maybe_html(r["meta"])}</div>\n')
            else:  # desc
                out.append(f'          <div class="desc">{maybe_html(r["html"])}</div>\n')

        out.append("        </div>\n")
        out.append("      </section>\n\n")

    out.append(HTML_TAIL)
    return "".join(out)

def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert a 3-column TSV (heading, content, meta) into Grid + row-pair HTML. First TSV row is a header and is discarded.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", help="Input TSV file (tab-separated) with header in first row")
    parser.add_argument("output", help="Output HTML file path (e.g., resume.html)")
    parser.add_argument("--title", help="Document title (defaults to output filename sans extension)")
    return parser

def main():
    parser = parse_args()
    try:
        args = parser.parse_args()
    except SystemExit:
        raise  # argparse already printed help/usage

    if not os.path.isfile(args.input):
        parser.error(f"Input file not found: {args.input}")

    rows = read_tsv(args.input)  # header dropped inside
    title = args.title if args.title else os.path.splitext(os.path.basename(args.output))[0]

    sections = build_sections(rows)
    html = render_html(title, sections)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Generated {args.output} with {len(sections)} sections.")

if __name__ == "__main__":
    main()
