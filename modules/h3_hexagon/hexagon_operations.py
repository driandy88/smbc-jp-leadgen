import logging
from typing import Set, Tuple, Union

import geopandas as gpd
import h3
from h3 import H3ResolutionError
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.ops import unary_union
from shapely.validation import make_valid

logger = logging.getLogger(__name__)


class HexagonGenerator:
    """
    Generates H3 hexagons from geographic boundaries using GeoPandas and H3.
    """

    def __init__(self, city_name: str = "", level: str = "", resolution: int = 6):
        """
        :param city_name: Name of the city or region to filter.
        :param level: Administrative level as a string (e.g., "1", "2").
        :param resolution: H3 resolution (default: 6).
        """
        self.city_name = city_name
        self.level = level
        self.resolution = resolution

    def generate_hexagons(self, gdf: gpd.GeoDataFrame) -> Set[str]:
        """
        Generate H3 hexagons covering the specified region.

        :param gdf: Input GeoDataFrame.
        :return: Set of H3 hexagon IDs.
        :raises: TypeError, ValueError, RuntimeError
        """
        if not isinstance(gdf, gpd.GeoDataFrame):
            raise TypeError("Input must be a GeoDataFrame.")

        filtered_gdf = gdf
        if self.level and self.level != "0":
            level_col = f"NAME_{self.level}"
            if level_col not in gdf.columns:
                raise ValueError(f"Column '{level_col}' not found in GeoDataFrame.")
            filtered_gdf = gdf[gdf[level_col] == self.city_name]

        if filtered_gdf.empty:
            raise ValueError(f"No data found for city: {self.city_name} at level: {self.level}")

        try:
            boundaries = unary_union(filtered_gdf.geometry)
            boundaries = boundaries.buffer(0.05)
            boundaries = make_valid(boundaries)
        except Exception as e:
            logger.error("Error processing geometry: %s", e)
            raise RuntimeError(f"Error processing geometry: {e}")

        if isinstance(boundaries, Polygon):
            polygons = [boundaries]
        elif isinstance(boundaries, MultiPolygon):
            polygons = list(boundaries.geoms)
        else:
            raise TypeError(f"Unsupported geometry type: {type(boundaries)}")

        hexes: Set[str] = set()
        for poly in polygons:
            if not poly.is_valid or poly.is_empty:
                continue
            geojson_poly = mapping(poly)
            try:
                hexes.update(h3.polyfill(geojson_poly, self.resolution, geo_json_conformant=True))
            except Exception as e:
                logger.error("Error during H3 polyfill: %s", e)
                raise RuntimeError(f"Error during H3 polyfill: {e}")

        if not hexes:
            raise ValueError("No hexagons generated. Check input geometry and resolution.")

        return hexes

    def get_hexagon_children(self, hex_id: str) -> Set[str]:
        """
        Get children hexagons of a given hexagon ID.

        :param hex_id: H3 hexagon ID.
        :param child_resolution: Desired child resolution (optional).
        :return: Set of child hexagon IDs.
        """
        if not isinstance(hex_id, str):
            raise TypeError("hex_id must be a string.")

        try:
            children = h3.h3_to_children(hex_id)
            return set(children)
        except H3ResolutionError:
            logger.warning("Hexagon reached maximum resolution: %d", self.get_hexagon_resolution(hex_id))
            return set()
        except Exception as e:
            logger.error("Error getting children for hexagon %s: %s", hex_id, e)
            raise RuntimeError(f"Error getting children for hexagon {hex_id}: {e}")

    def get_hexagon_resolution(self, hex_id: str) -> int:
        """
        Get the resolution of a given hexagon ID.

        :param hex_id: H3 hexagon ID.
        :return: Resolution as integer.
        """
        if not isinstance(hex_id, str):
            raise TypeError("hex_id must be a string.")

        try:
            return h3.h3_get_resolution(hex_id)
        except Exception as e:
            logger.error("Error getting resolution for hexagon %s: %s", hex_id, e)
            raise RuntimeError(f"Error getting resolution for hexagon {hex_id}: {e}")

    def get_hex_bbox(self, hex_id: Union[str, int]) -> Tuple[float, float, float, float]:
        """
        Return (min_lat, min_lon, max_lat, max_lon) for an H3 cell.

        :param hex_id: H3 hexagon ID (string or int).
        :return: Tuple of (min_lat, min_lon, max_lat, max_lon).
        """
        try:
            verts = h3.h3_to_geo_boundary(hex_id, geo_json=True)
            lats = [lat for _, lat in verts]
            lons = [lon for lon, _ in verts]
            return min(lats), min(lons), max(lats), max(lons)
        except Exception as e:
            logger.error("Error getting bounding box for hexagon %s: %s", hex_id, e)
            raise RuntimeError(f"Error getting bounding box for hexagon {hex_id}: {e}")
