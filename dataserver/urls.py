from django.conf import settings
from django.conf.urls import patterns, include, url
from django.conf.urls.static import static
from django.contrib import admin

from tastypie.api import Api

from accounts.api import UserResource, GroupResource, ProfileResource, ObjectProfileLinkResource
from bucket.api import BucketResource, BucketFileResource, BucketTagResource
from flipflop.api import BoardResource, ListResource, CardResource, TaskResource, LabelResource, CardCommentResource
from graffiti.api import TagResource, TaggedItemResource
from projects.api import ProjectResource
from projectsheet.api import (ProjectSheetResource, ProjectSheetTemplateResource,
                              ProjectSheetQuestionAnswerResource, ProjectSheetQuestionResource, QuestionChoiceResource)
from scout.api import (MapResource, TileLayerResource, DataLayerResource,
                       MarkerResource, MarkerCategoryResource, PostalAddressResource, PlaceResource)


admin.autodiscover()

# Build API
api = Api(api_name='v0')

# Scout
api.register(MapResource())
api.register(TileLayerResource())
api.register(MarkerResource())
api.register(DataLayerResource())
api.register(MarkerCategoryResource())
api.register(PostalAddressResource())
api.register(PlaceResource())


# Auth
api.register(UserResource())
api.register(GroupResource())
api.register(ProfileResource())
api.register(ObjectProfileLinkResource())

# Flipflop (Kanban)
api.register(BoardResource())
api.register(ListResource())
api.register(CardResource())
api.register(TaskResource())
api.register(CardCommentResource())
api.register(LabelResource())

# Bucket
api.register(BucketResource())
api.register(BucketTagResource())
api.register(BucketFileResource())

# Projects
api.register(ProjectResource())

# Project Sheets
api.register(ProjectSheetResource())
api.register(ProjectSheetTemplateResource())
api.register(ProjectSheetQuestionAnswerResource())
api.register(ProjectSheetQuestionResource())
api.register(QuestionChoiceResource())

# Projects Tools
api.register(ProjectToolResource())


# Unisson
api.register(IngredientResource())
api.register(EvaluationIngredientResource())

# Prestation
api.register(PrestationResource())
api.register(PrestationModuleResource())
api.register(SelectedModulesResource())

# Graffiti
api.register(TagResource())
api.register(TaggedItemResource())

# ucomment
api.register(CommentResource())


urlpatterns = patterns('',
    url(r'^admin/', include(admin.site.urls)),
    url(r'^api/', include(api.urls)),
    url(r'^bucket/', include('bucket.urls'))

)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
