from django.contrib import admin
from django.contrib.gis.geos import Point
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

from .settings import ADMIN_MAP_COORDINATES, ADMIN_MAP_ZOOM

GEODJANGO_IMPROVED_WIDGETS = 'olwidget' in settings.INSTALLED_APPS


if GEODJANGO_IMPROVED_WIDGETS:
    from olwidget.admin import GeoModelAdmin
else:
    from django.contrib.gis.admin import ModelAdmin as GeoModelAdmin


def _get_geodjango_map_coords():
    """ point to be used by geodjango """
    try:
        lat, lng = ADMIN_MAP_COORDINATES
    except KeyError:
        raise ImproperlyConfigured("incorrect NODESHOT_ADMIN_MAP_COORDINATES setting")
    
    point = Point(lng, lat, srid=4326)
    
    if GEODJANGO_IMPROVED_WIDGETS:
        return (lat, lng)
    else:
        point.transform(900913)
        return point
    
def _get_geodjango_map_zoom():
    """ zoom level to be used by geodjango """
    try:
        return ADMIN_MAP_ZOOM
    except KeyError:
        raise ImproperlyConfigured("incorrect NODESHOT_ADMIN_MAP_ZOOM setting")


class BaseAdmin(admin.ModelAdmin):
    """
    Abstract administration model for BaseDate models.
        * 'added' and 'updated' fields readonly
        * save-on-top button enabled by default
    """
    save_on_top = True
    readonly_fields = ['added', 'updated']
    
    html_editor_fields = []
    
    # preload tinymce editor static files
    if 'grappelli' in settings.INSTALLED_APPS:  
        class Media:
            js = [
                '%sgrappelli/tinymce/jscripts/tiny_mce/tiny_mce.js' % settings.STATIC_URL,
                '%sgrappelli/tinymce_setup/tinymce_setup_ns.js' % settings.STATIC_URL,
            ]
        
        # enable editor for "node description" only
        def formfield_for_dbfield(self, db_field, **kwargs):
            field = super(BaseAdmin, self).formfield_for_dbfield(db_field, **kwargs)
            
            if db_field.name in self.html_editor_fields:
                field.widget.attrs['class'] = 'html-editor %s' % field.widget.attrs.get('class', '')
            
            return field


class BaseGeoAdmin(BaseAdmin, GeoModelAdmin):
    """
    BaseAdmin + Geodjango support
    """
    if GEODJANGO_IMPROVED_WIDGETS:
        lat, lng = _get_geodjango_map_coords()
        options = {
            'layers': [
                'osm.mapnik',
                'google.streets',
                'google.physical',
                'google.satellite',
                'google.hybrid',
            ],
            'default_lat': lat,
            'default_lon': lng,
            'default_zoom': _get_geodjango_map_zoom(),
            'hide_textarea': not settings.DEBUG,  # TODO: this might be configured in the future
        }
    else:
        default_lon, default_lat = _get_geodjango_map_coords()
        default_zoom = _get_geodjango_map_zoom()


class PublishActionsAdminMixin(object):
    """
    Admin mixin that adds 2 actions in the admin list:
        * publish objects
        * unpublish objects
    """
    actions = ['publish_action', 'unpublish_action']

    def publish_action(self, request, queryset):
        rows_updated = queryset.update(is_published=True)
        
        if rows_updated == 1:
            message_bit = _("1 item was")
        else:
            message_bit = _("%s items were") % rows_updated
            
        self.message_user(request, _("%s successfully published.") % message_bit)
        
    publish_action.short_description = _("Publish selected items")
    
    def unpublish_action(self, request, queryset):
        rows_updated = queryset.update(is_published=False)
        
        if rows_updated == 1:
            message_bit = _("1 item was")
        else:
            message_bit = _("%s items were") % rows_updated
        
        self.message_user(request, _("%s successfully unpublished.") % message_bit)
    
    unpublish_action.short_description = _("Unpublish selected items")


class BaseStackedInline(admin.StackedInline):
    readonly_fields = ['added', 'updated']
    extra = 0


class BaseTabularInline(admin.TabularInline):
    readonly_fields = ['added', 'updated']
    extra = 0
