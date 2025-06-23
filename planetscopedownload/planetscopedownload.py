"""
This module creates a framework to download satalite data from the PlanetScope orders API.
Notice we use the Planet Data API to get the item ids of the images that we want and the orders api is used to download them

Author: Joel Nicolow, Coastal Research Collaborative, School of Ocean and Earth Science and Technology, University of Hawaii at Manoa
"""
import os
from glob import glob
import shutil
import json
import geojson
import requests
import pathlib
import time
import zipfile

def pretty_print(data):
    """Pretty printing of jsons"""
    print(json.dumps(data, indent = 2))


def write_api_key_file(api_key:str, overwrite:bool=False, data_dir:str=os.path.join(os.getcwd(), 'data')):
    sites_dir = os.path.join(data_dir, 'planetscope')
    if not os.path.exists(sites_dir): os.mkdir(sites_dir)
    
    file_path = os.path.join(sites_dir, 'PlanetScope_API_key.txt')
    if overwrite or not os.path.exists(file_path):
        # if we want to overwrite or if it doesnt exsist we will need to make it
        with open(file_path, "w") as file:
            file.write(api_key)


def load_api_key(api_text_fn):
    with open(api_text_fn, "r") as file:
        PLANET_API_KEY = file.read()  # Read entire file content
    return PLANET_API_KEY


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
    

def poll_for_success(order_url, auth, num_loops=200):
    count = 0
    while(count < num_loops):
        count += 1
        r = requests.get(order_url, auth=auth)
        response = r.json()
        state = response['state']
        print(state)
        end_states = ['success', 'failed', 'partial']
        if state in end_states:
            print(state)
            break
        time.sleep(10)

def download_results(results, sitename:str, data_dir:str, overwrite=False):
    dest_dir = os.path.join(data_dir, 'sat_images', sitename, 'PS')

    results_urls = [r['location'] for r in results]
    results_names = [r['name'] for r in results]
    print('{} items to download'.format(len(results_urls)))
    
    timestamp = None
    for url, name in zip(results_urls, results_names):
        short_fn = os.path.basename(name)
        # if '.tif' in short_fn:
        #     splits = short_fn.split('_')
        #     timestamp = f'{splits[0]}_{splits[1]}'
        # elif 'manifest' in short_fn:
        #     short_fn = f'{timestamp}_manifest.json' # NOTE each download will have one manifest so can prolly just delete it
        if 'manifest' in short_fn: continue # no need download manifest
        path = pathlib.Path(os.path.join(dest_dir, short_fn)) # PS for planetscope we dont care about the folders just the files
        
        if overwrite or not path.exists():
            print('downloading {} to {}'.format(name, path))
            r = requests.get(url, allow_redirects=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            open(path, 'wb').write(r.content)
        else:
            print('{} already exists, skipping {}'.format(path, name))



def retrieve_imagery(sitename:str, start_date:str, end_date:str, planet_api_key:str=None, data_dir:str='data', polygon=None, max_poll_itterations:int=200):
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
    if polygon[0] != polygon[-1]:
        polygon.append(polygon[0]) # NOTE the polygons need to be closed meaning the first and last point are the saem
    # print(f'{polygon=}')

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
        
        planet_api_key = load_api_key(api_path)

    auth = planet_auth(planet_api_key)

    #### GET ITEM IDs ####
    image_ids = get_item_ids(and_filter=and_filter, auth_or_api_key=auth)
    if len(image_ids) <= 0:
        print('No images avaible for this timeframe and AOI')
        return False
    # print(f'{len(image_ids)} applicable images')

    #### CREATE PRODUCTS ####
    # NOTE This is where we ask to clip the imagery 
    products = [
        {
            'item_ids': image_ids,
            'item_type': "PSScene",
            "product_bundle":"analytic_udm2"
        }
    ]

    # request = { # NOTE doesnt clip to AOI
    #     "name": sitename,
    #     "products":products,
    #     "delivery": {"single_archive": True, "archive_type": 'zip'}
    # }

    #### BUILD CLIP REQUEST ####
    clip_aoi = {
        "type" : "Polygon",
        "coordinates" : [ polygon ] 
    }

    clip = {
        "clip" : {
            "aoi" : clip_aoi
        }
    }

    # may need to add more specificity here (different TOAR for different sites/satalitess)
    toar = {
        "toar": {
            "scale_factor": 10000
        }
    }

    request_clip = {
        "name": sitename,
        "products": products,
        "tools": [clip, toar]
    }

    #### PLACE ORDER ####
    order_url = place_order(request_clip, auth=auth)

    #### POLLING FOR SUCCESS ####
    poll_for_success(order_url, auth, num_loops=max_poll_itterations)

    #### DOWNLOAD IMAGERY ####
    r = requests.get(order_url, auth=auth)
    response = r.json()

    if not 'results' in response['_links']:
        print('First poll for success completed with status still as running...polling again')
        poll_for_success(order_url, auth)
        r = requests.get(order_url, auth=auth)
        response = r.json() 
    if not 'results' in response['_links']:
        raise BaseException('Order is not prepared yet try increasing poll itterations usign retrieve_imagery()\'s max_poll_itterations') 

    results = response['_links']['results']
    # output_files = [r['name'] for r in results]

    download_results(results, sitename=sitename, data_dir=data_dir, overwrite=False)

    return True


