from django.conf.urls import *
from django.conf import settings
from django.http.response import HttpResponse
from django.contrib.contenttypes.models import ContentType

from tastypie.resources import ModelResource
from tastypie import fields
from tastypie.authorization import DjangoAuthorization
from tastypie.constants import ALL_WITH_RELATIONS
from tastypie.utils import trailing_slash
from tastypie import http

from .models import Vote

from dataserver.authentication import AnonymousApiKeyAuthentication

import json

class VoteResource(ModelResource):
    content_type = fields.CharField(attribute='content_type__model')

    class Meta:
        queryset = Vote.objects.all()
        resource_name = 'vote'
        authentication = AnonymousApiKeyAuthentication()
        authorization = DjangoAuthorization()
        default_format = "application/json"
        allowed_methods = ['get', 'post', 'patch']
        filtering = {
            "object_id" : ['exact', ],
            "content_type" : ['exact', ],
            "vote_type" : ['exact', ],

        }
        always_return_data = True

    def dehydrate(self, bundle):
        bundle.data["vote_type_label"] =  bundle.obj.get_vote_type_display()
        return bundle


    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/(?P<content_type>\w+?)/(?P<object_id>\d+?)%s$" % (self._meta.resource_name, trailing_slash()),
                self.wrap_view('dispatch_list'),
                name="api_dispatch_list"),
           url(r"^(?P<resource_name>%s)/(?P<content_type>\w+?)/(?P<object_id>\d+?)%s$" % (self._meta.resource_name, trailing_slash()),
               self.wrap_view('get_votes_for_object'),
               name="api_get_votes_for_object"),
           url(r"^(?P<resource_name>%s)/types/%s$" % (self._meta.resource_name, trailing_slash()),
               self.wrap_view('get_vote_types'),
               name="api_get_vote_types"),
        ]

    def dispatch_list(self, request, **kwargs):
        self.method_check(request, allowed=['get', 'post'])
        self.is_authenticated(request)
        self.throttle_check(request)

        if 'content_type' in kwargs and 'object_id' in kwargs and request.method=="POST":
            data = json.loads(request.body)
            print kwargs
            print data
            vote, created = Vote.objects.get_or_create(content_type=ContentType.objects.get(model=kwargs['content_type']),
                                                        object_id=kwargs['object_id'],
                                                        score=data['score'],
                                                        vote_type=data['vote_type'])
            bundle = self.build_bundle(obj=vote, request=request)
            bundle = self.full_dehydrate(bundle)
            bundle = self.alter_detail_data_to_serialize(request, bundle)

            return self.create_response(request,
                                        bundle,
                                        response_class=http.HttpCreated,
                                        location=self.get_resource_uri(bundle))
        return ModelResource.dispatch_list(self, request, **kwargs)

    def get_vote_types(self, request, **kwargs):
        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)
        self.throttle_check(request)



        vote_types = []
        for k,v in settings.VOTE_TYPE_CHOICES:
            vote_types.append({'code' : k, 'name' : v})

        code_filter = request.GET.get('code', '')
        if code_filter:
            vote_types = [vote_type for vote_type in vote_types if vote_type["code"] == code_filter]

        return HttpResponse(json.dumps(vote_types), content_type="application/json")


    def get_votes_for_object(self, request, **kwargs):
        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)
        self.throttle_check(request)

        if 'content_type' in kwargs and 'object_id' in kwargs:
            pass

        return
