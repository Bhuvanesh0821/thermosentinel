"""Industrial proximity analysis (PostGIS).

For each cluster the three nearest active facilities are found with a GIST-indexed
ST_DWithin search. Distance is measured to the facility's mapped footprint when one exists
(0 m when the cluster centre falls inside it), otherwise to its point location.

Relationship classes:
  inside_footprint  centre inside the mapped facility outline
  adjacent          <= PROXIMITY_NEAR_M
  nearby            <= PROXIMITY_ASSOC_M      (upper bound of "industrial association")
  distant           <= PROXIMITY_SEARCH_RADIUS_M
  none              no facility within the search radius
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import Settings

ASSOCIATED = ("inside_footprint", "adjacent", "nearby")


def compute_proximity(conn: Connection, cluster_ids: list[int], settings: Settings) -> dict:
    if not cluster_ids:
        return {"clusters": 0, "associated": 0}
    params = {
        "ids": cluster_ids,
        "search": settings.proximity_search_radius_m,
        "near": settings.proximity_near_m,
        "assoc": settings.proximity_assoc_m,
    }
    conn.execute(
        text("DELETE FROM cluster_facility_proximity WHERE cluster_id = ANY(CAST(:ids AS bigint[]))"), params
    )
    conn.execute(
        text(
            """
            INSERT INTO cluster_facility_proximity (cluster_id, facility_id, rank, distance_m, relationship)
            SELECT c.id, n.facility_id, n.rnk, n.dist,
                   CASE WHEN n.has_footprint AND n.dist = 0 THEN 'inside_footprint'
                        WHEN n.dist <= :near  THEN 'adjacent'
                        WHEN n.dist <= :assoc THEN 'nearby'
                        ELSE 'distant' END
              FROM thermal_clusters c
             CROSS JOIN LATERAL (
                    SELECT d.facility_id, d.dist, d.has_footprint,
                           row_number() OVER (ORDER BY d.dist, d.facility_id) AS rnk
                      FROM (
                            SELECT f.id AS facility_id,
                                   f.footprint IS NOT NULL AS has_footprint,
                                   ST_Distance(COALESCE(f.footprint, f.geom), c.geom) AS dist
                              FROM industrial_facilities f
                             WHERE f.is_active
                               AND (ST_DWithin(f.geom, c.geom, :search)
                                    OR ST_DWithin(f.footprint, c.geom, :assoc))
                           ) d
                     WHERE d.dist <= :search
                     ORDER BY d.dist, d.facility_id
                     LIMIT 3
                   ) n
             WHERE c.id = ANY(CAST(:ids AS bigint[]))
            """
        ),
        params,
    )
    conn.execute(
        text(
            """
            UPDATE thermal_clusters c
               SET nearest_facility_id = p.facility_id,
                   nearest_facility_distance_m = p.distance_m,
                   spatial_relationship = COALESCE(p.relationship, 'none'),
                   industrial_association = COALESCE(p.relationship IN ('inside_footprint', 'adjacent', 'nearby'), false)
              FROM (SELECT id FROM thermal_clusters WHERE id = ANY(CAST(:ids AS bigint[]))) ids
              LEFT JOIN cluster_facility_proximity p ON p.cluster_id = ids.id AND p.rank = 1
             WHERE c.id = ids.id
            """
        ),
        params,
    )
    # Share of member detections lying within the association radius of the nearest facility
    # (guards against a large agricultural cluster whose centre happens to fall near a site).
    conn.execute(
        text(
            """
            UPDATE thermal_clusters c
               SET facility_member_share = s.share
              FROM (
                    SELECT o.cluster_id,
                           avg(CASE WHEN ST_DWithin(COALESCE(f.footprint, f.geom), o.geom, :assoc) THEN 1.0 ELSE 0.0 END) AS share
                      FROM thermal_observations o
                      JOIN thermal_clusters cc ON cc.id = o.cluster_id
                      JOIN industrial_facilities f ON f.id = cc.nearest_facility_id
                     WHERE o.cluster_id = ANY(CAST(:ids AS bigint[]))
                     GROUP BY o.cluster_id
                   ) s
             WHERE c.id = s.cluster_id
            """
        ),
        params,
    )
    conn.execute(
        text(
            "UPDATE thermal_clusters SET facility_member_share = NULL "
            "WHERE id = ANY(CAST(:ids AS bigint[])) AND nearest_facility_id IS NULL"
        ),
        params,
    )
    associated = conn.execute(
        text(
            "SELECT count(*) FROM thermal_clusters WHERE id = ANY(CAST(:ids AS bigint[])) AND industrial_association"
        ),
        params,
    ).scalar_one()
    return {"clusters": len(cluster_ids), "associated": int(associated)}
