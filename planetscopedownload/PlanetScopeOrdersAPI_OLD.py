"""
This module creates a framework to download satalite data from the PlanetScope orders API.
Notice we use the Planet Data API to get the idem names of the images that we want

Author: Joel Nicolow, Coastal Research Collaborative, School of Ocean and Earth Science and Technology, University of Hawaii at Manoa
"""

# load modules
from logging import exception
import math
import os
from glob import glob
import datetime as dt
from os.path import exists # check if dirrectories exist
import json
from tracemalloc import stop # used to load site information from json files
import requests
from requests.auth import HTTPBasicAuth
import time # for giving rest period in while loop when waiting for activation
import concurrent.futures # this is for threading (specifically while waiting for API response)
# import urllib # downloading downloadable link
import traceback

#### Supporting functions
def only_keep_these_dict_elements(dictionary, keep):
    """
    Takes in a dictionary and a list of elements you want to keep. Then removes the elements you do not wish to keep

    :param dictionary: a dictionary
    :param keep: a list ([]) of the keys for the elements that you wish to keep

    :return: the updated dictionary
    """
    removes = []
    for key in dictionary.keys():
        if key not in keep:
            removes.append(key)
    for remove in removes:
        dictionary.pop(remove)
    return(dictionary)

def create_dir(path):
    split = os.path.split(path)

    endingList = [split[1]]
    while not split[1] == '':
        split = os.path.split(split[0])
        if split[1] == '':
            endingList.append(split[0])
        else:
            endingList.append(split[1])


    rootPath = endingList[len(endingList)-1]
    for i in range(len(endingList)-2, -1, -1):
        if not os.path.exists(os.path.join(rootPath, endingList[i])):
            os.mkdir(os.path.join(rootPath, endingList[i]))
        rootPath = os.path.join(rootPath, endingList[i])
    return(True)


def create_site_dict_json_for_API(sitename:str, aoi:list, start_date:str, end_date:str, data_dir:str=os.path.join(os.getcwd(), 'data')):
    """
    This function creates sites/<sitename>_site_dict.json for the given site
    """

    sites_dir = os.path.join(data_dir, 'sites')
    if not os.path.exists(sites_dir): os.mkdir(sites_dir)

    if aoi[0] != aoi[-1]: aoi.append(aoi[0].copy())  # PlanetScope API wants last coordinate to be copy of first coordinate

    site_entry = {
        "item_type": "PSScene",
        "geometry_filter": {
            "type": "GeometryFilter",
            "field_name": "geometry",
            "config": {
                "type": "Polygon",
                "coordinates": [aoi]
            }
        },
        "date_range_filter": {
            "type": "DateRangeFilter",
            "field_name": "acquired",
            "config": {
                "gte": f"{start_date}T00:00:00.000Z",
                "lte": f"{end_date}T00:00:00.000Z"
            }
        },
        "cloud_cover_filter": {
            "type": "RangeFilter",
            "field_name": "cloud_cover",
            "config": {"lte": 0.3}
        }
    }
    

    file_path = os.path.join(sites_dir, f'{sitename}_site_dict.json')

    # load existing data if file exists; otherwise, start with an empty dictionary
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            existing_data = json.load(f)
    else:
        existing_data = {}

    # add new entry to exsisting data
    existing_data.update(site_entry)
    

    with open(os.path.join(sites_dir, f'{sitename}_site_dict.json'), "w") as f: 
        json.dump(existing_data, f, indent=4) # indent=4 makes the JSON pretty-printed

    return existing_data


def write_api_key_file(api_key:str, overwrite:bool=False, data_dir:str=os.path.join(os.getcwd(), 'data')):
    sites_dir = os.path.join(data_dir, 'sites')
    if not os.path.exists(sites_dir): os.mkdir(sites_dir)
    
    file_path = os.path.join(sites_dir, 'PlanetScope_API_key.txt')
    if overwrite or not os.path.exists(file_path):
        # if we want to overwrite or if it doesnt exsist we will need to make it
        with open(file_path, "w") as file:
            file.write(api_key)



