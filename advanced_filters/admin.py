import logging

from adminsortable2.admin import SortableAdminMixin
from django.apps import apps
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.options import IS_POPUP_VAR
from django.contrib.admin.utils import unquote, quote
from django.forms import Media
from django.http import HttpResponseRedirect
from django.shortcuts import resolve_url
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

from .forms import AdvancedFilterForm
from .models import AdvancedFilter


logger = logging.getLogger('advanced_filters.admin')


class AdvancedListFilters(admin.SimpleListFilter):
    """Allow filtering by stored advanced filters (selection by title)"""
    title = _('Filters')
    template = 'admin/advanced_filters/filter.html'
    parameter_name = '_afilter'

    def __init__(self, request, params, model, model_admin):
        super().__init__(request, params, model, model_admin)
        self.request = request

    def choices(self, changelist):
        for lookup, title, heading in self.lookup_choices:
            if heading:
                yield {
                    'heading': True,
                    'query_string': lookup,
                    'display': title,
                }
            else:
                yield {
                    'selected': self.value() == str(lookup),
                    'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                    'display': title,
                }

    def lookups(self, request, model_admin):
        if not model_admin:
            raise Exception('Cannot use AdvancedListFilters without a '
                            'model_admin')
        model_name = "%s.%s" % (model_admin.model._meta.app_label,
                                model_admin.model._meta.object_name)
        return AdvancedFilter.objects.filter_by_user(request.user).filter(
            model=model_name).values_list('id', 'title', 'heading')

    def queryset(self, request, queryset):
        if self.value():
            filters = AdvancedFilter.objects.filter(id=self.value())
            if hasattr(filters, 'first'):
                advfilter = filters.first()
            if not advfilter:
                logger.error("AdvancedListFilters.queryset: Invalid filter id")
                return queryset
            return advfilter.filter_queryset(queryset)
        return queryset

    @property
    def active(self):
        return self.parameter_name in self.request.GET

    @property
    def clear_url(self):
        params = dict(self.request.GET.items())
        if self.parameter_name in params:
            del params[self.parameter_name]
        return '?%s' % urlencode(sorted(params.items()))


class AdminAdvancedFiltersMixin(object):
    """ Generic AdvancedFilters mixin """
    advanced_change_list_template = "admin/advanced_filters.html"
    advanced_filter_fields = ()

    @property
    def media(self):
        return super().media + Media(
            js=[
                'advanced-filters/jquery_adder.js',
                'magnific-popup/jquery.magnific-popup.js',
                'advanced-filters/advanced-filters.js',
            ],
            css={'screen': [
                'advanced-filters/advanced-filters.css',
                'magnific-popup/magnific-popup.css'
            ]}
        )

    def __init__(self, *args, **kwargs):
        super(AdminAdvancedFiltersMixin, self).__init__(*args, **kwargs)
        self.original_change_list_template = (
            self.change_list_template or "admin/change_list.html")
        self.change_list_template = self.advanced_change_list_template
        # add list filters to filters
        self.list_filter = (AdvancedListFilters,) + tuple(self.list_filter)

    def changelist_view(self, request, extra_context=None):
        """Add advanced_filters form to changelist context"""
        extra_context = extra_context or {}
        current_afilter = request.GET.get('_afilter')
        if not AdvancedFilter.objects.filter(id=current_afilter).exists():
            current_afilter = False
        extra_context.update({
            'original_change_list_template':
                self.original_change_list_template,
            'current_afilter': current_afilter,
            'model_label': self.opts.model._meta.label,
            'model_name': self.opts.model._meta.label.split('.')[1],
        })
        return super(AdminAdvancedFiltersMixin, self).changelist_view(
            request, extra_context=extra_context)


