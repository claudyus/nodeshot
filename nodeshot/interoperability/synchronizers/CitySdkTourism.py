import requests
import simplejson as json

from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist

from nodeshot.interoperability.synchronizers.base import BaseSynchronizer
from nodeshot.interoperability.models import NodeExternal

from celery.utils.log import get_logger
logger = get_logger(__name__)


class CitySdkTourismMixin(object):
    """
    CitySdkTourismMixin interoperability mixin
    Provides methods to perform following operations:
        * perform authentication into citysdk API
        * create or find a category
        * add new records
        * change existing records
        * delete existing records
    """
    REQUIRED_CONFIG_KEYS = [
        'url',
        'citysdk_url',
        'citysdk_category',
        'citysdk_type',
        'citysdk_username',
        'citysdk_password',
        'citysdk_lang',
        'citysdk_term',
    ]

    def __init__(self, *args, **kwargs):
        super(CitySdkTourismMixin, self).__init__(*args, **kwargs)
        self._init_config()

    def _init_config(self):
        """ Init required attributes if necessary (for internal use only) """
        if getattr(self, 'citysdk_categories_url', None) is None:
            self.citysdk_resource_url = '%s%ss/' % (self.config['citysdk_url'], self.config['citysdk_type'])
            self.citysdk_categories_url = '%scategories?list=%s&limit=0&format=json' % (self.config['citysdk_url'], self.config['citysdk_type'])
            self.citysdk_category_id = self.config.get('citysdk_category_id')

    def clean(self):
        """
        Custom Validation, is executed by ExternalLayer.clean();
        These validation methods will be called before saving an object into the DB
            * verify authentication works
        """
        self.authenticate()

    def after_external_layer_saved(self, layer_config=None):
        """
        Method that will be called after the external layer has been saved
        """
        self.find_citysdk_category(layer_config)

    def before_start(self, *args, **kwargs):
        """ before the import starts do authentication (1 time only) """
        # first time
        self.authenticate(force_http_request=True)
        # store cookies in a string
        self.config['cookies'] = self.cookies
        # save config
        self.layer.external.config = json.dumps(self.config, indent=4, sort_keys=True)
        self.layer.external.save(after_save=False)

    def authenticate(self, force_http_request=False):
        """ authenticate into the CitySDK API if necessary """
        # if session cookie is stored in DB no need to reauthenticate
        # if force_http_request is True do HTTP request anyway
        if force_http_request is False and self.config.get('cookies', False):
            self.cookies = self.config['cookies']
            return True

        self.verbose('Authenticating to CitySDK')
        logger.info('== Authenticating to CitySDK ==')

        citysdk_auth_url = '%sauth?format=json' % self.config['citysdk_url']

        response = requests.post(citysdk_auth_url, {
            'username': self.config['citysdk_username'],
            'password': self.config['citysdk_password'],
        })

        if response.status_code != 200:
            message = 'API Authentication Error: "%s"' % json.loads(response.content)['ResponseStatus']['Message']
            logger.error(message)
            raise ImproperlyConfigured(message)

        self.cookies = response.cookies.get_dict()

        return True

    def find_citysdk_category(self, layer_config=None):
        """
        Automatically finds the citysdk category ID
            * ensure the ID specified in config is correct otherwise auto-correct
            * create category if it does not exist
            * if category exist find the ID
            * store category ID in config
        """
        logger.info('== Going to find CitySDK category ID ==')

        self._init_config()

        if layer_config:
            self.config = json.loads(layer_config)

        citysdk_category_id = self.config.get('citysdk_category_id', False)
        response = requests.get(self.citysdk_categories_url, cookies=self.cookies)

        # do we already have the category id in the db config?
        # And is the category present in the API response?
        if citysdk_category_id is not False and citysdk_category_id in response.content:

            message = 'category with ID "%s" already present in config' % citysdk_category_id
            self.verbose(message)
            logger.info(message)

            # exit here
            return False
        # if not go and find it!
        else:
            # category does not exist, create it
            if self.config['citysdk_category'] not in response.content:

                category = {
                    "list": self.config['citysdk_type'],  # poi, event, route
                    "category": {
                        "label": [
                            {
                                "lang": self.config['citysdk_lang'],
                                "term": "primary",
                                "value": self.config['citysdk_category']
                            }
                        ],
                        "lang": self.config['citysdk_lang'],
                        "term": "category",
                        "value": self.config['citysdk_category']
                    }
                }

                self.verbose('Creating new category in CitySDK DB')
                logger.info('== Creating new category in CitySDK DB ==')
                # put to create
                response = requests.put(self.citysdk_categories_url, data=json.dumps(category),
                                        headers={'content-type': 'application/json'},
                                        cookies=self.cookies)

                # raise exception if something has gone wrong
                if response.status_code is not 200:
                    message = 'ERROR: %s' % response.content
                    self.verbose(message)
                    logger.error(message)
                    raise ImproperlyConfigured(response.content)

                # get ID
                citysdk_category_id = json.loads(response.content)

                message = 'category with ID "%s" has been created' % citysdk_category_id
                self.verbose(message)
                logger.info(message)
            # category already exists, find ID
            else:
                categories = json.loads(response.content)['categories']

                for category in categories:
                    if category['value'] == self.config['citysdk_category']:
                        citysdk_category_id = category['id']

                # raise exception if not found - should not happen but who knows
                if citysdk_category_id is None:
                    message = 'Category was thought to be there but could not be found!'
                    logger.info(message)
                    raise ImproperlyConfigured(message)

            # now store ID in the database both in case category has been created or not
            self.config['citysdk_category_id'] = citysdk_category_id
            self.layer.external.config = json.dumps(self.config, indent=4, sort_keys=True)
            self.layer.external.save()
            # verbose output
            message = 'category with ID "%s" has been stored in config' % citysdk_category_id
            self.verbose(message)
            logger.info(message)

    def convert_format(self, node):
        """ Prepares the JSON that will be sent to the CitySDK API """

        # determine description or fill some hopefully useful value
        if not node.description.strip():
            description = '%s in %s' % (node.name, node.address)
        else:
            description = node.description

        return {
            self.config['citysdk_type'] :{
                "location":{
                    "point":[
                        {
                            "Point":{
                                "posList":"%s %s" % (float(node.point.coords[1]), float(node.point.coords[0])),
                                "srsName":"http://www.opengis.net/def/crs/EPSG/0/4326"
                            },
                            "term": self.config['citysdk_term']
                        }
                    ],
                    "address": {
                        "value":"""BEGIN:VCARD
N:;%s;;;;
ADR;INTL;PARCEL;WORK:;;%s;%s;%s;;%s
END:VCARD""" % (
                            node.name,
                            node.data['address'],
                            node.data['city'],
                            node.data['province'],
                            node.data['country'],
                        ),
                        "type": "text/vcard"
                    },
                },
                "label":[
                    {
                        "term": "primary",
                        "value": node.name
                    },
                ],
                "description":[
                    {
                        "value": description,
                        "lang": self.config['citysdk_lang']
                    },
                ],
                "category":[
                    {
                        "id": self.citysdk_category_id
                    }
                ],
                "base": self.citysdk_resource_url,
                "lang": self.config['citysdk_lang'],
                "created": unicode(node.added),
                "author":{
                    "term": "primary",
                    "value": self.layer.organization
                },
                "license":{
                    "term": "primary",
                    "value": "open-data"
                }
            }
        }

    def add(self, node, authenticate=True):
        """ Add a new record into CitySDK db """
        if authenticate:
            self.authenticate()

        citysdk_record = self.convert_format(node)

        # citysdk sync
        response = requests.put(self.citysdk_resource_url, data=json.dumps(citysdk_record),
                     headers={ 'content-type': 'application/json' }, cookies=self.cookies)

        if response.status_code != 200:
            message = 'ERROR while creating "%s". Response: %s' % (node.name, response.content)
            logger.error(message)
            return False

        try:
            data = json.loads(response.content)
        except json.JSONDecodeError as e:
            logger.error('== ERROR: JSONDecodeError %s ==' % e)
            return False

        external = NodeExternal.objects.create(node=node, external_id=data['id'])
        message = 'New record "%s" saved in CitySDK through the HTTP API"' % node.name
        self.verbose(message)
        logger.info(message)

        return True

    def change(self, node, authenticate=True):
        """ Edit existing record in CitySDK db """
        if authenticate:
            self.authenticate()

        citysdk_record = self.convert_format(node)

        # citysdk sync
        try:
            citysdk_record['poi']['id'] = node.external.external_id
            response = requests.post(
                        self.citysdk_resource_url,
                        data=json.dumps(citysdk_record),
                        headers={ 'content-type': 'application/json' },
                        cookies=self.cookies)

            if response.status_code == 200:
                message = 'Updated record "%s" through the CitySDK HTTP API' % node.name
                self.verbose(message)
                logger.info(message)
            else:
                message = 'ERROR while updating record "%s" through CitySDK API\n%s' % (node.name, response.content)
                logger.error(message)
                raise ImproperlyConfigured(message)

            return True

        # in case external_id is not in the local DB we need to create instead
        except ObjectDoesNotExist:
            return self.add(node, authenticate=False)

    def delete(self, external_id, authenticate=True):
        """ Delete record from CitySDK db """
        if authenticate:
            self.authenticate()

        response = requests.delete(self.citysdk_resource_url, data='{"id":"%s"}' % external_id,
                            headers={ 'content-type': 'application/json' }, cookies=self.cookies)

        if response.status_code != 200:
            message = 'Failed to delete a record through the CitySDK HTTP API'
            self.verbose(message)
            logger.info(message)
            return False

        message = 'Deleted a record through the CitySDK HTTP API'
        self.verbose(message)
        logger.info(message)

        return True


class CitySdkTourism(CitySdkTourismMixin, BaseSynchronizer):
    pass
