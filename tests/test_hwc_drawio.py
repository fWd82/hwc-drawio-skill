"""Regression tests for embedded Huawei Cloud icon rendering."""

from __future__ import annotations

import base64
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import hwc_drawio  # noqa: E402


ICON_TITLES = (
    "Elastic Load Balance (ELB)",
    "Elastic Cloud Server (ECS)",
    "RDS for MySQL",
)


class EmbeddedIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = hwc_drawio.load_libraries(hwc_drawio.DEFAULT_LIBRARY_DIR)

    def build_three_icon_tree(self) -> ET.ElementTree:
        spec = {
            "title": "icon regression",
            "groups": [{"id": "cloud", "type": "Huawei Cloud"}],
            "nodes": [
                {"id": f"icon-{index}", "icon": title, "label": title, "parent": "cloud"}
                for index, title in enumerate(ICON_TITLES)
            ],
        }
        return hwc_drawio.DiagramBuilder(spec, self.records).build()

    def test_named_icons_have_complete_style_values(self) -> None:
        tree = self.build_three_icon_tree()
        cells = {cell.get("value"): cell for cell in tree.findall(".//mxCell")}
        for title in ICON_TITLES:
            with self.subTest(icon=title):
                value = hwc_drawio.extract_style_embedded_image(cells[title].get("style", ""))
                self.assertTrue(value.startswith("data:image/"))
                self.assertNotIn(";base64,", value)
                self.assertGreater(len(value.partition(",")[2]), 100)

    def test_named_icon_payloads_decode_to_valid_svg(self) -> None:
        tree = self.build_three_icon_tree()
        cells = {cell.get("value"): cell for cell in tree.findall(".//mxCell")}
        for title in ICON_TITLES:
            with self.subTest(icon=title):
                value = hwc_drawio.extract_style_embedded_image(cells[title].get("style", ""))
                mime_type, decoded = hwc_drawio.decode_style_embedded_image(value)
                self.assertEqual(mime_type.casefold(), "image/svg+xml")
                root = ET.fromstring(decoded)
                self.assertEqual(root.tag.rsplit("}", 1)[-1].casefold(), "svg")

    def test_normalization_preserves_every_library_payload(self) -> None:
        icons = [record for record in self.records if record["kind"] == "icon"]
        self.assertGreater(len(icons), 200)
        for record in icons:
            with self.subTest(icon=record["title"], library=record["library"]):
                raw = str(record["entry"]["data"])
                normalized = hwc_drawio.normalize_image_data_uri_for_style(raw)
                raw_payload = raw.split(";base64,", 1)[1]
                normalized_payload = normalized.split(",", 1)[1]
                self.assertEqual(normalized_payload, raw_payload)
                self.assertEqual(base64.b64decode(normalized_payload, validate=True), base64.b64decode(raw_payload, validate=True))

    def test_normalization_supports_image_mime_types_generically(self) -> None:
        payload = "QUJDRA=="
        for mime_type in ("image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"):
            with self.subTest(mime_type=mime_type):
                normalized = hwc_drawio.normalize_image_data_uri_for_style(
                    f"data:{mime_type};base64,{payload}"
                )
                self.assertEqual(normalized, f"data:{mime_type},{payload}")

    def test_complete_diagram_and_group_templates_validate(self) -> None:
        tree = self.build_three_icon_tree()
        self.assertEqual(hwc_drawio.validate_diagram_tree(tree)[0], 1)

    def test_default_reference_regions_are_added_with_bundled_icons(self) -> None:
        tree = self.build_three_icon_tree()
        joined = "\n".join(cell.get("value", "") for cell in tree.findall(".//mxCell"))
        for expected in ("Huawei Cloud Architecture - Customer Name", "Application User", "GitHub", "DockerHub", "Administrator<br>Local PC", "3rd-party Cloud<br>On-premises", "REFERENCE PLATFORM &amp; OPERATIONS SERVICES", "Security", "Cloud Operations", "Monitoring &amp; Logging", "Backup &amp; Recovery", "Image Management", "DEW\nEncryption", "SecMaster\nSecurity Ops", "CBR\nBackup & Recovery", "SWR\nContainer Images"):
            with self.subTest(expected=expected):
                self.assertIn(expected, joined)
        labels = {label for _, _, services in hwc_drawio.REFERENCE_SERVICES for _, label in services}
        reference_icons = [cell for cell in tree.findall(".//mxCell") if cell.get("value", "") in labels]
        self.assertEqual(len(reference_icons), 11)
        for cell in reference_icons:
            hwc_drawio.extract_style_embedded_image(cell.get("style", ""))

    def test_reference_regions_shift_only_root_content_and_expand_page(self) -> None:
        spec = {"page": {"width": 1200, "height": 700}, "groups": [
            {"id": "cloud", "type": "Huawei Cloud", "x": 80, "y": 60},
            {"id": "vpc", "type": "Virtual Private Cloud (VPC)", "x": 40, "y": 70, "parent": "cloud"},
        ]}
        tree = hwc_drawio.DiagramBuilder(spec, self.records).build()
        cells = tree.findall(".//mxCell")
        cloud = next(cell for cell in cells if cell.get("value") == "Huawei Cloud")
        vpc = next(cell for cell in cells if cell.get("value") == "Virtual Private Cloud (VPC)")
        self.assertEqual(cloud.find("mxGeometry").get("y"), str(60 + hwc_drawio.REFERENCE_HEADER_HEIGHT))
        self.assertEqual(vpc.find("mxGeometry").get("y"), "70")
        self.assertEqual(tree.find(".//mxGraphModel").get("pageHeight"), str(700 + hwc_drawio.REFERENCE_HEADER_HEIGHT + hwc_drawio.REFERENCE_FOOTER_HEIGHT))

    def test_reference_false_preserves_original_canvas_and_coordinates(self) -> None:
        spec = {"reference": False, "page": {"width": 900, "height": 600}, "groups": [{"id": "cloud", "type": "Huawei Cloud", "x": 80, "y": 60}]}
        tree = hwc_drawio.DiagramBuilder(spec, self.records).build()
        values = [cell.get("value", "") for cell in tree.findall(".//mxCell")]
        self.assertNotIn("Application User", values)
        cloud = next(cell for cell in tree.findall(".//mxCell") if cell.get("value") == "Huawei Cloud")
        self.assertEqual(cloud.find("mxGeometry").get("y"), "60")
        model = tree.find(".//mxGraphModel")
        self.assertEqual(model.get("pageWidth"), "900")
        self.assertEqual(model.get("pageHeight"), "600")

    def test_empty_reference_title_falls_back_to_visible_default(self) -> None:
        spec = {"reference": {"title": ""}}
        tree = hwc_drawio.DiagramBuilder(spec, self.records).build()
        joined = "\n".join(cell.get("value", "") for cell in tree.findall(".//mxCell"))
        self.assertIn("Huawei Cloud Architecture - Customer Name", joined)

    def test_simple_ecs_rds_obs_sample_is_logical_self_contained_and_valid(self) -> None:
        spec_path = ROOT / "samples" / "two-ecs-rds-obs-portal.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        self.assertNotEqual(spec.get("reference"), False)
        icons = [node["icon"] for node in spec["nodes"]]
        self.assertEqual(icons.count("Elastic Cloud Server (ECS)"), 2)
        self.assertEqual(icons.count("Relational Database Service (RDS)"), 1)
        self.assertEqual(icons.count("Object Storage Service (OBS)"), 1)
        forbidden = ("Elastic IP", "EIP", "Elastic Load Balance", "ELB", "NAT Gateway", "Domain Name Service", "DNS", "public IP")
        serialized_spec = json.dumps(spec)
        for term in forbidden:
            with self.subTest(forbidden=term):
                self.assertNotIn(term, serialized_spec)

        expected_pairs = {
            ("ecs-1", "rds"), ("ecs-1", "obs"),
            ("ecs-2", "rds"), ("ecs-2", "obs"),
        }
        actual_pairs = {(edge["from"], edge["to"]) for edge in spec["edges"]}
        self.assertTrue(expected_pairs.issubset(actual_pairs))

        tree = hwc_drawio.DiagramBuilder(spec, self.records).build()
        self.assertEqual(hwc_drawio.validate_diagram_tree(tree)[0], 1)
        self.assertIsNotNone(tree.find(".//diagram/mxGraphModel/root"))
        values = "\n".join(cell.get("value", "") for cell in tree.findall(".//mxCell"))
        self.assertIn("Huawei Cloud Architecture - Two ECS Servers with RDS and OBS", values)
        self.assertIn("Application User", values)
        self.assertIn("Portal access (logical)", values)
        self.assertNotIn("multiple AZs", values)
        self.assertNotIn("HA mode", values)

        portal_id = next(cell.get("id") for cell in tree.findall(".//mxCell") if cell.get("value", "").startswith("Customer Portal"))
        access_edge = next(cell for cell in tree.findall(".//mxCell") if cell.get("value") == "Portal access (logical)")
        actor_id = next(cell.get("id") for cell in tree.findall(".//mxCell") if cell.get("value") == "USER")
        self.assertEqual(access_edge.get("source"), actor_id)
        self.assertEqual(access_edge.get("target"), portal_id)
        self.assertNotEqual(access_edge.get("target"), next(cell.get("id") for cell in tree.findall(".//mxCell") if cell.get("value") == "Relational Database Service (RDS)"))
        self.assertNotEqual(access_edge.get("target"), next(cell.get("id") for cell in tree.findall(".//mxCell") if cell.get("value") == "Object Storage Service (OBS)"))

        xml = ET.tostring(tree.getroot(), encoding="unicode")
        self.assertNotIn("http://", xml)
        self.assertNotIn("https://", xml)
        for cell in tree.findall(".//mxCell"):
            style = cell.get("style", "")
            tokens = [token.strip().casefold() for token in style.split(";") if token.strip()]
            if "shape=image" in tokens:
                hwc_drawio.extract_style_embedded_image(style)

    def test_validator_rejects_previously_broken_style(self) -> None:
        raw = str(hwc_drawio.resolve(self.records, "Elastic Cloud Server (ECS)", "icon")["entry"]["data"])
        broken = f"shape=image;image={raw};resizable=0;"
        tree = make_single_image_tree(broken)
        with self.assertRaisesRegex(ValueError, "detached style token begins with base64"):
            hwc_drawio.validate_diagram_tree(tree)

    def test_validator_rejects_truncated_image_value(self) -> None:
        tree = make_single_image_tree("shape=image;image=data:image/svg+xml;resizable=0;")
        with self.assertRaisesRegex(ValueError, "truncated image value"):
            hwc_drawio.validate_diagram_tree(tree)

    def test_validator_rejects_missing_payload(self) -> None:
        tree = make_single_image_tree("shape=image;image=data:image/svg+xml,;resizable=0;")
        with self.assertRaisesRegex(ValueError, "empty payload"):
            hwc_drawio.validate_diagram_tree(tree)

    def test_validator_rejects_external_image_url(self) -> None:
        tree = make_single_image_tree("shape=image;image=https://example.com/icon.svg;resizable=0;")
        with self.assertRaisesRegex(ValueError, "not a usable embedded data URI"):
            hwc_drawio.validate_diagram_tree(tree)


def make_single_image_tree(style: str) -> ET.ElementTree:
    mxfile = ET.Element("mxfile")
    diagram = ET.SubElement(mxfile, "diagram")
    model = ET.SubElement(diagram, "mxGraphModel")
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    cell = ET.SubElement(root, "mxCell", {"id": "2", "parent": "1", "vertex": "1", "style": style})
    ET.SubElement(cell, "mxGeometry", {"as": "geometry"})
    return ET.ElementTree(mxfile)


if __name__ == "__main__":
    unittest.main()
