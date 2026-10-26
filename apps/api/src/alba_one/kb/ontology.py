"""Pydantic v2 models for the ALBA ONE Business Ontology (`kb/ontology.py`).

Maps business concepts (company, product, equipment, vessel, route, staff,
model_release) to DBA-controlled PostgreSQL views, ACL tags, and decision rules.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from alba_one.kb.ontology_logic import OntologyCatalog, load_ontology_catalog


class EntityDefinition(BaseModel):
    """Pydantic v2 schema for a single business entity type in the tenant ontology."""

    model_config = ConfigDict(extra="forbid")

    entity_type: str = Field(..., min_length=1)
    label_ja: str = Field(..., min_length=1)
    label_en: str = Field(..., min_length=1)
    source_view: str = Field(..., min_length=1)
    source_table: str = Field(..., min_length=1)
    primary_key: str = Field(default="id", min_length=1)
    acl_tags: list[str] = Field(..., min_length=1)
    attributes: list[str] = Field(default_factory=list)
    decision_fields: dict[str, str] = Field(default_factory=dict)


class RelationDefinition(BaseModel):
    """Pydantic v2 schema for a directed relationship between two ontology entities."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    from_entity: str = Field(..., min_length=1)
    to_entity: str = Field(..., min_length=1)
    join_condition: str = Field(..., min_length=1)
    description_ja: str = Field(..., min_length=1)
    description_en: str = Field(..., min_length=1)


class TenantOntology(BaseModel):
    """Complete Pydantic v2 business ontology for a single tenant."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    tenant_name_ja: str = Field(..., min_length=1)
    tenant_name_en: str = Field(..., min_length=1)
    version: str = Field(default="1.0.0")
    entities: dict[str, EntityDefinition] = Field(..., min_length=1)
    relations: list[RelationDefinition] = Field(default_factory=list)

    @classmethod
    def from_yaml(
        cls,
        yaml_path: str | Path,
        expected_tenant_id: str | None = None,
    ) -> TenantOntology:
        """Load and validate a `TenantOntology` from YAML."""
        catalog: OntologyCatalog = load_ontology_catalog(
            yaml_path, expected_tenant_id=expected_tenant_id
        )
        return cls(
            tenant_id=catalog.tenant_id,
            tenant_name_ja=catalog.tenant_name_ja,
            tenant_name_en=catalog.tenant_name_en,
            version=catalog.version,
            entities={
                k: EntityDefinition(
                    entity_type=v.entity_type,
                    label_ja=v.label_ja,
                    label_en=v.label_en,
                    source_view=v.source_view,
                    source_table=v.source_table,
                    primary_key=v.primary_key,
                    acl_tags=v.acl_tags,
                    attributes=v.attributes,
                    decision_fields=v.decision_fields,
                )
                for k, v in catalog.entities.items()
            },
            relations=[
                RelationDefinition(
                    name=r.name,
                    from_entity=r.from_entity,
                    to_entity=r.to_entity,
                    join_condition=r.join_condition,
                    description_ja=r.description_ja,
                    description_en=r.description_en,
                )
                for r in catalog.relations
            ],
        )
