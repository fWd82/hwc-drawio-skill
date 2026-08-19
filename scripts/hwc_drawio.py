#!/usr/bin/env python3
"""Generate editable Draw.io diagrams from bundled Huawei Cloud libraries."""

from __future__ import annotations

import argparse
import base64
import binascii
import html
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LIBRARY_DIR = SKILL_DIR / "assets" / "libraries"
RAW_BASE64_DATA_URI = re.compile(r"\Adata:([^;,]+);base64,(.*)\Z", re.IGNORECASE | re.DOTALL)
STYLE_SAFE_DATA_URI = re.compile(r"\Adata:([^;,]+),(.*)\Z", re.IGNORECASE | re.DOTALL)


REFERENCE_HEADER_HEIGHT = 190
REFERENCE_FOOTER_HEIGHT = 390
REFERENCE_APPLICATION_USER_ID = "reference-application-user"
REFERENCE_SERVICES = (
 ("Security","#C7000B",(("Data Encryption Worshop (DEW)","DEW\nEncryption"),("Host Security Service (HSS)","HSS\nHost Security"),("Container Security Service (CGS)","CGS\nContainer Security"),("SecMaster","SecMaster\nSecurity Ops"))),
 ("Cloud Operations","#5B6B8C",(("Cloud Operations Center (COC)","COC\nCloud Operations"),("Cloud Trace Service (CTS)","CTS\nOperation Audit"))),
 ("Monitoring & Logging","#2368A2",(("Log Tank Servce (LTS)","LTS\nCentralized Logging"),("Cloud Eye Service (CES)","Cloud Eye\nMonitoring"))),
 ("Backup & Recovery","#6B4AA0",(("Cloud Backup and Recovery (CBR)","CBR\nBackup & Recovery"),)),
 ("Image Management","#008C95",(("Image Management Service (IMS)","IMS\nVM Images"),("SoftWare Repository for Container (SWR)","SWR\nContainer Images"))),
)


def die(message: str, code: int = 2) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def load_libraries(library_dir: Path) -> list[dict[str, Any]]:
    if not library_dir.is_dir():
        die(f"library directory not found: {library_dir}")
    records: list[dict[str, Any]] = []
    for path in sorted(library_dir.glob("*.xml")):
        raw = path.read_text(encoding="utf-8-sig").strip()
        match = re.fullmatch(r"<mxlibrary>(.*)</mxlibrary>", raw, re.DOTALL)
        if not match:
            die(f"not a Draw.io mxlibrary file: {path}")
        try:
            entries = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            die(f"invalid library JSON in {path}: {exc}")
        category = re.sub(r"\s*\(color\)\s*$", "", path.stem).strip()
        category = re.sub(r"^HWC\s+", "", category).strip()
        for index, entry in enumerate(entries):
            title = str(entry.get("title") or f"Untitled {index + 1}")
            kind = "icon" if "data" in entry else "group" if "xml" in entry else "unknown"
            records.append({
                "title": title,
                "normalized": normalize(title),
                "kind": kind,
                "category": category,
                "library": path.name,
                "entry": entry,
            })
    if not records:
        die(f"no .xml libraries found in {library_dir}")
    return records


def resolve(records: list[dict[str, Any]], query: str, kind: str) -> dict[str, Any]:
    candidates = [r for r in records if r["kind"] == kind]
    query_norm = normalize(query)
    exact = [r for r in candidates if r["normalized"] == query_norm]
    if len(exact) == 1:
        return exact[0]
    contains = [r for r in candidates if query_norm and query_norm in r["normalized"]]
    if len(contains) == 1:
        return contains[0]
    tokens = set(query_norm.split())
    ranked = sorted(
        ((len(tokens.intersection(r["normalized"].split())), r) for r in candidates),
        key=lambda item: (-item[0], item[1]["title"]),
    )
    best_score = ranked[0][0] if ranked else 0
    fuzzy = [r for score, r in ranked if score == best_score and score > 0]
    choices = exact or contains or fuzzy
    if not choices:
        die(f"no {kind} matches {query!r}; run the search command")
    names = ", ".join(r["title"] for r in choices[:12])
    suffix = " ..." if len(choices) > 12 else ""
    die(f"ambiguous {kind} {query!r}; candidates: {names}{suffix}")


