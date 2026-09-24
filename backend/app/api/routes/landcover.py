from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from app.api.deps import parse_bbox, require_db
from app.api.schemas import ERROR_RESPONSES, ApiResponse, FeatureCollection
from app.core.responses import ok
from app.db.engine import connection
from app.ingestion.landcover.worldcover import DATASET_VERSION, WORLDCOVER_CLASSES
from app.repositories.filters import Where, feature_collection, point_feature

router = APIRouter(tags=["Land cover"], responses=ERROR_RESPONSES)


@router.get("/landcover/classes", summary="ESA WorldCover legend")
def get_classes():
    return ok(
        [{"code": code, "name": name, "color": color} for code, (name, color) in WORLDCOVER_CLASSES.items()],
        {"dataset": f"ESA WorldCover 10 m {DATASET_VERSION}", "license": "CC BY 4.0"},
    )


@router.get(
    "/landcover",
    response_model=ApiResponse[FeatureCollection],
    dependencies=[Depends(require_db)],
    summary="Land-cover samples (GeoJSON)",
)
def get_landcover(bbox: str | None = None, limit: int = Query(20000, ge=1, le=50000)):
    """ESA WorldCover samples taken around thermal clusters (dominant class + class fractions)."""
    w = Where().add("lc.status = 'ok'")
    w.bbox("lc.geom", parse_bbox(bbox))
    with connection() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT lc.id, lc.latitude, lc.longitude, lc.dominant_class_code, lc.dominant_class_name,
                       lc.dominant_fraction, lc.class_fractions, lc.sample_radius_m, lc.sampled_at
                  FROM land_cover lc {w.sql}
                 ORDER BY lc.sampled_at DESC LIMIT :limit
                """
            ),
            {**w.params, "limit": limit},
        ).mappings().all()
    features = [
        point_feature(
            r["id"],
            r["latitude"],
            r["longitude"],
            {
                "id": r["id"],
                "class_code": r["dominant_class_code"],
                "class_name": r["dominant_class_name"],
                "fraction": r["dominant_fraction"],
                "fractions": r["class_fractions"],
                "color": WORLDCOVER_CLASSES.get(r["dominant_class_code"], ("", "#999999"))[1],
                "radius_m": r["sample_radius_m"],
                "sampled_at": r["sampled_at"],
            },
        )
        for r in rows
    ]
    return ok(feature_collection(features), {"count": len(features), "dataset": f"ESA WorldCover {DATASET_VERSION}"})
