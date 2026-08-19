# Diagram specification

## Contents

- Coordinate model
- Top-level schema
- Optional reference regions
- Groups
- Nodes
- Edges
- Notes
- Complete example

## Coordinate model

The page origin is at the upper-left. Coordinates are in Draw.io points. A child with `parent` uses coordinates relative to that parent. Declare every parent before its children. A practical spacing unit is 20–40 points; keep at least 80 points between icon centers.

Containers render in declaration order, followed by nodes, notes, and edges. Put outer groups before inner groups.

## Top-level schema

```json
{
  "title": "Diagram page title",
  "page": { "width": 1600, "height": 1000, "grid": true, "background": "#FFFFFF" },
  "reference": { "customer": "Customer Name", "subtitle": "Solution Architecture" },
  "groups": [],
  "nodes": [],
  "edges": [],
  "notes": []
}
```

Unknown fields are ignored. Title, page, and all arrays are optional. IDs must be unique and must not contain spaces.

## Optional reference regions

Every generated diagram includes two clearly labeled, editable reference regions by default:

- A header titled Huawei Cloud Architecture - Customer Name, with Application User, Administrator / Local PC, GitHub, DockerHub, and third-party cloud / on-premises context.
- A footer with example Huawei Cloud security, operations, monitoring/logging, backup/recovery, and image-management services using exact bundled color icons.

These are examples only. They do not imply customer scope, licensing, sizing, connectivity, or commercial commitment. Adapt or delete them in diagrams.net. Customize the text with:

~~~json
"reference": {
  "customer": "Example Customer",
  "title": "Huawei Cloud Architecture - Customer Portal",
  "subtitle": "Production Solution Architecture",
  "application_entry": "portal",
  "application_access_label": "Portal access (logical)",
  "ha_guidance": false
}
~~~

Omit reference to keep the complete default header, title, Application User context, and five-category footer. A short or simple architecture is not a reason to disable them.

Use "reference": false (or "reference": {"enabled": false}) only when the user explicitly requests a clean canvas, no header/footer, or removal of the reference regions. Use "show_title": false only when the user explicitly asks to omit the visible title.

For a user-facing application, add an editable note or component representing the logical portal/application entry and set application_entry to that ID. The generator connects Application User to it with application_access_label. This is a logical access path, not an inferred EIP, ELB, NAT Gateway, public IP, DNS service, port, or routing design. Do not target RDS, OBS, or another data store.

Set ha_guidance to false when the prompt does not establish an HA or multi-AZ requirement. When reference regions are enabled, only root-level content is shifted down; child coordinates remain relative to their parents. The page expands to keep the footer below the architecture.

## Groups

```json
{
  "id": "vpc-prod",
  "type": "Virtual Private Cloud (VPC)",
  "label": "Production VPC\n10.10.0.0/16",
  "x": 80,
  "y": 80,
  "width": 1100,
  "height": 650,
  "parent": "region-uae"
}
```

- `type`: Exact or uniquely matching group library title.
- `label`: Optional replacement for the template title.
- `x`, `y`, `width`, `height`: Optional; sensible defaults are applied.
- `parent`: Optional group ID. Coordinates become parent-relative.
- `style`: Optional Draw.io style suffix for advanced overrides.

Canonical group types are: `Huawei Cloud`, `Region`, `Availability Zone (AZ)`, `Virtual Private Cloud (VPC)`, `Subnet`, `Security Group`, `Cloud Container Engine (CCE)`, and `Auto Scaling Group (AS Group)`.

## Nodes

```json
{
  "id": "web-1",
  "icon": "Elastic Cloud Server (ECS)",
  "label": "Web ECS 1",
  "x": 120,
  "y": 150,
  "width": 56,
  "height": 56,
  "parent": "subnet-web"
}
```

- `icon`: Exact or uniquely matching icon title. Use `search` before guessing.
- `label`: Defaults to the icon title. Use `""` to hide it.
- `x`, `y`: Optional. Missing positions receive a simple grid placement.
- `width`, `height`: Optional; default to 56.
- `parent`: Optional group ID, with parent-relative coordinates.
- `style`: Optional Draw.io style suffix.

## Edges

```json
{
  "id": "client-to-elb",
  "from": "client",
  "to": "elb",
  "label": "HTTPS :443",
  "color": "#4E5969",
  "dashed": false,
  "bidirectional": false,
  "style": "exitX=1;exitY=0.5;entryX=0;entryY=0.5;"
}
```

`from` and `to` must reference a node or group ID. Orthogonal routing and an end arrow are the defaults. Set `bidirectional` for arrows at both ends. `style` can append routing hints.

## Notes

```json
{
  "id": "assumptions",
  "text": "Assumption: private subnets use NAT Gateway for egress.",
  "x": 80,
  "y": 780,
  "width": 420,
  "height": 70,
  "fill": "#FFF7E6",
  "stroke": "#FFB648",
  "parent": "region-uae"
}
```

Notes are editable rounded rectangles. Use them sparingly for assumptions, legends, and operational details.

## Complete example

```json
{
  "title": "Highly available web service",
  "page": { "width": 1500, "height": 900 },
  "groups": [
    { "id": "cloud", "type": "Huawei Cloud", "x": 260, "y": 40, "width": 1160, "height": 760 },
    { "id": "region", "type": "Region", "label": "Region: example", "x": 40, "y": 60, "width": 1080, "height": 650, "parent": "cloud" },
    { "id": "vpc", "type": "Virtual Private Cloud (VPC)", "label": "Production VPC", "x": 40, "y": 70, "width": 1000, "height": 530, "parent": "region" },
    { "id": "az1", "type": "Availability Zone (AZ)", "label": "AZ 1", "x": 50, "y": 80, "width": 430, "height": 390, "parent": "vpc" },
    { "id": "az2", "type": "Availability Zone (AZ)", "label": "AZ 2", "x": 520, "y": 80, "width": 430, "height": 390, "parent": "vpc" }
  ],
  "nodes": [
    { "id": "elb", "icon": "Elastic Load Balance (ELB)", "label": "Public ELB", "x": 520, "y": 10, "parent": "vpc" },
    { "id": "ecs1", "icon": "Elastic Cloud Server (ECS)", "label": "App ECS 1", "x": 170, "y": 160, "parent": "az1" },
    { "id": "ecs2", "icon": "Elastic Cloud Server (ECS)", "label": "App ECS 2", "x": 170, "y": 160, "parent": "az2" }
  ],
  "edges": [
    { "from": "elb", "to": "ecs1", "label": "HTTP :8080" },
    { "from": "elb", "to": "ecs2", "label": "HTTP :8080" }
  ]
}
```