class PlanetScopeAPIOrder(object):
    """
    Each class instance represents one query to the PlanetScope orders API
    """

    def __init__(self, dictionaries=None, rootDir=os.path.join('data'), dataRootDir=None, oneSite=False, selectSites=False, threading=False, printAll=False, printPolling=False):
        """
        Class constructor

        :param self: self is class instance and is passed to all class functions
        :param dictionaries: dictionaries that have all information needed to query the API (for one site) (default=None)
        :param rootDir: specify a directory other than the working dir for which supporting files can be found specify that here (default=None)
        :param dataRootDir: specify a directory other than the working dir to downloud data to (default=None)
        """
        if rootDir is None:
            self.ROOT_DIR = os.getcwd()
        else:
            self.ROOT_DIR = rootDir

        if dataRootDir is None:
            self.DATA_ROOT_DIR = os.getcwd()
        else:
            self.DATA_ROOT_DIR = dataRootDir
        self.PRINT_ALL = printAll
        self.PRINT_POLLING = printPolling
        if not oneSite:
            # if we are planning to run multiple sites at one time we need to load in all of the API dictionaries
            if dictionaries == None:
                # load from json
                single_site_dicts = glob(os.path.join(self.ROOT_DIR, 'sites', '*_site_dict.json'))
                self.SITE_DICTS = {}
                for site_dict_fn in single_site_dicts:
                    f = open(site_dict_fn)
                    data = json.load(f)
                    sitename = os.path.basename(site_dict_fn).replace('_site_dict.json', '')
                    self.SITE_DICTS[sitename] = data

            else:   
                self.SITE_DICTS = dictionaries # list of dictionaries that contain all needed information for a specific site

        f = open(os.path.join(self.ROOT_DIR, 'sites', 'PlanetScope_API_key.txt'))
        self.PLANET_API_KEY = f.read()
        f.close()

        self.QUERY_LIMIT = 500 # we can only request 500 items per query
        self.SELECT_SITES = selectSites # should we ask the user what sites/regions they want to run (from what is in the dictionaries)
        self.THREAD = threading # this means we will run [at least the site] API requests concurrently 
        self.ORDERS_URL = 'https://api.planet.com/compute/ops/orders/v2'
        self.AUTH = HTTPBasicAuth(self.PLANET_API_KEY, '') # we only need to do this once per "use" so it can be authorized when the class is constructed
        self.HEADERS = {'content-type': 'application/json'}


    def get_all_data(self):
        """
        This function runs through each site and downloads its data

        :param self:
        """

        # lets user decide what sites they would like to run
        if self.SELECT_SITES:
            print("here is a list of the sites available:")
            for sitename, site_dict in self.SITE_DICTS.items():
                print(sitename)
                print(site_dict.keys())
            print("Enter the site (if multiple enter in comma dilimeted list) you would like to look at (or 'all' for every site)")
            sites = input("site(s): ")
            if sites == 'all':
                sites = self.SITE_DICTS.keys()
            else:
                sites = sites.split(',')

            self.SITE_DICTS = only_keep_these_dict_elements(self.SITE_DICTS, sites)

        print(self.SITE_DICTS)

        if self.THREAD:
            self.get_all_data_concurrent()
        else:
            for sitename, site_dict in self.SITE_DICTS.items():
                self.get_one_site_data(sitename, site_dict)


    def get_all_data_concurrent(self):
        """
        This function uses threading so that we can ask the API for multiple site downloads at a time and wait for their responses together
        rahter than doing one waiting and then going to the next

        :param self:
        """
        import concurrent.futures # threading
        # THE COMMENTED OUT CODE BELOW IS FOR IF YOU WANTED TO TRY RUN THE REGIONS CONCURENTLY (could maybe test not having them both say with __ as executor and use as ex for one)
        # with concurrent.futures.ThreadPoolExecutor() as executor:
        #     [executor.submit(self.get_regional_data_concurrent(regionDict)) for _, regionDict in self.REGION_DICTS.items()] # '_' for the first element of items (the name)
        for sitename, site_dict in self.SITE_DICTS.items():
            # print(regionDict)
            # the first variable is a throwaway variable because we dont need it but it is the regionName
            # each region represents a collection sites (beaches) for example O'ahu would be a region with beaches on O'ahu
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(site_dict)) as executor:
                
                firstSite = True
                for sitename, site_dict in site_dict.items():
                    if not firstSite:
                        time.sleep(60) # setting a n second delay between queries so that we do not get a HTTP 429 (too many queries response)
                    else:
                        firstSite = False
                    executor.submit(self.get_one_site_data, sitename, site_dict)
                    

    def get_one_site_data(self, sitename, site_dict):
        """
        This function downloads data for one site from the Planet orders API

        :param self:
        :param sitename: name of beach
        :param site_dict: the dictionary for one specific site
        """

        print("site name: " + sitename)
        # The Planet data API will not return 250 or more items at a time so if there are more than
        # maxDays in the daterange we assume that it will be more than 250 items and we split it up
        maxDays = 200
        dtFormat = '%Y-%m-%dT%H:%M:%S.%fZ' # e.g. '2022-08-22T00:00:00.000Z'
        print(site_dict)
        print(site_dict['date_range_filter']['config']['gte'])
        print(site_dict['date_range_filter']['config']['lte'])
        gte = dt.datetime.strptime(site_dict['date_range_filter']['config']['gte'], dtFormat)
        lte = dt.datetime.strptime(site_dict['date_range_filter']['config']['lte'], dtFormat)
        timeRangeLength = lte-gte

        if timeRangeLength.days > maxDays:
            # breack up the date range into multiple sections
            temp = gte
            for i in range(0, math.ceil(timeRangeLength.days / maxDays), 1):
                start = temp
                temp = temp + dt.timedelta(days=maxDays)
                
                if temp >= lte:
                    end = lte
                else:
                    end = temp #- dt.timedelta(microseconds=1) # so the date ranges to not overlap
                    
                # print('start'+ start)
                # print('end' + end)
                startTime = start.strftime(dtFormat)[:-4] + 'Z' # we have to trim the micro seconds down to three digits hence [0:-4]
                endTime = end.strftime(dtFormat)[:-4] + 'Z'

                print(startTime)
                print(endTime)

                site_dict['date_range_filter']['config']['gte'] = startTime
                site_dict['date_range_filter']['config']['lte'] = endTime
                products = self.build_clip_request_dict(site_dict, sitename)
                if not products or products['products'] == False:
                    continue
                # productsShell1 = products.copy()
                self.get_one_site_data_from_products(sitename, site_dict, products)
                    

            # print(len(allItemIds))
            # print(len(allItemIds[0]))
            # productsShell1['products'][0]['item_ids'] = allItemIds # 
            # print(productsShell1['products'][0]['item_ids'])
            # products = productsShell1 # no need to copy in this instance

        else:
            products = self.build_clip_request_dict(site_dict, sitename)
            # print(products.keys())
        
            self.get_one_site_data_from_products(sitename, site_dict, products)



    def get_one_site_data_from_products(self, sitename, site_dict, products, max_retries=3):
        """
        This function is a helper function that takes in the products returned from self.build_clip_request_dict()
        """
        if not products or products['products'] == False:
            # do nothing
            print('\nThere is no data for {} at this time and aoi'.format(sitename))
        else:
            if len(products['products']) > 1:
                # because there were too many items to all query at once it was split into multiple products
                # now we will run each product individually (currently not concurrently)
                productsShell = products.copy()  # if we don't use copy then it will be a pointer to products and not a separate element
                productsShell.pop('products')

                for i in range(len(products['products'])):
                    productsShell['products'] = products['products'][i]
                    productsPartial = productsShell  # no need to copy here because we are overwriting the products element in productShell each iteration

                    try:
                        request_url = self.place_order(productsPartial)
                        if request_url is None:
                            print(f"Order failed or empty for site {sitename}, skipping...")
                            continue
                    except Exception as e:
                        if "no access to assets" in str(e):
                            print(f"Skipping inaccessible product: {productsShell['products'].get('item_ids')} - {productsShell['products'].get('item_type')}")
                            continue # just try the next product and see if it works
                        else:
                            raise  # let unexpected errors propagate            

                    retry_count = 0
                    while retry_count < max_retries:
                        try:
                            self.poll_for_success(request_url, sitename)
                            self.download_order(request_url, sitename, site_dict)
                            print(f'download pau: {sitename}')
                            break  # Break out of the retry loop if successful
                        except Exception as e:
                            retry_count += 1
                            print(f"Error occurred: {str(e)}")
                            print(f"Retrying {retry_count}/{max_retries} in 30 seconds...")
                            time.sleep(30)
                            traceback.print_exc()  # This will print the traceback to help debug the issue
                            if retry_count == max_retries:
                                print(f"Maximum retries reached. Returning with the error.")
                                return str(e)

            else:
                print(products)
                try:
                    request_urls = [self.place_order(products)]
                except Exception as e:
                    if "no access to assets" in str(e):
                        request_urls = self.break_up_product(sitename, products)

                for request_url in request_urls:
                    print(request_url)
                    if request_url is None: 
                        print('The products for this time were empty so skipping')
                        print('if item_ids is not empty this is mostlikely and issue with the API key being used sites/PlanetScope_API_key.txt')
                        continue # this is just to skip the download portion
                    retry_count = 0
                    while retry_count < max_retries:
                        try:
                            self.poll_for_success(request_url, sitename)
                            self.download_order(request_url, sitename, site_dict)
                            print(f'download pau: {sitename}')
                            break  # Break out of the retry loop if successful
                        except Exception as e:
                            retry_count += 1
                            print(f"Error occurred: {str(e)}")
                            print(f"Retrying {retry_count}/{max_retries} in 30 seconds...")
                            time.sleep(30)
                            traceback.print_exc()  # This will print the traceback to help debug the issue
                            if retry_count == max_retries:
                                print(f"Maximum retries reached. Returning with the error.")
                                return str(e)

    
    def break_up_product(self,  sitename, product):
        """
        Its possible that not all of the idems in the product are not accessable so this runs them individually to see which ones might still work
        it is important to note this splits up one product into a seperate product for each item id 
        """
        request_urls = []
        print(product)
        print('&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&')

        base_shell = product.copy()
        base_shell.pop('products', None)
        request_urls = []
        item_ids = product['products'][0]['item_ids']
        for i, item_id in enumerate(item_ids):
            print(f'{item_id=}')
            # this f
            print(f"\nPlacing order for item {i + 1}/{len(item_ids)} for product of {sitename}")

            product_payload = base_shell.copy()
            print(product_payload)
            print(type(product_payload))
            product_payload['products'] = product

            try:
                request_url = self.place_order(product_payload)
                if request_url is None:
                    print(f"Order failed or returned None for product {i + 1}, skipping...")
                    continue
            except Exception as e:
                print(f'failed {e}')
                traceback.print_exc()
                continue
                # if "no access to assets" in str(e):
                #     print(f"Skipping inaccessible product: {product.get('item_ids')} - {product.get('item_type')}")
                #     continue
                # else:
                #     print(f"Unexpected error placing order for product {i + 1}: {e}")
                #     traceback.print_exc()
                #     continue
            request_urls.append(request_url)
        # print(f"Skipping inaccessible product: {products.get('item_ids')} - {products.get('item_type')}")

        return request_urls


    def get_combined_filter(self, site_dict):
        """
        combines filter generated from one site in self.DICTS (or a dictionary with the same structure)
        
        :param self:
        :param site_dict: the dictionary for one specific site
        :return: combined filter_all 
        """
        combined_filter = {
            "type" : "AndFilter",
            "config" : [site_dict["geometry_filter"], site_dict["date_range_filter"], site_dict["cloud_cover_filter"]]
        }

        return(combined_filter)


    def build_products_dict(self, sitename, site_dict, bundle_type = "analytic"):
        """
        This function lists through all assets avaible from PlanetScope that satisfy the combined filter.
        This also checks to make sure we havent already downloaded the assets

        :param self:
        :param sitename: name of site, this is only used to see if the items have already been downloaded
        :param site_dict: the dictionary for one specific site
        :param bundle_type: the type of bundle we want to download (default "analytic")
        """
        item_type = site_dict["item_type"] 
        if self.PRINT_ALL:
            print("item type: " + item_type)
        # info on item types here: https://developers.planet.com/docs/apis/data/items-assets/
        if item_type == "PSScene":
            bundle_type = "analytic_udm2" # PSScene is not availible for "analytic" so we switch to a bundle type that it is availible for
        if self.PRINT_ALL:
            print("bundle type: " + bundle_type)

        # API request object
        search_request = {
        "item_types": [item_type], 
        "filter": self.get_combined_filter(site_dict)
        }

        # fire off the POST request
        # https://api.planet.com/compute/ops/orders/v2
        # data api for quick search: 'https://api.planet.com/data/v1/quick-search'
        search_result = \
        requests.post(
            'https://api.planet.com/data/v1/quick-search',
            auth=HTTPBasicAuth(self.PLANET_API_KEY, ''),
            json=search_request)

        # print(json.dumps(search_result.json(), indent=1))

        # the search returns metadata for all of the images withing our Area Of Interest (AOI) that match our date range and cloud coverage filters. (this will mostlikely consist of multiple images)
    
        # extract image IDs only
        image_ids = [feature['id'] for feature in search_result.json()['features']]
        if self.PRINT_ALL:
            print(sitename)
            # print(image_ids)
            print(f'length before test sats and already downloaded removed: {len(image_ids)}')

        # remove images from test satalites Note: item_ids ending in the following characters are items from test satellites and may not have the full range of associated assets
        testSataliteStrings = ['0f02', '0f06', '0f4c', '1055'] # https://developers.planet.com/docs/orders/ordering/
        # get assets from test satalites
        idList = []
        for id in image_ids:
            for testSat in testSataliteStrings:
                if testSat in id:
                    idList.append(id)
                    break # if it matches one of the test satalite strings no need for check if there're other test sat strings

        # remove test satalite 
        for id in idList:
            image_ids.remove(id)

        # remove images that have previously been downloaded
        alreadyDownloaded = ''
        if exists(os.path.join(self.DATA_ROOT_DIR, 'data', 'sat_images', sitename)):
            alreadyDownloaded = os.listdir(os.path.join(self.DATA_ROOT_DIR, 'data', 'sat_images', sitename))
            alreadyDownloaded = ''.join(alreadyDownloaded) # make it one string so we can just search if it exists
        idList = [] # reset idList because the old contents have already been removed
        # get already downloaded assets
        for id in image_ids:
            if id in alreadyDownloaded:
                idList.append(id)
        # remove already downloaded
        for id in idList:
            image_ids.remove(id)
        if self.PRINT_ALL:
            print(f'length after removal: {len(image_ids)}')
            # print(image_ids) # this can get very long

        if len(image_ids) > 1:
            # proccess and order with this list as the item IDS
            if len(image_ids) > self.QUERY_LIMIT:
                lenDivide = len(image_ids) / self.QUERY_LIMIT
                nDivide = int(math.ceil(lenDivide))
                splitQuerySize = int(math.ceil(len(image_ids) / nDivide))
                itemIndex = 0
                products = []
                for i in range(nDivide):
                    theseItems = image_ids[itemIndex:itemIndex+splitQuerySize]
                    itemIndex = itemIndex+splitQuerySize
                    theseProducts = [
                                        {
                                        "item_ids": theseItems, 
                                        "item_type": item_type, 
                                        "product_bundle": bundle_type
                                        }
                                    ]
                    products.append(theseProducts)
            else:
                products = [
                                {
                                "item_ids": image_ids, 
                                "item_type": item_type, 
                                "product_bundle": bundle_type
                                }
                            ]
            return(products)
        else:
            return(False)


    def build_clip_request_dict(self, site_dict, sitename):
        """
        creates request dictionary for cliping the images

        :param self:
        :param site_dict:  the dictionary for one specific site
        :return: products dictionary (or False if there are no )
        """
        clip_aoi = {
            "type" : "Polygon",
            "coordinates" : site_dict["geometry_filter"]["config"]["coordinates"]
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
            "products": self.build_products_dict(sitename, site_dict),
            "tools": [clip, toar]
            }
        # print(request_clip)
        return(request_clip)
    
    
    def place_order(self, request):
        """
        This function places the order and returns the url

        :param request: request dictionary made by self.build_clip_request_dict()
        :return: order url 
        """
        
        for i in range(0, len(request['products'])):
            if len(request['products'][i]['item_ids']) < 1:
                del request['products'][i]  # remove empty item group
        if len(request['products']) == 0:
            return None # that means the products list was empty
        response = requests.post(self.ORDERS_URL, data=json.dumps(request), auth=self.AUTH, headers=self.HEADERS)
        
        if self.PRINT_ALL:
            print(response)
        if not response.ok:
            # if there is an error "no access to assets" for some of the items we simply want to remove those items from the list and rerun the request
            if b'message":"No access to assets:' in response.content:
                assetNames = response.content.split(b'message":"No access to assets:')
                invalidAssets = []
                for asset in assetNames:
                    if b'Details' not in asset and b'/' in asset:
                        invalidAssets.append(asset.split(b'/')[1])
                currItemIds = request['products'][0]['item_ids']
                for item in invalidAssets:
                    currItemIds.remove(item.decode()) # need to decode because it is as a b'' string now
                request['products'][0]['item_ids'] = currItemIds
                # recursive call next line
                return(self.place_order(request)) # this calls self.place_order again but this time with out the invalid item ids
            # This only will run if the conditional above is false (because of the return statement)
            raise Exception(response.content)

        order_id = response.json()['id']
        order_url = self.ORDERS_URL + '/' + order_id
        print(order_url)
        if self.PRINT_ALL:
            print(order_url)
        return(order_url)


    def poll_for_success(self, request_order_url, sitename='unknown'):
        """
        checks to see if order is available.

        :param self:
        :param num_loops: how many times we poll for success (default 50)
        :param sitename: name of the site default uknown
        """

        success_states = ['success', 'partial']
        while(True):
            # this loop check 
            r = requests.get(request_order_url, auth=self.AUTH)
            if self.PRINT_POLLING or self.PRINT_ALL:
                print(f'status code: {r.status_code}')
                if r.status_code == 429:
                    print(f'{sitename} r: {r}, too many queries at the same time')
                if r.status_code == 401:
                    print(r.text)
                    print(r.message)
                    print(f'{sitename} 401')            
            
            response = r.json()
            state = response['state']
            if self.PRINT_POLLING or self.PRINT_ALL:
                # print(f'{sitename}: {state}, {request_order_url}')
                print(f'{sitename}: {state}')

            if state == 'failed':
                raise Exception(response)
            elif state in success_states:
                break 
            
            time.sleep(10)


    def download_order(self, request_order_url, sitename, site_dict, overwrite=False):
        """
        This function downloads all of the downloadable links returned by the API

        :param self:
        :param request_order_url: url returned by self.place_order()
        :param sitename: name of beach
        :param site_dict: the dictionary for one specific site
        :param region: region that the site is in (used for save path)
        :param overwrite: if it should overwrite and already downloaded item default=False

        :return: downloaded file names
        """
        if self.PRINT_ALL:
            print(request_order_url)
        r = requests.get(request_order_url, auth=self.AUTH)
        if self.PRINT_ALL:
            print(r)

        response = r.json()
        results = response['_links']['results']
        results_urls = [r['location'] for r in results]
        results_names = [r['name'] for r in results]


        results_fileNames = []
        for resultName in results_names:
            # query_id = resultName.split("/")[0]
            # item_type = resultName.split("/")[1]
            fileName = resultName.split("/")[-1]
            results_fileNames.append(fileName)

        # innerDir = 'files'
        # siteDir = (sitename + "_images_" + site_dict['item_type'])

        create_dir(os.path.join(self.DATA_ROOT_DIR, 'data', 'sat_images', sitename))

        results_paths = [os.path.join(self.DATA_ROOT_DIR, 'data', 'sat_images', sitename, n) for n in results_fileNames]

        print(f'{len(results_urls)} items to download for {sitename}')
        
        for url, name, path in zip(results_urls, results_names, results_paths):
            if overwrite or not exists(path):
                if ".tif" in name or  ".json" in name or '.xml' in name:
                    # we only wnat the tif files rn
                    if self.PRINT_ALL:
                        print('downloading {} to {}'.format(name, path))
                    r = requests.get(url, allow_redirects=True)
                    open(path, 'wb').write(r.content)
            else:
                if self.PRINT_ALL:
                    print('{} already exists, skipping {}'.format(path, name))
                
        return dict(zip(results_names, results_paths))

