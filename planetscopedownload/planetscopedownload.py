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


def get_item_ids(and_filter:dict, auth_or_api_key:requests.auth.HTTPBasicAuth, data_quick_search_url='https://api.planet.com/data/v1/quick-search', item_type='PSScene'):

    if isinstance(auth_or_api_key, str):
        auth = planet_auth(auth_or_api_key) 
    elif isinstance(auth_or_api_key, requests.auth.HTTPBasicAuth):
        auth = auth_or_api_key

    desired_products = [
        'assets.ortho_analytic_4b_sr:download', # toar image
        'assets.ortho_udm2:download' # udm file
    ]
    

    search_request = {
        "item_types": [item_type],
        "filter": and_filter
    }


    search_result = requests.post(
        data_quick_search_url,
        auth = auth,
        json=search_request
    )

    if not search_result.status_code in (200, 201, 202):
        print("❌ Failed to place order")
        print(f"Status code: {search_result.status_code}")
        try:
            print("Error details:", json.dumps(search_result.json(), indent=2))
        except Exception:
            print("Raw response:", search_result.text)
        raise RuntimeError('See above issue in data API')

    # print(feature['id'])
    # p(feature['_permissions']) # NOTE maybe can tell us if we have access
    features = search_result.json()['features']
    image_ids = []
    for feature in features:
        valid = True
        for product_type in desired_products:
            if not product_type in feature['_permissions']:
                # print(f'{product_type} missing permissions for {feature["id"]}')
                valid=False # NOTE if there inst permission to all the data we need skip this id
        if valid: image_ids.append(feature['id'])
    
    return(image_ids)

    
def place_order(request, auth, orders_url='https://api.planet.com/compute/ops/orders/v2', headers = {'content-type': 'application/json'}):
    response = requests.post(orders_url, data=json.dumps(request), auth=auth, headers=headers)

    if response.status_code in (200, 201, 202):
        print("✅ Order placed successfully")
        order_id = response.json()['id']
        print(f"Order ID: {order_id}")
        order_url = orders_url + '/' + order_id
        return order_url
    else:
        print("❌ Failed to place order")
        print(f"Status code: {response.status_code}")
        try:
            print("Error details:", json.dumps(response.json(), indent=2))
        except Exception:
            print("Raw response:", response.text)
        return None


def retrieve_imagery(sitename:str, start_date:str, end_date:str, planet_api_key:str=None, data_dir:str='data', polygon=None):
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
            'lte' : f'{end_date}T23:59:59.999Z' # inclusive
        }
    }

    if polygon is None:
        # then the polygon must be loaded from a geojson
        if not os.path.join(data_dir, 'siteinfo', sitename, f"{sitename}_polygon.geojson"):
            raise BaseException(f'No polygon given and no polygon geojson availble to retrieve_imagery() for {sitename}')
        else:
            polygon_path = os.path.join('siteinfo', sitename, f'{sitename}_polygon.geojson')
            if not os.path.exists(polygon_path):
                polygon_path = os.path.join(data_dir, 'siteinfo', sitename, f'{sitename}_polygon.geojson')
            if not os.path.exists(polygon_path):
                print(polygon_path)
                raise BaseException('There is no polygon geojsonfiles in <data_dir>/siteinfo/<sitename>/<sitename>_polygon.geojson or data/siteinfo/<sitename>/<sitename>_polygon.geojson')
            with open(polygon_path, 'r') as file: geojson_data = geojson.load(file)
            coords = geojson_data["features"][0]["geometry"]['coordinates'][0]
            polygon = [[coord[0], coord[1]] for coord in coords]  # Keep only lat, lon

    print(polygon)

    geometry = {
        "type": "GeometryFilter",
        "field_name": "geometry",
        "config": {
            "type": 'Polygon',
            "coordinates" :[ polygon ] # note this does not yet clip imagery 
        }
    }

    cloud_filter = {
        "type": "RangeFilter",
        "field_name": "cloud_cover",
        "config": {
            'lt': 0.1 # images must be less than 0.1 cloudyness
        }
    }

    and_filter = {
        "type": 'AndFilter',
        "config": [geometry, data_filter, cloud_filter]
    }

    #### AUTHENTIFICATE ####
    # DATA_URL =  'https://api.planet.com/data/v1'
    # DATA_QUICK_SEARCH_URL = f'{DATA_URL}/quick-search'
    # ORDERS_URL = 'https://api.planet.com/compute/ops/orders/v2'
    # ITEM_TYPE = "PSScene"

    if planet_api_key is None:
        api_path = os.path.join(data_dir, 'planetscope', "PlanetScope_API_key.txt")
        if not os.path.exists(api_path):
             raise BaseException(f'Planetscope api not passed as argument and could not find at {api_path}')
        
        planet_api_key = planetscopedownload.load_api_key(api_path)

    auth = planet_auth(planet_api_key)

    #### GET ITEM IDs ####
    image_ids = get_item_ids(and_filter=and_filter, auth_or_api_key=auth)
    print(image_ids)

    #### CREATE PRODUCT ####
    # # NOTE This is where we ask to clip the imagery 
    # products = [
    #     {
    #         'item_ids': image_ids,
    #         'item_type': "PSScene",
    #         "product_bundle":"analytic_udm2"
    #     }
    # ]

    # request = {
    #     "name": sitename,
    #     "products":products,
    #     "delivery": {"single_archive": True, "archive_type": 'zip'}
    # }

    # #### PLACE ORDER ####
    # order_url = place_order(request, auth=auth)
