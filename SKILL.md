---
name: hwc-drawio-skill
description: Generate, revise, and validate editable Draw.io (.drawio) architecture diagrams that use bundled official-style Huawei Cloud service icons and Huawei Cloud enclosure groups. Use for Huawei Cloud architecture diagrams, topology maps, solution designs, network diagrams, VPC/AZ/subnet/security-group layouts, CCE diagrams, migration diagrams, and any request to convert a Huawei Cloud design or description into Draw.io XML.
---

# Huawei Cloud Draw.io

Create self-contained, editable Draw.io diagrams with the bundled Huawei Cloud libraries. Use the deterministic generator instead of manually embedding icon data.

## Workflow

1. Understand the architecture before drawing. Identify trust boundaries, regions, availability zones, VPCs, subnets, security groups, tiers, ingress/egress paths, and HA relationships.
2. Search for exact icon and group names:

   ```bash
   python scripts/hwc_drawio.py search "elastic cloud server"
   python scripts/hwc_drawio.py search "vpc" --kind group
   ```

   Read [references/icon-catalog.md](references/icon-catalog.md) only when broad discovery is needed. Regenerate it with `python scripts/hwc_drawio.py catalog --markdown references/icon-catalog.md` if libraries change.
3. Create a JSON specification. Read [references/specification.md](references/specification.md) for the schema and layout rules. Prefer exact catalog titles for `icon` and group `type` values.
4. Generate and validate:

   ```bash
   python scripts/hwc_drawio.py generate architecture.json architecture.drawio
   python scripts/hwc_drawio.py validate architecture.drawio
   ```

5. Inspect the result. Open it in diagrams.net/Draw.io when browser or GUI tooling is available. Verify labels, containment, connector direction, overlap, and reading order. Iterate on the JSON rather than hand-editing large embedded data URIs.
6. Deliver the `.drawio` file and, when useful, the JSON source specification.

## Diagram standards

- Use the bundled group templates for Huawei Cloud, Region, Availability Zone, VPC, Subnet, Security Group, CCE, and Auto Scaling Group boundaries.
- Nest containers semantically with `parent`; coordinates of children are relative to the parent.
- Keep outer containers behind inner containers and resources. Declare parents before children.
- Use left-to-right flow for request/data paths unless the architecture strongly suggests another direction.
- Label connections with protocols, ports, or purpose when known. Never invent missing security rules, CIDRs, regions, or HA claims; mark assumptions visibly.
- Prefer one primary architectural story per page. Use multiple pages only when the user asks for separate views; the generator currently creates one page per specification.
- Keep icons at their default 56×56 size when possible. Use short visible labels and put detail in notes.
- Use orthogonal connectors, avoid line crossings, and use dashed connectors for optional, asynchronous, backup, or control-plane paths when appropriate.
- Preserve editability: do not rasterize the final diagram or depend on external image URLs.
- Preserve the reference header and footer by default for every diagram, including short or simple architecture prompts. Omit the reference field when no customization is needed.
- Set "reference": false only when the user explicitly requests a clean canvas, no header/footer, or removal of the reference regions. Never infer this preference from brevity, few resources, or a simple topology.
- Always show an editable, architecture-specific title unless the user explicitly asks to omit it. Set reference.title, or derive a concise title from the requested services and purpose. Use reference.show_title: false only for an explicit title-omission request.
- Include Application User for a user-facing portal or application. Create an editable logical portal/application entry note, set reference.application_entry to its ID, and label the connection Portal access (logical) or Application access (logical).
- Treat the Application User connection as a logical access path when ingress is unspecified. Do not infer EIP, ELB, NAT Gateway, public IP, DNS, ports, or any other network implementation. Never connect Application User directly to RDS, OBS, or another data store.
- Treat every reference-region item as an editable example, not confirmed customer scope. Do not remove the regions merely because their items are optional.
- The operations footer uses exact bundled Huawei Cloud color icons. TMS is absent from the bundled catalog, so the template uses Cloud Operations Center (COC) alongside CTS and must not relabel COC as TMS.

## Updating libraries

Place Draw.io `<mxlibrary>` XML files in `assets/libraries/`. Run `catalog` and then regenerate the Markdown catalog. The generator automatically distinguishes icon entries (`data`) from group templates (`xml`). Do not rewrite or decode the embedded SVG data.

Keep library `data:<image-mime>;base64,<payload>` values unchanged. When generating a cell, the script removes only the `;base64` marker required for safe embedding in a semicolon-delimited mxGraph style; it never decodes or re-encodes the payload. Run `python -m unittest discover -s tests -v` after changing image handling or libraries.

## Failure handling

- If a lookup is ambiguous, use one of the candidates printed by `search` or `generate`.
- If a requested service has no exact icon, ask before substituting when the identity matters. Otherwise use the closest generic Huawei Cloud icon and disclose the substitution.
- If Python is unavailable, create standards-compliant uncompressed Draw.io XML manually, but copy exact styles/data only from the bundled libraries and validate the XML parser can open it.
- Never place a raw `;base64,` data URI inside an mxGraph `style` attribute. Use the generator's normalization helper and enhanced validator.