def geometry(cell: ET.Element) -> ET.Element | None:
    return cell.find("mxGeometry")


def float_attr(element: ET.Element | None, name: str, default: float = 0.0) -> float:
    if element is None:
        return default
    try:
        return float(element.get(name, default))
    except (TypeError, ValueError):
        return default


def append_style(base: str, suffix: Any) -> str:
    result = base or ""
    if result and not result.endswith(";"):
        result += ";"
    extra = str(suffix or "").strip()
    if extra:
        result += extra
        if not result.endswith(";"):
            result += ";"
    return result


def normalize_image_data_uri_for_style(data_uri: str) -> str:
    """Return a self-contained image data URI safe inside an mxGraph style.

    mxGraph separates style properties with semicolons, so the standard
    ;base64, data-URI marker cannot appear inside an image= value.
    diagrams.net accepts the same untouched base64 payload after the MIME type
    and a comma. Already-normalized values are returned unchanged.
    """
    raw = str(data_uri)
    match = RAW_BASE64_DATA_URI.fullmatch(raw)
    if match:
        mime_type, payload = match.groups()
        if not mime_type.casefold().startswith("image/"):
            raise ValueError(f"embedded data URI is not an image MIME type: {mime_type}")
        if not payload:
            raise ValueError("embedded image data URI has an empty payload")
        return f"data:{mime_type},{payload}"
    match = STYLE_SAFE_DATA_URI.fullmatch(raw)
    if match:
        mime_type, payload = match.groups()
        if not mime_type.casefold().startswith("image/"):
            raise ValueError(f"embedded data URI is not an image MIME type: {mime_type}")
        if not payload:
            raise ValueError("embedded image data URI has an empty payload")
        return raw
    raise ValueError("unsupported embedded image data URI; expected data:<image-mime>;base64,<payload>")


def decode_style_embedded_image(image_value: str) -> tuple[str, bytes]:
    """Validate and decode a diagrams.net-compatible embedded image value."""
    match = STYLE_SAFE_DATA_URI.fullmatch(image_value)
    if not match:
        if image_value.casefold().startswith("data:image/") and "," not in image_value:
            raise ValueError(f"truncated image value: {image_value}")
        raise ValueError("image value is not a usable embedded data URI")
    mime_type, payload = match.groups()
    if not mime_type.casefold().startswith("image/"):
        raise ValueError(f"embedded data URI is not an image MIME type: {mime_type}")
    if not payload:
        raise ValueError("embedded image data URI has an empty payload")
    try:
        decoded = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("embedded image payload is not valid base64") from exc
    if not decoded:
        raise ValueError("embedded image payload decodes to no data")
    if mime_type.casefold() == "image/svg+xml":
        try:
            svg_root = ET.fromstring(decoded)
        except ET.ParseError as exc:
            raise ValueError("embedded SVG payload is not valid XML") from exc
        if svg_root.tag.rsplit("}", 1)[-1].casefold() != "svg":
            raise ValueError("embedded SVG payload has no svg root element")
    return mime_type, decoded


def extract_style_embedded_image(style: str) -> str:
    """Extract one complete embedded image value or raise on broken styles."""
    tokens = [token.strip() for token in str(style or "").split(";") if token.strip()]
    for token in tokens:
        if token.casefold().startswith("base64,"):
            raise ValueError("detached style token begins with base64,")
    image_values = [
        token.partition("=")[2]
        for token in tokens
        if token.partition("=")[0].casefold() == "image"
    ]
    if not image_values:
        raise ValueError("image cell has no image property")
    if len(image_values) != 1:
        raise ValueError("image cell must have exactly one image property")
    decode_style_embedded_image(image_values[0])
    return image_values[0]


