from django.contrib import admin
from django.db import models
from .models import Bucket, BucketFile

class InlineBucketFile(admin.TabularInline):
    model = BucketFile

class BucketAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'files_count', 'is_orphan')
    search_fields = ('name', )
    inlines = [
        InlineBucketFile,
    ]

    def is_orphan(self, obj):
        return obj.projectsheet_set.exists()
    is_orphan.short_description = 'Orphelin'
    is_orphan.boolean = True

    def get_queryset(self, request):
        qs = super(BucketAdmin, self).get_queryset(request)
        qs = qs.annotate(models.Count('files'))
        return qs



    def files_count(self, obj):
        return obj.files.count()
    files_count.short_description = 'Nb de fichiers'
    files_count.admin_order_field = 'files__count'

admin.site.register(Bucket, BucketAdmin)
