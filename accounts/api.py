# -*- encoding: utf-8 -*-
import json
import requests

from django.db.models import Count
from django.conf.urls import url
from django.conf import settings
from django.contrib.auth.models import User, Group
from django.contrib.auth import authenticate, logout
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.shortcuts import get_object_or_404
from django.db import IntegrityError
from django.core.exceptions import SuspiciousOperation

from tastypie import fields
from tastypie import http
from tastypie.http import HttpUnauthorized, HttpForbidden
from tastypie.authentication import Authentication, BasicAuthentication, ApiKeyAuthentication
from tastypie.authorization import DjangoAuthorization, Authorization
from tastypie.constants import ALL_WITH_RELATIONS
from tastypie.models import ApiKey, create_api_key
from tastypie.resources import ModelResource
from tastypie.utils import trailing_slash

from dataserver.authentication import AnonymousApiKeyAuthentication
from .models import Profile, ObjectProfileLink

from requests_oauthlib import OAuth1
from urlparse import parse_qs, parse_qsl
from urllib import urlencode
from django.http import HttpResponse,HttpResponseRedirect

from django.core.mail import send_mail
import hashlib
class UserResource(ModelResource):
    class Meta:
        queryset = User.objects.exclude(pk=-1) # Exclude anonymous user
        detail_uri_name = 'username'
        allowed_methods = ['get', 'post', 'patch']
        resource_name = 'account/user'
        authentication = Authentication()
        authorization = Authorization()
        fields = ['id', 'username', 'first_name', 'last_name', 'groups', 'email', 'date_joined']
        filtering = {
            "id" : ['exact',],
            "username": ALL_WITH_RELATIONS,
            "email" : ['exact',],
        }

    # groups = fields.ToManyField('accounts.api.GroupResource', 'groups', null=True, full=False)

    def dehydrate(self, bundle):
        if bundle.request.user.is_anonymous():
            del bundle.data['email']
        else:
            try:
                bundle.data['profile'] = {
                    'avatar' : bundle.obj.profile.mugshot.url,
                    'id' : bundle.obj.profile.id
                }
                bundle.data['groups'] = [{"id" : group.id, "name":group.name} for group in bundle.obj.groups.all()]
            except:
                pass
        return bundle

    def obj_create(self, bundle, request=None, **kwargs):
        try:
            bundle = super(UserResource, self).obj_create(bundle, **kwargs)
            bundle.obj.set_password(bundle.data.get('password'))
            bundle.obj.save()
        except IntegrityError:
            raise SuspiciousOperation('That username already exists')
        return bundle

    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/login%s$" %
                (self._meta.resource_name, trailing_slash()),
                self.wrap_view('login'), name="api_login"),
            url(r"^(?P<resource_name>%s)/login/google%s$" %
                (self._meta.resource_name, trailing_slash()),
                self.wrap_view('login_google'), name="api_login_google"),
            url(r"^(?P<resource_name>%s)/login/facebook%s$" %
                (self._meta.resource_name, trailing_slash()),
                self.wrap_view('login_facebook'), name="api_login_facebook"),
            url(r"^(?P<resource_name>%s)/login/twitter%s$" %
                (self._meta.resource_name, trailing_slash()),
                self.wrap_view('login_twitter'), name="api_login_twitter"),
            url(r'^(?P<resource_name>%s)/logout%s$' %
                (self._meta.resource_name, trailing_slash()),
                self.wrap_view('logout'), name='api_logout'),
            url(r'^(?P<resource_name>%s)/report/abuse%s$' %
                (self._meta.resource_name, trailing_slash()),
                self.wrap_view('report_abuse'), name='api_report_abuse'),
        ]

    def send_email(self, request, data, recipients):
        payload = dict(secret=settings.GOOGLE_RECAPTCHA_SECRET,
                       response=data['recaptcha_response'])

        r = requests.post("https://www.google.com/recaptcha/api/siteverify", data=payload)
        resp = json.loads(r.text)
        if resp["success"] and len(recipients):
            try:
                send_mail(data["subject"],
                        data["body"],
                        data["sender_email"],
                        recipients,
                        fail_silently=False)
            except:
                return self.create_response(request, {'success': False})
            return self.create_response(request, {'success': True})
        else:
            return self.create_response(request, {'success': False})


    def report_abuse(self, request, **kwargs):
        """
        Send a message to user after checking captcha with google service
        """
        self.method_check(request, allowed=['post'])
        data = self.deserialize(request, request.body, format=request.META.get('CONTENT_TYPE', 'application/json'))

        recipients = User.objects.filter(is_superuser=True).values_list('email', flat=True)

        return self.send_email(request, data, recipients)

    def login_google(self, request, **kwargs):
        """
        Given an oauth2 google token, check it and if ok, return or
        create a user.
        """
        self.method_check(request, allowed=['post'])
        data = self.deserialize(request, request.body, format=request.META.get('CONTENT_TYPE', 'application/json'))

        access_token_url = 'https://accounts.google.com/o/oauth2/token'
        people_api_url = 'https://www.googleapis.com/plus/v1/people/me/openIdConnect'

        payload = dict(client_id=data['clientId'],
                       redirect_uri=data['redirectUri'],
                       client_secret=settings.GOOGLE_CLIENT_SECRET,
                       code=data['code'],
                       grant_type='authorization_code')

        # Step 1. Exchange authorization code for access token.
        r = requests.post(access_token_url, data=payload)
        token = json.loads(r.text)
        headers = {'Authorization': 'Bearer {0}'.format(token['access_token'])}

        # Step 2. Retrieve information about the current user.
        r = requests.get(people_api_url, headers=headers)

        user = None
        if r.status_code == 200:
            data = json.loads(r.text)
            if data['email_verified']:
                user, created = User.objects.get_or_create(username=hashlib.sha1(data['email']).hexdigest()[:30],
                                                           email=data['email'],
                                                           first_name=data['given_name'],
                                                           last_name=data['family_name'])
        else:
            return self.create_response(request, {'success': False,
                                                'reason': 'google auth rejected',
                                                'google_message' : r.text,
                                                'skip_login_redir': True, }, HttpUnauthorized)
        return self.login_to_apikey(request, user)

    def login_facebook(self, request, **kwargs):
        """
        Given an oauth2 facebook token, check it and if ok, return or
        create a user.
        """

        self.method_check(request, allowed=['post'])
        data = self.deserialize(request, request.body, format=request.META.get('CONTENT_TYPE', 'application/json'))

        access_token_url = 'https://graph.facebook.com/v2.4/oauth/access_token'
        graph_api_url = 'https://graph.facebook.com/v2.4/me'

        params = {
            'client_id': data['clientId'],
            'redirect_uri': data['redirectUri'],
            'client_secret': settings.FACEBOOK_CLIENT_SECRET,
            'code': data['code']
        }

        # Step 1. Exchange authorization code for access token.
        r = requests.get(access_token_url, params=params)
        access_token = json.loads(r.text)
        access_token["fields"]="email,first_name,last_name"
        # Step 2. Retrieve information about the current user.
        r = requests.get(graph_api_url, params=access_token)
        profile = json.loads(r.text)

        user = None
        if r.status_code == 200:
            data = json.loads(r.text)
            user, created = User.objects.get_or_create(username=hashlib.sha1(data['email']).hexdigest()[:30],
                                                       email=data['email'],
                                                       first_name=data['first_name'],
                                                       last_name=data['last_name'])
        else:
            return self.create_response(request, {'success': False,
                                                'reason': 'faceboot auth rejected',
                                                'facebook_message' : r.text,
                                                'skip_login_redir': True, }, HttpUnauthorized)
        return self.login_to_apikey(request, user)

    def login_twitter(self, request, **kwargs):
        """
        Given an oauth2 twitter token, check it and if ok, return or
        create a user.
        """

        self.method_check(request, allowed=['get', 'post'])
        if request.method == 'GET':
            data = request.GET
        else:
            data = self.deserialize(request, request.body, format=request.META.get('CONTENT_TYPE', 'application/json'))

        request_token_url = 'https://api.twitter.com/oauth/request_token'
        access_token_url = 'https://api.twitter.com/oauth/access_token'
        authenticate_url = 'https://api.twitter.com/oauth/authenticate'

        if request.GET.get('oauth_token') and request.GET.get('oauth_verifier'):
            auth = OAuth1(settings.TWITTER_CLIENT_ID,
                           client_secret=settings.TWITTER_CLIENT_SECRET,
                           resource_owner_key=request.GET.get('oauth_token'),
                           verifier=request.GET.get('oauth_verifier'))
            r = requests.post(access_token_url, auth=auth)
            cred = dict(parse_qsl(r.text))

            auth = OAuth1(settings.TWITTER_CLIENT_ID,
                          settings.TWITTER_CLIENT_SECRET,
                          cred["oauth_token"],
                          cred["oauth_token_secret"])

            r = requests.get("https://api.twitter.com/1.1/account/verify_credentials.json",
                              headers={'include_entities' : 'false',
                                       'skip_status' : 'true',
                                       'include_email':"true"},
                              auth=auth)
            data = json.loads(r.text)
            user, created = User.objects.get_or_create(username=data['screen_name'],
                                                       email='',
                                                       first_name=data['name'].split(' ')[0],
                                                       last_name=data['name'].split(' ')[1])

            return self.login_to_apikey(request, user)
        else:
            # POST
            post_data = json.loads(request.body)
            oauth = OAuth1(post_data['clientId'],
                           client_secret=settings.TWITTER_CLIENT_SECRET,
                           callback_uri=post_data['redirectUri'])
            r = requests.post(request_token_url, auth=oauth)
            oauth_token = dict(parse_qsl(r.text))
            qs = urlencode(dict(oauth_token=oauth_token['oauth_token']))
            response = HttpResponseRedirect(authenticate_url + '?' + qs)
            return response

    def login(self, request, **kwargs):
        """
        Login a user against a username/password.
        Return an API Key that's going to be used for the following requests
        """
        self.method_check(request, allowed=['post'])

        data = self.deserialize(request, request.body, format=request.META.get('CONTENT_TYPE', 'application/json'))

        username = data.get('username', '')
        password = data.get('password', '')

        user = authenticate(username=username, password=password)

        return self.login_to_apikey(request, user, basic_login=True)


    def login_to_apikey(self, request, user, basic_login=False):
        if user:
            if user.is_active:
                # login(request, user)

                try:
                    key = ApiKey.objects.get(user=user)
                except ApiKey.DoesNotExist:
                    return self.create_response(
                        request, {
                            'success': False,
                            'reason': 'missing key',
                        },
                        HttpForbidden,
                    )

                ret = self.create_response(request, {'success': True, 'username': user.username, 'token': key.key,})
                return ret
            else:
                return self.create_response({'success': False, 'reason': 'disabled',}, HttpForbidden)
        else:
            if basic_login:
                return self.create_response(request, {'success': False})

            return self.create_response(
                request, {'success': False, 'reason': 'invalid login', 'skip_login_redir': True, }, HttpUnauthorized)

    def logout(self, request, **kwargs):
        self.method_check(request, allowed=['get'])
        if request.user and request.user.is_authenticated():
            logout(request)
            return self.create_response(request, {'success': True})
        else:
            return self.create_response(request, {'success': False}, HttpUnauthorized)


