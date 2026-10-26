"""Pure ontology loading, validation, and ACL filtering logic (stdlib + PyYAML)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REQUIRED_ENTITY_TYPES: tuple[str, ...] = (
    "company",
    "product",
    "equipment",
    "vessel",
    "route",
    "staff",
    "model_release",
)


@dataclass(frozen=True)
class EntitySpec:
    """Pure representation of a tenant business entity definition."""

    entity_type: str
    label_ja: str
    label_en: str
    source_view: str
    source_table: str
    primary_key: str
    acl_tags: list[str]
    attributes: list[str]
    decision_fields: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RelationSpec:
    """Pure representation of a relationship between two business entities."""

    name: str
    from_entity: str
    to_entity: str
    join_condition: str
    description_ja: str
    description_en: str


@dataclass(frozen=True)
class OntologyCatalog:
    """Complete per-tenant business ontology loaded from YAML."""

    tenant_id: str
    tenant_name_ja: str
    tenant_name_en: str
    version: str
    entities: dict[str, EntitySpec]
    relations: list[RelationSpec]

    def filter_entities_for_acl(self, caller_acl_tags: set[str]) -> list[EntitySpec]:
        """Return only entities whose `acl_tags` intersect with `caller_acl_tags`."""
        allowed: list[EntitySpec] = []
        for spec in self.entities.values():
            if set(spec.acl_tags) & caller_acl_tags:
                allowed.append(spec)
        return allowed


def load_ontology_catalog(yaml_path: str | Path, expected_tenant_id: str | None = None) -> OntologyCatalog:
    """Load and validate a tenant ontology YAML file."""
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Ontology YAML not found: {path}")

    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Ontology YAML root must be a mapping.")

    tenant_id = str(raw.get("tenant_id", "")).strip()
    if not tenant_id:
        raise ValueError("Ontology YAML must declare non-empty 'tenant_id'.")
    if expected_tenant_id and tenant_id != expected_tenant_id:
        raise PermissionError(
            f"Ontology tenant_id mismatch: expected '{expected_tenant_id}', got '{tenant_id}'."
        )

    raw_entities = raw.get("entities", {})
    if not isinstance(raw_entities, dict) or not raw_entities:
        raise ValueError("Ontology YAML must define non-empty 'entities' mapping.")

    entities: dict[str, EntitySpec] = {}
    for etype, edata in raw_entities.items():
        if not isinstance(edata, dict):
            raise ValueError(f"Entity '{etype}' definition must be a mapping.")
        acl_tags = [str(t) for t in edata.get("acl_tags", [])]
        if not acl_tags:
            raise ValueError(f"Entity '{etype}' must declare at least one ACL tag.")
        entities[str(etype)] = EntitySpec(
            entity_type=str(etype),
            label_ja=str(edata.get("label_ja", etype)),
            label_en=str(edata.get("label_en", etype)),
            source_view=str(edata.get("source_view", "")),
            source_table=str(edata.get("source_table", "")),
            primary_key=str(edata.get("primary_key", "id")),
            acl_tags=acl_tags,
            attributes=[str(a) for a in edata.get("attributes", [])],
            decision_fields={
                str(k): str(v) for k, v in (edata.get("decision_fields") or {}).items()
            },
        )

    relations: list[RelationSpec] = []
    for rdata in raw.get("relations", []):
        if isinstance(rdata, dict):
            from_ent = str(rdata.get("from_entity", ""))
            to_ent = str(rdata.get("to_entity", ""))
            if from_ent not in entities or to_ent not in entities:
                raise ValueError(
                    f"Relation '{rdata.get('name')}' references unknown entity '{from_ent}' or '{to_ent}'."
                )
            join_cond = str(rdata.get("join_condition") or rdata.get("join_Condition") or "")
            relations.append(
                RelationSpec(
                    name=str(rdata.get("name", "")),
                    from_entity=from_ent,
                    to_entity=to_ent,
                    join_condition=join_cond,
                    description_ja=str(rdata.get("description_ja", "")),
                    description_en=str(rdata.get("description_en", "")),
                )
            )

    return OntologyCatalog(
        tenant_id=tenant_id,
        tenant_name_ja=str(raw.get("tenant_name_ja", "")),
        tenant_name_en=str(raw.get("tenant_name_en", "")),
        version=str(raw.get("version", "1.0.0")),
        entities=entities,
        relations=relations,
    )
