from django.conf.urls import *

from tastypie.resources import ModelResource
from tastypie import fields

from .models import Post
from accounts.models import Profile, ObjectProfileLink

from graffiti.api import TaggedItemResource
from dataserver.authentication import AnonymousApiKeyAuthentication
from tastypie.authorization import DjangoAuthorization
from tastypie.constants import ALL_WITH_RELATIONS
from tastypie.utils import trailing_slash

from accounts.api import ProfileResource


class PostResource(ModelResource):

    """ A post resource """

    tags = fields.ToManyField(TaggedItemResource, 'tagged_items', full=True, null=True)
    parent = fields.OneToOneField("megafon.api.PostResource", 'parent', null=True)
    answers = fields.ToManyField("megafon.api.PostResource", 'answers', full=True, null=True)


    class Meta:
        queryset = Post.objects.all()
        resource_name = 'megafon/post'
        allowed_methods = ['get', 'post']
        always_return_data = True
        authentication = AnonymousApiKeyAuthentication()
        authorization = DjangoAuthorization()

        filtering = {
            "slug": ('exact',),
            "id": ('exact',),
            "level" : ('exact', ),
            "answers_count" : ('exact', ),
        }
        ordering = ['updated_on', 'answers_count']

    def dehydrate(self, bundle):
        try:
            o = ObjectProfileLink.objects.get(content_type__model="post", object_id=bundle.obj.id, level=30)
            author_resource = ProfileResource()
            author_bundle = author_resource.build_bundle(obj=o.profile, request=bundle.request)
            bundle.data["author"] = author_resource.full_dehydrate(author_bundle)
        except ObjectProfileLink.DoesNotExist:
            pass
        try:
            o_list = ObjectProfileLink.objects.filter(content_type__model="post", object_id=bundle.obj.id, level=31)
            bundle.data["contributors"] = []
            for o in o_list:
                contributor_resource = ProfileResource()
                contributor_bundle = contributor_resource.build_bundle(obj=o.profile, request=bundle.request)
                bundle.data["contributors"].append(contributor_resource.full_dehydrate(contributor_bundle))
        except:
            pass
        # author_resource = ProfileResource()
        # author_bundle = author_resource.build_bundle(obj=o.profile, request=bundle.request)
        # bundle.data["author"] = author_resource.full_dehydrate(author_bundle)
        return bundle

    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/questions%s$" % (self._meta.resource_name, trailing_slash()), self.wrap_view('get_questions'), name="api_get_questions"),
            url(r"^(?P<resource_name>%s)/(?P<pk>\w[\w/-]*)/answers%s$" % (self._meta.resource_name, trailing_slash()), self.wrap_view('get_answers'), name="api_get_answers"),
            url(r"^(?P<resource_name>%s)/(?P<pk>\w[\w/-]*)/root%s$" % (self._meta.resource_name, trailing_slash()), self.wrap_view('get_root'), name="api_get_root"),
        ]

    def get_questions(self, request, **kwargs):
        kwargs['level'] = 0
        return self.get_list(request, **kwargs)


    def get_answers(self, request, **kwargs):
        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)
        self.throttle_check(request)

        post = self.get_object_list(request).get(id=kwargs['pk'])
        answers = post.get_children().order_by('-updated_on')

        bundles = []
        for obj in answers:
            bundle = self.build_bundle(obj=obj, request=request)
            bundles.append(self.full_dehydrate(bundle, for_list=True))

        return self.create_response(request, {'objects' : bundles})

    def get_root(self, request, **kwargs):
        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)
        self.throttle_check(request)

        try :
            post = self.get_object_list(request).get(id=kwargs['pk']).get_root()
            bundle = self.build_bundle(obj=post, request=request)
            return self.create_response(request, self.full_dehydrate(bundle))
        except:
            pass

        return self.create_response(request, {})