class GroupResource(ModelResource):
    class Meta:
        queryset = Group.objects.all()
        resource_name = 'account/group'
        authentication = Authentication()
        authorization = Authorization()

    users = fields.ToManyField(UserResource, 'user_set', full=True, null=True)


# Create API key for every new user
models.signals.post_save.connect(create_api_key, sender=User)

class ProfileResource(ModelResource):
    user = fields.OneToOneField(UserResource, 'user', full=True)
    avatar = fields.FileField(attribute="mugshot", null=True, blank=True)

    class Meta:
        queryset = Profile.objects.all()
        allowed_methods = ['get', 'post']
        resource_name = 'account/profile'
        authentication = Authentication()
        authorization = Authorization()
        filtering = {
            "id" : ['exact',],
            "user" : ALL_WITH_RELATIONS,
        }
        excludes = ('mugshot', 'privacy')

    def dehydrate(self, bundle):
        bundle.data["username"] = bundle.obj.username
        return bundle

    def alter_list_data_to_serialize(self, request, data):
        if request.GET.get('count_only'):
            return {'meta': data['meta'], 'objects' : []}
        return data

class ObjectProfileLinkResource(ModelResource):
    """
    Resource for linking profile with objects s.a a Project, a Category, etc.
    """
    content_type = fields.CharField(attribute='content_type__model')
    profile = fields.OneToOneField(ProfileResource, 'profile', full=True)
    level = fields.IntegerField(attribute='level')
    detail = fields.CharField(attribute='detail')
    isValidated = fields.BooleanField(attribute='isValidated')

    class Meta:
        queryset = ObjectProfileLink.objects.all().order_by('-created_on')
        resource_name = 'objectprofilelink'
        authentication = AnonymousApiKeyAuthentication()
        authorization = DjangoAuthorization()
        default_format = "application/json"
        allowed_methods = ['get', 'post', 'delete', 'patch']
        filtering = {
            "object_id" : ['exact', ],
            "content_type" : ['exact', ],
            "level" : ['exact', ],
            "profile" : ALL_WITH_RELATIONS,
            "isValidated" : ['exact', ]

        }
        always_return_data = True



    def prepend_urls(self):
        return [
           url(r"^(?P<resource_name>%s)/(?P<content_type>\w+?)/(?P<object_id>\d+?)%s$" % (self._meta.resource_name, trailing_slash()),
               self.wrap_view('dispatch_list'),
               name="api_dispatch_list"),
            url(r"^(?P<resource_name>%s)/(?P<content_type>\w+?)/best%s$" % (self._meta.resource_name, trailing_slash()),
                self.wrap_view('get_best_linked_profiles'),
                name="api_best_linked_profiles"),
            url(r"^(?P<resource_name>%s)/purge%s$" % (self._meta.resource_name, trailing_slash()),
                self.wrap_view('purge_links'),
                name="api_purge_links"),
        ]

    def dispatch_list(self, request, **kwargs):
        self.method_check(request, allowed=['get', 'post'])
        self.is_authenticated(request)
        self.throttle_check(request)

        if 'content_type' in kwargs and 'object_id' in kwargs and request.method=="POST":
            data = json.loads(request.body)
            if 'profile_id' in data:
                profile = get_object_or_404(Profile, pk=data['profile_id'])
            else:
                profile=request.user.profile
            objectprofilelink_item, created = ObjectProfileLink.objects.get_or_create(profile=profile,
                                            content_type=ContentType.objects.get(model=kwargs['content_type']),
                                            object_id=kwargs['object_id'],
                                            level=data['level'],
                                            detail=data['detail'],
                                            isValidated=data['isValidated'])
            bundle = self.build_bundle(obj=objectprofilelink_item, request=request)
            bundle = self.full_dehydrate(bundle)
            bundle = self.alter_detail_data_to_serialize(request, bundle)

            return self.create_response(request,
                                        bundle,
                                        response_class=http.HttpCreated,
                                        location=self.get_resource_uri(bundle))

        return ModelResource.dispatch_list(self, request, **kwargs)

    def get_best_linked_profiles(self, request, **kwargs):
        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)
        self.throttle_check(request)

        if 'content_type' in kwargs:
            levels = []
            if 'level' in request.GET:
                levels = [int(lvl) for lvl in request.GET.getlist('level')]

            profiles = Profile.objects.filter(id__gt=1,
                        objectprofilelink__content_type__model=kwargs["content_type"],
                        objectprofilelink__level__in=levels).annotate(score=Count('objectprofilelink')).order_by('-score')

            if 'limit' in request.GET:
                profiles = profiles[:request.GET.get('limit')]

            bundles = []
            for obj in profiles:
                profile_resource = ProfileResource()
                bundle = profile_resource.build_bundle(obj=obj, request=request)
                bundle.data["score"] = obj.score
                bundles.append(profile_resource.full_dehydrate(bundle, for_list=True))

            return self.create_response(request, {'objects' : bundles})

        return ModelResource.dispatch_list(self, request, **kwargs)

    def purge_links(self, request, **kwargs):
        total_cpt = 0
        total_delete = 0
        for link in ObjectProfileLink.objects.all():
            if not link.content_object:
                total_delete+=1
                link.delete()
            else:
                total_cpt+=1
        return self.create_response(request, {'total_cpt': total_cpt, 'total_delete': total_delete})
