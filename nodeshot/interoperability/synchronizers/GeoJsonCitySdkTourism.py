from nodeshot.interoperability.synchronizers.GeoJson import GeoJson
from .CitySdkTourism import CitySdkTourismMixin


class GeoJsonCitySdkTourism(CitySdkTourismMixin, GeoJson):
    """ Import GeoJson and sync CitySDK tourism API """
    REQUIRED_CONFIG_KEYS = [
        'url',
        'map',
        'citysdk_url',
        'citysdk_category',
        'citysdk_type',
        'citysdk_username',
        'citysdk_password',
        'citysdk_lang',
        'citysdk_term',
    ]

    def convert_format(self, node):
        # determine description or fill some hopefully useful value
        if node.description.strip() == '':
            description = node.name
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
ADR;INTL;PARCEL;WORK:;;%s;
END:VCARD""" % (
                            node.name,
                            description
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
