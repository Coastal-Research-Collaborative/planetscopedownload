"""
This module creates a framework to download satalite data from the PlanetScope orders API.
Notice we use the Planet Data API to get the item ids of the images that we want and the orders api is used to download them

Author: Joel Nicolow, Coastal Research Collaborative, School of Ocean and Earth Science and Technology, University of Hawaii at Manoa
"""
import os
import json
import geojson
import requests

def load_api_key(api_text_fn):
    with open(api_text_fn, "r") as file:
        PLANET_API_KEY = file.read()  # Read entire file content
    return PLANET_API_KEY

def pretty_print(data):
    """Pretty printing of jsons"""
    print(json.dumps(data, indent = 2))


def create_polygon_geojson(sitename:str, coords:list, data_dir:str='data'):
    """
    Given a list of lat long coordinates this creates a polygon function used in the imagery download process
    """
    if coords[0] != coords[-1]:
        coords.append(coords[0])  # Close the polygon by repeating the first coordinate


    geojson_data = {
        "type": "FeatureCollection",
        "name": f"{sitename}_polygon",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "Name": "Polygon 1",
                    "description": None,
                    "timestamp": None,
                    "begin": None,
                    "end": None,
                    "altitudeMode": None,
                    "tessellate": -1,
                    "extrude": 0,
                    "visibility": -1,
                    "drawOrder": None,
                    "icon": None
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [coords]
                }
            }
        ]
    }

    save_dir = os.path.join(data_dir, 'siteinfo', sitename)
    if not os.path.exists(save_dir): 
        os.makedirs(save_dir)
    
    save_path = os.path.join(save_dir, f"{sitename}_polygon.geojson")
    
    with open(save_path, 'w') as geojson_file:
        json.dump(geojson_data, geojson_file, indent=4)


def planet_auth(planet_api, data_url='https://api.planet.com/data/v1', orders_url='https://api.planet.com/compute/ops/orders/v2'):
    auth = requests.auth.HTTPBasicAuth(planet_api, '')
    data_response = requests.get(data_url, auth=auth)
    orders_response = requests.get(orders_url, auth=auth)
    if not data_response.status_code in [200, 201, 202]: raise RuntimeError(f"Authentification failed for data api: {json.dumps(data_response.json(), indent=2)}")
    if not orders_response.status_code in [200, 201, 202]: raise RuntimeError(f"Authentification failed for orders api: {json.dumps(orders_response.json(), indent=2)}")
    print('Planets data and orders API authentification successful')
    return auth


def retrieve_imagery(sitename:str, start_date:str, end_date:str, data_dir:str='data', polygon=None):
    """

    :param sitename: str the name of the side (folders will be created based on this)
    :param start_date: first date of image aquisition (e.g. '1990-06-06')
    :param end_date: last date of image aquisition (e.g. '1990-06-06')
    """

    #### CREATE FILTERS FOR QUICK SEARCH ####
    data_filter = {
        "type": "DateRangeFilter",
        "field_name": "acquired",
        "config": {
            "gte" : f"{start_date}T00:00:00.000Z",
            'lte' : f'{end_date}T24:00:00.000Z' # inclusive
        }
    }

    if polygon is None:
        # then the polygon must be loaded from a geojson
        if not os.path.join(data_dir, 'siteinfo', sitename, f"{sitename}_polygon.geojson"):
            raise RuntimeError(f'No polygon given and no polygon geojson availble to retrieve_imagery() for {sitename}')
        else:
            polygon_path = os.path.join('siteinfo', sitename, f'{sitename}_polygon.geojson')
            if not os.path.exists(polygon_path):
                polygon_path = os.path.join(data_dir, 'siteinfo', sitename, f'{sitename}_polygon.geojson')
            if not os.path.exists(polygon_path):
                print(polygon_path)
                raise('There is no polygon geojsonfiles in siteinfo/<sitename>/<sitename>_polygon.geojson or data/siteinfo/<sitename>/<sitename>_polygon.geojson')
            with open(polygon_path, 'r') as file: geojson_data = geojson.load(file)
            coords = geojson_data["features"][0]["geometry"]['coordinates'][0]
            polygon = [[coord[0], coord[1]] for coord in coords]  # Keep only lat, lon

    print(polygon)

    geometry = {
        "type": "GeometryFilter",
        "field_name": "geometry",
        "config": {
            "type": 'Polygon',
            "coordinates" :[ polygon ]
        }
    }

    cloud_filter = {
        "type": "RangeFilter",
        "field_name": "cloud_cover",
        "config": {
            'lt': 0.1
        }
    }

    and_filter = {
        "type": 'AndFilter',
        "config": [geometry, data_filter, cloud_filter]
    }

    #### AUTHENTIFICATE ####
    DATA_URL =  'https://api.planet.com/data/v1'
    DATA_QUICK_SEARCH_URL = f'{DATA_URL}/quick-search'
    ORDERS_URL = 'https://api.planet.com/compute/ops/orders/v2'
    ITEM_TYPE = "PSScene"



