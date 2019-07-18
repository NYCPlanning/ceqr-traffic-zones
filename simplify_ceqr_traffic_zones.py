import pandas as pd
import numpy as np
import geopandas as gpd

from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry.polygon import Polygon
from shapely.geometry.point import Point
from shapely.ops import cascaded_union, snap

from sklearn.neighbors import KDTree


def load_data():
    # Remote URLs
    # census_tract_url = 'http://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/nyct2010/FeatureServer/0/query?where=1=1&outFields=*&outSR=4326&f=geojson'
    # census_block_url = 'http://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/nycb2010/FeatureServer/0/query?where=1=1&outFields=*&outSR=4326&f=geojson'
    # traffic_zones_url = 'https://planninglabs.carto.com:443/api/v2/sql?q=select * from planninglabs.ceqr_transportation_zones_v2015'

    traffic_zones_url = 'data/ceqr_transportation_zones_v2015.gpkg'
    census_blocks_url = 'data/census_blocks.geojson'
    census_tracts_url = 'data/census_tracts.geojson'

    traffic_zones = gpd.read_file(traffic_zones_url)
    print("Loaded {} traffic zones.".format(len(traffic_zones)))

    census_tracts = gpd.read_file(census_tracts_url)
    print("Loaded {} census tracts.".format(len(census_tracts)))

    census_blocks = gpd.read_file(census_blocks_url)
    # Create

    print("Loaded {} census blocks.".format(len(census_blocks)))

    return traffic_zones, census_blocks, census_tracts


def flatten_traffic_zone_blocks(traffic_zones):
    """ Creates a tuple (zone_number, polygon) for each geometry in each of the 
        5 traffic zones. 
    """

    flattened_traffic_zones = []
    for zone in traffic_zones.iterrows():
        for block in zone[1]['geometry']:
            flattened_traffic_zones.append((zone[1]['ceqrzone'], block))
    return flattened_traffic_zones


def add_geometry_to_zone(geo_dict, zone_id, geo):
    """ Updates [geo_dict] with {zone_id: [geo]} """
    if zone_id in geo_dict.keys():
        geo_dict[zone_id] = geo_dict[zone_id] + [geo]
    else:
        geo_dict[zone_id] = [geo]


def union_and_save(zone_and_geo):
    unioned_zones = {zone: cascaded_union(geometry) for (
        zone, geometry) in zone_and_geo.items()}

    geojson = gpd.GeoSeries(unioned_zones).to_json()

    file = open('simplified_ceqr_traffic_zones.geojson', 'w')
    file.write(geojson)
    file.close()


def main(census_tract_k=600, census_block_k=1000):
    
    print("Loading Traffic zones and census geometry...")
    traffic_zones, census_blocks, census_tracts = load_data()
    print("Finished loading Traffic zones and census geometry.\n")

    # Create BoroCT field for census_blocks.
    census_blocks['BoroCT2010'] = census_blocks['BCTCB2010'].apply(
        lambda x: x[:-4])

    # Create flattened_traffic_zones.
    flattened_traffic_zones = flatten_traffic_zone_blocks(traffic_zones)

    # Create centroids and KD Tree for traffic zones for fast nearest neighbor calculations
    traffic_blocks_centroids = np.array(
        [(traffic_block.centroid.x, traffic_block.centroid.y) for _, traffic_block in flattened_traffic_zones])

    traffic_blocks_tree = KDTree(traffic_blocks_centroids, leaf_size=2)

    print("Simplifying Geometry...")
    # Find census geometry for each traffic zone.
    zone_and_geo = {}

    for i, tract in enumerate(census_tracts.iterrows()):
        if (i % 100 == 0):
            print(i)

        # Add a 0 buffer to make sure all the geometry is closed.
        tract_geometry = tract[1]['geometry'].buffer(0)
        traffic_block_tract_intersects = []

        # Get the census_tract_k nearest nearest traffic_blocks of each census tract.
        k_neighbors_ids = traffic_blocks_tree.query(
            [(tract_geometry.centroid.x, tract_geometry.centroid.y)], k=census_tract_k)[1][0]

        # For each traffic_zone neighbor, add the geometry to a list if intersects with the census tract.
        for traffic_id in k_neighbors_ids:
            traffic_block_centroid = traffic_blocks_centroids[traffic_id]
            traffic_block_geometry = flattened_traffic_zones[traffic_id][1]

            if tract_geometry.intersects(traffic_block_geometry):
                traffic_block_tract_intersects.append(
                    flattened_traffic_zones[traffic_id])

        # If the current census tract intersedts with a traffic zone, add some geometry!
        if (len(traffic_block_tract_intersects) > 0):
            # If the traffic zones within the tract are the same zone, add the tract geometry.
            # If they are not all the same zone, add geometry by census block.
            unique_zones = set(list(zip(*traffic_block_tract_intersects))[0])
            if (len(unique_zones) == 1):
                zone_id = list(unique_zones)[0]
                add_geometry_to_zone(zone_and_geo, zone_id, tract_geometry)
            else:
                # Get the census blocks of the current census tract
                tract_num = tract[1]['BoroCT2010']
                tract_blocks = census_blocks[census_blocks['BoroCT2010'] == tract_num]

                # For each census block within the current census tract, find
                # the nearest and most intersecting traffic zone block, and add
                # the census_block geometry.
                for tract_block in tract_blocks.iterrows():
                    tract_block_geometry = tract_block[1]['geometry'].buffer(0)
                    tract_block_centroid = (
                        tract_block_geometry.centroid.x, tract_block_geometry.centroid.y)

                    # Get censu_block_k nearest traffic zone blocks for the current block.
                    k_neighbors_ids = traffic_blocks_tree.query(
                        [tract_block_centroid], k=census_block_k)[1][0]

                    track_block_id_to_intersection_area = []

                    # Calculate the interection area between the current block and the census_k nearest traffic zones.
                    for traffic_id in k_neighbors_ids:
                        traffic_block_zone_id = flattened_traffic_zones[traffic_id][0]
                        traffic_block_geometry = flattened_traffic_zones[traffic_id][1]

                        traffic_census_block_intersection_area = tract_block_geometry.intersection(
                            traffic_block_geometry).area

                        track_block_id_to_intersection_area.append(
                            [traffic_id, traffic_census_block_intersection_area])

                    # Select the the traffic zone block, zone id with the largest intersecting area.
                    track_block_id_to_intersection_area = sorted(
                        track_block_id_to_intersection_area, key=lambda tup: tup[1], reverse=True)
                    nearest_traffic_block_id = track_block_id_to_intersection_area[0][0]
                    nearest_traffic_block_zone = flattened_traffic_zones[nearest_traffic_block_id][0]
                    add_geometry_to_zone(
                        zone_and_geo, nearest_traffic_block_zone, tract_block_geometry)

    print("Done simplifying geometry.")
    print("Saving the simplified geometry.")
    union_and_save(zone_and_geo)


if __name__ == "__main__":
    census_tract_k=600
    census_block_k=1000
    
    main(census_tract_k, census_block_k)
