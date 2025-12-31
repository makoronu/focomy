"""Schema API endpoints - content type definitions."""

from typing import Any

from fastapi import APIRouter, HTTPException

from ..services.field import field_service

router = APIRouter(prefix="/schema", tags=["schema"])


@router.get("")
async def get_all_schemas() -> dict[str, Any]:
    """Get all content type definitions."""
    content_types = field_service.get_all_content_types()
    relations = field_service.get_all_relation_types()

    return {
        "content_types": {
            name: {
                "name": ct.name,
                "label": ct.label,
                "label_plural": ct.label_plural,
                "icon": ct.icon,
                "admin_menu": ct.admin_menu,
                "searchable": ct.searchable,
                "fields": [
                    {
                        "name": f.name,
                        "type": f.type,
                        "label": f.label,
                        "required": f.required,
                        "unique": f.unique,
                        "options": f.options,
                        "default": f.default,
                    }
                    for f in ct.fields
                ],
                "relations": [
                    {
                        "type": r.type,
                        "label": r.label,
                        "required": r.required,
                    }
                    for r in ct.relations
                ],
            }
            for name, ct in content_types.items()
        },
        "relations": {
            name: {
                "from": rel.from_type,
                "to": rel.to_type,
                "type": rel.type,
                "label": rel.label,
                "required": rel.required,
            }
            for name, rel in relations.items()
        },
    }


@router.get("/{type_name}")
async def get_schema(type_name: str) -> dict[str, Any]:
    """Get a specific content type definition."""
    # Handle /relations specially to avoid route order conflict
    if type_name == "relations":
        return await get_relations()

    ct = field_service.get_content_type(type_name)
    if not ct:
        raise HTTPException(status_code=404, detail=f"Content type '{type_name}' not found")

    return {
        "name": ct.name,
        "label": ct.label,
        "label_plural": ct.label_plural,
        "icon": ct.icon,
        "admin_menu": ct.admin_menu,
        "searchable": ct.searchable,
        "hierarchical": ct.hierarchical,
        "auth_entity": ct.auth_entity,
        "fields": [
            {
                "name": f.name,
                "type": f.type,
                "label": f.label,
                "required": f.required,
                "unique": f.unique,
                "indexed": f.indexed,
                "max_length": f.max_length,
                "options": f.options,
                "default": f.default,
                "auto_generate": f.auto_generate,
                "accept": f.accept,
                "multiple": f.multiple,
            }
            for f in ct.fields
        ],
        "relations": [
            {
                "type": r.type,
                "label": r.label,
                "required": r.required,
                "target": r.target,
                "self_referential": r.self_referential,
            }
            for r in ct.relations
        ],
    }


@router.get("/relations")
async def get_relations() -> dict[str, Any]:
    """Get all relation type definitions."""
    relations = field_service.get_all_relation_types()

    return {
        name: {
            "from": rel.from_type,
            "to": rel.to_type,
            "type": rel.type,
            "label": rel.label,
            "required": rel.required,
            "self_referential": rel.self_referential,
        }
        for name, rel in relations.items()
    }