class DiagramBuilder:
    def __init__(self, spec: dict[str, Any], records: list[dict[str, Any]]) -> None:
        self.spec = spec
        self.records = records
        self.ids: dict[str, str] = {}
        self.counter = 2
        self.root = ET.Element("root")
        ET.SubElement(self.root, "mxCell", {"id": "0"})
        ET.SubElement(self.root, "mxCell", {"id": "1", "parent": "0"})
        reference = spec.get("reference", {})
        self.reference = reference if isinstance(reference, dict) else {}
        self.reference_enabled = reference is not False and self.reference.get("enabled", True) is not False
        self.content_offset_y = REFERENCE_HEADER_HEIGHT if self.reference_enabled else 0

    def root_y(self, value: float, parent: Any) -> float:
        return value + self.content_offset_y if parent in (None, "") else value

    def add_box(
        self, value: str, x: float, y: float, width: float, height: float,
        style: str, logical: str | None = None,
    ) -> ET.Element:
        cell = ET.SubElement(self.root, "mxCell", {"id": self.new_id(logical), "value": value, "style": style, "vertex": "1", "parent": "1"})
        ET.SubElement(cell, "mxGeometry", {"x": number(x), "y": number(y), "width": number(width), "height": number(height), "as": "geometry"})
        return cell

    def add_library_icon(self, title: str, label: str, x: float, y: float) -> None:
        icon = resolve(self.records, title, "icon")
        try:
            data = normalize_image_data_uri_for_style(str(icon["entry"]["data"]))
        except ValueError as exc:
            die(f"invalid embedded image for {icon['title']}: {exc}")
        self.add_box(label, x, y, 48, 48,
            "shape=image;verticalLabelPosition=bottom;verticalAlign=top;labelPosition=center;align=center;"
            "html=1;aspect=fixed;imageAspect=0;fontFamily=Arial;fontSize=10;fontColor=#282B33;whiteSpace=wrap;"
            f"image={data};")

    def add_reference_header(self, width: int) -> None:
        customer = str(self.reference.get("customer", "Customer Name"))
        title = str(self.reference.get("title", f"Huawei Cloud Architecture - {customer}"))
        subtitle = str(self.reference.get("subtitle", "Solution Architecture"))
        if self.reference.get("show_title", True) is not False:
            title = title.strip() or f"Huawei Cloud Architecture - {customer}"
            self.add_box(f"<b>{html.escape(title)}</b><br><font style=\"font-size: 16px\">{html.escape(subtitle)}</font>",40,28,400,60,
                "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;fontFamily=Arial;fontSize=22;fontColor=#111111;whiteSpace=wrap;")
        self.add_box("REFERENCE ACCESS &amp; INTEGRATION CONTEXT -- optional; adapt or delete",455,18,max(680,width-495),24,
            "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF7E6;strokeColor=#FFB648;fontColor=#7A4A00;fontFamily=Arial;fontSize=10;align=center;")
        actors=(("GH","GitHub","#24292F"),("DH","DockerHub","#2496ED"),("PC","Administrator<br>Local PC","#5B6B8C"),("USER","Application User","#C7000B"),("SITE","3rd-party Cloud<br>On-premises","#6B4AA0"))
        gap=max(680,width-495)/len(actors)
        for i,(badge,label,color) in enumerate(actors):
            center=455+gap*(i+.5)
            logical = REFERENCE_APPLICATION_USER_ID if label == "Application User" else None
            self.add_box(badge,center-24,58,48,48,f"ellipse;html=1;fillColor={color};strokeColor={color};fontColor=#FFFFFF;fontStyle=1;fontFamily=Arial;fontSize=11;align=center;verticalAlign=middle;",logical)
            self.add_box(label,center-58,110,116,42,"text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=top;fontFamily=Arial;fontSize=11;fontColor=#282B33;whiteSpace=wrap;")
        self.add_box("Typical entry points and delivery-system integrations are for reference only. Connect, rename, or remove them to match the approved customer design.",455,154,max(680,width-495),24,
            "text;html=1;strokeColor=none;fillColor=none;align=center;fontFamily=Arial;fontSize=10;fontColor=#6B7280;fontStyle=2;whiteSpace=wrap;")

    def add_reference_footer(self, width: int, content_height: int) -> None:
        top=self.content_offset_y+content_height+24; footer_width=max(1120,width-80); start=(width-footer_width)/2
        self.add_box("",start,top,footer_width,340,"rounded=0;html=1;fillColor=#FFFFFF;strokeColor=#C7000B;strokeWidth=2;dashed=1;dashPattern=8 4;")
        self.add_box("REFERENCE PLATFORM &amp; OPERATIONS SERVICES -- optional; adapt or delete this entire section",start+18,top+14,footer_width-36,28,
            "rounded=1;html=1;fillColor=#FFF1F0;strokeColor=#C7000B;fontColor=#C7000B;fontStyle=1;fontFamily=Arial;fontSize=12;align=center;")
        guidance=self.reference.get("ha_guidance","Reference resilience guidance: deploy applicable hosting components across multiple AZs in HA mode, subject to workload requirements.")
        if guidance is not False:
            self.add_box(html.escape(str(guidance)),start+18,top+52,footer_width-36,34,
                "shape=parallelogram;perimeter=parallelogramPerimeter;html=1;fillColor=#C7000B;strokeColor=#C7000B;fontColor=#FFFFFF;fontStyle=1;fontFamily=Arial;fontSize=11;align=center;")
        widths=(310,190,205,155,220); total=sum(widths)+12*(len(widths)-1); x=start+(footer_width-total)/2; y=top+102
        for (category,color,services),panel_width in zip(REFERENCE_SERVICES,widths):
            self.add_box("",x,y,panel_width,190,"rounded=0;html=1;fillColor=#FFFFFF;strokeColor=#AAB2BD;dashed=1;")
            self.add_box(html.escape(category),x,y,panel_width,30,f"rounded=0;html=1;fillColor={color};strokeColor={color};fontColor=#FFFFFF;fontStyle=1;fontFamily=Arial;fontSize=11;align=left;spacingLeft=10;")
            slot=panel_width/len(services)
            for i,(icon,label) in enumerate(services): self.add_library_icon(icon,label,x+slot*(i+.5)-24,y+58)
            x+=panel_width+12
        self.add_box("Examples only -- inclusion does not imply customer scope, licensing, sizing, or commercial commitment.",start+18,top+304,footer_width-36,22,
            "text;html=1;strokeColor=none;fillColor=none;align=center;fontFamily=Arial;fontSize=10;fontColor=#6B7280;fontStyle=2;whiteSpace=wrap;")

    def add_reference_access_edge(self) -> None:
        target = self.reference.get("application_entry")
        if target in (None, ""):
            return
        target = str(target)
        if target not in self.ids:
            die(f"reference application_entry {target!r} must identify a declared node, group, or note")
        label = str(self.reference.get("application_access_label", "Application access (logical)"))
        cell = ET.SubElement(self.root, "mxCell", {
            "id": self.new_id(), "value": label,
            "style": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#C7000B;strokeWidth=2;dashed=1;exitX=0.5;exitY=1;entryX=0.5;entryY=0;endArrow=classic;endFill=1;",
            "edge": "1", "parent": "1", "source": self.ids[REFERENCE_APPLICATION_USER_ID], "target": self.ids[target],
        })
        ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})

    def new_id(self, logical: str | None = None) -> str:
        if logical:
            if not re.fullmatch(r"[A-Za-z0-9_.:-]+", logical):
                die(f"invalid id {logical!r}; use letters, digits, dot, colon, underscore, or hyphen")
            if logical in self.ids:
                die(f"duplicate id: {logical}")
        cell_id = f"hwc-{self.counter}"
        self.counter += 1
        if logical:
            self.ids[logical] = cell_id
        return cell_id

    def parent_id(self, logical: Any) -> str:
        if logical in (None, ""):
            return "1"
        if str(logical) not in self.ids:
            die(f"parent {logical!r} must be declared before its child")
        return self.ids[str(logical)]

    def add_groups(self) -> None:
        for index, item in enumerate(self.spec.get("groups", [])):
            if not isinstance(item, dict):
                die(f"groups[{index}] must be an object")
            logical = str(item.get("id") or f"group-{index + 1}")
            template = resolve(self.records, str(item.get("type") or ""), "group")
            try:
                template_root = ET.fromstring(html.unescape(template["entry"]["xml"]))
            except ET.ParseError as exc:
                die(f"invalid group template {template['title']}: {exc}")
            cells = [c for c in template_root.findall(".//mxCell") if c.get("vertex") == "1" and geometry(c) is not None]
            if not cells:
                die(f"group template has no vertex cells: {template['title']}")
            primary = max(cells, key=lambda c: float_attr(geometry(c), "width") * float_attr(geometry(c), "height"))
            pg = geometry(primary)
            default_w = float(template["entry"].get("w") or float_attr(pg, "width", 400))
            default_h = float(template["entry"].get("h") or float_attr(pg, "height", 240))
            x = float(item.get("x", 40 + (index % 2) * 620))
            y = self.root_y(float(item.get("y", 40 + (index // 2) * 420)), item.get("parent"))
            width = float(item.get("width", max(default_w, 520)))
            height = float(item.get("height", max(default_h, 300)))
            cell_id = self.new_id(logical)
            attrs = {
                "id": cell_id,
                "value": str(item.get("label", template["title"])),
                "style": append_style(primary.get("style", "rounded=1;whiteSpace=wrap;html=1;verticalAlign=top;align=left;"), item.get("style")),
                "vertex": "1",
                "parent": self.parent_id(item.get("parent")),
            }
            group_cell = ET.SubElement(self.root, "mxCell", attrs)
            ET.SubElement(group_cell, "mxGeometry", {
                "x": number(x), "y": number(y), "width": number(width), "height": number(height), "as": "geometry"
            })
            px = float_attr(pg, "x")
            py = float_attr(pg, "y")
            for extra_index, extra in enumerate(c for c in cells if c is not primary):
                clone = deepcopy(extra)
                clone.set("id", self.new_id())
                clone.set("parent", cell_id)
                eg = geometry(clone)
                if eg is not None:
                    eg.set("x", number(float_attr(eg, "x") - px))
                    eg.set("y", number(float_attr(eg, "y") - py))
                self.root.append(clone)

    def add_nodes(self) -> None:
        for index, item in enumerate(self.spec.get("nodes", [])):
            if not isinstance(item, dict):
                die(f"nodes[{index}] must be an object")
            logical = str(item.get("id") or f"node-{index + 1}")
            icon = resolve(self.records, str(item.get("icon") or ""), "icon")
            entry = icon["entry"]
            x = float(item.get("x", 80 + (index % 5) * 150))
            y = self.root_y(float(item.get("y", 100 + (index // 5) * 140)), item.get("parent"))
            width = float(item.get("width", 56))
            height = float(item.get("height", 56))
            try:
                data = normalize_image_data_uri_for_style(str(entry["data"]))
            except ValueError as exc:
                die(f"invalid embedded image for {icon['title']}: {exc}")
            style = (
                "shape=image;verticalLabelPosition=bottom;verticalAlign=top;"
                "labelPosition=center;align=center;html=1;aspect=fixed;imageAspect=0;"
                f"image={data};"
            )
            cell = ET.SubElement(self.root, "mxCell", {
                "id": self.new_id(logical),
                "value": str(item["label"] if "label" in item else icon["title"]),
                "style": append_style(style, item.get("style")),
                "vertex": "1",
                "parent": self.parent_id(item.get("parent")),
            })
            ET.SubElement(cell, "mxGeometry", {
                "x": number(x), "y": number(y), "width": number(width), "height": number(height), "as": "geometry"
            })

    def add_notes(self) -> None:
        for index, item in enumerate(self.spec.get("notes", [])):
            if not isinstance(item, dict):
                die(f"notes[{index}] must be an object")
            logical = str(item.get("id") or f"note-{index + 1}")
            style = (
                "rounded=1;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacing=10;"
                f"fillColor={item.get('fill', '#FFF7E6')};strokeColor={item.get('stroke', '#FFB648')};"
                "fontColor=#282B33;fontFamily=Arial;fontSize=12;"
            )
            cell = ET.SubElement(self.root, "mxCell", {
                "id": self.new_id(logical), "value": str(item.get("text", "")),
                "style": append_style(style, item.get("style")), "vertex": "1",
                "parent": self.parent_id(item.get("parent")),
            })
            ET.SubElement(cell, "mxGeometry", {
                "x": number(float(item.get("x", 40))),
                "y": number(self.root_y(float(item.get("y", 40)), item.get("parent"))),
                "width": number(float(item.get("width", 320))), "height": number(float(item.get("height", 70))),
                "as": "geometry",
            })

    def add_edges(self) -> None:
        for index, item in enumerate(self.spec.get("edges", [])):
            if not isinstance(item, dict):
                die(f"edges[{index}] must be an object")
            source, target = str(item.get("from", "")), str(item.get("to", ""))
            if source not in self.ids or target not in self.ids:
                die(f"edge {index + 1} references unknown endpoint: {source!r} -> {target!r}")
            color = item.get("color", "#4E5969")
            dashed = "1" if item.get("dashed", False) else "0"
            start_arrow = "classic" if item.get("bidirectional", False) else "none"
            style = (
                "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;"
                f"strokeColor={color};strokeWidth=2;dashed={dashed};startArrow={start_arrow};"
                "startFill=1;endArrow=classic;endFill=1;"
            )
            cell = ET.SubElement(self.root, "mxCell", {
                "id": self.new_id(str(item["id"]) if item.get("id") else None),
                "value": str(item.get("label", "")), "style": append_style(style, item.get("style")),
                "edge": "1", "parent": "1", "source": self.ids[source], "target": self.ids[target],
            })
            ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})

    def build(self) -> ET.ElementTree:
        page = self.spec.get("page") or {}
        width = max(1200, int(page.get("width", 1600))) if self.reference_enabled else int(page.get("width", 1600))
        content_height = int(page.get("height", 1000))
        if self.reference_enabled:
            self.add_reference_header(width)
        self.add_groups()
        self.add_nodes()
        self.add_notes()
        if self.reference_enabled:
            self.add_reference_access_edge()
            self.add_reference_footer(width, content_height)
        self.add_edges()
        height = content_height + REFERENCE_HEADER_HEIGHT + REFERENCE_FOOTER_HEIGHT if self.reference_enabled else content_height
        model = ET.Element("mxGraphModel", {
            "dx": "1200", "dy": "800", "grid": "1" if page.get("grid", True) else "0",
            "gridSize": "10", "guides": "1", "tooltips": "1", "connect": "1", "arrows": "1",
            "fold": "1", "page": "1", "pageScale": "1", "pageWidth": str(width), "pageHeight": str(height),
            "math": "0", "shadow": "0", "background": str(page.get("background", "#FFFFFF")),
        })
        model.append(self.root)
        diagram = ET.Element("diagram", {"id": "hwc-page-1", "name": str(self.spec.get("title", "Huawei Cloud Architecture"))})
        diagram.append(model)
        mxfile = ET.Element("mxfile", {"host": "app.diagrams.net", "agent": "hwc-drawio-skill", "version": "24.7.17"})
        mxfile.append(diagram)
        return ET.ElementTree(mxfile)


def number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def command_search(args: argparse.Namespace) -> None:
    records = load_libraries(args.libraries)
    query = normalize(args.query)
    matches = [r for r in records if (args.kind == "all" or r["kind"] == args.kind) and query in r["normalized"]]
    if not matches:
        tokens = set(query.split())
        matches = [r for r in records if (args.kind == "all" or r["kind"] == args.kind) and tokens.intersection(r["normalized"].split())]
    for record in sorted(matches, key=lambda r: (r["kind"], r["category"], r["title"])):
        print(f"{record['kind']}\t{record['category']}\t{record['title']}")
    if not matches:
        raise SystemExit(1)


def command_catalog(args: argparse.Namespace) -> None:
    records = load_libraries(args.libraries)
    groups: dict[tuple[str, str], list[str]] = {}
    for record in records:
        groups.setdefault((record["kind"], record["category"]), []).append(record["title"])
    lines = ["# Huawei Cloud icon catalog", "", "Generated from the bundled Draw.io libraries.", ""]
    for (kind, category), titles in sorted(groups.items()):
        lines.extend([f"## {category} — {kind}s ({len(titles)})", ""])
        lines.extend(f"- {title}" for title in sorted(titles))
        lines.append("")
    output = "\n".join(lines).rstrip() + "\n"
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(output, encoding="utf-8")
        print(f"wrote {args.markdown}")
    else:
        print(output, end="")


def command_generate(args: argparse.Namespace) -> None:
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        die(f"specification not found: {args.spec}")
    except json.JSONDecodeError as exc:
        die(f"invalid JSON specification: {exc}")
    if not isinstance(spec, dict):
        die("specification root must be a JSON object")
    tree = DiagramBuilder(spec, load_libraries(args.libraries)).build()
    ET.indent(tree, space="  ")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(args.output, encoding="utf-8", xml_declaration=True)
    command_validate(argparse.Namespace(file=args.output))
    print(f"generated {args.output}")


def validate_diagram_tree(tree: ET.ElementTree) -> tuple[int, int]:
    root = tree.getroot()
    if root.tag != "mxfile":
        raise ValueError(f"expected mxfile root, found {root.tag}")
    diagrams = root.findall("diagram")
    if not diagrams:
        raise ValueError("mxfile contains no diagram")
    ids: set[str] = set()
    cells = root.findall(".//mxCell")
    for cell in cells:
        cell_id = cell.get("id")
        if not cell_id:
            raise ValueError("mxCell without id")
        if cell_id in ids:
            raise ValueError(f"duplicate mxCell id: {cell_id}")
        ids.add(cell_id)
    for cell in cells:
        for attr in ("parent", "source", "target"):
            reference = cell.get(attr)
            if reference and reference not in ids:
                raise ValueError(f"mxCell {cell.get('id')} has missing {attr} reference {reference}")
        style = cell.get("style", "")
        style_tokens = [token.strip().casefold() for token in style.split(";") if token.strip()]
        is_image_cell = (
            "shape=image" in style_tokens
            or any(token.startswith("image=") for token in style_tokens)
        )
        if is_image_cell:
            try:
                extract_style_embedded_image(style)
            except ValueError as exc:
                raise ValueError(
                    f"mxCell {cell.get('id')} has invalid embedded image: {exc}"
                ) from exc
    return len(diagrams), len(cells)


def command_validate(args: argparse.Namespace) -> None:
    try:
        tree = ET.parse(args.file)
    except FileNotFoundError:
        die(f"file not found: {args.file}")
    except ET.ParseError as exc:
        die(f"invalid XML: {exc}")
    try:
        diagram_count, cell_count = validate_diagram_tree(tree)
    except ValueError as exc:
        die(str(exc))
    page_label = "page" if diagram_count == 1 else "pages"
    print(f"valid: {args.file} ({diagram_count} {page_label}, {cell_count} cells)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libraries", type=Path, default=DEFAULT_LIBRARY_DIR, help="directory containing mxlibrary XML files")
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search", help="search icon and group titles")
    search.add_argument("query")
    search.add_argument("--kind", choices=("all", "icon", "group"), default="all")
    search.set_defaults(func=command_search)
    catalog = sub.add_parser("catalog", help="print or write the full catalog")
    catalog.add_argument("--markdown", type=Path, help="write Markdown catalog to this path")
    catalog.set_defaults(func=command_catalog)
    generate = sub.add_parser("generate", help="generate a .drawio file from a JSON specification")
    generate.add_argument("spec", type=Path)
    generate.add_argument("output", type=Path)
    generate.set_defaults(func=command_generate)
    validate = sub.add_parser("validate", help="validate Draw.io XML and references")
    validate.add_argument("file", type=Path)
    validate.set_defaults(func=command_validate)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.libraries = args.libraries.resolve()
    args.func(args)


if __name__ == "__main__":
    main()