class AdvancedFilterAdmin(SortableAdminMixin, admin.ModelAdmin):
    model = AdvancedFilter
    form = AdvancedFilterForm
    extra = 0

    list_display = ('title', 'model_link', 'heading',)
    list_filter = ('model_name',)
    search_fields = ('model_name', 'title',)
    readonly_fields = ('model_link', 'usage_links', 'edit_link',)

    fields = (
        'title',
        'heading',
        'model_link',
        'usage_links',
    )
    iframe_fields = (
        'title',
        'heading',
        'usage_links',
    )

    def get_fields(self, request, obj=None):
        if request.GET.get(IS_POPUP_VAR) == 'iframe':
            return self.iframe_fields
        return super().get_fields(request, obj)

    def edit_link(self, obj):
        if not obj.pk:
            return ''
        path = resolve_url(
            'admin:advanced_filters_advancedfilter_change', obj.pk)
        return mark_safe(
            '<a href="{}" target="_top">Full admin page</a>'.format(path))
    edit_link.short_description = ''

    def model_link(self, obj):
        app, model = obj.model.split('.')
        path = resolve_url(
            'admin:{}_{}_changelist'.format(app, model.lower()))
        return mark_safe(
            '<a href="{}?_afilter={}" target="_top">{}</a>'.format(
                path, obj.id, obj.model_name))
    model_link.short_description = 'model'
    model_link.admin_order_field = 'model_name'

    def usage_links(self, obj):
        if not obj or not obj.id:
            return '(new)'
        out = []
        for counter in obj.counters.all():
            url = reverse(
                'admin:admin_index_counter_change', args=(counter.id,))
            out.append(
                f'<a href="{url}" target="_blank">{counter}</a>')
        out = out or ['(unused)']
        return mark_safe('<br />\n'.join(out))
    usage_links.short_description = 'Used'

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super(AdvancedFilterAdmin, self).get_form(
            request, obj, change, **kwargs)
        if 'model' in request.GET:
            form.model = apps.get_model(*request.GET['model'].split('.'))
        return form

    def save_model(self, request, new_object, *args, **kwargs):
        if new_object and not new_object.pk:
            new_object.created_by = request.user
            new_object.model_name = new_object.model.split('.')[1]

        super(AdvancedFilterAdmin, self).save_model(
            request, new_object, *args, **kwargs)

    def _iframe_context(self, request, extra_context):
        extra_context = extra_context or {}
        if request.GET.get(IS_POPUP_VAR) == 'iframe':
            extra_context['is_iframe'] = True
            extra_context['is_popup'] = True
        return extra_context

    def add_view(self, request, form_url='', extra_context=None):
        extra_context = self._iframe_context(request, extra_context)
        return super().add_view(request, form_url, extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = self._iframe_context(request, extra_context)
        orig_response = super(AdvancedFilterAdmin, self).change_view(
            request, object_id, form_url, extra_context)
        if '_save_goto' in request.POST:
            obj = self.get_object(request, unquote(object_id))
            if obj:
                app, model = obj.model.split('.')
                path = resolve_url('admin:%s_%s_changelist' % (
                    app, model.lower()))
                url = "{path}{qparams}".format(
                    path=path, qparams="?_afilter={id}".format(id=object_id))
                return HttpResponseRedirect(url)
        return orig_response

    def response_delete(self, request, obj_display, obj_id):
        """
        Determine the HttpResponse for the delete_view stage.
        """
        opts = self.model._meta
        if request.GET.get(IS_POPUP_VAR) == 'iframe':
            return TemplateResponse(request, self.popup_response_template or [
                'admin/%s/%s/iframe_response.html' % (opts.app_label, opts.model_name),
                'admin/%s/iframe_response.html' % opts.app_label,
                'admin/iframe_response.html',
            ], {})
        return super().response_delete(request, obj_display, obj_id)

    def response_add(self, request, obj):
        """
        Determine the HttpResponse for the change_view stage.
        """

        if request.GET.get(IS_POPUP_VAR) != 'iframe':
            return super().response_change(request, obj)

        opts = obj._meta
        obj_url = reverse(
            'admin:%s_%s_change' % (opts.app_label, opts.model_name),
            args=(quote(obj.pk),),
            current_app=self.admin_site.name,
        )
        msg_dict = {
            'name': opts.verbose_name,
            'obj': obj,
        }
        msg = format_html(
            _('The {name} "{obj}" was changed successfully. You may edit it again below.'),
            **msg_dict
        )
        self.message_user(request, msg, messages.SUCCESS)
        obj_url = obj_url + '?_popup=iframe'  # TODO something smarter
        return HttpResponseRedirect(obj_url)

    def response_change(self, request, obj):
        """
        Determine the HttpResponse for the change_view stage.
        """

        if request.GET.get(IS_POPUP_VAR) != 'iframe':
            return super().response_change(request, obj)

        opts = self.model._meta
        msg_dict = {
            'name': opts.verbose_name,
            'obj': obj,
        }
        msg = format_html(
            _('The {name} "{obj}" was changed successfully. You may edit it again below.'),
            **msg_dict
        )
        self.message_user(request, msg, messages.SUCCESS)
        redirect_url = request.path + '?_popup=iframe'  # TODO something smarter
        return HttpResponseRedirect(redirect_url)

    def _response_post_save(self, request, obj):
        response = super()._response_post_save(request, obj)
        if request.GET.get('_popup') == 'iframe':
            response['location'] += '?_popup=iframe'
        return response

    @staticmethod
    def user_has_permission(user):
        """Filters by user if not superuser or explicitly allowed in settings"""
        return user.is_superuser or not getattr(settings, "ADVANCED_FILTER_EDIT_BY_USER", True)

    def get_queryset(self, request):
        if self.user_has_permission(request.user):
            return super(AdvancedFilterAdmin, self).get_queryset(request)
        else:
            return self.model.objects.filter_by_user(request.user)

    def has_add_permission(self, request):
        if not request.GET.get('model'):
            return False
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return super(AdvancedFilterAdmin, self).has_change_permission(request)
        return self.user_has_permission(request.user) or obj in self.model.objects.filter_by_user(request.user)

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return super(AdvancedFilterAdmin, self).has_delete_permission(request)
        return self.user_has_permission(request.user) or obj in self.model.objects.filter_by_user(request.user)

    def get_search_results(self, request, queryset, search_term):
        results, use_distinct = super().get_search_results(
            request, queryset, search_term)
        if request.is_ajax():
            new_results = []
            for result in results.order_by('model_name', 'order'):
                if not result.heading:
                    new_results.append(result)
        else:
            new_results = results
        return new_results, use_distinct

admin.site.register(AdvancedFilter, AdvancedFilterAdmin)
