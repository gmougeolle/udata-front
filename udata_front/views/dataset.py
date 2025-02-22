from collections import defaultdict, OrderedDict

from flask import abort, request, url_for, redirect
from werkzeug.contrib.atom import AtomFeed

from udata.models import Reuse, Follow
from udata.core.dataset.models import Dataset, RESOURCE_TYPES, get_resource
from udata.core.dataset.search import DatasetSearch
from udata.core.dataset.permissions import ResourceEditPermission, DatasetEditPermission
from udata.core.site.models import current_site

from udata_front.theme import render as render_template
from udata.sitemap import sitemap
from udata.i18n import I18nBlueprint, lazy_gettext as _
from udata_front.views.base import DetailView, SearchView


blueprint = I18nBlueprint('datasets', __name__, url_prefix='/datasets')


@blueprint.route('/recent.atom')
def recent_feed():
    feed = AtomFeed(_('Last datasets'),
                    feed_url=request.url, url=request.url_root)
    datasets = (Dataset.objects.visible().order_by('-created_at')
                .limit(current_site.feed_size))
    for dataset in datasets:
        author = None
        if dataset.organization:
            author = {
                'name': dataset.organization.name,
                'uri': url_for('organizations.show',
                               org=dataset.organization.id, _external=True),
            }
        elif dataset.owner:
            author = {
                'name': dataset.owner.fullname,
                'uri': url_for('users.show',
                               user=dataset.owner.id, _external=True),
            }
        feed.add(dataset.title,
                 render_template('dataset/feed_item.html', dataset=dataset),
                 content_type='html',
                 author=author,
                 url=url_for('datasets.show',
                             dataset=dataset.id, _external=True),
                 updated=dataset.last_modified,
                 published=dataset.created_at)
    return feed.get_response()


@blueprint.route('/', endpoint='list')
class DatasetListView(SearchView):
    model = Dataset
    search_adapter = DatasetSearch
    context_name = 'datasets'
    template_name = 'dataset/list.html'


class DatasetView(object):
    model = Dataset
    object_name = 'dataset'

    @property
    def dataset(self):
        return self.get_object()

    def get_context(self):
        return super(DatasetView, self).get_context()


class ProtectedDatasetView(DatasetView):
    def can(self, *args, **kwargs):
        permission = DatasetEditPermission(self.dataset)
        return permission.can()


@blueprint.route('/<dataset:dataset>/', endpoint='show')
class DatasetDetailView(DatasetView, DetailView):
    template_name = 'dataset/display.html'

    def dispatch_request(self, *args, **kwargs):
        return super(DatasetDetailView, self).dispatch_request(*args, **kwargs)

    def get_context(self):
        context = super(DatasetDetailView, self).get_context()
        if not DatasetEditPermission(self.dataset).can():
            if self.dataset.private:
                abort(404)
            elif self.dataset.deleted:
                abort(410)
        context['reuses'] = Reuse.objects(datasets=self.dataset).visible()
        context['can_edit'] = DatasetEditPermission(self.dataset)
        context['can_edit_resource'] = ResourceEditPermission

        return context


@blueprint.route('/<dataset:dataset>/followers/', endpoint='followers')
class DatasetFollowersView(DatasetView, DetailView):
    template_name = 'dataset/followers.html'

    def get_context(self):
        context = super(DatasetFollowersView, self).get_context()
        context['followers'] = (Follow.objects.followers(self.dataset)
                                              .order_by('follower.fullname'))
        return context


@blueprint.route('/r/<uuid:id>', endpoint='resource')
def resource_redirect(id):
    '''
    Redirect to the latest version of a resource given its identifier.
    '''
    resource = get_resource(id)
    return redirect(resource.url.strip()) if resource else abort(404)


@sitemap.register_generator
def sitemap_urls():
    for dataset in Dataset.objects.visible().only('id', 'slug'):
        yield ('datasets.show_redirect', {'dataset': dataset},
               None, 'weekly', 0.8)


@blueprint.app_template_filter()
def group_resources_by_type(resources):
    """Group a list of `resources` by `type` with order"""
    groups = defaultdict(list)
    for resource in resources:
        groups[getattr(resource, 'type')].append(resource)
    ordered = OrderedDict()
    for rtype, rtype_label in RESOURCE_TYPES.items():
        if groups[rtype]:
            ordered[(rtype, str(rtype_label))] = groups[rtype]
    return ordered
